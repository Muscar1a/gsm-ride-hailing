"""Finite price comparisons under the accepted fixed-online, evidence-C contract."""

from __future__ import annotations

import copy
import dataclasses
import time
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t

from gsm_poc.causal.estimate import ModelBundle
from gsm_poc.causal.scenario import ScenarioRequest
from gsm_poc.causal.uncertainty import BootstrapResult, interval_sensitivity
from gsm_poc.core.artifacts import fingerprint, safe_id
from gsm_poc.core.config import Config
from gsm_poc.simulation.demand import DemandPlan, prepare_demand_plan
from gsm_poc.simulation.evaluation import METRIC_UNITS, _run_record
from gsm_poc.simulation.rules import normalize_rules

UNITS = METRIC_UNITS | {
    "unserved_fraction": "fraction of created requests expired or canceled before pickup",
    "gross_booking_value": "SYNTHETIC_UNIT",
    "conditional_surplus": "SYNTHETIC_UNIT",
}
COST_FIELDS = ("per_completed_trip", "per_online_hour", "per_horizon")


def finite_number(value: Any, name: str, minimum: float | None = None) -> float:
    if type(value) not in (int, float) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return float(value)


def validate_policy_spec(spec: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version",
        "source_kind",
        "candidates",
        "seed_start",
        "n_seeds",
        "bootstrap_draws",
        "replicates_per_draw",
        "max_seconds",
        "interval_level",
        "criterion",
        "guardrails",
        "costs",
        "sensitivities",
    }
    if not isinstance(spec, dict) or set(spec) != fields:
        raise ValueError("Policy specification has missing or unknown fields")
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1:
        raise ValueError("Unsupported policy schema_version")
    if spec["source_kind"] != "synthetic":
        raise ValueError("Policy comparisons currently support synthetic evidence C only")
    for key, lower, upper in (
        ("seed_start", 0, 2**31 - 10000),
        ("n_seeds", 2, 1000),
        ("bootstrap_draws", 0, 1000),
        ("replicates_per_draw", 2, 100),
    ):
        if type(spec[key]) is not int or not lower <= spec[key] <= upper:
            raise ValueError(f"{key} must be an integer within [{lower}, {upper}]")
    if not 0 < finite_number(spec["max_seconds"], "max_seconds") <= 3600:
        raise ValueError("max_seconds must be within (0, 3600]")
    if not 0 < finite_number(spec["interval_level"], "interval_level") < 1:
        raise ValueError("interval_level must be within (0, 1)")
    candidates = spec["candidates"]
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 12:
        raise ValueError("Declare 2–12 finite price candidates including baseline")
    ids, actions = set(), set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {"policy_id", "delta_x", "delta_y"}:
            raise ValueError("Candidate fields must be policy_id, delta_x and delta_y")
        if not isinstance(candidate["policy_id"], str):
            raise ValueError("policy_id must be a string")
        policy_id = safe_id(candidate["policy_id"])
        action = tuple(finite_number(candidate[key], key) for key in ("delta_x", "delta_y"))
        if policy_id in ids or action in actions or min(action) <= -1:
            raise ValueError("Candidate IDs/actions must be unique and prices positive")
        ids.add(policy_id)
        actions.add(action)
    if candidates[0] != {"policy_id": "baseline", "delta_x": 0.0, "delta_y": 0.0}:
        raise ValueError("First candidate must be unchanged baseline")
    criterion = spec["criterion"]
    if not isinstance(criterion, dict) or set(criterion) != {"metric", "direction", "minimum_gain"}:
        raise ValueError("Criterion needs metric, direction and minimum_gain")
    if criterion["metric"] not in UNITS or criterion["direction"] not in ("maximize", "minimize"):
        raise ValueError("Unsupported criterion metric or direction")
    finite_number(criterion["minimum_gain"], "minimum_gain", 0)
    if not isinstance(spec["guardrails"], list):
        raise ValueError("guardrails must be an explicit list")
    for guardrail in spec["guardrails"]:
        if not isinstance(guardrail, dict) or set(guardrail) != {"metric", "direction", "limit"}:
            raise ValueError("Guardrail needs metric, direction and limit")
        if guardrail["metric"] not in UNITS or guardrail["direction"] not in ("maximum", "minimum"):
            raise ValueError("Unsupported guardrail metric or direction")
        finite_number(guardrail["limit"], "guardrail limit")
    costs = spec["costs"]
    if not isinstance(costs, dict) or set(costs) != {"currency", *COST_FIELDS}:
        raise ValueError("Costs need explicit currency and trip/hour/horizon components")
    if costs["currency"] != "SYNTHETIC_UNIT":
        raise ValueError("Costs must use the synthetic fare currency")
    for key in COST_FIELDS:
        if costs[key] is not None:
            finite_number(costs[key], key, 0)
    sensitivities = spec["sensitivities"]
    if not isinstance(sensitivities, list) or len(sensitivities) > 8:
        raise ValueError("sensitivities must contain at most eight declared rule alternatives")
    seen = {"declared_rules"}
    for sensitivity in sensitivities:
        if not isinstance(sensitivity, dict) or set(sensitivity) != {
            "sensitivity_id",
            "acceptance_probability",
            "travel_time_multiplier",
        }:
            raise ValueError(
                "Sensitivity needs ID, acceptance_probability and travel_time_multiplier"
            )
        if not isinstance(sensitivity["sensitivity_id"], str):
            raise ValueError("sensitivity_id must be a string")
        sensitivity_id = safe_id(sensitivity["sensitivity_id"])
        if sensitivity_id in seen:
            raise ValueError("Duplicate sensitivity_id")
        seen.add(sensitivity_id)
        if (
            not 0
            <= finite_number(sensitivity["acceptance_probability"], "acceptance_probability")
            <= 1
        ):
            raise ValueError("acceptance_probability must be within [0, 1]")
        if (
            not 0
            < finite_number(sensitivity["travel_time_multiplier"], "travel_time_multiplier")
            <= 10
        ):
            raise ValueError("travel_time_multiplier must be within (0, 10]")
    jobs = len(candidates) * (
        spec["n_seeds"] * (1 + len(sensitivities))
        + spec["bootstrap_draws"] * spec["replicates_per_draw"]
    )
    if jobs > 10000:
        raise ValueError("Policy workload exceeds 10,000 trajectories")
    return copy.deepcopy(spec)


