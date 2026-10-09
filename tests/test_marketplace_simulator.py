from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gsm_poc.artifacts import (
    completed_run,
    fingerprint,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.cli import main
from gsm_poc.demand import DemandPlan, validate_snapshot
from gsm_poc.marketplace_simulator import simulate_marketplace
from gsm_poc.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rules():
    value = read_json(ROOT / "configs/week3_simulation.json")
    value["schema_version"] = 1
    value.pop("max_wait_seconds", None)
    value.pop("cancel_policy", None)
    return value


@pytest.fixture
def market_plan(config):
    snapshot = validate_snapshot(read_json(ROOT / "configs/week3_snapshot.json"), config)
    spec = {
        "schema_version": 1,
        "model_version": "model-v1",
        "source_version": "source-v1",
        "snapshot_version": snapshot["snapshot_version"],
        "units": {"request_rate": "requests/hour"},
        "policy": {"delta_price_x": 0.0},
    }
    spec["policy_version"] = fingerprint(spec["policy"])
    version = fingerprint(spec)
    rows = []
    for zone in (161, 162):
        for service, rate in (("X", 2.0), ("Y", 1.0)):
            rows.append(
                {
                    "zone_id": zone,
                    "service_id": service,
                    "block_start": pd.Timestamp(snapshot["horizon_start"]),
                    "block_end": pd.Timestamp(snapshot["horizon_end"]),
                    "block_hours": 2.0,
                    "request_rate": rate,
                    "expected_bookings": rate * 2,
                    "source_block_id": f"block-{zone}",
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
            )
    result = {
        "schema_version": 1,
        "usable_for_simulation": True,
        "status": "ok",
        "demand_plan_version": version,
        "source_kind": "synthetic",
        "summary": {"expected_bookings": sum(r["expected_bookings"] for r in rows)},
    }
    return DemandPlan(pd.DataFrame(rows), result, snapshot, spec)


@pytest.fixture
def prescribed():
    return pd.read_csv(ROOT / "configs/week3_requests.csv")


def _refresh_snapshot(plan, config):
    plan.snapshot = validate_snapshot(plan.snapshot, config)
    plan.spec["snapshot_version"] = plan.snapshot["snapshot_version"]
    version = fingerprint(plan.spec)
    plan.result["demand_plan_version"] = version
    plan.frame["demand_plan_version"] = version


def _zero_demand(plan):
    plan.frame["request_rate"] = 0.0
    plan.frame["expected_bookings"] = 0.0
    plan.result["summary"]["expected_bookings"] = 0.0


def test_two_vehicle_timeline_has_known_wait_and_time_accounting(
    config, market_plan, rules, prescribed
):
    original = copy.deepcopy(market_plan)
    simulation = simulate_marketplace(market_plan, rules, config, 42, prescribed)
    requests = simulation.requests.set_index("request_id")
    assert requests.vehicle_id.to_dict() == {
        "request-01": "vehicle-1",
        "request-02": "vehicle-2",
        "request-03": "vehicle-1",
    }
    assert requests.wait_seconds.to_dict() == {
        "request-01": 60.0,
        "request-02": 60.0,
        "request-03": 660.0,
    }
    assert pd.Timestamp(requests.loc["request-03", "completed_at"]) == pd.Timestamp(
        "2024-01-26T08:27:00-05:00"
    )
    summary = simulation.result["summary"]
    assert summary["created_requests"] == summary["completed_trips"] == 3
    assert summary["open_requests_end"] == 0
    assert summary["total_vehicle_hours"] == summary["serviceable_hours"] == pytest.approx(4)
    assert summary["idle_hours"] == pytest.approx(4 - 2280 / 3600)
    assert summary["mean_wait_seconds"] == pytest.approx(260)
    assert summary["p95_wait_seconds"] == pytest.approx(600)
    for _, group in simulation.vehicle_intervals.groupby("vehicle_id"):
        assert group.duration_seconds.sum() == pytest.approx(7200)
        assert (
            pd.to_datetime(group.end.iloc[:-1]).to_list()
            == pd.to_datetime(group.start.iloc[1:]).to_list()
        )
    for _, group in simulation.request_events.groupby("request_id"):
        assert group.state.to_list() == [
            "created",
            "queued",
            "assigned",
            "pickup",
            "on_trip",
            "completed",
        ]
    assert simulation.spec["arrival_mode"] == "prescribed"
    pd.testing.assert_frame_equal(original.frame, market_plan.frame)
    assert original.snapshot == market_plan.snapshot
    pd.testing.assert_frame_equal(prescribed, pd.read_csv(ROOT / "configs/week3_requests.csv"))


def test_zero_supply_preserves_open_requests_without_canceling(
    config, market_plan, rules, prescribed
):
    market_plan.snapshot["vehicles"] = []
    _refresh_snapshot(market_plan, config)
    simulation = simulate_marketplace(market_plan, rules, config, 42, prescribed)
    summary = simulation.result["summary"]
    assert summary["created_requests"] == summary["open_requests_end"] == 3
    assert (
        summary["completed_trips"]
        == summary["canceled_requests"]
        == summary["expired_requests"]
        == 0
    )
    assert summary["serviceable_hours"] == 0
    assert summary["mean_wait_seconds"] is None
    assert simulation.requests.wait_censored.all()
    assert simulation.result["wait_status"] == "unavailable_no_pickups"
    assert simulation.vehicle_intervals.empty
    assert len(simulation.end_snapshot["open_requests"]) == 3


def test_zero_demand_is_idle_and_no_wait_is_not_reported_as_zero(config, market_plan, rules):
    _zero_demand(market_plan)
    simulation = simulate_marketplace(market_plan, rules, config, 42)
    assert simulation.requests.empty and simulation.request_events.empty
    assert simulation.result["summary"]["created_requests"] == 0
    assert simulation.result["summary"]["idle_hours"] == pytest.approx(4)
    assert simulation.result["summary"]["mean_wait_seconds"] is None


def test_shared_roster_never_assigns_same_vehicle_to_overlapping_services(
    config, market_plan, rules, prescribed
):
    market_plan.snapshot["vehicles"] = market_plan.snapshot["vehicles"][:1]
    _refresh_snapshot(market_plan, config)
    simulation = simulate_marketplace(market_plan, rules, config, 42, prescribed)
    assert simulation.result["summary"]["total_vehicle_hours"] == pytest.approx(2)
    requests = simulation.requests
    assert requests.vehicle_id.eq("vehicle-1").all()
    assigned, completed = (
        pd.to_datetime(requests.assigned_at),
        pd.to_datetime(requests.completed_at),
    )
    assert (
        assigned.iloc[1:].reset_index(drop=True) >= completed.iloc[:-1].reset_index(drop=True)
    ).all()


@pytest.mark.parametrize("state", ["pickup", "on_trip"])
def test_unfinished_trip_is_censored_with_busy_vehicle_and_remaining_phase(
    config, market_plan, rules, state
):
    for vehicle in market_plan.snapshot["vehicles"]:
        vehicle["shift_end"] = "2024-01-26T11:00:00-05:00"
    _refresh_snapshot(market_plan, config)
    minute = 59 if state == "pickup" else 58
    requests = pd.DataFrame(
        [
            {
                "request_id": "late",
                "created_at": f"2024-01-26T09:{minute}:30-05:00",
                "origin_zone_id": 161,
                "destination_zone_id": 162,
                "service_id": "X",
            }
        ]
    )
    simulation = simulate_marketplace(market_plan, rules, config, 42, requests)
    assert simulation.requests.state.to_list() == [state]
    assert simulation.requests.completion_censored.all()
    assert simulation.requests.wait_censored.to_list() == [state == "pickup"]
    assert simulation.result["summary"]["open_requests_end"] == 1
    active = next(v for v in simulation.end_snapshot["vehicles"] if v["active_request_id"])
    assert active["state"] == ("to_pickup" if state == "pickup" else "on_trip")
    assert active["remaining_phase_seconds"] == pytest.approx(30 if state == "pickup" else 870)
    assert simulation.end_snapshot["open_requests"][0]["request_id"] == "late"


def test_completion_at_horizon_end_is_counted_but_new_arrival_at_end_is_rejected(
    config, market_plan, rules
):
    requests = pd.DataFrame(
        [
            {
                "request_id": "last",
                "created_at": "2024-01-26T09:49:00-05:00",
                "origin_zone_id": 161,
                "destination_zone_id": 161,
                "service_id": "X",
            }
        ]
    )
    simulation = simulate_marketplace(market_plan, rules, config, 42, requests)
    assert simulation.result["summary"]["completed_trips"] == 1
    assert simulation.end_snapshot["vehicles"][0]["state"] == "offline"
    requests.loc[0, "created_at"] = "2024-01-26T10:00:00-05:00"
    with pytest.raises(ValueError, match="timestamp"):
        simulate_marketplace(market_plan, rules, config, 42, requests)


def test_shift_start_end_and_static_soc_preserve_fixed_admission(
    config, market_plan, rules, prescribed
):
    vehicle = market_plan.snapshot["vehicles"][0]
    vehicle.update(
        state="offline",
        shift_start="2024-01-26T08:10:00-05:00",
        shift_end="2024-01-26T08:30:00-05:00",
    )
    market_plan.snapshot["vehicles"][1]["soc"] = 0.05
    _refresh_snapshot(market_plan, config)
    simulation = simulate_marketplace(market_plan, rules, config, 42, prescribed)
    summary = simulation.result["summary"]
    assert summary["serviceable_hours"] == pytest.approx(20 / 60)
    assert summary["ineligible_hours"] == pytest.approx(2)
    assert summary["offline_hours"] == pytest.approx(100 / 60)
    assert summary["completed_trips"] == 1
    assert summary["open_requests_end"] == 2
    assert pd.Timestamp(simulation.requests.iloc[0].assigned_at) == pd.Timestamp(
        "2024-01-26T08:10:00-05:00"
    )
    assert simulation.end_snapshot["vehicles"][1]["soc"] == 0.05


@pytest.mark.parametrize("reason", ["service", "radius", "offline", "shift_end"])
def test_ineligible_vehicle_does_not_receive_request(
    config, market_plan, rules, prescribed, reason
):
    requests = prescribed.iloc[:1]
    for vehicle in market_plan.snapshot["vehicles"]:
        if reason == "service":
            vehicle["eligible_services"] = ["Y"]
        elif reason == "radius":
            rules["max_pickup_seconds"] = 0
        elif reason == "offline":
            vehicle["state"] = "offline"
        else:
            vehicle["shift_end"] = "2024-01-26T08:05:00-05:00"
    _refresh_snapshot(market_plan, config)
    simulation = simulate_marketplace(market_plan, rules, config, 42, requests)
    assert simulation.requests.state.to_list() == ["queued"]
    assert simulation.result["summary"]["completed_trips"] == 0


def test_poisson_replay_is_deterministic_and_input_order_independent(config, market_plan, rules):
    first = simulate_marketplace(market_plan, rules, config, 42)
    market_plan.frame = market_plan.frame.sample(frac=1, random_state=1)
    rules["travel_times"].reverse()
    market_plan.snapshot["vehicles"].reverse()
    _refresh_snapshot(market_plan, config)
    second = simulate_marketplace(market_plan, rules, config, 42)
    pd.testing.assert_frame_equal(first.requests, second.requests)
    pd.testing.assert_frame_equal(first.request_events, second.request_events)
    pd.testing.assert_frame_equal(first.vehicle_intervals, second.vehicle_intervals)
    assert first.spec["request_version"] == second.spec["request_version"]
    different = simulate_marketplace(market_plan, rules, config, 43)
    assert first.spec["request_version"] != different.spec["request_version"]


def test_zero_pickup_duration_and_simultaneous_arrivals_have_stable_tie_breaks(
    config, market_plan, rules, prescribed
):
    for row in rules["travel_times"]:
        row["pickup_seconds"] = 0
    simultaneous = prescribed.iloc[:2].copy()
    simultaneous["origin_zone_id"] = 161
    simulation = simulate_marketplace(market_plan, rules, config, 42, simultaneous.iloc[::-1])
    assert simulation.requests.vehicle_id.to_list() == ["vehicle-1", "vehicle-2"]
    assert simulation.requests.wait_seconds.eq(0).all()
    assert simulation.result["summary"]["pickup_hours"] == 0


@pytest.mark.parametrize(
    "failure",
    [
        "gate",
        "negative",
        "nan",
        "units",
        "version",
        "snapshot",
        "support",
        "duplicate",
        "gap",
        "rate_count",
    ],
)
def test_invalid_demand_is_rejected_before_simulation(config, market_plan, rules, failure):
    if failure == "gate":
        market_plan.result["usable_for_simulation"] = False
    elif failure == "negative":
        market_plan.frame.loc[0, "request_rate"] = -1.0
    elif failure == "nan":
        market_plan.frame.loc[0, "request_rate"] = np.nan
    elif failure == "units":
        market_plan.spec["units"]["request_rate"] = "requests/minute"
    elif failure == "version":
        market_plan.frame.loc[0, "policy_version"] = "different"
    elif failure == "snapshot":
        market_plan.snapshot["vehicles"][0]["soc"] = 0.7
    elif failure == "support":
        market_plan.frame.loc[0, "support_status"] = "insufficient_support"
    elif failure == "duplicate":
        market_plan.frame = pd.concat([market_plan.frame, market_plan.frame.iloc[:1]])
    elif failure == "gap":
        market_plan.frame = market_plan.frame.iloc[1:]
    else:
        market_plan.frame.loc[0, "expected_bookings"] += 1
    with pytest.raises(ValueError):
        simulate_marketplace(market_plan, rules, config, 42)


@pytest.mark.parametrize(
    "failure",
    [
        "matrix_gap",
        "duplicate",
        "probability",
        "nan",
        "negative_trip",
        "unknown",
        "unbounded",
        "mode",
    ],
)
def test_invalid_operational_rules_are_rejected(config, market_plan, rules, failure):
    if failure == "matrix_gap":
        rules["travel_times"].pop()
    elif failure == "duplicate":
        rules["travel_times"].append(copy.deepcopy(rules["travel_times"][0]))
    elif failure == "probability":
        rules["travel_times"][0]["destination_probability"] = 0.8
    elif failure == "nan":
        rules["travel_times"][0]["pickup_seconds"] = float("nan")
    elif failure == "negative_trip":
        rules["travel_times"][0]["trip_seconds"] = -1
    elif failure == "unknown":
        rules["typo"] = 1
    elif failure == "unbounded":
        rules["max_events"] = 0
    else:
        rules["boundary_rule"] = "open_cluster"
    with pytest.raises(ValueError):
        simulate_marketplace(market_plan, rules, config, 42)


@pytest.mark.parametrize("limit", ["max_requests", "max_events", "max_seconds"])
def test_budget_exhaustion_is_a_failure_without_success_shaped_results(
    config, market_plan, rules, prescribed, limit
):
    rules[limit] = 1e-12 if limit == "max_seconds" else 1
    with pytest.raises(RuntimeError, match=limit):
        simulate_marketplace(market_plan, rules, config, 42, prescribed)


@pytest.mark.parametrize(
    "failure", ["duplicate", "naive", "outside", "zone", "service", "missing", "unknown"]
)
def test_prescribed_request_contract_rejects_invalid_inputs(
    config, market_plan, rules, prescribed, failure
):
    if failure == "duplicate":
        prescribed.loc[1, "request_id"] = prescribed.loc[0, "request_id"]
    elif failure == "naive":
        prescribed.loc[0, "created_at"] = "2024-01-26T08:00:00"
    elif failure == "outside":
        prescribed.loc[0, "created_at"] = "2024-01-26T07:59:59-05:00"
    elif failure == "zone":
        prescribed.loc[0, "destination_zone_id"] = 999
    elif failure == "service":
        prescribed.loc[0, "service_id"] = "NONE"
    elif failure == "missing":
        prescribed.loc[0, "request_id"] = None
    else:
        prescribed["price_multiplier"] = 1.1
    with pytest.raises(ValueError):
        simulate_marketplace(market_plan, rules, config, 42, prescribed)


def test_price_policy_is_not_applied_again_inside_simulator(config, market_plan, rules):
    baseline = simulate_marketplace(market_plan, rules, config, 42)
    market_plan.spec["policy"]["delta_price_x"] = 0.1
    market_plan.spec["policy_version"] = fingerprint(market_plan.spec["policy"])
    market_plan.frame["policy_version"] = market_plan.spec["policy_version"]
    _refresh_snapshot(market_plan, config)
    # Only metadata changes. The rates remain the authoritative input to the simulator.
    target = simulate_marketplace(market_plan, rules, config, 42)
    pd.testing.assert_frame_equal(baseline.requests, target.requests)
    pd.testing.assert_frame_equal(baseline.vehicle_intervals, target.vehicle_intervals)


def test_rate_changes_use_common_arrival_and_od_streams(config, market_plan, rules):
    baseline = simulate_marketplace(market_plan, rules, config, 42)
    market_plan.frame["request_rate"] *= 2
    market_plan.frame["expected_bookings"] *= 2
    market_plan.result["summary"]["expected_bookings"] *= 2
    target = simulate_marketplace(market_plan, rules, config, 42)
    common = baseline.requests.merge(
        target.requests, on="request_id", suffixes=("_baseline", "_target"), validate="one_to_one"
    )
    assert len(common) == len(baseline.requests) > 0
    assert common.destination_zone_id_baseline.equals(common.destination_zone_id_target)
    start = pd.Timestamp(market_plan.snapshot["horizon_start"])
    baseline_time = (
        pd.to_datetime(common.created_at_baseline, format="ISO8601") - start
    ).dt.total_seconds()
    target_time = (
        pd.to_datetime(common.created_at_target, format="ISO8601") - start
    ).dt.total_seconds()
    assert target_time.to_numpy() == pytest.approx(baseline_time.to_numpy() / 2, abs=1e-6)


@pytest.fixture
def demand_run(config, market_plan):
    # A completed handoff fixture exercises integrity gates without refitting models.
    pipeline = Pipeline(config, "demand-source")
    with pipeline.run.stage("prepare_demand", {"fixture": True}):
        paths = []
        frame_path = pipeline.run.path / "demand_plan.parquet"
        write_frame(frame_path, market_plan.frame)
        paths.append(frame_path)
        for name, value in (
            ("demand_result.json", market_plan.result),
            ("demand_spec.json", market_plan.spec),
            ("baseline_snapshot.json", market_plan.snapshot),
        ):
            path = pipeline.run.path / name
            write_json(path, value)
            paths.append(path)
        pipeline.run.manifest["demand_source"] = {"source_config": config.as_dict()}
        pipeline.run.outputs("prepare_demand", paths)
    pipeline.run.complete()
    return pipeline


def test_cli_freezes_inputs_preserves_source_and_reuses_intact_outputs(
    demand_run, rules, prescribed, monkeypatch, capsys
):
    config = demand_run.config
    rules_path, requests_path = config.workspace / "rules.json", config.workspace / "requests.csv"
    write_json(rules_path, rules)
    prescribed.to_csv(requests_path, index=False)
    source_hash = sha256_file(demand_run.run.manifest_path)
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: config)
    args = [
        "simulate-marketplace",
        "--demand-run-id",
        demand_run.run.run_id,
        "--rules",
        str(rules_path),
        "--requests",
        str(requests_path),
        "--run-id",
        "simulation-test",
    ]
    assert main(args) == 0
    manifest = completed_run(config.workspace, "simulation-test")
    output = config.workspace / "runs/simulation-test"
    assert read_json(output / "simulation_result.json")["summary"]["completed_trips"] == 3
    assert (
        output / "simulation_inputs/prescribed_requests.csv"
    ).read_bytes() == requests_path.read_bytes()
    assert sha256_file(demand_run.run.manifest_path) == source_hash
    assert len(pd.read_parquet(output / "requests.parquet")) == 3
    capsys.readouterr()
    assert main(args) == 0
    assert "simulate_marketplace: reuse verified artifacts" in capsys.readouterr().out
    assert (
        completed_run(config.workspace, "simulation-test")["stages"]["simulate_marketplace"][
            "duration_seconds"
        ]
        == manifest["stages"]["simulate_marketplace"]["duration_seconds"]
    )
    (output / "requests.csv").write_text("corrupt", encoding="utf-8")
    assert main(args) == 0
    assert "simulate_marketplace: running" in capsys.readouterr().out
    assert len(pd.read_csv(output / "requests.csv")) == 3
    rules["travel_times"][0]["trip_seconds"] = 1200
    write_json(rules_path, rules)
    assert main(args) == 0
    assert "simulate_marketplace: running" in capsys.readouterr().out
    completed_run(config.workspace, "simulation-test")


@pytest.mark.parametrize("failure", ["checksum", "gate", "budget", "same_run"])
def test_pipeline_records_integrity_and_budget_failures(demand_run, rules, failure):
    config = demand_run.config
    rules_path = config.workspace / "rules.json"
    if failure == "budget":
        rules["max_events"] = 1
    write_json(rules_path, rules)
    if failure == "checksum":
        (demand_run.run.path / "demand_plan.parquet").write_bytes(b"corrupt")
    elif failure == "gate":
        path = demand_run.run.path / "demand_result.json"
        value = read_json(path)
        value["usable_for_simulation"] = False
        write_json(path, value)
        demand_run.run.register([path])
    source_hash = sha256_file(demand_run.run.manifest_path)
    consumer = demand_run if failure == "same_run" else Pipeline(config, "failed-simulation")
    with pytest.raises((ValueError, RuntimeError)):
        consumer.simulate_marketplace(demand_run.run.run_id, rules_path)
    if failure != "same_run":
        assert consumer.run.manifest["stages"]["simulate_marketplace"]["status"] == "failed"
        assert not (consumer.run.path / "simulation_result.json").exists()
    assert sha256_file(demand_run.run.manifest_path) == source_hash


def test_consumer_config_cannot_change_frozen_demand_scope(demand_run, rules):
    rules_path = demand_run.config.workspace / "rules.json"
    write_json(rules_path, rules)
    config = dataclasses.replace(
        demand_run.config,
        source=dataclasses.replace(
            demand_run.config.source, assumed_timezone="Asia/Bangkok", zones=(999,)
        ),
    )
    consumer = Pipeline(config, "different-consumer-scope")
    result = consumer.simulate_marketplace(demand_run.run.run_id, rules_path)
    assert result["scope"]["zones"] == [161, 162]
    assert result["scope"]["horizon_start"] == "2024-01-26T13:00:00+00:00"


START = "2024-01-26T08:00:00-05:00"
CUT = "2024-01-26T08:10:00-05:00"
END = "2024-01-26T08:30:00-05:00"


@pytest.fixture
def window_rules():
    value = read_json(ROOT / "configs/week3_simulation.json")
    value.update(schema_version=2, max_wait_seconds=None, cancel_policy="before_pickup_finish_leg")
    return value


def _rehash(checkpoint):
    checkpoint["checkpoint_version"] = fingerprint(
        {key: value for key, value in checkpoint.items() if key != "checkpoint_version"}
    )


def _simulate(
    plan, window_rules, config, prescribed=None, start=START, end=END, carry=None, seed=42
):
    return simulate_marketplace(
        plan,
        window_rules,
        config,
        seed,
        prescribed,
        window_start=start,
        window_end=end,
        carry_in=carry,
    )


def test_split_run_preserves_queue_trip_events_and_wait(
    config, market_plan, window_rules, prescribed
):
    whole = _simulate(market_plan, window_rules, config, prescribed)
    first = _simulate(market_plan, window_rules, config, prescribed, end=CUT)
    saved = copy.deepcopy(first.end_snapshot)
    second = _simulate(market_plan, window_rules, config, start=CUT, carry=first.end_snapshot)
    assert first.end_snapshot == saved
    assert first.result["summary"]["open_requests_end"] == 3
    summary = second.result["summary"]
    assert summary["open_requests_start"] == summary["completed_trips"] == 3
    assert summary["created_requests"] == summary["open_requests_end"] == 0
    assert summary["wait_observed_requests"] == 1
    assert summary["mean_wait_seconds"] == 660
    assert second.requests.carry_in.all() and (not second.requests.created_in_window.any())
    fields = [
        "request_id",
        "created_at",
        "assigned_at",
        "pickup_at",
        "completed_at",
        "wait_seconds",
        "state",
        "vehicle_id",
    ]
    pd.testing.assert_frame_equal(whole.requests[fields], second.requests[fields])
    pd.testing.assert_frame_equal(
        whole.request_events,
        pd.concat([first.request_events, second.request_events], ignore_index=True),
    )
    for metric in ("idle_hours", "pickup_hours", "on_trip_hours", "total_vehicle_hours"):
        assert first.result["summary"][metric] + summary[metric] == pytest.approx(
            whole.result["summary"][metric]
        )
    assert whole.end_snapshot == second.end_snapshot


@pytest.mark.parametrize("cut", ["08:00:30", "08:01:00", "08:11:00", "08:12:00"])
def test_boundaries_preserve_events_without_replaying_arrivals(
    config, market_plan, window_rules, prescribed, cut
):
    boundary = f"2024-01-26T{cut}-05:00"
    whole = _simulate(market_plan, window_rules, config, prescribed)
    first = _simulate(market_plan, window_rules, config, prescribed, end=boundary)
    second = _simulate(market_plan, window_rules, config, start=boundary, carry=first.end_snapshot)
    pd.testing.assert_frame_equal(
        whole.request_events,
        pd.concat([first.request_events, second.request_events], ignore_index=True),
    )
    assert whole.end_snapshot == second.end_snapshot
    if cut == "08:01:00":
        assert first.result["summary"]["created_requests"] == 2
        assert second.result["summary"]["created_requests"] == 1
    if cut == "08:11:00":
        assert first.result["summary"]["completed_trips"] == 2
        assert second.result["summary"]["completed_trips"] == 1


@pytest.mark.parametrize("seed", [0, 42, 2026])
def test_poisson_schedule_is_frozen_across_multiple_windows(
    config, market_plan, window_rules, seed
):
    whole = _simulate(market_plan, window_rules, config, end="2024-01-26T10:00:00-05:00", seed=seed)
    boundaries = [START, CUT, END, "2024-01-26T10:00:00-05:00"]
    carry, traces = (None, [])
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        part = _simulate(
            market_plan, window_rules, config, start=start, end=end, carry=carry, seed=seed
        )
        carry = part.end_snapshot
        traces.append(part.request_events)
        assert part.spec["request_version"] == whole.spec["request_version"]
    pd.testing.assert_frame_equal(whole.request_events, pd.concat(traces, ignore_index=True))
    assert whole.end_snapshot == carry


def test_expiry_is_terminal_and_not_a_picked_up_wait(config, market_plan, window_rules, prescribed):
    window_rules["max_wait_seconds"] = 300
    simulation = _simulate(market_plan, window_rules, config, prescribed)
    request = simulation.requests.set_index("request_id").loc["request-03"]
    assert request.state == "expired"
    assert pd.Timestamp(request.expired_at) == pd.Timestamp("2024-01-26T08:06:00-05:00")
    assert pd.isna(request.wait_seconds) and request.observed_wait_seconds == 300
    assert not request.wait_censored and (not request.completion_censored)
    assert request.wait_status == "terminated_before_pickup"
    summary = simulation.result["summary"]
    assert summary["completed_trips"] == 2 and summary["expired_requests"] == 1
    assert summary["mean_wait_seconds"] == 60 and summary["wait_observed_requests"] == 2


def test_expiry_crosses_windows_without_resetting_deadline(
    config, market_plan, window_rules, prescribed
):
    window_rules["max_wait_seconds"] = 300
    cut = "2024-01-26T08:04:00-05:00"
    first = _simulate(market_plan, window_rules, config, prescribed, end=cut)
    second = _simulate(market_plan, window_rules, config, start=cut, carry=first.end_snapshot)
    request = second.requests.set_index("request_id", drop=False).loc["request-03"]
    assert request.request_id == "request-03" and request.state == "expired"
    assert request.observed_wait_seconds == 300
    assert second.result["summary"]["expired_requests"] == 1
    assert second.result["summary"]["wait_observed_requests"] == 0
    assert second.result["summary"]["mean_wait_seconds"] is None


@pytest.mark.parametrize("terminal", ["cancel", "expire"])
def test_aborted_pickup_finishes_leg_and_continues_from_checkpoint(
    config, market_plan, window_rules, prescribed, terminal
):
    market_plan.snapshot["vehicles"] = market_plan.snapshot["vehicles"][:1]
    _refresh_snapshot(market_plan, config)
    prescribed = prescribed.iloc[:2].copy()
    if terminal == "cancel":
        prescribed["cancel_at"] = ["2024-01-26T08:00:30-05:00", None]
    else:
        window_rules["max_wait_seconds"] = 30
    cut = "2024-01-26T08:00:45-05:00"
    whole = _simulate(market_plan, window_rules, config, prescribed)
    first = _simulate(market_plan, window_rules, config, prescribed, end=cut)
    vehicle = first.end_snapshot["vehicles"][0]
    assert vehicle["state"] == "to_pickup" and vehicle["active_request_id"] is None
    assert vehicle["pending_action"] == {
        "kind": "finish_aborted_pickup",
        "request_id": "request-01",
    }
    assert pd.Timestamp(vehicle["next_event_at"]) == pd.Timestamp("2024-01-26T08:01:00-05:00")
    second = _simulate(market_plan, window_rules, config, start=cut, carry=first.end_snapshot)
    pd.testing.assert_frame_equal(
        whole.request_events,
        pd.concat([first.request_events, second.request_events], ignore_index=True),
    )
    assert whole.end_snapshot == second.end_snapshot
    assert first.result["summary"]["aborted_pickup_hours"] + second.result["summary"][
        "aborted_pickup_hours"
    ] == pytest.approx(30 / 3600)
    if terminal == "cancel":
        request = whole.requests.set_index("request_id").loc["request-02"]
        assert pd.Timestamp(request.assigned_at) == pd.Timestamp("2024-01-26T08:01:00-05:00")
        assert whole.result["summary"]["completed_trips"] == 1


def test_pickup_wins_deadline_tie_and_cancel_after_pickup_is_ignored(
    config, market_plan, window_rules, prescribed
):
    window_rules["max_wait_seconds"] = 60
    prescribed = prescribed.iloc[:1].copy()
    prescribed["cancel_at"] = "2024-01-26T08:02:00-05:00"
    simulation = _simulate(market_plan, window_rules, config, prescribed)
    assert simulation.requests.state.to_list() == ["completed"]
    assert (
        simulation.result["summary"]["expired_requests"]
        == simulation.result["summary"]["canceled_requests"]
        == 0
    )


def test_zero_patience_expires_before_dispatch(config, market_plan, window_rules, prescribed):
    window_rules["max_wait_seconds"] = 0
    simulation = _simulate(market_plan, window_rules, config, prescribed)
    assert simulation.requests.state.eq("expired").all()
    assert simulation.requests.assigned_at.isna().all()
    assert simulation.requests.observed_wait_seconds.eq(0).all()
    assert simulation.result["summary"]["idle_hours"] == pytest.approx(1)


def test_zero_supply_expiry_and_empty_demand(config, market_plan, window_rules, prescribed):
    market_plan.snapshot["vehicles"] = []
    _refresh_snapshot(market_plan, config)
    window_rules["max_wait_seconds"] = 300
    simulation = _simulate(market_plan, window_rules, config, prescribed)
    assert simulation.result["summary"]["expired_requests"] == 3
    assert simulation.result["summary"]["total_vehicle_hours"] == 0
    assert simulation.vehicle_intervals.empty
    market_plan.frame[["request_rate", "expected_bookings"]] = 0.0
    market_plan.result["summary"]["expected_bookings"] = 0.0
    empty = _simulate(market_plan, window_rules, config)
    assert empty.requests.empty and empty.request_events.empty
    assert empty.result["summary"]["mean_wait_seconds"] is None


@pytest.mark.parametrize(
    "start,end",
    [
        (CUT, END),
        (START, START),
        (START, "2024-01-26T11:00:00-05:00"),
        ("2024-01-26T08:00:00", END),
    ],
)
def test_rejects_invalid_or_missing_carry_windows(config, market_plan, window_rules, start, end):
    with pytest.raises(ValueError):
        _simulate(market_plan, window_rules, config, start=start, end=end)


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "seed",
        "timestamp",
        "missing_phase",
        "duplicate_phase",
        "counter",
        "assignment",
        "deadline",
        "missing_arrival",
        "bad_zone",
        "missing_history",
    ],
)
def test_rejects_corrupt_checkpoint_even_when_rehashed(
    config, market_plan, window_rules, prescribed, mutation
):
    first = _simulate(
        market_plan, window_rules, config, prescribed, end="2024-01-26T08:00:30-05:00"
    )
    checkpoint = copy.deepcopy(first.end_snapshot)
    if mutation == "hash":
        checkpoint["checkpoint_version"] = "wrong"
    elif mutation == "seed":
        checkpoint["seed"] = 9
    elif mutation == "timestamp":
        checkpoint["timestamp"] = START
    elif mutation == "missing_phase":
        checkpoint["pending_events"] = [
            e
            for e in checkpoint["pending_events"]
            if not (e[2] == "pickup_complete" and e[3] == "vehicle-1")
        ]
    elif mutation == "duplicate_phase":
        event = copy.deepcopy(
            next(e for e in checkpoint["pending_events"] if e[2] == "pickup_complete")
        )
        event[1] = checkpoint["next_sequence"]
        checkpoint["next_sequence"] += 1
        checkpoint["pending_events"].append(event)
    elif mutation == "counter":
        checkpoint["next_event_id"] = 0
    elif mutation == "assignment":
        checkpoint["vehicles"][0]["active_request_id"] = "request-02"
    elif mutation == "deadline":
        checkpoint["request_records"][0]["deadline_at"] = END
    elif mutation == "missing_arrival":
        checkpoint["pending_events"] = [
            e for e in checkpoint["pending_events"] if e[2] != "arrival"
        ]
    elif mutation == "bad_zone":
        checkpoint["arrival_schedule"][0]["origin_zone_id"] = 999
        checkpoint["request_version"] = fingerprint(checkpoint["arrival_schedule"])
    elif mutation == "missing_history":
        checkpoint["request_records"] = checkpoint["request_records"][1:]
        checkpoint["open_requests"] = checkpoint["request_records"]
    if mutation != "hash":
        _rehash(checkpoint)
    with pytest.raises(ValueError, match="Carry-in"):
        _simulate(
            market_plan, window_rules, config, start="2024-01-26T08:00:30-05:00", carry=checkpoint
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_wait_seconds", -1),
        ("max_wait_seconds", True),
        ("max_wait_seconds", float("inf")),
        ("cancel_policy", "release_immediately"),
    ],
)
def test_rejects_invalid_operational_rules(config, market_plan, window_rules, field, value):
    window_rules[field] = value
    with pytest.raises(ValueError):
        _simulate(market_plan, window_rules, config)


