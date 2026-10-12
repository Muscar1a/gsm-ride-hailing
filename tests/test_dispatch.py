from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest
from gsm_poc.artifacts import fingerprint, read_json
from gsm_poc.demand import DemandPlan, validate_snapshot
from gsm_poc.marketplace import simulate_marketplace

from gsm_poc.simulation.rules import normalize_rules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def market_plan(config):
    snapshot = validate_snapshot(read_json(ROOT / "configs/week3_snapshot.json"), config)
    spec = {
        "schema_version": 1,
        "model_version": "model-v1",
        "source_version": "source-v1",
        "snapshot_version": snapshot["snapshot_version"],
        "units": {"request_rate": "requests/hour"},
        "policy": {
            "baseline_multiplier_x": 1.0,
            "baseline_multiplier_y": 1.0,
            "delta_price_x": 0.0,
            "delta_price_y": 0.0,
        },
    }
    spec["policy_version"] = fingerprint(spec["policy"])
    version = fingerprint(spec)
    rows = [
        {
            "zone_id": zone,
            "service_id": service,
            "block_start": pd.Timestamp(snapshot["horizon_start"]),
            "block_end": pd.Timestamp(snapshot["horizon_end"]),
            "block_hours": 2.0,
            "request_rate": 1.0,
            "expected_bookings": 2.0,
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
        for zone in (161, 162)
        for service in ("X", "Y")
    ]
    result = {
        "schema_version": 1,
        "usable_for_simulation": True,
        "status": "ok",
        "demand_plan_version": version,
        "source_kind": "synthetic",
        "summary": {"expected_bookings": 8.0},
    }
    return DemandPlan(pd.DataFrame(rows), result, snapshot, spec)


def _refresh_snapshot(plan, config):
    plan.snapshot = validate_snapshot(plan.snapshot, config)
    plan.spec["snapshot_version"] = plan.snapshot["snapshot_version"]
    version = fingerprint(plan.spec)
    plan.result["demand_plan_version"] = version
    plan.frame["demand_plan_version"] = version


def _pay_policy(plan):
    plan.spec["policy"]["delta_price_x"] = 0.1
    plan.spec["policy_version"] = fingerprint(plan.spec["policy"])
    version = fingerprint(plan.spec)
    plan.result["demand_plan_version"] = version
    plan.frame["demand_plan_version"] = version
    plan.frame["policy_version"] = plan.spec["policy_version"]


@pytest.fixture
def compensation():
    return read_json(ROOT / "configs/week3_compensation.json")


@pytest.fixture
def offer_rules():
    return read_json(ROOT / "configs/week3_poc.json")


def _requests(plan, seconds=(0,), cancel_seconds=None):
    start = pd.Timestamp(plan.snapshot["horizon_start"])
    rows = [
        {
            "request_id": f"request-{index}",
            "created_at": (start + pd.Timedelta(seconds=second)).isoformat(),
            "origin_zone_id": 161,
            "destination_zone_id": 161,
            "service_id": "X",
        }
        for index, second in enumerate(seconds)
    ]
    if cancel_seconds is not None:
        for row in rows:
            row["cancel_at"] = (start + pd.Timedelta(seconds=cancel_seconds)).isoformat()
    return pd.DataFrame(rows)


def _single_driver(plan, config):
    plan.snapshot["vehicles"] = plan.snapshot["vehicles"][:1]
    _refresh_snapshot(plan, config)


def _checkpoint_hash(checkpoint):
    checkpoint["checkpoint_version"] = fingerprint(
        {key: value for key, value in checkpoint.items() if key != "checkpoint_version"}
    )


def test_completed_trip_has_predecision_pay_and_offer_wait(
    config, market_plan, offer_rules, compensation
):
    _single_driver(market_plan, config)
    _pay_policy(market_plan)
    offer_rules["acceptance_probability"] = 1
    result = simulate_marketplace(
        market_plan, offer_rules, config, 42, _requests(market_plan), compensation=compensation
    )
    assert result.result["summary"]["completed_trips"] == 1
    assert result.requests.wait_seconds.tolist() == [63]
    assert result.driver_offers.state.tolist() == ["accepted"]
    assert result.offer_events.state.tolist() == ["offered", "accepted"]
    offer = result.driver_offers.iloc[0]
    assert pd.Timestamp(offer.offered_at) < pd.Timestamp(offer.resolved_at)
    assert offer.displayed_fare == offer.offered_driver_pay == pytest.approx(1.1)
    assert result.financial_tables["earnings_ledger"].driver_pay.tolist() == [1.1]
    assert result.result["summary"]["dispatch_hours"] == pytest.approx(3 / 3600)
    assert result.result["summary"]["online_hours"] == 2
    assert result.end_snapshot["vehicles"][0]["state"] == "idle"


def test_refusals_leave_drivers_online_and_never_retry_unchanged_pair(
    config, market_plan, offer_rules
):
    offer_rules["acceptance_probability"] = 0
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert result.driver_offers.state.tolist() == ["rejected", "rejected"]
    assert not result.driver_offers.duplicated(["request_id", "vehicle_id"]).any()
    assert result.result["offers"]["offered"] == 2
    assert result.result["offers"]["acceptance_rate"] == 0
    assert result.requests.state.tolist() == ["expired"]
    assert result.result["summary"]["online_hours"] == 4
    assert result.result["summary"]["offline_hours"] == 0
    assert {vehicle["state"] for vehicle in result.end_snapshot["vehicles"]} == {"idle"}


def test_attempt_budget_limits_refusal_cascade(config, market_plan, offer_rules):
    offer_rules.update(acceptance_probability=0, max_offer_attempts=1)
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert len(result.driver_offers) == 1
    assert result.result["offers"]["rejected"] == 1
    assert result.requests.state.tolist() == ["expired"]


def test_timeout_is_response_failure_and_releases_reservation(config, market_plan, offer_rules):
    offer_rules.update(acceptance_probability=1, response_seconds=11, max_offer_attempts=1)
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert result.driver_offers.state.tolist() == ["timed_out"]
    assert result.result["summary"]["dispatch_hours"] == pytest.approx(10 / 3600)
    assert result.result["offers"]["acceptance_denominator"] == 1


@pytest.mark.parametrize("cancel_seconds", [1, 3])
def test_pending_offer_withdrawn_before_or_at_decision(
    config, market_plan, offer_rules, cancel_seconds
):
    offer_rules["acceptance_probability"] = 1
    result = simulate_marketplace(
        market_plan,
        offer_rules,
        config,
        42,
        _requests(market_plan, cancel_seconds=cancel_seconds),
    )
    assert result.driver_offers.state.tolist() == ["withdrawn"]
    assert result.requests.state.tolist() == ["canceled"]
    assert result.result["offers"]["acceptance_rate"] is None
    assert result.result["offers"]["pending_end"] == 0


def test_busy_driver_cannot_accept_simultaneous_requests(config, market_plan, offer_rules):
    _single_driver(market_plan, config)
    offer_rules["acceptance_probability"] = 1
    result = simulate_marketplace(
        market_plan, offer_rules, config, 42, _requests(market_plan, seconds=(0, 0))
    )
    assert result.result["summary"]["completed_trips"] == 1
    assert result.result["summary"]["expired_requests"] == 1
    assert len(result.driver_offers) == 1


def test_late_trip_can_start_and_is_censored_at_observation_end(
    config, market_plan, offer_rules, compensation
):
    _single_driver(market_plan, config)
    _pay_policy(market_plan)
    offer_rules["acceptance_probability"] = 1
    result = simulate_marketplace(
        market_plan,
        offer_rules,
        config,
        42,
        _requests(market_plan, seconds=(7100,)),
        compensation=compensation,
    )
    assert result.requests.state.tolist() == ["on_trip"]
    assert result.requests.completion_censored.tolist() == [True]
    assert result.end_snapshot["vehicles"][0]["state"] == "on_trip"
    assert pd.Timestamp(result.end_snapshot["vehicles"][0]["next_event_at"]) > pd.Timestamp(
        market_plan.snapshot["horizon_end"]
    )
    assert result.financial_tables["earnings_ledger"].empty
    assert result.result["summary"]["online_hours"] == 2


@pytest.mark.parametrize("split_seconds", [1, 3, 20, 100, 664])
def test_split_window_preserves_offers_events_and_pays_once(
    config, market_plan, offer_rules, compensation, split_seconds
):
    _single_driver(market_plan, config)
    _pay_policy(market_plan)
    offer_rules["acceptance_probability"] = 1
    requests = _requests(market_plan)
    end = (
        pd.Timestamp(market_plan.snapshot["horizon_start"]) + pd.Timedelta(seconds=split_seconds)
    ).isoformat()
    full = simulate_marketplace(
        market_plan, offer_rules, config, 42, requests, compensation=compensation
    )
    first = simulate_marketplace(
        market_plan, offer_rules, config, 42, requests, window_end=end, compensation=compensation
    )
    second = simulate_marketplace(
        market_plan,
        offer_rules,
        config,
        42,
        window_start=end,
        carry_in=first.end_snapshot,
        compensation=compensation,
    )
    assert second.end_snapshot == full.end_snapshot
    pd.testing.assert_frame_equal(
        pd.concat([first.offer_events, second.offer_events], ignore_index=True), full.offer_events
    )
    assert sum(len(part.financial_tables["earnings_ledger"]) for part in (first, second)) == 1
    assert sum(
        part.result["summary"]["dispatch_hours"] for part in (first, second)
    ) == pytest.approx(3 / 3600)


def test_split_after_withdrawal_preserves_stale_noop_response(config, market_plan, offer_rules):
    requests = _requests(market_plan, cancel_seconds=1)
    end = (
        pd.Timestamp(market_plan.snapshot["horizon_start"]) + pd.Timedelta(seconds=2)
    ).isoformat()
    first = simulate_marketplace(market_plan, offer_rules, config, 42, requests, window_end=end)
    second = simulate_marketplace(
        market_plan, offer_rules, config, 42, window_start=end, carry_in=first.end_snapshot
    )
    assert second.result["offers"]["offered"] == 0
    assert second.result["offers"]["accepted"] == 0
    assert second.end_snapshot["offer_records"][0]["state"] == "withdrawn"


@pytest.mark.parametrize(
    "mutation", ["reservation", "response", "decision", "counter", "events", "pay"]
)
def test_rehashed_malformed_checkpoint_is_rejected(
    config, market_plan, offer_rules, compensation, mutation
):
    _pay_policy(market_plan)
    end = (
        pd.Timestamp(market_plan.snapshot["horizon_start"]) + pd.Timedelta(seconds=1)
    ).isoformat()
    first = simulate_marketplace(
        market_plan,
        offer_rules,
        config,
        42,
        _requests(market_plan),
        window_end=end,
        compensation=compensation,
    )
    checkpoint = copy.deepcopy(first.end_snapshot)
    if mutation == "reservation":
        checkpoint["vehicles"][0]["pending_offer_id"] = None
    elif mutation == "response":
        checkpoint["offer_records"][0]["response_at"] = end
    elif mutation == "decision":
        checkpoint["offer_records"][0]["state"] = "accepted"
    elif mutation == "counter":
        checkpoint["next_offer_event_id"] += 1
    elif mutation == "events":
        checkpoint["pending_events"] = []
    else:
        checkpoint["offer_records"][0]["offered_driver_pay"] = -1
    _checkpoint_hash(checkpoint)
    with pytest.raises(ValueError):
        simulate_marketplace(
            market_plan,
            offer_rules,
            config,
            42,
            window_start=end,
            carry_in=checkpoint,
            compensation=compensation,
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("acceptance_probability", -1),
        ("acceptance_probability", float("nan")),
        ("acceptance_probability", 1.1),
        ("response_seconds", -1),
        ("response_timeout_seconds", 0),
        ("max_offer_attempts", True),
        ("max_offer_attempts", 0),
        ("online_population_rule", "dynamic"),
    ],
)
def test_offer_rule_boundary_validation(market_plan, offer_rules, key, value):
    offer_rules[key] = value
    with pytest.raises(ValueError):
        normalize_rules(offer_rules, market_plan.snapshot)


