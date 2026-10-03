"""Bootstrap original days and refit every learned component."""

from __future__ import annotations

import dataclasses
import time

import numpy as np
import pandas as pd

from gsm_poc.config import Config
from gsm_poc.estimate import ModelBundle, fit_estimator


@dataclasses.dataclass
class BootstrapResult:
    estimator: str
    records: list[dict]
    bundles: list[ModelBundle | None]
    interval_status: str
    requested_draws: int
    interval_level: float
    stability: dict = dataclasses.field(default_factory=dict)

    @property
    def successful_draws(self) -> int:
        return sum(bundle is not None for bundle in self.bundles)


def bootstrap_sample(train: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    days = np.sort(train.original_day_id.unique())
    selected = rng.choice(days, size=len(days), replace=True)
    parts = []
    for duplicate, day in enumerate(selected):
        part = train.loc[train.original_day_id == day].copy()
        part["bootstrap_copy"] = duplicate
        # The group remains the original day; copies never split across folds.
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def bootstrap(
    train: pd.DataFrame, config: Config, estimator: str, seed: int | None = None
) -> BootstrapResult:
    actual_seed = config.simulation.seed if seed is None else seed
    rng = np.random.default_rng(np.random.SeedSequence([actual_seed, 8071]))
    records, bundles = [], []
    for draw in range(config.evaluation.bootstrap_draws):
        started = time.perf_counter()
        record = {"draw_id": draw, "estimator": estimator, "status": "failed"}
        bundle = None
        try:
            sampled = bootstrap_sample(train, rng)
            result = fit_estimator(sampled, config, estimator, seed=actual_seed)
            if result.bundle is None:
                raise ValueError(
                    result.diagnostics.get("reason", "Bootstrap draw is not identified")
                )
            bundle = result.bundle
            record.update(status="succeeded", original_days=int(sampled.original_day_id.nunique()))
            for j, outcome in enumerate(("x", "y")):
                for k, index in enumerate(bundle.active_treatments):
                    record[f"theta_{outcome}{('x', 'y')[index]}"] = float(bundle.theta[j, k])
            record["baseline_coefficients"] = bundle.base_rate_model.coef_.tolist()
            record["baseline_intercepts"] = bundle.base_rate_model.intercept_.tolist()
        except (ValueError, np.linalg.LinAlgError, RuntimeError) as exc:
            record.update(error_type=type(exc).__name__, error=str(exc))
        record["duration_seconds"] = time.perf_counter() - started
        records.append(record)
        bundles.append(bundle)
    success = sum(b is not None for b in bundles)
    requested = config.evaluation.bootstrap_draws
    failed_fraction = 1 - success / requested if requested else 1.0
    status = (
        "ok"
        if (
            success >= config.evaluation.reporting_min_draws
            and failed_fraction <= config.evaluation.max_failure_fraction
        )
        else "interval_unstable"
    )
    successful = [b for b in bundles if b is not None]
    stability = interval_sensitivity(
        np.array([b.theta.ravel() for b in successful]), config.evaluation.interval_level
    )
    if stability.get("unstable"):
        status = "interval_unstable"
    return BootstrapResult(
        estimator, records, bundles, status, requested, config.evaluation.interval_level, stability
    )


def percentile_interval(values: np.ndarray, level: float) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError(
            "At least two finite bootstrap values are needed for a percentile interval"
        )
    alpha = (1 - level) / 2
    return tuple(np.quantile(values, [alpha, 1 - alpha], axis=0))


def interval_sensitivity(values: np.ndarray, level: float) -> dict:
    """Report change in widths when using half versus all successful draws."""
    if len(values) < 20:
        return {"assessed": False, "reason": "Fewer than 20 successful draws"}
    low, high = percentile_interval(values, level)
    half_low, half_high = percentile_interval(values[: len(values) // 2], level)
    change = np.abs((high - low) - (half_high - half_low)) / np.maximum(high - low, 1e-8)
    return {
        "assessed": True,
        "max_relative_width_change": float(change.max()),
        "unstable": bool((change > 0.5).any()),
    }