def test_rejects_changed_rules_seed_and_prescribed_schedule(
    config, market_plan, window_rules, prescribed
):
    first = _simulate(market_plan, window_rules, config, prescribed, end=CUT)
    with pytest.raises(ValueError, match="versions.*seed"):
        _simulate(market_plan, window_rules, config, start=CUT, carry=first.end_snapshot, seed=43)
    changed = copy.deepcopy(window_rules)
    changed["max_wait_seconds"] = 300
    with pytest.raises(ValueError, match="versions"):
        _simulate(market_plan, changed, config, start=CUT, carry=first.end_snapshot)
    prescribed.loc[0, "destination_zone_id"] = 162
    with pytest.raises(ValueError, match="schedule differs"):
        _simulate(
            market_plan, window_rules, config, prescribed, start=CUT, carry=first.end_snapshot
        )


def test_cancel_before_creation_and_event_budget_fail(
    config, market_plan, window_rules, prescribed
):
    prescribed["cancel_at"] = "2024-01-26T07:59:00-05:00"
    with pytest.raises(ValueError, match="precedes"):
        _simulate(market_plan, window_rules, config, prescribed)
    window_rules["max_events"] = 1
    with pytest.raises(RuntimeError, match="max_events"):
        _simulate(market_plan, window_rules, config, prescribed.drop(columns="cancel_at"))


