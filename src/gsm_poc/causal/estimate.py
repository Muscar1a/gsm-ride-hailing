"""OLS baselines and EconML LinearDML with common 2x2 effects."""

from __future__ import annotations

import dataclasses
from itertools import product

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from gsm_poc.causal.features import (
    OUTCOME_COLUMNS,
    PRICE_LEVELS,
    TREATMENT_COLUMNS,
    Encoder,
    date_splits,
    day_folds,
    require_observed,
)
from gsm_poc.core.config import Config
from gsm_poc.core.validators import valid_probabilities


@dataclasses.dataclass
class ModelBundle:
    estimator: str
    theta: np.ndarray
    active_treatments: tuple[int, ...]
    base_rate_model: LinearRegression
    encoder: Encoder
    train_support: pd.DataFrame
    diagnostics: dict
    source_kind: str
    dataset_id: str
    dgp_id: str
    seed: int
    outcome_order: tuple[str, ...] = ("X", "Y")
    treatment_order: tuple[str, ...] = ("X", "Y")

    def baseline(self, context: pd.DataFrame) -> np.ndarray:
        return self.base_rate_model.predict(self.encoder.transform(context))

    def probabilities(self, context: pd.DataFrame, treatment: np.ndarray) -> np.ndarray:
        treatment = np.broadcast_to(np.asarray(treatment, dtype=float), (len(context), 2))
        xy = self.baseline(context) + treatment[:, self.active_treatments] @ self.theta.T
        return np.column_stack([xy, 1 - xy.sum(axis=1)])


@dataclasses.dataclass
class FitResult:
    bundle: ModelBundle | None
    diagnostics: dict


def _rank(residual: np.ndarray, weights: np.ndarray) -> tuple[int, float | None]:
    covariance = residual.T @ (residual * weights[:, None]) / weights.sum()
    rank = int(np.linalg.matrix_rank(covariance, tol=1e-10))
    condition = float(np.linalg.cond(covariance))
    return rank, condition if np.isfinite(condition) else None