def policy_plan(
    bundle: ModelBundle,
    contexts: pd.DataFrame,
    snapshot: dict,
    candidate: dict,
    config: Config,
    model_run_id: str,
    model_version: str,
    source_version: str,
    *,
    support_bundle: ModelBundle | None = None,
) -> DemandPlan:
    # Identification support belongs to original training, not bootstrap multiplicities.
    if support_bundle is not None:
        bundle = dataclasses.replace(bundle, train_support=support_bundle.train_support)
    return prepare_demand_plan(
        bundle,
        contexts,
        snapshot,
        ScenarioRequest(
            candidate["policy_id"],
            delta_price_x=candidate["delta_x"],
            delta_price_y=candidate["delta_y"],
        ),
        config,
        model_run_id,
        model_version,
        source_version,
    )


def policy_record(
    plan: DemandPlan,
    config: Config,
    rules: dict,
    compensation: dict,
    seed: int,
    deadline: float,
    costs: dict,
) -> dict:
    record = _run_record(plan, config, rules, compensation, seed, "policy", deadline)
    if record["status"] == "succeeded":
        created = record["created_requests"]
        record["unserved_fraction"] = (
            (record["expired_requests"] + record["canceled_requests"]) / created
            if created
            else None
        )
        # The accepted compensation contract pays exactly 100% of collected fixture fares.
        record["gross_booking_value"] = record["total_driver_pay"]
        record["conditional_surplus"] = (
            record["gross_booking_value"]
            - record["total_driver_pay"]
            - costs["per_completed_trip"] * record["completed_trips"]
            - costs["per_online_hour"] * record["online_hours"]
            - costs["per_horizon"]
            if all(costs[key] is not None for key in COST_FIELDS)
            else None
        )
    return record


