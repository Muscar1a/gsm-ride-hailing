"""Frozen-seed controlled evaluation of the fixed driver-randomized contrast."""

from __future__ import annotations

import dataclasses
import time
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from gsm_poc.causal.supply import OUTCOMES, SupplySpec, fit_supply
from gsm_poc.core.artifacts import fingerprint
from gsm_poc.simulation.supply import generate_supply


@dataclasses.dataclass(frozen=True)
class SupplyProtocol:
    schema_version: int = 1
    phase: str = "assessment"
    rct_seed_start: int = 61001
    null_seed_start: int = 62001
    n_seeds: int = 100
    max_seconds: float = 600.0
    coverage_floor: float = 0.90
    max_null_false_positive_rate: float = 0.10
    max_participation_bias: float = 0.04
    max_hours_bias: float = 0.20
    max_participation_rmse: float = 0.08
    max_hours_rmse: float = 0.30

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("Unsupported supply benchmark protocol")
        if self.phase not in ("pilot", "assessment"):
            raise ValueError("Supply benchmark phase must be pilot or assessment")
        if type(self.n_seeds) is not int or not 1 <= self.n_seeds <= 500:
            raise ValueError("Supply benchmark requires 1-500 seeds per DGP")
        if self.phase == "assessment" and self.n_seeds < 50:
            raise ValueError("Assessment requires at least 50 independent seeds per DGP")
        for name in ("rct_seed_start", "null_seed_start"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value < 2**32 - self.n_seeds:
                raise ValueError("Benchmark seed ranges must be valid nonnegative integers")
        rct = set(range(self.rct_seed_start, self.rct_seed_start + self.n_seeds))
        null = set(range(self.null_seed_start, self.null_seed_start + self.n_seeds))
        if rct & null:
            raise ValueError("RCT and null benchmark seed ranges must be disjoint")
        for field in dataclasses.fields(self):
            if field.name in {
                "schema_version",
                "phase",
                "n_seeds",
                "rct_seed_start",
                "null_seed_start",
            }:
                continue
            value = getattr(self, field.name)
            if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
                raise ValueError(f"Invalid benchmark limit: {field.name}")
        if not 0 < self.max_seconds <= 600:
            raise ValueError("Benchmark time budget must be in (0, 600] seconds")
        if not 0 < self.coverage_floor < 1 or not 0 <= self.max_null_false_positive_rate < 1:
            raise ValueError("Invalid benchmark coverage/false-positive limits")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SupplyProtocol:
        if not isinstance(value, dict) or set(value) != {
            field.name for field in dataclasses.fields(cls)
        }:
            raise ValueError("Supply protocol has missing or unknown fields")
        return cls(**value)


def evaluate_supply(
    spec: SupplySpec, protocol: SupplyProtocol
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """No method selection or tuning: oracle values are read only after fitting."""
    started = time.perf_counter()
    records = []
    for dgp, first_seed in (
        ("RCT_SUPPLY", protocol.rct_seed_start),
        ("NULL_SUPPLY", protocol.null_seed_start),
    ):
        for seed in range(first_seed, first_seed + protocol.n_seeds):
            if time.perf_counter() - started >= protocol.max_seconds:
                raise RuntimeError(
                    "Supply benchmark time budget exhausted; no completed assessment"
                )
            settings = dataclasses.replace(
                spec,
                seed=seed,
                **(
                    {"participation_effect": 0.0, "conditional_hours_effect": 0.0}
                    if dgp == "NULL_SUPPLY"
                    else {}
                ),
            )
            observed, oracle = generate_supply(settings)
            fitted = fit_supply(observed, settings.contract())
            oracle_id = fingerprint(oracle.to_dict("list"))
            for row in fitted["effects"]:
                outcome = row["outcome"]
                truth = float((oracle[f"{outcome}_target"] - oracle[f"{outcome}_baseline"]).mean())
                available = row["interval_status"] == "ok"
                records.append(
                    {
                        "dgp": dgp,
                        "seed": seed,
                        "outcome": outcome,
                        "truth": truth,
                        "estimate": row["effect"],
                        "ci_low": row["ci_low"],
                        "ci_high": row["ci_high"],
                        "interval_available": available,
                        "covered": row["ci_low"] <= truth <= row["ci_high"] if available else None,
                        "false_positive": not row["ci_low"] <= 0 <= row["ci_high"]
                        if available and dgp == "NULL_SUPPLY"
                        else None,
                        "status": row["status"],
                        "interval_status": row["interval_status"],
                        "observed_id": fitted["observed_id"],
                        "oracle_id": oracle_id,
                        "model_id": fitted["model_id"],
                        "no_response_baseline": 0.0,
                    }
                )
    frame = pd.DataFrame(records)
    summaries = []
    for dgp in ("RCT_SUPPLY", "NULL_SUPPLY"):
        for outcome in OUTCOMES:
            subset = frame.loc[frame.dgp.eq(dgp) & frame.outcome.eq(outcome)]
            valid_points = subset.loc[subset.status.eq("ok")]
            valid = subset.loc[subset.interval_available]
            errors = valid_points.estimate.to_numpy(dtype=float) - valid_points.truth.to_numpy(
                dtype=float
            )
            n_valid, covered = len(valid), int(valid.covered.sum())
            calibration = binomtest(covered, n_valid).proportion_ci() if n_valid else None
            coverage = covered / n_valid if n_valid else None
            bias = float(errors.mean()) if len(errors) else None
            rmse = float(np.sqrt(np.mean(errors**2))) if len(errors) else None
            false_positives = int(valid.false_positive.sum()) if dgp == "NULL_SUPPLY" else None
            false_positive_rate = (
                false_positives / n_valid if n_valid and false_positives is not None else None
            )
            false_positive_interval = (
                binomtest(false_positives, n_valid).proportion_ci()
                if false_positives is not None and n_valid
                else None
            )
            bias_limit = (
                protocol.max_participation_bias
                if outcome == "participated"
                else protocol.max_hours_bias
            )
            rmse_limit = (
                protocol.max_participation_rmse
                if outcome == "participated"
                else protocol.max_hours_rmse
            )
            checks = {
                "all_points_and_intervals_available": len(valid_points) == n_valid == len(subset),
                "bias": bias is not None and abs(bias) <= bias_limit,
                "rmse": rmse is not None and rmse <= rmse_limit,
                "coverage_floor": coverage is not None and coverage >= protocol.coverage_floor,
                "null_false_positives": dgp != "NULL_SUPPLY"
                or (
                    false_positive_rate is not None
                    and false_positive_rate <= protocol.max_null_false_positive_rate
                ),
            }
            summaries.append(
                {
                    "dgp": dgp,
                    "outcome": outcome,
                    "attempted": len(subset),
                    "valid_points": len(valid_points),
                    "available_intervals": n_valid,
                    "unavailable_intervals": len(subset) - n_valid,
                    "bias": bias,
                    "rmse": rmse,
                    "no_response_baseline_rmse": float(np.sqrt(np.mean(subset.truth**2))),
                    "coverage": coverage,
                    "covered": covered,
                    "coverage_ci_low": float(calibration.low) if calibration else None,
                    "coverage_ci_high": float(calibration.high) if calibration else None,
                    "mean_interval_width": float((valid.ci_high - valid.ci_low).mean())
                    if n_valid
                    else None,
                    "null_false_positive_rate": false_positive_rate,
                    "null_false_positive_ci_low": float(false_positive_interval.low)
                    if false_positive_interval
                    else None,
                    "null_false_positive_ci_high": float(false_positive_interval.high)
                    if false_positive_interval
                    else None,
                    "checks": checks,
                    "status": "development_only"
                    if protocol.phase == "pilot"
                    else (
                        "controlled_checks_passed"
                        if all(checks.values())
                        else "controlled_checks_failed"
                    ),
                }
            )
    duration = time.perf_counter() - started
    if duration > protocol.max_seconds:
        raise RuntimeError("Supply benchmark time budget exhausted; no completed assessment")
    return frame, {
        "schema_version": 1,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "phase": protocol.phase,
        "protocol": dataclasses.asdict(protocol),
        "protocol_id": fingerprint(dataclasses.asdict(protocol)),
        "spec": dataclasses.asdict(spec),
        "spec_id": fingerprint(dataclasses.asdict(spec)),
        "estimator": "randomized_driver_mean_contrast",
        "inference_unit": "driver_id",
        "interval_scope": "individual_outcome",
        "nominal_interval_level": spec.interval_level,
        "calibration_status": "controlled_assessment_not_gsm_calibration",
        "nominal_coverage_certified": False,
        "duration_seconds": duration,
        "attempted_seed_jobs": 2 * protocol.n_seeds,
        "seed_jobs_with_all_intervals": int(
            frame.groupby(["dgp", "seed"]).interval_available.all().sum()
        ),
        "summaries": summaries,
        "status": "development_only"
        if protocol.phase == "pilot"
        else (
            "controlled_checks_passed"
            if all(row["status"] == "controlled_checks_passed" for row in summaries)
            else "controlled_checks_failed"
        ),
    }