def test_zero_online_roster_and_zero_requests_remain_valid(config, market_plan, offer_rules):
    market_plan.snapshot["vehicles"] = []
    _refresh_snapshot(market_plan, config)
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert result.result["scope"]["online_drivers"] == 0
    assert result.result["summary"]["online_hours"] == 0
    assert result.driver_offers.empty
    assert result.requests.state.tolist() == ["expired"]
    market_plan.frame["request_rate"] = 0
    market_plan.frame["expected_bookings"] = 0
    market_plan.result["summary"]["expected_bookings"] = 0
    empty = simulate_marketplace(market_plan, offer_rules, config, 42)
    assert empty.requests.empty
    assert empty.result["offers"]["acceptance_rate"] is None


def test_operational_budget_failure_is_explicit(config, market_plan, offer_rules):
    offer_rules["max_events"] = 1
    with pytest.raises(RuntimeError, match="max_events"):
        simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))


def test_offer_draws_stable_when_only_price_changes(config, market_plan, offer_rules, compensation):
    _pay_policy(market_plan)
    baseline = simulate_marketplace(
        market_plan, offer_rules, config, 42, _requests(market_plan), compensation=compensation
    )
    market_plan.spec["policy"]["delta_price_x"] = 0.2
    market_plan.spec["policy_version"] = fingerprint(market_plan.spec["policy"])
    version = fingerprint(market_plan.spec)
    market_plan.result["demand_plan_version"] = version
    market_plan.frame["demand_plan_version"] = version
    market_plan.frame["policy_version"] = market_plan.spec["policy_version"]
    changed = simulate_marketplace(
        market_plan, offer_rules, config, 42, _requests(market_plan), compensation=compensation
    )
    assert baseline.driver_offers.offer_id.tolist() == changed.driver_offers.offer_id.tolist()
    assert baseline.driver_offers.state.tolist() == changed.driver_offers.state.tolist()
    assert changed.driver_offers.displayed_fare.tolist() == [1.2] * len(changed.driver_offers)