def summarize_policies(records: pd.DataFrame, spec: dict) -> list[dict]:
    """Never silently discard failed, missing or undefined pairs from an interval."""
    rows = []
    sensitivities = ["declared_rules", *[s["sensitivity_id"] for s in spec["sensitivities"]]]
    for sensitivity_id in sensitivities:
        selected = records[records.kind.eq("point") & records.sensitivity_id.eq(sensitivity_id)]
        baseline = selected[selected.policy_id.eq("baseline")].set_index("seed")
        for candidate in spec["candidates"]:
            policy_id = candidate["policy_id"]
            target = selected[selected.policy_id.eq(policy_id)].set_index("seed")
            paired = target.join(baseline, lsuffix="_target", rsuffix="_baseline", how="outer")
            for metric, unit in UNITS.items():
                missing = pd.Series(np.nan, index=paired.index)
                left = pd.to_numeric(paired.get(f"{metric}_baseline", missing), errors="coerce")
                right = pd.to_numeric(paired.get(f"{metric}_target", missing), errors="coerce")
                valid = (
                    paired.status_target.eq("succeeded")
                    & paired.status_baseline.eq("succeeded")
                    & np.isfinite(left)
                    & np.isfinite(right)
                )
                differences = right[valid] - left[valid]
                count = len(differences)
                complete = count == spec["n_seeds"]
                half = (
                    float(
                        t.ppf((1 + spec["interval_level"]) / 2, count - 1)
                        * differences.std(ddof=1)
                        / np.sqrt(count)
                    )
                    if complete
                    else None
                )
                mean = float(differences.mean()) if count else None
                row = {
                    "policy_id": policy_id,
                    "sensitivity_id": sensitivity_id,
                    "metric": metric,
                    "unit": unit,
                    "attempted_pairs": spec["n_seeds"],
                    "valid_pairs": count,
                    "unavailable_pairs": spec["n_seeds"] - count,
                    "baseline_mean": float(left[valid].mean()) if count else None,
                    "target_mean": float(right[valid].mean()) if count else None,
                    "delta_mean": mean,
                    "mc_delta_lower": mean - half
                    if mean is not None and half is not None
                    else None,
                    "mc_delta_upper": mean + half
                    if mean is not None and half is not None
                    else None,
                    "model_delta_lower": None,
                    "model_delta_upper": None,
                    "valid_model_draws": 0,
                    "requested_model_draws": spec["bootstrap_draws"],
                    "interval_status": "unavailable",
                    "width_stability": None,
                }
                if sensitivity_id == "declared_rules":
                    draws = records[records.kind.eq("bootstrap")]
                    values = []
                    for draw_id in range(spec["bootstrap_draws"]):
                        draw = draws[draws.draw_id.eq(draw_id)]
                        a = draw[draw.policy_id.eq("baseline")].set_index("seed")
                        b = draw[draw.policy_id.eq(policy_id)].set_index("seed")
                        if len(a) != spec["replicates_per_draw"] or len(b) != len(a):
                            continue
                        if not a.status.eq("succeeded").all() or not b.status.eq("succeeded").all():
                            continue
                        if metric not in a or metric not in b:
                            continue
                        difference = pd.to_numeric(b[metric], errors="coerce") - pd.to_numeric(
                            a[metric], errors="coerce"
                        )
                        if np.isfinite(difference).all():
                            values.append(float(difference.mean()))
                    row["valid_model_draws"] = len(values)
                    if len(values) >= 20 and len(values) == spec["bootstrap_draws"] and complete:
                        alpha = (1 - spec["interval_level"]) / 2
                        lower, upper = np.quantile(values, [alpha, 1 - alpha])
                        stability = interval_sensitivity(np.asarray(values), spec["interval_level"])
                        row.update(
                            model_delta_lower=float(lower),
                            model_delta_upper=float(upper),
                            interval_status="unstable"
                            if stability.get("unstable")
                            else "available",
                            width_stability=stability,
                        )
                rows.append(row)
    return rows


