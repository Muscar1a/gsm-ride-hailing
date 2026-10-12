"""Frozen, bounded checks of the fixed-online synthetic marketplace PoC."""

from __future__ import annotations

import copy
import time
import tracemalloc
from typing import Any, cast

import numpy as np
import pandas as pd
from scipy.stats import t

from gsm_poc.core.artifacts import fingerprint
from gsm_poc.core.config import Config
from gsm_poc.simulation.compensation import resolve_compensation
from gsm_poc.simulation.demand import DemandPlan, validate_snapshot
from gsm_poc.simulation.marketplace import _validate_plan, simulate_marketplace
from gsm_poc.simulation.rules import normalize_rules

METRIC_UNITS = {
    "created_requests": "requests",
    "created_x": "requests",
    "created_y": "requests",
    "completed_trips": "trips",
    "canceled_requests": "requests",
    "expired_requests": "requests",
    "open_requests_end": "requests",
    "mean_wait_seconds": "seconds",
    "p95_wait_seconds": "seconds",
    "wait_observed_requests": "picked_up_requests",
    "wait_censored_requests": "requests",
    "online_hours": "driver_hours",
    "serviceable_hours": "vehicle_hours",
    "idle_hours": "vehicle_hours",
    "dispatch_hours": "vehicle_hours",
    "pickup_hours": "vehicle_hours",
    "on_trip_hours": "vehicle_hours",
    "offered": "offers",
    "accepted": "offers",
    "rejected": "offers",
    "timed_out": "offers",
    "withdrawn": "offers",
    "pending_end": "offers",
    "acceptance_denominator": "resolved_response_events",
    "acceptance_rate": "fraction",
    "total_driver_pay": "SYNTHETIC_UNIT",
    "pay_per_presence_hour": "SYNTHETIC_UNIT/presence_hour",
}


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version",
        "phase",
        "seed_start",
        "n_seeds",
        "max_seconds",
        "interval_level",
        "max_completed_mean_error",
        "max_idle_mean_error",
        "max_poisson_standardized_error",
        "max_workload_seconds",
        "max_peak_python_bytes",
    }
    if not isinstance(protocol, dict) or set(protocol) != fields:
        raise ValueError("Marketplace protocol has missing or unknown fields")
    if (
        type(protocol["schema_version"]) is not int
        or protocol["schema_version"] != 1
        or protocol["phase"] not in ("pilot", "assessment")
    ):
        raise ValueError("Unsupported marketplace protocol version or phase")
    for key in ("seed_start", "n_seeds", "max_peak_python_bytes"):
        if type(protocol[key]) is not int or protocol[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if protocol["seed_start"] + protocol["n_seeds"] > 2**32 or not 1 <= protocol["n_seeds"] <= 100:
        raise ValueError("Marketplace seed range/count exceeds the bounded profile")
    if protocol["phase"] == "assessment" and protocol["n_seeds"] < 50:
        raise ValueError("Assessment requires at least 50 independent seeds")
    for key in fields - {
        "schema_version",
        "phase",
        "seed_start",
        "n_seeds",
        "max_peak_python_bytes",
    }:
        value = protocol[key]
        if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be positive and finite")
    if not 0 < protocol["interval_level"] < 1:
        raise ValueError("interval_level must lie within (0, 1)")
    if protocol["max_seconds"] > 600 or protocol["max_workload_seconds"] > 60:
        raise ValueError("Protocol runtime budgets exceed the bounded profile")
    return copy.deepcopy(protocol)


def _roster_plan(plan: DemandPlan, config: Config, count: int, label: str) -> DemandPlan:
    copied = copy.deepcopy(plan)
    template = copied.snapshot["vehicles"][0]
    copied.snapshot["snapshot_id"] = label
    copied.snapshot["vehicles"] = [
        template
        | {
            "vehicle_id": f"{label}-vehicle-{index}",
            "driver_id": f"{label}-driver-{index}",
            "shift_id": f"{label}-presence-{index}",
            "zone_id": copied.snapshot["zone_ids"][index % len(copied.snapshot["zone_ids"])],
            "state": "idle",
            "eligible_services": ["X", "Y"],
            "shift_start": copied.snapshot["horizon_start"],
            "shift_end": copied.snapshot["horizon_end"],
        }
        for index in range(count)
    ]
    copied.snapshot = validate_snapshot(copied.snapshot, config)
    copied.spec["snapshot_version"] = copied.snapshot["snapshot_version"]
    copied.result["demand_plan_version"] = fingerprint(copied.spec)
    copied.frame["demand_plan_version"] = copied.result["demand_plan_version"]
    copied.frame["snapshot_id"] = label
    return copied


def _finite(value: Any, name: str, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not np.isfinite(value):
        raise RuntimeError(f"Simulation metric {name} is missing or nonfinite")
    return float(value)


def _run_record(
    plan: DemandPlan,
    config: Config,
    rules: dict[str, Any],
    compensation: dict[str, Any],
    seed: int,
    arm: str,
    deadline: float,
    prescribed: pd.DataFrame | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"seed": seed, "arm": arm, "status": "failed", "reason": None}
    started = time.perf_counter()
    remaining = deadline - started
    if remaining <= 0:
        return record | {
            "status": "budget_exceeded",
            "reason": "Evaluator max_seconds exhausted",
            "wall_seconds": 0.0,
        }
    bounded_rules = rules | {"max_seconds": min(rules["max_seconds"], remaining)}
    try:
        simulation = simulate_marketplace(
            plan,
            bounded_rules,
            config,
            seed,
            prescribed,
            compensation=compensation,
        )
        summary, offers = simulation.result["summary"], simulation.result["offers"]
        earnings = simulation.result["earnings"]["summary"]
        for key in METRIC_UNITS:
            if key in ("created_x", "created_y"):
                service = key[-1].upper()
                value = int(simulation.requests.service_id.eq(service).sum())
            else:
                value = (earnings if key in earnings else offers if key in offers else summary).get(
                    key
                )
            record[key] = _finite(
                value,
                key,
                optional=key
                in {
                    "mean_wait_seconds",
                    "p95_wait_seconds",
                    "acceptance_rate",
                    "pay_per_presence_hour",
                },
            )
        record["budget_work_units"] = simulation.result["budget_work_units"]
        for zone in plan.snapshot["zone_ids"]:
            for service in ("X", "Y"):
                record[f"created_{zone}_{service}"] = int(
                    (
                        simulation.requests.origin_zone_id.eq(zone)
                        & simulation.requests.service_id.eq(service)
                    ).sum()
                )
        record["request_events"] = len(simulation.request_events)
        record["offer_events"] = (
            len(simulation.offer_events) if simulation.offer_events is not None else 0
        )
        record["status"] = "succeeded"
    except (ValueError, RuntimeError, OverflowError) as exc:
        record.update(
            status="budget_exceeded" if "budget" in str(exc).lower() else "failed", reason=str(exc)
        )
    record["wall_seconds"] = time.perf_counter() - started
    return record


def _paired_summary(records: pd.DataFrame, protocol: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = records[records.arm.eq("baseline")].set_index("seed")
    target = records[records.arm.eq("target")].set_index("seed")
    paired = baseline.status.eq("succeeded") & target.status.eq("succeeded")
    rows = []
    for key, unit in METRIC_UNITS.items():
        left = pd.to_numeric(
            baseline.get(key, pd.Series(index=baseline.index, dtype=float)), errors="coerce"
        )
        right = pd.to_numeric(
            target.get(key, pd.Series(index=target.index, dtype=float)), errors="coerce"
        )
        valid = paired & np.isfinite(left) & np.isfinite(right)
        differences = right[valid] - left[valid]
        count = len(differences)
        mean = float(differences.mean()) if count else None
        half_width = (
            float(
                t.ppf((1 + protocol["interval_level"]) / 2, count - 1)
                * differences.std(ddof=1)
                / np.sqrt(count)
            )
            if count > 1
            else None
        )
        rows.append(
            {
                "metric": key,
                "unit": unit,
                "attempted_pairs": protocol["n_seeds"],
                "available_pairs": count,
                "unavailable_pairs": protocol["n_seeds"] - count,
                "baseline_mean": float(left[valid].mean()) if count else None,
                "target_mean": float(right[valid].mean()) if count else None,
                "delta_mean": mean,
                "delta_lower": mean - half_width
                if mean is not None and half_width is not None
                else None,
                "delta_upper": mean + half_width
                if mean is not None and half_width is not None
                else None,
                "status": "ok"
                if count == protocol["n_seeds"]
                else "partial"
                if count
                else "unavailable",
                "interval_status": "monte_carlo_conditional"
                if half_width is not None
                else "interval_unavailable",
                "interval_target": (
                    "mean paired trajectory difference conditional on fixed fitted demand and rules"
                ),
            }
        )
    return rows


def _poisson_checks(
    records: pd.DataFrame, plans: dict[str, DemandPlan], protocol: dict[str, Any]
) -> list[dict[str, Any]]:
    checks = []
    for arm, plan in plans.items():
        group = records[records.arm.eq(arm)]
        for key, blocks in plan.frame.groupby(["zone_id", "service_id"]):
            zone, service = cast(tuple[int, str], key)
            expected = float(blocks.expected_bookings.sum())
            column = f"created_{zone}_{service}"
            observed = pd.to_numeric(
                group.get(column, pd.Series(index=group.index, dtype=float)), errors="coerce"
            )
            valid = group.status.eq("succeeded") & np.isfinite(observed)
            count = int(valid.sum())
            mean = float(observed[valid].mean()) if count else None
            error = mean - expected if mean is not None else None
            standardized = error / np.sqrt(expected / count) if expected > 0 and count else None
            passed = count == protocol["n_seeds"] and (
                abs(standardized) <= protocol["max_poisson_standardized_error"]
                if standardized is not None
                else mean == expected == 0
            )
            checks.append(
                {
                    "arm": arm,
                    "zone_id": int(zone),
                    "service_id": service,
                    "unit": "requests/trajectory",
                    "expected": expected,
                    "observed_mean": mean,
                    "mean_error": error,
                    "standardized_error": standardized,
                    "attempted": protocol["n_seeds"],
                    "available": count,
                    "passed": bool(passed),
                }
            )
    return checks


def evaluate_marketplace(
    baseline_plan: DemandPlan,
    target_plan: DemandPlan,
    config: Config,
    rules: dict[str, Any],
    compensation: dict[str, Any],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate scoped synthetic operations; never certify GSM or full-chain causal CIs."""
    protocol = validate_protocol(protocol)
    started = time.perf_counter()
    deadline = started + protocol["max_seconds"]
    validated_frames = []
    for plan in (baseline_plan, target_plan):
        validated_frames.append(_validate_plan(plan, config)[0])
        normalize_rules(rules, plan.snapshot)
        resolve_compensation(compensation, plan.spec["policy"])
    if rules["schema_version"] != 3:
        raise ValueError("Marketplace assessment requires fixed-online version-3 offer rules")
    if (
        baseline_plan.snapshot != target_plan.snapshot
        or baseline_plan.spec["model_version"] != target_plan.spec["model_version"]
        or baseline_plan.spec["source_version"] != target_plan.spec["source_version"]
    ):
        raise ValueError("Comparison requires the same frozen roster/horizon, model and source")
    lineage_columns = [
        "zone_id",
        "service_id",
        "block_start",
        "block_end",
        "block_hours",
        "source_block_id",
    ]
    lineage_columns.extend(
        key
        for key in ("quote_sessions", "model_run_id")
        if key in baseline_plan.frame or key in target_plan.frame
    )
    if any(key not in frame for frame in validated_frames for key in lineage_columns) or not (
        validated_frames[0][lineage_columns].equals(validated_frames[1][lineage_columns])
    ):
        raise ValueError("Comparison requires the same frozen demand blocks and quote exposure")
    hours = (
        pd.Timestamp(baseline_plan.snapshot["horizon_end"])
        - pd.Timestamp(baseline_plan.snapshot["horizon_start"])
    ).total_seconds() / 3600
    if hours != 2 or not 1 <= len(baseline_plan.snapshot["vehicles"]) <= 100:
        raise ValueError("Frozen evaluation is scoped to a two-hour, 1–100-driver PoC")
    policy = baseline_plan.spec["policy"]
    if any(policy[f"delta_price_{service}"] != 0 for service in ("x", "y")) or any(
        policy[f"baseline_multiplier_{service}"]
        != target_plan.spec["policy"][f"baseline_multiplier_{service}"]
        for service in ("x", "y")
    ):
        raise ValueError("Baseline must be unchanged pricing with shared baseline fare multipliers")
    fare = resolve_compensation(compensation, policy)["effective_fares"]["X"]
    if not np.isfinite(15 * fare) or not np.isfinite(protocol["max_completed_mean_error"] * fare):
        raise ValueError("Controlled fare truth/tolerance overflows its finite units")
    if rules["max_requests"] > 10000 or rules["max_events"] > 500000:
        raise ValueError("Input trajectory workload exceeds the bounded assessment profile")
    controlled_plan = _roster_plan(baseline_plan, config, 1, "controlled-one-driver")
    controlled_rules = rules | {
        "rules_id": "controlled-separated-offers-v1",
        "acceptance_probability": 0.5,
        "response_seconds": 3,
        "response_timeout_seconds": 10,
        "max_offer_attempts": 1,
        "max_wait_seconds": 120,
        "max_requests": 30,
        "max_events": 10000,
        "travel_times": [
            row
            | {
                "pickup_seconds": 0,
                "trip_seconds": 60,
                "destination_probability": float(
                    row["origin_zone_id"] == row["destination_zone_id"]
                ),
            }
            for row in rules["travel_times"]
        ],
    }
    zone = controlled_plan.snapshot["zone_ids"][0]
    requests = pd.DataFrame(
        [
            {
                "request_id": f"controlled-{index}",
                "created_at": cast(
                    pd.Timestamp,
                    (
                        pd.Timestamp(controlled_plan.snapshot["horizon_start"])
                        + pd.Timedelta(seconds=30 + 240 * index)
                    ),
                ).isoformat(),
                "origin_zone_id": zone,
                "destination_zone_id": zone,
                "service_id": "X",
            }
            for index in range(30)
        ]
    )
    seed_rows, controlled_rows = [], []
    for seed in range(protocol["seed_start"], protocol["seed_start"] + protocol["n_seeds"]):
        for arm, plan in (("baseline", baseline_plan), ("target", target_plan)):
            seed_rows.append(_run_record(plan, config, rules, compensation, seed, arm, deadline))
        controlled_rows.append(
            _run_record(
                controlled_plan,
                config,
                controlled_rules,
                compensation,
                seed,
                "controlled",
                deadline,
                requests,
            )
        )
    seed_records = pd.DataFrame(seed_rows)
    controlled_records = pd.DataFrame(controlled_rows)
    truths = {
        "created_requests": (30.0, 1e-12),
        "offered": (30.0, 1e-12),
        "completed_trips": (15.0, protocol["max_completed_mean_error"]),
        "accepted": (15.0, protocol["max_completed_mean_error"]),
        "total_driver_pay": (15.0 * fare, protocol["max_completed_mean_error"] * fare),
        "dispatch_hours": (0.025, 1e-12),
        "on_trip_hours": (0.25, protocol["max_idle_mean_error"]),
        "idle_hours": (1.725, protocol["max_idle_mean_error"]),
        "online_hours": (2.0, 1e-12),
    }
    controlled_checks = []
    for metric, (truth, tolerance) in truths.items():
        values = pd.to_numeric(
            controlled_records.get(metric, pd.Series(index=controlled_records.index, dtype=float)),
            errors="coerce",
        )
        valid = controlled_records.status.eq("succeeded") & np.isfinite(values)
        count = int(valid.sum())
        mean = float(values[valid].mean()) if count else None
        error = mean - truth if mean is not None else None
        controlled_checks.append(
            {
                "metric": metric,
                "unit": METRIC_UNITS[metric],
                "truth": truth,
                "observed_mean": mean,
                "mean_error": error,
                "max_absolute_error": tolerance,
                "attempted": protocol["n_seeds"],
                "available": count,
                "passed": count == protocol["n_seeds"]
                and error is not None
                and abs(error) <= tolerance,
            }
        )
    workload_rows = []
    for count in (2, 20, 100):
        workload_plan = _roster_plan(target_plan, config, count, f"workload-{count}-drivers")
        workload_rules = rules | {
            "max_events": 500000,
            "max_seconds": min(rules["max_seconds"], protocol["max_workload_seconds"]),
        }
        tracemalloc.start()
        try:
            row = _run_record(
                workload_plan,
                config,
                workload_rules,
                compensation,
                protocol["seed_start"],
                "workload",
                deadline,
            )
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        row.update(
            online_drivers=count,
            peak_python_bytes=peak,
            max_events=500000,
            max_requests=rules["max_requests"],
            max_seconds=workload_rules["max_seconds"],
        )
        row["passed"] = (
            row["status"] == "succeeded"
            and row["wall_seconds"] <= protocol["max_workload_seconds"]
            and peak <= protocol["max_peak_python_bytes"]
        )
        workload_rows.append(row)
    workload_records = pd.DataFrame(workload_rows)
    poisson_checks = _poisson_checks(
        seed_records, {"baseline": baseline_plan, "target": target_plan}, protocol
    )
    frames = (seed_records, controlled_records, workload_records)
    failed = sum(int(frame.status.ne("succeeded").sum()) for frame in frames)
    passed = not failed and all(
        row["passed"] for row in controlled_checks + poisson_checks + workload_rows
    )
    summary = _paired_summary(seed_records, protocol)
    same_policy = all(
        baseline_plan.spec["policy"][key] == target_plan.spec["policy"][key]
        for key in (
            "baseline_multiplier_x",
            "baseline_multiplier_y",
            "delta_price_x",
            "delta_price_y",
        )
    )
    paired_baseline = seed_records[seed_records.arm.eq("baseline")].set_index("seed")
    paired_target = seed_records[seed_records.arm.eq("target")].set_index("seed")
    identity = (
        all(
            (
                paired_baseline[key].eq(paired_target[key])
                | (paired_baseline[key].isna() & paired_target[key].isna())
            ).all()
            for key in METRIC_UNITS
        )
        if same_policy and not failed
        else None
    )
    if same_policy and not identity:
        passed = False
    return {
        "seed_records": seed_records,
        "controlled_records": controlled_records,
        "workload_records": workload_records,
        "result": {
            "schema_version": 1,
            "status": "development_only"
            if protocol["phase"] == "pilot"
            else "controlled_checks_passed"
            if passed
            else "controlled_checks_failed",
            "execution_status": "completed" if not failed else "completed_with_failures",
            "all_checks_passed": bool(passed),
            "attempted_jobs": 3 * protocol["n_seeds"] + 3,
            "succeeded_jobs": 3 * protocol["n_seeds"] + 3 - failed,
            "failed_jobs": failed,
            "elapsed_seconds": time.perf_counter() - started,
            "protocol": protocol,
            "protocol_version": fingerprint(protocol),
            "source_kind": "synthetic",
            "evidence_level": "C",
            "calibration_status": "not_calibrated",
            "model_version": baseline_plan.spec["model_version"],
            "source_version": baseline_plan.spec["source_version"],
            "baseline_demand_version": baseline_plan.result["demand_plan_version"],
            "target_demand_version": target_plan.result["demand_plan_version"],
            "snapshot_version": baseline_plan.snapshot["snapshot_version"],
            "rules_version": fingerprint(rules),
            "compensation_version": fingerprint(compensation),
            "scope": {
                key: baseline_plan.snapshot[key]
                for key in (
                    "zone_ids",
                    "service_ids",
                    "horizon_start",
                    "horizon_end",
                    "demand_mode",
                    "exposure_mode",
                )
            }
            | {
                "online_drivers": len(baseline_plan.snapshot["vehicles"]),
                "population": "fixed declared online roster, shared X/Y",
            },
            "comparison": summary,
            "comparison_publishable": bool(passed),
            "same_policy_identity": identity,
            "poisson_checks": poisson_checks,
            "controlled_checks": controlled_checks,
            "controlled_case": {
                "drivers": 1,
                "requests": 30,
                "service_id": "X",
                "probability": 0.5,
                "response_seconds": 3,
                "pickup_seconds": 0,
                "trip_seconds": 60,
                "horizon_hours": 2,
                "baseline_resolved_fare": fare,
                "truth_scope": "known separated-offer synthetic mechanism",
            },
            "workload_checks": workload_rows,
            "memory_measurement": (
                "tracemalloc peak Python allocations during each cold trajectory; not process RSS"
            ),
            "interval_scope": (
                "individual Student-t intervals of paired Monte Carlo means across independent "
                "seeds; fixed fitted demand/rules, not causal or full-chain intervals"
            ),
            "metric_population": (
                "new requests and response/completion events in the common observation horizon; "
                "idle and earnings include zero-trip online drivers"
            ),
            "wait_denominator": (
                "pickups observed in each run; comparison averages run-level conditional wait means"
            ),
            "acceptance_denominator": (
                "accepted + rejected + timed_out; withdrawals/pending excluded"
            ),
            "nominal_coverage_certified": False,
            "labor_elasticity_status": "not_identified",
            "gsm_calibration_status": "not_evaluated",
            "profit_status": "not_evaluated",
            "roi_status": "not_evaluated",
        },
    }
