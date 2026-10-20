"""Prospective switchback plans and reconciliation of frozen paired-block outcomes."""

from __future__ import annotations

import math
from typing import cast

import numpy as np
import pandas as pd
from scipy.stats import binomtest, norm, t

from gsm_poc.core.artifacts import fingerprint, safe_id
from gsm_poc.simulation.policies import UNITS, finite_number
from gsm_poc.simulation.rules import parse_timestamp


def plan_experiment(spec: dict, forecast: dict) -> tuple[dict, pd.DataFrame]:
    fields = {
        "schema_version",
        "source_kind",
        "experiment_id",
        "candidate_id",
        "metric",
        "mode",
        "start",
        "clusters",
        "pairs_per_cluster",
        "block_minutes",
        "washout_minutes",
        "seed",
        "alpha",
        "power",
        "minimum_effect",
        "paired_difference_sd",
        "independence_assumption",
        "carryover_assumption",
    }
    if not isinstance(spec, dict) or set(spec) != fields:
        raise ValueError("Experiment specification has missing or unknown fields")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("Unsupported experiment schema_version")
    if spec["source_kind"] != "synthetic" or spec["mode"] not in ("AA", "AB"):
        raise ValueError("Only explicitly synthetic AA/AB plans are currently supported")
    safe_id(spec["experiment_id"])
    if spec["metric"] not in UNITS:
        raise ValueError("Unknown experiment metric")
    candidates = {row["policy_id"] for row in forecast["decisions"]}
    if spec["candidate_id"] not in candidates - {"baseline"}:
        raise ValueError("Experiment candidate must be a frozen nonbaseline policy")
    if forecast["failed_trajectories"]:
        raise ValueError("Cannot freeze an experiment forecast from failed policy trajectories")
    clusters = spec["clusters"]
    if not isinstance(clusters, list) or not clusters or len(clusters) > 100:
        raise ValueError("Declare 1–100 unique cluster IDs")
    if any(not isinstance(cluster, str) for cluster in clusters):
        raise ValueError("Cluster IDs must be strings")
    if len(set(clusters)) != len(clusters):
        raise ValueError("Duplicate cluster IDs")
    for cluster in clusters:
        safe_id(cluster)
    for key, minimum, maximum in (
        ("pairs_per_cluster", 1, 10000),
        ("block_minutes", 1, 10080),
        ("washout_minutes", 0, 10080),
        ("seed", 0, 2**31 - 1),
    ):
        if type(spec[key]) is not int or not minimum <= spec[key] <= maximum:
            raise ValueError(f"{key} must be an integer in [{minimum}, {maximum}]")
    if len(clusters) * spec["pairs_per_cluster"] > 10000:
        raise ValueError("Experiment exceeds 10,000 assignment pairs")
    for key in ("independence_assumption", "carryover_assumption"):
        if not isinstance(spec[key], str) or not spec[key].strip():
            raise ValueError(f"Declare {key} explicitly")
    alpha = finite_number(spec["alpha"], "alpha")
    power = finite_number(spec["power"], "power")
    effect = finite_number(spec["minimum_effect"], "minimum_effect")
    if not 0 < alpha < 1 or not 0.5 < power < 1 or effect <= 0:
        raise ValueError("Require alpha in (0,1), power in (0.5,1) and positive minimum_effect")
    sd = spec["paired_difference_sd"]
    required = None
    if sd is not None:
        sd = finite_number(sd, "paired_difference_sd")
        if sd <= 0:
            raise ValueError("paired_difference_sd must be positive")
        required = max(
            2, math.ceil(((norm.ppf(1 - alpha / 2) + norm.ppf(power)) * sd / effect) ** 2)
        )
    start = parse_timestamp(spec["start"], "experiment start")
    rng = np.random.default_rng(spec["seed"])
    rows = []
    for cluster in clusters:
        for pair in range(spec["pairs_per_cluster"]):
            assignment = ["control", "treatment"]
            if rng.integers(2):
                assignment.reverse()
            for position, arm in enumerate(assignment):
                offset = (2 * pair + position) * (spec["block_minutes"] + spec["washout_minutes"])
                beginning = cast(pd.Timestamp, start + pd.Timedelta(minutes=offset))
                rows.append(
                    {
                        "experiment_id": spec["experiment_id"],
                        "cluster_id": cluster,
                        "pair_id": f"{cluster}-{pair}",
                        "block_id": f"{cluster}-{pair}-{position}",
                        "arm": arm,
                        "policy_id": spec["candidate_id"]
                        if arm == "treatment" and spec["mode"] == "AB"
                        else "baseline",
                        "start": beginning.isoformat(),
                        "end": cast(
                            pd.Timestamp, beginning + pd.Timedelta(minutes=spec["block_minutes"])
                        ).isoformat(),
                        "assignment_probability": 0.5,
                    }
                )
    target = next(
        row
        for row in forecast["summary"]
        if row["policy_id"] == spec["candidate_id"]
        and row["metric"] == spec["metric"]
        and row["sensitivity_id"] == "declared_rules"
    )
    horizon = forecast["scope"]["horizon_minutes"]
    matching = spec["block_minutes"] == horizon and len(clusters) == 1
    frozen_prediction = {
        "metric": spec["metric"],
        "unit": UNITS[spec["metric"]],
        "scope": forecast["scope"],
        "source_policy_version": forecast["spec_version"],
        "status": "available" if matching or spec["mode"] == "AA" else "scope_mismatch",
        "delta": 0.0 if spec["mode"] == "AA" else target["delta_mean"] if matching else None,
        "lower": 0.0 if spec["mode"] == "AA" else target["model_delta_lower"] if matching else None,
        "upper": 0.0 if spec["mode"] == "AA" else target["model_delta_upper"] if matching else None,
        "transport_assumption": (
            "Repeated future blocks match the frozen zone/context/roster population"
        ),
    }
    plan = {
        "schema_version": 1,
        "experiment_id": spec["experiment_id"],
        "spec": spec,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "status": "draft_not_authorized_for_gsm",
        "schedule_version": fingerprint(rows),
        "prediction": frozen_prediction,
        "power": {
            "status": "normal_approximation"
            if required is not None
            else "unavailable_missing_variance",
            "required_independent_pairs": required,
            "scheduled_pairs": len(clusters) * spec["pairs_per_cluster"],
            "sufficient_under_assumptions": len(clusters) * spec["pairs_per_cluster"] >= required
            if required is not None
            else None,
            "variance_unit": "independent paired block differences; no quote-row inflation",
            "calibration_status": "not_evaluated_on_gsm",
        },
        "analysis": {
            "unit": "independent randomized block pair",
            "estimator": "mean treatment minus control",
            "interval": "two-sided Student-t across complete independent pairs",
            "stopping": "fixed scheduled sample; no optional stopping",
            "missingness": "incomplete pairs invalidate final effect inference",
            "aa_checks": [
                "exact schedule/exposure matching",
                "one outcome per scheduled block",
                "paired completeness",
                "sample ratio mismatch",
                "zero-effect interval",
            ],
            "assumptions": [spec["independence_assumption"], spec["carryover_assumption"]],
        },
    }
    return plan, pd.DataFrame(rows)