def fit_estimator(
    train: pd.DataFrame, config: Config, estimator: str, seed: int | None = None
) -> FitResult:
    require_observed(train)
    encoder = Encoder(config.source.zones)
    w = encoder.transform(train)
    treatment_all = train[list(TREATMENT_COLUMNS)].to_numpy(float)
    outcome = train[list(OUTCOME_COLUMNS)].to_numpy(float)
    weights = train.n_sessions.to_numpy(float)
    active = tuple(np.flatnonzero(np.ptp(treatment_all, axis=0) > 1e-10).tolist())
    diagnostic = {
        "estimator": estimator,
        "status": "ok",
        "outcome_order": ["X", "Y"],
        "treatment_order": ["X", "Y"],
        "active_treatments": list(active),
        "train_blocks": len(train),
        "train_days": int(train.original_day_id.nunique()),
        "train_sessions": int(weights.sum()),
        "weighting": "session_count",
        "feature_allowlist": encoder.names,
        "warnings": [],
    }
    diagnostic["constant_log_prices"] = {
        ("X", "Y")[k]: float(treatment_all[0, k]) for k in range(2) if k not in active
    }
    support = []
    for x, y in product(PRICE_LEVELS, repeat=2):
        count = int(
            (
                (np.isclose(treatment_all[:, 0], np.log(x)))
                & np.isclose(treatment_all[:, 1], np.log(y))
            ).sum()
        )
        support.append({"multiplier_x": float(x), "multiplier_y": float(y), "blocks": count})
    diagnostic["joint_price_support"] = support
    if any(cell["blocks"] < config.model.min_price_cell_count for cell in support):
        diagnostic["warnings"].append(
            "Some joint price cells have fewer than the configured blocks"
        )
    if not active:
        diagnostic.update(status="not_identified", reason="Neither price varies", residual_rank=0)
        return FitResult(None, diagnostic)
    t = treatment_all[:, active]
    adjusted_t = LinearRegression().fit(w, t, sample_weight=weights)
    adjusted_residual = t - adjusted_t.predict(w)
    rank, condition = _rank(adjusted_residual, weights)
    diagnostic.update(residual_rank=rank, condition_number=condition)
    if rank < len(active):
        diagnostic.update(status="not_identified", reason="Residual price covariance lacks rank")
        return FitResult(None, diagnostic)
    if condition is None or condition > config.model.max_condition_number:
        diagnostic["warnings"].append("Residual price covariance is poorly conditioned")
    actual_seed = config.simulation.seed if seed is None else seed
    if estimator in ("naive_ols", "adjusted_ols"):
        design = t if estimator == "naive_ols" else np.column_stack([t, w])
        model = LinearRegression().fit(design, outcome, sample_weight=weights)
        theta = model.coef_[:, : len(active)]
    elif estimator == "dml":
        # Lazy import keeps non-DML commands lightweight; no analytic IID interval is used.
        from econml.dml import LinearDML

        forests = [
            RandomForestRegressor(
                n_estimators=config.model.n_trees,
                max_depth=config.model.max_depth,
                min_samples_leaf=config.model.min_samples_leaf,
                random_state=actual_seed + i,
                n_jobs=1,
            )
            for i in range(2)
        ]
        folds = day_folds(train, config.model.folds)
        model = LinearDML(
            model_y=forests[0],
            model_t=forests[1],
            cv=folds,
            discrete_outcome=False,
            discrete_treatment=False,
            random_state=actual_seed,
        )
        model.fit(
            outcome,
            t,
            X=None,
            W=w,
            sample_weight=weights,
            groups=train.original_day_id.to_numpy(),
            inference=None,
            cache_values=True,
        )
        theta = np.asarray(model.const_marginal_effect()).reshape(2, len(active))
        residual_t = model.residuals_[1].reshape(len(train), len(active))
        rank, condition = _rank(residual_t, weights)
        diagnostic.update(residual_rank=rank, condition_number=condition)
        if rank < len(active):
            diagnostic.update(
                status="not_identified", reason="Cross-fitted residual price lacks rank"
            )
            return FitResult(None, diagnostic)
        diagnostic["folds"] = [
            {
                "fold": i,
                "train_original_days": sorted(set(train.original_day_id.iloc[a])),
                "validation_original_days": sorted(set(train.original_day_id.iloc[b])),
            }
            for i, (a, b) in enumerate(folds)
        ]
    else:
        raise ValueError(f"Unknown estimator: {estimator}")
    if not np.isfinite(theta).all():
        raise ValueError("Estimator produced nonfinite effects")
    target = outcome - t @ theta.T
    base_rate = LinearRegression().fit(w, target, sample_weight=weights)
    # Fixed basis matches the declared additive DGP; no oracle targets are used.
    support_frame = train[
        ["zone_id", "weekday", "is_weekend", "is_peak", "hour", "multiplier_x", "multiplier_y"]
    ].copy()
    bundle = ModelBundle(
        estimator,
        theta,
        active,
        base_rate,
        encoder,
        support_frame,
        diagnostic,
        str(train.source_kind.iloc[0]),
        str(train.dataset_id.iloc[0]),
        str(train.dgp_id.iloc[0]),
        int(train.seed.iloc[0]),
    )
    return FitResult(bundle, diagnostic)


def fit_all(blocks: pd.DataFrame, config: Config) -> tuple[dict[str, FitResult], dict]:
    require_observed(blocks)
    if blocks.duplicated(["dataset_id", "block_id"]).any():
        raise ValueError("Duplicate observed block grain")
    splits = date_splits(blocks, config)
    results = {
        name: fit_estimator(splits["train"], config, name) for name in config.model.estimators
    }
    for result in results.values():
        if result.bundle is not None:
            validation = splits["validation"]
            probabilities = result.bundle.probabilities(
                validation, validation[list(TREATMENT_COLUMNS)].to_numpy()
            )
            result.diagnostics["validation_probability_valid"] = valid_probabilities(probabilities)
            if not result.diagnostics["validation_probability_valid"]:
                reason = (
                    f"{result.bundle.estimator}: invalid choice probabilities on validation; "
                    "model rejected"
                )
                result.diagnostics.update(status="invalid_probability", reason=reason)
                raise ValueError(reason)
            result.diagnostics["validation_prediction_rmse"] = float(
                np.sqrt(
                    np.average(
                        np.mean(
                            (probabilities[:, :2] - validation[list(OUTCOME_COLUMNS)].to_numpy())
                            ** 2,
                            axis=1,
                        ),
                        weights=validation.n_sessions,
                    )
                )
            )
    split_record = {
        name: {"blocks": len(part), "days": sorted(set(part.day_id))}
        for name, part in splits.items()
    }
    return results, split_record