def test_cli_freezes_parent_checkpoint_and_reuses_outputs(
    demand_run, window_rules, prescribed, monkeypatch, capsys
):
    config = demand_run.config
    rules_path, requests_path = (config.workspace / "rules.json", config.workspace / "requests.csv")
    write_json(rules_path, window_rules)
    prescribed.to_csv(requests_path, index=False)
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: config)
    common = [
        "simulate-marketplace",
        "--demand-run-id",
        demand_run.run.run_id,
        "--rules",
        str(rules_path),
    ]
    first_args = common + [
        "--run-id",
        "window-first",
        "--requests",
        str(requests_path),
        "--window-start",
        START,
        "--window-end",
        CUT,
    ]
    assert main(first_args) == 0
    parent = config.workspace / "runs/window-first"
    parent_hash = sha256_file(parent / "manifest.json")
    source_hash = sha256_file(demand_run.run.manifest_path)
    args = common + [
        "--run-id",
        "window-second",
        "--carry-in-run-id",
        "window-first",
        "--window-start",
        CUT,
        "--window-end",
        END,
    ]
    assert main(args) == 0
    output = config.workspace / "runs/window-second"
    assert (output / "simulation_inputs/carry_in.json").read_bytes() == (
        parent / "end_snapshot.json"
    ).read_bytes()
    summary = read_json(output / "simulation_result.json")["summary"]
    assert summary["completed_trips"] == 3 and summary["created_requests"] == 0
    assert sha256_file(parent / "manifest.json") == parent_hash
    assert sha256_file(demand_run.run.manifest_path) == source_hash
    completed_run(config.workspace, "window-second")
    capsys.readouterr()
    assert main(args) == 0
    assert "reuse verified artifacts" in capsys.readouterr().out
    (parent / "end_snapshot.json").write_text("corrupt", encoding="utf-8")
    assert main(args) == 1
    assert "checksum" in capsys.readouterr().err.lower()


