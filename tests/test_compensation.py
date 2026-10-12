from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gsm_poc.simulation.compensation import (
    resolve_compensation,
    settle_earnings,
    validate_compensation,
)

START = "2024-01-26T08:00:00-05:00"
END = "2024-01-26T09:00:00-05:00"


@pytest.fixture
def compensation():
    return json.loads((Path(__file__).parents[1] / "configs/week3_compensation.json").read_text())


@pytest.fixture
def policy():
    return {
        "baseline_multiplier_x": 2.0,
        "baseline_multiplier_y": 1.5,
        "delta_price_x": 0.1,
        "delta_price_y": -0.2,
    }


@pytest.fixture
def earnings_inputs(compensation, policy):
    roster = [{"vehicle_id": f"v{i}", "driver_id": f"d{i}", "shift_id": f"s{i}"} for i in (1, 2, 3)]
    requests = pd.DataFrame(
        [
            {
                "request_id": "done",
                "service_id": "X",
                "created_at": START,
                "assigned_at": START,
                "completed_at": "2024-01-26T08:15:00-05:00",
                "state": "completed",
                "vehicle_id": "v1",
            },
            {
                "request_id": "canceled",
                "service_id": "Y",
                "created_at": START,
                "assigned_at": START,
                "completed_at": None,
                "state": "canceled",
                "vehicle_id": "v2",
            },
            {
                "request_id": "expired",
                "service_id": "X",
                "created_at": START,
                "assigned_at": None,
                "completed_at": None,
                "state": "expired",
                "vehicle_id": None,
            },
            {
                "request_id": "pending",
                "service_id": "Y",
                "created_at": START,
                "assigned_at": None,
                "completed_at": None,
                "state": "queued",
                "vehicle_id": None,
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "request_id": "done",
                "timestamp": "2024-01-26T08:15:00-05:00",
                "state": "completed",
                "vehicle_id": "v1",
            },
            {
                "request_id": "canceled",
                "timestamp": "2024-01-26T08:10:00-05:00",
                "state": "canceled",
                "vehicle_id": "v2",
            },
            {
                "request_id": "expired",
                "timestamp": "2024-01-26T08:10:00-05:00",
                "state": "expired",
                "vehicle_id": None,
            },
        ]
    )
    intervals = pd.DataFrame(
        [
            {
                **vehicle,
                "state": "offline" if vehicle["vehicle_id"] == "v3" else "idle",
                "start": START,
                "end": END,
                "duration_hours": 1.0,
            }
            for vehicle in roster
        ]
    )
    return {
        "requests": requests,
        "request_events": events,
        "vehicle_intervals": intervals,
        "snapshot": {"vehicles": roster},
        "resolved": resolve_compensation(compensation, policy),
        "window_start": START,
        "window_end": END,
    }


def test_effective_fare_uses_absolute_tariff_and_full_policy(compensation, policy):
    original = copy.deepcopy(compensation)
    compensation["baseline_fares"] = {"X": 10, "Y": 20}
    resolved = resolve_compensation(compensation, policy)
    assert resolved["effective_fares"] == pytest.approx({"X": 22, "Y": 24})
    assert resolved["contract"]["driver_fare_share"] == 1
    assert resolved == resolve_compensation(compensation, policy)
    assert original["baseline_fares"] == {"X": 1, "Y": 1}
    changed = resolve_compensation(compensation, policy | {"delta_price_x": 0.2})
    assert changed["compensation_version"] == resolved["compensation_version"]
    assert changed["terms_version"] != resolved["terms_version"]


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"currency": "VND"},
        {"source_kind": "public"},
        {"evidence_level": "A"},
        {"calibration_status": "calibrated"},
        {"driver_fare_share": 0.8},
        {"driver_fare_share": True},
        {"cancel_payment": 1},
        {"baseline_fares": {"X": 1}},
        {"baseline_fares": {"X": np.inf, "Y": 1}},
        {"baseline_fares": {"X": -1, "Y": 1}},
        {"baseline_fares": {"X": True, "Y": 1}},
        {"compensation_id": ""},
        {"settlement_rule": "assigned"},
        {"extra": 1},
    ],
)
def test_invalid_compensation_rejected(compensation, changes):
    with pytest.raises(ValueError):
        validate_compensation(compensation | changes)


