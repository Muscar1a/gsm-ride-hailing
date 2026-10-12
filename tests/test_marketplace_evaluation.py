from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gsm_poc.core.artifacts import fingerprint, read_json
from gsm_poc.simulation.demand import DemandPlan, validate_snapshot
from gsm_poc.simulation.evaluation import evaluate_marketplace, validate_protocol

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def protocol():
    value = read_json(ROOT / "configs/week3_poc_pilot.json")
    return value | {"n_seeds": 2}


@pytest.fixture
def evaluation_plan(config):
    snapshot = validate_snapshot(read_json(ROOT / "configs/week3_snapshot.json"), config)
    policy = {
        "baseline_multiplier_x": 1.0,
        "baseline_multiplier_y": 1.0,
        "delta_price_x": 0.0,
        "delta_price_y": 0.0,
    }
    spec = {
        "model_version": "controlled-test-model",
        "source_version": "controlled-test-source",
        "snapshot_version": snapshot["snapshot_version"],
        "units": {"request_rate": "requests/hour"},
        "policy": policy,
        "policy_version": fingerprint(policy),
    }
    version = fingerprint(spec)
    rows = [
        {
            "zone_id": zone,
            "service_id": service,
            "block_start": pd.Timestamp(snapshot["horizon_start"]),
            "block_end": pd.Timestamp(snapshot["horizon_end"]),
            "block_hours": 2.0,
            "request_rate": 0.0,
            "expected_bookings": 0.0,
            "source_block_id": f"test-{zone}",
            "status": "ok",
            "support_status": "ok",
            "demand_plan_version": version,
            "snapshot_id": snapshot["snapshot_id"],
            "model_version": spec["model_version"],
            "source_version": spec["source_version"],
            "policy_version": spec["policy_version"],
            "source_kind": "synthetic",
            "evidence_level": "C",
            "demand_mode": snapshot["demand_mode"],
            "exposure_mode": snapshot["exposure_mode"],
        }
        for zone in snapshot["zone_ids"]
        for service in ("X", "Y")
    ]
    result = {
        "usable_for_simulation": True,
        "status": "ok",
        "demand_plan_version": version,
        "source_kind": "synthetic",
        "summary": {"expected_bookings": 0.0},
    }
    return DemandPlan(pd.DataFrame(rows), result, snapshot, spec)


@pytest.fixture
def evaluation_rules():
    return read_json(ROOT / "configs/week3_poc.json")


@pytest.fixture
def compensation():
    return read_json(ROOT / "configs/week3_compensation.json")


@pytest.mark.parametrize(
    "change",
    [
        {"unknown": 1},
        {"n_seeds": True},
        {"seed_start": -1},
        {"n_seeds": 101},
        {"max_seconds": np.inf},
        {"max_seconds": 601},
        {"interval_level": 1.0},
        {"max_peak_python_bytes": 0},
        {"max_idle_mean_error": np.nan},
        {"phase": "assessment", "n_seeds": 2},
        {"phase": "other"},
    ],
)
def test_protocol_rejects_invalid_or_unbounded_inputs(protocol, change):
    with pytest.raises(ValueError):
        validate_protocol(protocol | change)


def test_checked_profiles_keep_independent_pilot_and_assessment_seeds():
    pilot = validate_protocol(read_json(ROOT / "configs/week3_poc_pilot.json"))
    final = validate_protocol(read_json(ROOT / "configs/week3_poc_assessment.json"))
    assert set(range(pilot["seed_start"], pilot["seed_start"] + pilot["n_seeds"])).isdisjoint(
        range(final["seed_start"], final["seed_start"] + final["n_seeds"])
    )
    assert final["n_seeds"] == 100
    assert pilot["max_completed_mean_error"] == final["max_completed_mean_error"] == 1.2