def test_version_one_checkpoint_cannot_be_resumed(demand_run, window_rules):
    old_rules = {
        key: value
        for key, value in window_rules.items()
        if key not in ("cancel_policy", "max_wait_seconds")
    }
    old_rules["schema_version"] = 1
    rules_path = demand_run.config.workspace / "rules.json"
    write_json(rules_path, old_rules)
    parent = Pipeline(demand_run.config, "old-window")
    parent.simulate_marketplace(demand_run.run.run_id, rules_path)
    parent.run.complete()
    write_json(rules_path, window_rules)
    child = Pipeline(demand_run.config, "invalid-carry")
    with pytest.raises(ValueError, match="checkpoint fields"):
        child.simulate_marketplace(demand_run.run.run_id, rules_path, carry_in_run_id="old-window")
    assert child.run.manifest["stages"]["simulate_marketplace"]["status"] == "failed"
    assert not (child.run.path / "simulation_result.json").exists()


def test_fractional_phase_rounding_cannot_finish_outside_shift(
    config, market_plan, window_rules, prescribed
):
    market_plan.snapshot["vehicles"] = market_plan.snapshot["vehicles"][:1]
    market_plan.snapshot["vehicles"][0]["shift_end"] = "2024-01-26T08:00:01.000000001-05:00"
    _refresh_snapshot(market_plan, config)
    for row in window_rules["travel_times"]:
        row["pickup_seconds"] = 0.5000000006
        row["trip_seconds"] = 0.5000000006
    simulation = _simulate(market_plan, window_rules, config, prescribed.iloc[:1])
    # Each phase rounds to 500,000,001 ns; their sum exceeds the shift by 1 ns.
    assert simulation.requests.state.to_list() == ["queued"]
    assert simulation.requests.assigned_at.isna().all()
    assert simulation.result["summary"]["completed_trips"] == 0


@pytest.mark.parametrize("field", ["kind", "entity_id", "state", "active_id", "vehicle_id"])
def test_checkpoint_nested_invalid_types_have_useful_failures(
    config, market_plan, window_rules, prescribed, field
):
    cut = "2024-01-26T08:00:30-05:00"
    first = _simulate(market_plan, window_rules, config, prescribed, end=cut)
    checkpoint = copy.deepcopy(first.end_snapshot)
    if field in ("kind", "entity_id"):
        checkpoint["pending_events"][0][2 if field == "kind" else 3] = []
    elif field == "state":
        checkpoint["request_records"][0]["state"] = []
    elif field == "active_id":
        checkpoint["vehicles"][0]["active_request_id"] = []
    else:
        checkpoint["vehicles"][0]["vehicle_id"] = []
    _rehash(checkpoint)
    with pytest.raises(ValueError, match="Carry-in"):
        _simulate(market_plan, window_rules, config, start=cut, carry=checkpoint)


def test_unrepresentable_patience_is_rejected(config, market_plan, window_rules):
    window_rules["max_wait_seconds"] = 1e300
    with pytest.raises(ValueError, match="timestamp range"):
        _simulate(market_plan, window_rules, config)