def test_missing_contract_and_policy_values_rejected(compensation, policy):
    compensation.pop("currency")
    with pytest.raises(ValueError, match="missing"):
        validate_compensation(compensation)
    for key in policy:
        partial = policy.copy()
        partial.pop(key)
        with pytest.raises(ValueError, match=key):
            resolve_compensation(
                json.loads(
                    (Path(__file__).parents[1] / "configs/week3_compensation.json").read_text()
                ),
                partial,
            )


@pytest.mark.parametrize(
    "changes",
    [
        {"baseline_multiplier_x": 0},
        {"baseline_multiplier_y": np.nan},
        {"delta_price_y": -1},
        {"delta_price_x": True},
    ],
)
def test_invalid_policy_rejected(compensation, policy, changes):
    with pytest.raises(ValueError):
        resolve_compensation(compensation, policy | changes)


def test_completed_only_pay_and_zero_trip_presence_income(earnings_inputs):
    result = settle_earnings(**earnings_inputs)
    assert len(result["quote_terms"]) == 4
    assert len(result["driver_pay_terms"]) == 2
    assert result["driver_pay_terms"].set_index("request_id").loc[
        "canceled", "offered_driver_pay"
    ] == pytest.approx(1.2)
    ledger = result["earnings_ledger"]
    assert ledger.request_id.tolist() == ["done"]
    assert ledger.rider_payment.tolist() == pytest.approx([2.2])
    assert ledger.driver_pay.tolist() == pytest.approx([2.2])
    income = result["driver_income"].set_index("driver_id")
    assert income.loc["d1", "pay_per_presence_hour"] == pytest.approx(2.2)
    assert income.loc["d2", "presence_hours"] == 1
    assert income.loc["d2", "total_driver_pay"] == 0
    assert income.loc["d2", "pay_per_presence_hour"] == 0
    assert pd.isna(income.loc["d3", "pay_per_presence_hour"])
    assert income.loc["d3", "income_rate_status"] == "unavailable_zero_presence"
    assert result["result"]["summary"]["pay_per_presence_hour"] == pytest.approx(1.1)
    assert result["result"]["profit_status"] == "not_evaluated"


def test_historical_completion_not_paid_in_next_window(earnings_inputs):
    first = settle_earnings(**earnings_inputs)
    second_inputs = copy.deepcopy(earnings_inputs)
    second_inputs["window_start"] = END
    second_inputs["window_end"] = "2024-01-26T10:00:00-05:00"
    second_inputs["request_events"] = earnings_inputs["request_events"].iloc[0:0]
    second_inputs["vehicle_intervals"]["start"] = END
    second_inputs["vehicle_intervals"]["end"] = second_inputs["window_end"]
    second = settle_earnings(**second_inputs)
    assert len(first["earnings_ledger"]) == 1
    assert second["earnings_ledger"].empty
    assert second["result"]["summary"]["total_driver_pay"] == 0


def test_boundary_completion_is_settled_once(earnings_inputs):
    earnings_inputs["requests"].loc[0, "completed_at"] = END
    earnings_inputs["request_events"].loc[0, "timestamp"] = END
    result = settle_earnings(**earnings_inputs)
    assert result["result"]["summary"]["settled_completed_trips"] == 1


def test_replay_is_deterministic_and_preserves_inputs(earnings_inputs):
    original = copy.deepcopy(earnings_inputs)
    first = settle_earnings(**earnings_inputs)
    second = settle_earnings(**earnings_inputs)
    for key in ("quote_terms", "driver_pay_terms", "earnings_ledger", "driver_income"):
        pd.testing.assert_frame_equal(first[key], second[key])
    for key in ("requests", "request_events", "vehicle_intervals"):
        pd.testing.assert_frame_equal(original[key], earnings_inputs[key])
    assert first["result"] == second["result"]