def test_rejection_history_survives_pending_second_offer_checkpoint(
    config, market_plan, offer_rules
):
    offer_rules["acceptance_probability"] = 0
    end = (
        pd.Timestamp(market_plan.snapshot["horizon_start"]) + pd.Timedelta(seconds=4)
    ).isoformat()
    requests = _requests(market_plan)
    full = simulate_marketplace(market_plan, offer_rules, config, 42, requests)
    first = simulate_marketplace(market_plan, offer_rules, config, 42, requests, window_end=end)
    assert first.result["offers"]["rejected"] == 1
    assert first.result["offers"]["pending_end"] == 1
    second = simulate_marketplace(
        market_plan, offer_rules, config, 42, window_start=end, carry_in=first.end_snapshot
    )
    assert second.end_snapshot == full.end_snapshot
    assert second.result["offers"]["offered"] == 0
    assert second.result["offers"]["rejected"] == 1
    assert second.result["summary"]["online_hours"] == pytest.approx(4 - 8 / 3600)


def test_canceled_accepted_offer_finishes_aborted_pickup_without_pay(
    config, market_plan, offer_rules, compensation
):
    _single_driver(market_plan, config)
    offer_rules["acceptance_probability"] = 1
    requests = _requests(market_plan, cancel_seconds=30)
    end = (
        pd.Timestamp(market_plan.snapshot["horizon_start"]) + pd.Timedelta(seconds=40)
    ).isoformat()
    first = simulate_marketplace(
        market_plan, offer_rules, config, 42, requests, window_end=end, compensation=compensation
    )
    second = simulate_marketplace(
        market_plan,
        offer_rules,
        config,
        42,
        window_start=end,
        carry_in=first.end_snapshot,
        compensation=compensation,
    )
    assert first.requests.state.tolist() == ["canceled"]
    assert first.driver_offers.state.tolist() == ["accepted"]
    assert first.financial_tables["earnings_ledger"].empty
    assert second.financial_tables["earnings_ledger"].empty
    assert second.end_snapshot["vehicles"][0]["state"] == "idle"