def reconcile_experiment(plan: dict, schedule: pd.DataFrame, observations: pd.DataFrame) -> dict:
    """Validate assigned exposure before consulting observed effects; preserve prediction."""
    if fingerprint(schedule.to_dict("records")) != plan["schedule_version"]:
        raise ValueError("Frozen schedule checksum differs")
    required = {"block_id", "applied_policy_id", "metric", "unit", "value", "source_kind"}
    if set(observations) != required or observations.empty or observations.isna().to_numpy().any():
        raise ValueError("Observation columns or values violate the outcome contract")
    if observations.block_id.duplicated().any():
        raise ValueError("Duplicate block outcomes")
    if not set(observations.block_id) <= set(schedule.block_id):
        raise ValueError("Outcomes contain unknown schedule blocks")
    metric = plan["spec"]["metric"]
    if not observations.metric.eq(metric).all() or not observations.unit.eq(UNITS[metric]).all():
        raise ValueError("Outcome metric or units differ from the preregistered experiment")
    if not observations.source_kind.eq("synthetic").all():
        raise ValueError("This reconciliation is validated for synthetic observations only")
    values = observations.value
    if not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values):
        raise ValueError("Outcome values must be numeric")
    if not np.isfinite(values).all():
        raise ValueError("Outcome values must be finite")
    joined = schedule.merge(observations, on="block_id", how="left", validate="one_to_one")
    exposed = joined.applied_policy_id.notna()
    if not joined.loc[exposed, "applied_policy_id"].eq(joined.loc[exposed, "policy_id"]).all():
        raise ValueError("Applied policy differs from frozen assignment")
    wide = joined.pivot(index="pair_id", columns="arm", values="value")
    complete = wide.dropna()
    difference = complete.treatment - complete.control
    count = len(difference)
    missing = len(schedule) - len(observations)
    valid = not missing and count >= 2
    effect = float(difference.mean()) if count else None
    alpha = plan["spec"]["alpha"]
    half = (
        float(t.ppf(1 - alpha / 2, count - 1) * difference.std(ddof=1) / np.sqrt(count))
        if valid
        else None
    )
    interval = [effect - half, effect + half] if effect is not None and half is not None else None
    control_count = int(joined.loc[exposed, "arm"].eq("control").sum())
    srm = float(binomtest(control_count, int(exposed.sum()), 0.5).pvalue)
    prediction = plan["prediction"]
    error = effect - prediction["delta"] if valid and prediction["delta"] is not None else None
    return {
        "schema_version": 1,
        "experiment_id": plan["experiment_id"],
        "source_kind": "synthetic",
        "evidence_level": "C",
        "status": "completed" if valid else "incomplete",
        "expected_blocks": len(schedule),
        "observed_blocks": len(observations),
        "expected_pairs": len(wide),
        "complete_pairs": count,
        "missing_blocks": missing,
        "sample_ratio_pvalue": srm,
        "sample_ratio_status": "warning" if srm < alpha else "ok",
        "observed_effect": effect,
        "interval": interval,
        "interval_status": "available_under_declared_independence" if valid else "unavailable",
        "aa_zero_in_interval": bool(interval[0] <= 0 <= interval[1])
        if interval is not None and plan["spec"]["mode"] == "AA"
        else None,
        "frozen_prediction": prediction,
        "forecast_error": error,
        "forecast_reconciliation_status": "matched_under_transport_assumption"
        if error is not None
        else "not_evaluated_scope_or_completeness",
        "gsm_causal_validation_status": "not_evaluated",
    }