def test_real_zero_demand_retains_unavailable_wait_and_fixed_online_hours(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
):
    original = copy.deepcopy(evaluation_plan)
    evaluated = evaluate_marketplace(
        evaluation_plan,
        evaluation_plan,
        config,
        evaluation_rules,
        compensation,
        protocol,
    )
    result = evaluated["result"]
    assert result["execution_status"] == "completed"
    assert result["attempted_jobs"] == result["succeeded_jobs"] == 9
    assert result["failed_jobs"] == 0
    assert result["status"] == "development_only"
    assert result["same_policy_identity"] is True
    assert all(row["passed"] for row in result["poisson_checks"])
    comparison = {row["metric"]: row for row in result["comparison"]}
    assert comparison["created_requests"]["delta_mean"] == 0
    assert comparison["online_hours"]["baseline_mean"] == pytest.approx(4)
    assert comparison["mean_wait_seconds"]["available_pairs"] == 0
    assert comparison["mean_wait_seconds"]["unavailable_pairs"] == 2
    assert comparison["mean_wait_seconds"]["delta_mean"] is None
    assert comparison["mean_wait_seconds"]["interval_status"] == "interval_unavailable"
    assert evaluated["controlled_records"].created_requests.eq(30).all()
    assert evaluated["controlled_records"].offered.eq(30).all()
    assert evaluated["controlled_records"].dispatch_hours.to_numpy() == pytest.approx(
        [0.025, 0.025]
    )
    accounted = evaluated["controlled_records"]
    assert (
        accounted.idle_hours + accounted.on_trip_hours + accounted.dispatch_hours
    ).to_numpy() == pytest.approx([2, 2])
    assert result["controlled_case"]["baseline_resolved_fare"] == 1
    assert result["nominal_coverage_certified"] is False
    assert result["gsm_calibration_status"] == "not_evaluated"
    assert evaluated["workload_records"].online_drivers.to_list() == [2, 20, 100]
    assert evaluated["workload_records"].online_hours.to_list() == pytest.approx([4, 40, 200])
    assert evaluated["workload_records"].peak_python_bytes.gt(0).all()
    pd.testing.assert_frame_equal(original.frame, evaluation_plan.frame)
    assert original.spec == evaluation_plan.spec and original.snapshot == evaluation_plan.snapshot


def test_failed_attempts_remain_in_denominators_and_block_publication(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
):
    def fail_simulation(*args, **kwargs):
        raise RuntimeError("Deliberate max_events budget exhausted")

    monkeypatch.setattr("gsm_poc.simulation.evaluation.simulate_marketplace", fail_simulation)
    result = evaluate_marketplace(
        evaluation_plan,
        evaluation_plan,
        config,
        evaluation_rules,
        compensation,
        protocol,
    )
    assert result["result"]["execution_status"] == "completed_with_failures"
    assert result["result"]["failed_jobs"] == 9
    assert result["result"]["comparison_publishable"] is False
    assert result["seed_records"].status.eq("budget_exceeded").all()
    assert result["seed_records"].reason.str.contains("max_events").all()
    assert all(
        row["available"] == 0 and row["attempted"] == 2
        for row in result["result"]["poisson_checks"]
    )
    assert all(
        row["available"] == 0 and row["attempted"] == 2
        for row in result["result"]["controlled_checks"]
    )
    assert all(
        row["available_pairs"] == 0 and row["unavailable_pairs"] == 2
        for row in result["result"]["comparison"]
    )


def test_total_deadline_prevents_starting_more_jobs(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
):
    monkeypatch.setattr(
        "gsm_poc.simulation.evaluation.time.perf_counter", iter(range(100)).__next__
    )

    def unexpected_simulation(*args, **kwargs):
        raise AssertionError("Expired evaluator must not launch a simulation")

    monkeypatch.setattr("gsm_poc.simulation.evaluation.simulate_marketplace", unexpected_simulation)
    result = evaluate_marketplace(
        evaluation_plan,
        evaluation_plan,
        config,
        evaluation_rules,
        compensation,
        protocol | {"max_seconds": 0.1},
    )
    assert result["result"]["failed_jobs"] == result["result"]["attempted_jobs"]
    assert result["controlled_records"].reason.str.contains("Evaluator max_seconds").all()