def decide_policies(summary: list[dict], spec: dict) -> dict:
    decisions: list[dict[str, Any]] = []
    criterion = spec["criterion"]
    sign = 1 if criterion["direction"] == "maximize" else -1
    for candidate in spec["candidates"]:
        policy_id = candidate["policy_id"]
        rows = [r for r in summary if r["policy_id"] == policy_id]
        objective = next(
            r
            for r in rows
            if r["metric"] == criterion["metric"] and r["sensitivity_id"] == "declared_rules"
        )
        reasons = []
        if objective["interval_status"] != "available":
            reasons.append("Model-and-operation interval unavailable or unstable")
        gain_bound = objective["model_delta_lower" if sign == 1 else "model_delta_upper"]
        conservative_gain = sign * gain_bound if gain_bound is not None else None
        if conservative_gain is None or conservative_gain < criterion["minimum_gain"]:
            reasons.append("Minimum worthwhile gain is not established")
        checks = []
        for row in rows:
            if row["metric"] == criterion["metric"] and row["sensitivity_id"] != "declared_rules":
                bound = row["mc_delta_lower" if sign == 1 else "mc_delta_upper"]
                if bound is None or sign * bound < criterion["minimum_gain"]:
                    reasons.append(f"Objective not robust under {row['sensitivity_id']}")
            for guardrail in spec["guardrails"]:
                if row["metric"] != guardrail["metric"]:
                    continue
                value = row["target_mean"]
                passed = (
                    value is not None
                    and row["unavailable_pairs"] == 0
                    and (
                        value <= guardrail["limit"]
                        if guardrail["direction"] == "maximum"
                        else value >= guardrail["limit"]
                    )
                )
                checks.append(
                    guardrail
                    | {
                        "sensitivity_id": row["sensitivity_id"],
                        "observed_mean": value,
                        "status": "passed" if passed else "violated_or_unavailable",
                    }
                )
                if not passed:
                    reasons.append(
                        f"Guardrail {row['metric']} failed under {row['sensitivity_id']}"
                    )
        decisions.append(
            {
                "policy_id": policy_id,
                "score": objective["target_mean"],
                "conservative_gain": conservative_gain,
                "guardrails": checks,
                "status": "development_candidate" if not reasons else "not_recommended",
                "reasons": reasons,
            }
        )
    eligible = [d for d in decisions if d["status"] == "development_candidate"]
    selected = max(eligible, key=lambda d: sign * d["score"])["policy_id"] if eligible else None
    return {
        "selected_policy_id": selected,
        "decisions": decisions,
        "selection_status": "development_only" if selected else "no_candidate_qualifies",
        "gsm_recommendation_status": "pending_gsm_data_and_business_confirmation",
        "guardrail_scope": (
            "point mean across paired trajectories, under every declared sensitivity"
        ),
    }


def evaluate_frozen_decision(summary: list[dict], spec: dict, selected_policy: str | None) -> dict:
    """Evaluator-only finite reference under declared mean guardrails; never reselect."""
    metric = spec["criterion"]["metric"]
    sign = 1 if spec["criterion"]["direction"] == "maximize" else -1
    scores = {
        row["policy_id"]: row["target_mean"]
        for row in summary
        if row["metric"] == metric
        and row["unavailable_pairs"] == 0
        and row["target_mean"] is not None
    }
    feasible = set(scores)
    for guardrail in spec["guardrails"]:
        feasible &= {
            row["policy_id"]
            for row in summary
            if row["metric"] == guardrail["metric"]
            and row["unavailable_pairs"] == 0
            and row["target_mean"] is not None
            and (
                row["target_mean"] <= guardrail["limit"]
                if guardrail["direction"] == "maximum"
                else row["target_mean"] >= guardrail["limit"]
            )
        }
    order = [candidate["policy_id"] for candidate in spec["candidates"]]
    best = max(
        (policy for policy in order if policy in feasible),
        key=lambda policy: sign * scores[policy],
        default=None,
    )
    value = scores.get(selected_policy)
    return {
        "frozen_policy_id": selected_policy,
        "frozen_policy_value": value,
        "frozen_policy_guardrails_passed": selected_policy in feasible
        if selected_policy is not None
        else None,
        "baseline_value": scores.get("baseline"),
        "reference_best_policy_id": best,
        "reference_best_value": scores[best] if best is not None else None,
        "regret": sign * (scores[best] - value)
        if best is not None and value is not None and selected_policy in feasible
        else None,
        "reference_scope": "finite declared candidates; controlled truth; Monte Carlo point means",
        "regret_interval_status": "not_evaluated",
        "reselection": False,
    }