def test_expiry_beats_equal_time_response(config, market_plan, offer_rules):
    offer_rules.update(acceptance_probability=1, max_wait_seconds=3)
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert result.driver_offers.state.tolist() == ["withdrawn"]
    assert result.requests.state.tolist() == ["expired"]


def test_immediate_certain_acceptance_has_no_reservation_time(config, market_plan, offer_rules):
    offer_rules.update(acceptance_probability=1, response_seconds=0)
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert result.requests.wait_seconds.tolist() == [60]
    assert result.result["summary"]["dispatch_hours"] == 0
    assert result.result["offers"]["pending_end"] == 0


def test_online_but_ineligible_drivers_do_not_create_capacity(config, market_plan, offer_rules):
    for vehicle in market_plan.snapshot["vehicles"]:
        vehicle["eligible_services"] = ["Y"]
    _refresh_snapshot(market_plan, config)
    result = simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))
    assert result.driver_offers.empty
    assert result.requests.state.tolist() == ["expired"]
    assert result.result["summary"]["idle_hours"] == 4


def test_fixed_online_rejects_partial_attendance(config, market_plan, offer_rules):
    vehicle = market_plan.snapshot["vehicles"][0]
    vehicle["shift_end"] = (
        pd.Timestamp(vehicle["shift_end"]) - pd.Timedelta(seconds=1)
    ).isoformat()
    _refresh_snapshot(market_plan, config)
    with pytest.raises(ValueError, match="whole horizon"):
        simulate_marketplace(market_plan, offer_rules, config, 42, _requests(market_plan))


@pytest.mark.parametrize("change", ["seed", "rules", "pay"])
def test_resume_rejects_changed_offer_context(
    config, market_plan, offer_rules, compensation, change
):
    end = (
        pd.Timestamp(market_plan.snapshot["horizon_start"]) + pd.Timedelta(seconds=1)
    ).isoformat()
    first = simulate_marketplace(
        market_plan,
        offer_rules,
        config,
        42,
        _requests(market_plan),
        window_end=end,
        compensation=compensation,
    )
    seed = 43 if change == "seed" else 42
    if change == "rules":
        offer_rules["acceptance_probability"] = 0.5
    if change == "pay":
        compensation["baseline_fares"]["X"] = 2
    with pytest.raises(ValueError):
        simulate_marketplace(
            market_plan,
            offer_rules,
            config,
            seed,
            window_start=end,
            carry_in=first.end_snapshot,
            compensation=compensation,
        )