def test_one_failed_pair_has_no_interval_and_does_not_disappear(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
):
    from gsm_poc.simulation.marketplace import simulate_marketplace

    calls = 0

    def fail_first_target(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Deliberate target failure")
        return simulate_marketplace(*args, **kwargs)

    monkeypatch.setattr("gsm_poc.simulation.evaluation.simulate_marketplace", fail_first_target)
    evaluated = evaluate_marketplace(
        evaluation_plan,
        evaluation_plan,
        config,
        evaluation_rules,
        compensation,
        protocol,
    )
    result = evaluated["result"]
    assert result["failed_jobs"] == 1 and result["succeeded_jobs"] == 8
    assert result["execution_status"] == "completed_with_failures"
    assert result["same_policy_identity"] is None
    assert result["comparison_publishable"] is False
    completed = next(row for row in result["comparison"] if row["metric"] == "completed_trips")
    assert completed["available_pairs"] == completed["unavailable_pairs"] == 1
    assert completed["delta_mean"] == 0.0
    assert completed["delta_lower"] is None and completed["delta_upper"] is None
    assert completed["status"] == "partial"
    assert completed["interval_status"] == "interval_unavailable"
    assert all(
        row["available"] == 1 and not row["passed"]
        for row in result["poisson_checks"]
        if row["arm"] == "target"
    )


def test_unchanged_policy_identity_rejects_opposite_per_seed_errors(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
):
    from gsm_poc.simulation.evaluation import _run_record

    def inconsistent_online_hours(*args, **kwargs):
        row = _run_record(*args, **kwargs)
        if row["arm"] == "target":
            row["online_hours"] += 1 if row["seed"] == protocol["seed_start"] else -1
        return row

    monkeypatch.setattr(
        "gsm_poc.simulation.evaluation._run_record",
        inconsistent_online_hours,
    )
    evaluated = evaluate_marketplace(
        evaluation_plan,
        evaluation_plan,
        config,
        evaluation_rules,
        compensation,
        protocol | {"max_completed_mean_error": 30, "max_idle_mean_error": 2},
    )
    result = evaluated["result"]
    online = next(row for row in result["comparison"] if row["metric"] == "online_hours")
    assert online["delta_mean"] == 0.0
    assert result["failed_jobs"] == 0
    assert all(row["passed"] for row in result["controlled_checks"])
    assert all(row["passed"] for row in result["poisson_checks"])
    assert all(row["passed"] for row in result["workload_checks"])
    assert result["same_policy_identity"] is False
    assert result["all_checks_passed"] is False
    assert result["comparison_publishable"] is False


@pytest.mark.parametrize("column", ["source_block_id", "quote_sessions"])
def test_comparison_rejects_changed_block_or_quote_lineage(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
    column,
):
    if column == "quote_sessions":
        evaluation_plan.frame[column] = 50
    target = copy.deepcopy(evaluation_plan)
    target.frame[column] = "different-block" if column == "source_block_id" else 100

    def unexpected_simulation(*args, **kwargs):
        raise AssertionError("Different frozen population must not launch a comparison")

    monkeypatch.setattr("gsm_poc.simulation.evaluation.simulate_marketplace", unexpected_simulation)
    with pytest.raises(ValueError, match="blocks and quote exposure"):
        evaluate_marketplace(
            evaluation_plan,
            target,
            config,
            evaluation_rules,
            compensation,
            protocol,
        )


def test_nonfinite_controlled_money_truth_rejects_before_simulation(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
):
    compensation["baseline_fares"]["X"] = 1e308

    def unexpected_simulation(*args, **kwargs):
        raise AssertionError("Overflowing monetary truth must not launch a simulation")

    monkeypatch.setattr("gsm_poc.simulation.evaluation.simulate_marketplace", unexpected_simulation)
    with pytest.raises(ValueError, match="overflows"):
        evaluate_marketplace(
            evaluation_plan,
            evaluation_plan,
            config,
            evaluation_rules,
            compensation,
            protocol,
        )


@pytest.mark.parametrize("change", ["support", "roster", "model", "source", "baseline_policy"])
def test_rejects_unsupported_or_incompatible_comparison_before_simulating(
    config,
    evaluation_plan,
    evaluation_rules,
    compensation,
    protocol,
    monkeypatch,
    change,
):
    target = copy.deepcopy(evaluation_plan)
    if change == "support":
        target.result["usable_for_simulation"] = False
    elif change == "roster":
        target.snapshot["vehicles"][0]["driver_id"] = "different-driver"
    elif change in ("model", "source"):
        target.spec[f"{change}_version"] = "different"
    else:
        evaluation_plan.spec["policy"]["delta_price_x"] = 0.1

    def unexpected_simulation(*args, **kwargs):
        raise AssertionError("Invalid comparison must not launch a simulation")

    monkeypatch.setattr("gsm_poc.simulation.evaluation.simulate_marketplace", unexpected_simulation)
    with pytest.raises(ValueError):
        evaluate_marketplace(
            evaluation_plan,
            target,
            config,
            evaluation_rules,
            compensation,
            protocol,
        )