def compare_policies(
    bundle: ModelBundle,
    draws: BootstrapResult,
    contexts: pd.DataFrame,
    snapshot: dict,
    config: Config,
    rules: dict,
    compensation: dict,
    spec: dict,
    model_run_id: str,
    model_version: str,
    source_version: str,
) -> dict:
    spec = validate_policy_spec(spec)
    if rules.get("schema_version") != 3:
        raise ValueError("Week 4 requires the accepted V3 fixed-online rules")
    if draws.requested_draws != len(draws.bundles) or len(draws.records) != len(draws.bundles):
        raise ValueError("Bootstrap records, bundles and attempted count disagree")
    if spec["bootstrap_draws"] > len(draws.bundles):
        raise ValueError(
            "Requested model draws exceed the frozen bootstrap; refit a new source run"
        )
    deadline = time.perf_counter() + spec["max_seconds"]
    plans = {
        c["policy_id"]: policy_plan(
            bundle, contexts, snapshot, c, config, model_run_id, model_version, source_version
        )
        for c in spec["candidates"]
    }
    records = []
    variants = [{"sensitivity_id": "declared_rules"}, *spec["sensitivities"]]
    for variant in variants:
        alternative = copy.deepcopy(rules)
        if variant["sensitivity_id"] != "declared_rules":
            alternative["acceptance_probability"] = variant["acceptance_probability"]
            for row in alternative["travel_times"]:
                for key in ("pickup_seconds", "trip_seconds"):
                    row[key] *= variant["travel_time_multiplier"]
        alternative = normalize_rules(alternative, snapshot)
        for index in range(spec["n_seeds"]):
            seed = spec["seed_start"] + index
            for policy_id, plan in plans.items():
                record = policy_record(
                    plan, config, alternative, compensation, seed, deadline, spec["costs"]
                )
                records.append(
                    record | {"kind": "point", "draw_id": -1, "policy_id": policy_id, **variant}
                )
    for draw_id in range(spec["bootstrap_draws"]):
        draw = draws.bundles[draw_id]
        for candidate in spec["candidates"]:
            policy_id = candidate["policy_id"]
            draw_plan = None
            reason = "Frozen bootstrap fit failed"
            if draw is not None:
                draw_plan = policy_plan(
                    draw,
                    contexts,
                    snapshot,
                    candidate,
                    config,
                    model_run_id,
                    f"bootstrap-{draw_id}",
                    source_version,
                    support_bundle=bundle,
                )
            for index in range(spec["replicates_per_draw"]):
                seed = spec["seed_start"] + 10000 + draw_id * spec["replicates_per_draw"] + index
                record = (
                    policy_record(
                        draw_plan, config, rules, compensation, seed, deadline, spec["costs"]
                    )
                    if draw_plan is not None
                    else {"seed": seed, "status": "failed", "reason": reason}
                )
                records.append(
                    record
                    | {
                        "kind": "bootstrap",
                        "draw_id": draw_id,
                        "policy_id": policy_id,
                        "sensitivity_id": "declared_rules",
                    }
                )
    frame = pd.DataFrame(records)
    summary = summarize_policies(frame, spec)
    failed = int(frame.status.ne("succeeded").sum())
    result = {
        "schema_version": 1,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "status": "completed_with_failures" if failed else "completed",
        "attempted_trajectories": len(frame),
        "failed_trajectories": failed,
        "spec_version": fingerprint(spec),
        "summary": summary,
        **decide_policies(summary, spec),
        "uncertainty": {
            "method": "original-day bootstrap refits propagated through paired operational runs",
            "target": "fixed candidate policy contrasts on frozen quote contexts and roster",
            "model_interval": "percentiles of per-model paired replicate means",
            "operation_interval": "Student-t Monte Carlo interval conditional on point fit",
            "excludes": [
                "policy-selection uncertainty",
                "GSM calibration",
                "unknown rule uncertainty",
                "quote-population shifts",
                "simultaneous coverage",
            ],
            "calibration_status": "not_evaluated",
            "minimum_complete_model_draws": 20,
            "limitation": "Finite inner replicates retain Monte Carlo error in model intervals",
        },
        "economics": {
            "status": "conditional_only"
            if all(spec["costs"][k] is not None for k in COST_FIELDS)
            else "not_evaluated_missing_costs",
            "costs": spec["costs"],
            "formula": "completed fare receipts - driver pay - trip/hour/horizon declared costs",
            "profit_status": "not_evaluated",
            "roi_status": "not_evaluated",
            "reason": "Synthetic fare receipts and declared costs are not GSM accounting",
        },
    }
    return {"result": result, "records": frame, "plans": plans}
