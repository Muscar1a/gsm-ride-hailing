"""Compact joint coefficient covariance for individual conditional scenario intervals."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.stats import norm, t

from gsm_poc.causal.features import OUTCOME_COLUMNS, TREATMENT_COLUMNS, require_observed
from gsm_poc.core.artifacts import fingerprint

if TYPE_CHECKING:
    from gsm_poc.causal.estimate import ModelBundle


def model_identity(bundle: ModelBundle) -> str:
    return fingerprint(
        {
            "estimator": bundle.estimator,
            "dataset_id": bundle.dataset_id,
            "source_kind": bundle.source_kind,
            "dgp_id": bundle.dgp_id,
            "seed": bundle.seed,
            "active_treatments": bundle.active_treatments,
            "features": bundle.encoder.names,
            "theta": bundle.theta.tolist(),
            "coefficients": bundle.base_rate_model.coef_.tolist(),
            "intercepts": np.asarray(bundle.base_rate_model.intercept_).tolist(),
        }
    )


def coefficient_covariance(
    bundle: ModelBundle,
    train: pd.DataFrame,
    residuals: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict:
    """Use observed train rows only; preserve theta/baseline and X/Y cross-covariance."""
    require_observed(train)
    weights = train.n_sessions.to_numpy(float)
    treatment = train[list(TREATMENT_COLUMNS)].to_numpy(float)[:, bundle.active_treatments]
    outcome = train[list(OUTCOME_COLUMNS)].to_numpy(float)
    controls = np.column_stack([np.ones(len(train)), bundle.encoder.transform(train)])
    design = np.column_stack([treatment, controls])
    rank = int(np.linalg.matrix_rank(design * np.sqrt(weights[:, None])))
    if len(train) <= rank:
        raise ValueError("Analytic inference has no residual degrees of freedom")
    active_count = len(bundle.active_treatments)
    if bundle.estimator == "adjusted_ols":
        inverse = np.linalg.pinv(design.T @ (weights[:, None] * design), hermitian=True)
        fitted = (inverse @ design.T @ (weights[:, None] * outcome)).T
        if not np.allclose(fitted[:, :active_count], bundle.theta, atol=1e-10, rtol=1e-9):
            raise ValueError("OLS score reconstruction differs from fitted effects")
        residual = outcome - design @ fitted.T
        loadings = (weights[:, None] * design) @ inverse
        leverage = np.sum(design * loadings, axis=1)
        if (leverage < -1e-10).any() or (leverage >= 1 - 1e-10).any():
            raise ValueError("Analytic inference requires valid non-unit leverage")
        influence = loadings[:, None, :] * residual[:, :, None]
        scores = influence.reshape(len(train), -1)
        scores /= 1 - leverage[:, None]
        method, degrees = "block_hc3_t", len(train) - rank
    elif bundle.estimator == "dml":
        if residuals is None:
            raise ValueError("DML analytic inference requires out-of-fold training residuals")
        residual_y, residual_t = residuals
        if (
            residual_y.shape != (len(train), 2)
            or residual_t.shape != treatment.shape
            or not np.isfinite(residual_y).all()
            or not np.isfinite(residual_t).all()
        ):
            raise ValueError("DML residuals must match finite original training rows")
        gram = residual_t.T @ (weights[:, None] * residual_t)
        if np.linalg.matrix_rank(gram) != active_count:
            raise ValueError("Rank-deficient DML score Jacobian")
        inverse = np.linalg.inv(gram)
        reconstructed = (inverse @ residual_t.T @ (weights[:, None] * residual_y)).T
        if not np.allclose(reconstructed, bundle.theta, atol=1e-10, rtol=1e-9):
            raise ValueError("DML score reconstruction differs from fitted effects")
        residual = residual_y - residual_t @ bundle.theta.T
        theta_score = ((weights[:, None] * residual_t) @ inverse)[:, None, :]
        theta_score = theta_score * residual[:, :, None]
        control_inverse = np.linalg.pinv(controls.T @ (weights[:, None] * controls), hermitian=True)
        base_loadings = (weights[:, None] * controls) @ control_inverse
        coupling = control_inverse @ controls.T @ (weights[:, None] * treatment)
        base_residual = outcome - treatment @ bundle.theta.T - bundle.baseline(train)
        base_score = base_loadings[:, None, :] * base_residual[:, :, None]
        base_score -= theta_score @ coupling.T
        scores = np.concatenate([theta_score, base_score], axis=2).reshape(len(train), -1)
        if not np.allclose(scores.sum(axis=0), 0, atol=1e-8):
            raise ValueError("DML joint estimating equations do not sum to zero")
        method, degrees = "block_score_normal", None
    else:
        raise ValueError("Analytic inference is qualified only for adjusted_ols and dml")
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite analytic coefficient scores")
    return {
        "schema_version": 1,
        "model_identity": model_identity(bundle),
        "method": method,
        "covariance": (scores.T @ scores).tolist(),
        "degrees_of_freedom": degrees,
        "train_blocks": len(train),
        "train_days": int(train.original_day_id.nunique()),
        "design_rank": rank,
        "assumption": "Independent choice-block scores; conditional on fixed contexts/nuisances",
    }


def validate_covariance(bundle: ModelBundle, record: dict) -> np.ndarray:
    if not isinstance(record, dict):
        raise ValueError("Analytic covariance must be an object")
    method = {"adjusted_ols": "block_hc3_t", "dml": "block_score_normal"}.get(bundle.estimator)
    size = 2 * (len(bundle.active_treatments) + len(bundle.encoder.names) + 1)
    covariance = np.asarray(record.get("covariance"), dtype=float)
    degrees = record.get("degrees_of_freedom")
    if (
        record.get("schema_version") != 1
        or method is None
        or record.get("method") != method
        or record.get("model_identity") != model_identity(bundle)
        or covariance.shape != (size, size)
        or not np.isfinite(covariance).all()
        or not np.allclose(covariance, covariance.T, atol=1e-12, rtol=0)
        or np.linalg.eigvalsh(covariance).min() < -1e-10
        or (method == "block_hc3_t" and (type(degrees) is not int or degrees <= 0))
        or (method == "block_score_normal" and degrees is not None)
        or type(record.get("train_blocks")) is not int
        or record["train_blocks"] <= 0
        or not isinstance(record.get("assumption"), str)
    ):
        raise ValueError("Analytic covariance is invalid or does not match the fitted model")
    return covariance


def analytic_intervals(
    bundle: ModelBundle,
    contexts: pd.DataFrame,
    weights: np.ndarray,
    t0: np.ndarray,
    t1: np.ndarray,
    output: dict,
    level: float,
    n_sessions: int,
) -> dict:
    record = getattr(bundle, "analytic_inference", None)
    if record is None:
        return {
            "analytic": {
                "interval_status": "interval_unavailable",
                "reason": (
                    "Compact covariance unavailable; prepare inference offline or select bootstrap"
                ),
            }
        }
    covariance = validate_covariance(bundle, record)
    degrees = record["degrees_of_freedom"]
    critical = float(
        norm.ppf((1 + level) / 2) if degrees is None else t.ppf((1 + level) / 2, degrees)
    )
    size = covariance.shape[0] // 2
    mean_controls = np.r_[
        1.0, np.average(bundle.encoder.transform(contexts), axis=0, weights=weights)
    ]
    gradients = []
    for price in (t0, t1):
        xy = np.zeros((2, 2 * size))
        for j in range(2):
            xy[j, j * size : (j + 1) * size] = np.r_[
                price[list(bundle.active_treatments)], mean_controls
            ]
        gradients.append(np.vstack([xy, -xy.sum(axis=0)]))
    before, after = gradients
    delta = after - before

    def bounds(point: float, gradient: np.ndarray) -> dict:
        variance = float(gradient @ covariance @ gradient)
        if not np.isfinite(variance) or variance < -1e-12:
            raise ValueError("Invalid analytic transformed variance")
        half_width = critical * np.sqrt(max(variance, 0))
        return {"lower": float(point - half_width), "upper": float(point + half_width)}

    intervals = {}
    for metric, gradient in zip(
        ("before_probability", "after_probability", "delta_percentage_points"),
        (before, after, 100 * delta),
        strict=True,
    ):
        for j, label in enumerate(("X", "Y", "NONE")):
            intervals[f"{label}_{metric}"] = bounds(
                output["probabilities"][label][metric], gradient[j]
            )
    intervals["delta_expected_bookings"] = bounds(
        output["delta_expected_bookings"], n_sessions * delta[:2].sum(axis=0)
    )
    theta_intervals, elasticity_intervals = (
        [[None, None], [None, None]],
        [[None, None], [None, None]],
    )
    for j, label in enumerate(("X", "Y")):
        p0 = output["probabilities"][label]["before_probability"]
        for k, active in enumerate(bundle.active_treatments):
            gradient = np.zeros(2 * size)
            gradient[j * size + k] = 1
            theta_intervals[j][active] = bounds(float(bundle.theta[j, k]), gradient)
            elasticity = output["elasticity_at_baseline"][j][active]
            if elasticity is not None:
                elasticity_intervals[j][active] = bounds(
                    elasticity, gradient / p0 - bundle.theta[j, k] / p0**2 * before[j]
                )
    return {
        "analytic": {
            "interval_status": "ok",
            "method": record["method"],
            "degrees_of_freedom": degrees,
            "train_blocks": record["train_blocks"],
            "assumption": record["assumption"],
        },
        "interval": intervals,
        "interval_level": level,
        "theta_interval": theta_intervals,
        "elasticity_interval": elasticity_intervals,
    }