@pytest.mark.parametrize(
    "corruption",
    [
        "duplicate",
        "missing_event",
        "wrong_time",
        "wrong_vehicle",
        "unknown_vehicle",
        "duration",
        "nan_duration",
        "overlap",
        "terms",
        "missing_money",
        "completion_state",
    ],
)
def test_inconsistent_settlement_inputs_rejected(earnings_inputs, corruption):
    if corruption == "duplicate":
        earnings_inputs["request_events"] = pd.concat(
            [earnings_inputs["request_events"], earnings_inputs["request_events"].iloc[:1]],
            ignore_index=True,
        )
    elif corruption == "missing_event":
        earnings_inputs["request_events"] = earnings_inputs["request_events"].iloc[1:]
    elif corruption == "wrong_time":
        earnings_inputs["request_events"].loc[0, "timestamp"] = START
    elif corruption == "wrong_vehicle":
        earnings_inputs["request_events"].loc[0, "vehicle_id"] = "v2"
    elif corruption == "unknown_vehicle":
        earnings_inputs["requests"].loc[0, "vehicle_id"] = "unknown"
    elif corruption == "duration":
        earnings_inputs["vehicle_intervals"].loc[0, "duration_hours"] = 2
    elif corruption == "nan_duration":
        earnings_inputs["vehicle_intervals"].loc[0, "duration_hours"] = np.nan
    elif corruption == "overlap":
        earnings_inputs["vehicle_intervals"] = pd.concat(
            [earnings_inputs["vehicle_intervals"], earnings_inputs["vehicle_intervals"].iloc[:1]],
            ignore_index=True,
        )
    elif corruption == "terms":
        earnings_inputs["resolved"]["effective_fares"]["X"] = 99
    elif corruption == "missing_money":
        earnings_inputs["resolved"]["contract"]["baseline_fares"].pop("Y")
    else:
        earnings_inputs["requests"].loc[0, "state"] = "queued"
    with pytest.raises(ValueError):
        settle_earnings(**earnings_inputs)


def test_zero_demand_still_exports_all_roster_incomes(earnings_inputs):
    earnings_inputs["requests"] = earnings_inputs["requests"].iloc[0:0]
    earnings_inputs["request_events"] = earnings_inputs["request_events"].iloc[0:0]
    result = settle_earnings(**earnings_inputs)
    assert result["earnings_ledger"].empty
    assert len(result["driver_income"]) == 3
    assert result["driver_income"].total_driver_pay.eq(0).all()
    assert result["result"]["summary"]["total_driver_pay"] == 0


def test_start_boundary_history_is_excluded_but_new_missing_completion_fails(earnings_inputs):
    earnings_inputs["requests"].loc[0, "completed_at"] = START
    earnings_inputs["request_events"] = earnings_inputs["request_events"].iloc[1:]
    with pytest.raises(ValueError, match="missing its settlement event"):
        settle_earnings(**earnings_inputs)
    earlier = "2024-01-26T07:59:00-05:00"
    earnings_inputs["requests"].loc[0, ["created_at", "assigned_at"]] = earlier
    result = settle_earnings(**earnings_inputs)
    assert result["earnings_ledger"].empty


def test_individual_income_rate_overflow_is_rejected(earnings_inputs):
    resolved = earnings_inputs["resolved"]
    spec = resolved["contract"] | {"baseline_fares": {"X": 1e308, "Y": 1}}
    policy = resolved["policy"] | {"baseline_multiplier_x": 1, "delta_price_x": 0}
    earnings_inputs["resolved"] = resolve_compensation(spec, policy)
    instant = "2024-01-26T13:00:00.000001+00:00"
    first = earnings_inputs["vehicle_intervals"].iloc[0].to_dict()
    second = first | {"start": instant, "state": "offline", "duration_hours": 1 - 1e-6 / 3600}
    first.update(end=instant, duration_hours=1e-6 / 3600)
    earnings_inputs["vehicle_intervals"] = pd.concat(
        [pd.DataFrame([first, second]), earnings_inputs["vehicle_intervals"].iloc[1:]],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="Driver income rate overflows"):
        settle_earnings(**earnings_inputs)


def test_nested_invalid_state_and_unassigned_active_request_fail_cleanly(earnings_inputs):
    earnings_inputs["requests"].at[0, "state"] = []
    with pytest.raises(ValueError, match="state is invalid"):
        settle_earnings(**earnings_inputs)
    earnings_inputs["requests"].at[0, "state"] = "completed"
    earnings_inputs["requests"].at[3, "state"] = "on_trip"
    with pytest.raises(ValueError, match="missing its driver assignment"):
        settle_earnings(**earnings_inputs)
