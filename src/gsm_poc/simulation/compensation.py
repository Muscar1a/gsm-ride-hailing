"""Declared synthetic fares and completed-trip pay under a 100% driver share."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pandas as pd

from gsm_poc.core.artifacts import fingerprint
from gsm_poc.simulation.rules import parse_timestamp


def _amount(value: Any, field: str) -> float:
    if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return float(value)


def validate_compensation(spec: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version",
        "compensation_id",
        "source_kind",
        "evidence_level",
        "calibration_status",
        "currency",
        "driver_fare_share",
        "baseline_fares",
        "settlement_rule",
        "cancel_payment",
    }
    if not isinstance(spec, dict) or set(spec) != fields:
        raise ValueError("Compensation has missing or unknown contract fields")
    fixed = {
        "schema_version": 1,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "currency": "SYNTHETIC_UNIT",
        "settlement_rule": "completed_only",
    }
    if type(spec["schema_version"]) is not int or any(spec[k] != v for k, v in fixed.items()):
        raise ValueError("Only the declared synthetic completed-only compensation is supported")
    if not isinstance(spec["compensation_id"], str) or not spec["compensation_id"].strip():
        raise ValueError("compensation_id must be a nonempty string")
    if _amount(spec["driver_fare_share"], "driver_fare_share") != 1:
        raise ValueError("driver_fare_share must be 1.0 (100% of displayed fare)")
    if _amount(spec["cancel_payment"], "cancel_payment") != 0:
        raise ValueError("cancel_payment must be zero under the initial declared rule")
    fares = spec["baseline_fares"]
    if not isinstance(fares, dict) or set(fares) != {"X", "Y"}:
        raise ValueError("baseline_fares must contain exactly X and Y")
    normalized = copy.deepcopy(spec)
    normalized.update(
        driver_fare_share=1.0,
        cancel_payment=0.0,
        baseline_fares={
            service: _amount(fares[service], f"{service} fare") for service in ("X", "Y")
        },
    )
    return normalized


def resolve_compensation(spec: dict[str, Any], demand_policy: dict[str, Any]) -> dict[str, Any]:
    contract = validate_compensation(spec)
    policy: dict[str, float] = {}
    if not isinstance(demand_policy, dict):
        raise ValueError("Compensation requires a complete X/Y demand policy")
    for service in ("x", "y"):
        for key, lower_bound in (
            (f"baseline_multiplier_{service}", 0),
            (f"delta_price_{service}", -1),
        ):
            if key not in demand_policy:
                raise ValueError(f"Compensation policy is missing {key}")
            value = demand_policy[key]
            if type(value) not in (int, float) or not np.isfinite(value) or value <= lower_bound:
                raise ValueError(
                    f"Compensation policy {key} must be finite and above {lower_bound}"
                )
            policy[key] = float(value)
    fares = {
        service.upper(): contract["baseline_fares"][service.upper()]
        * policy[f"baseline_multiplier_{service}"]
        * (1 + policy[f"delta_price_{service}"])
        for service in ("x", "y")
    }
    if any(not np.isfinite(value) for value in fares.values()):
        raise ValueError("Effective fares overflow their finite monetary units")
    payload = {"contract": contract, "effective_fares": fares, "policy": policy}
    return payload | {
        "compensation_version": fingerprint(contract),
        "terms_version": fingerprint(payload),
    }


def _required(frame: pd.DataFrame, fields: set[str], label: str) -> None:
    if not isinstance(frame, pd.DataFrame) or fields - set(frame.columns):
        raise ValueError(f"{label} is missing required fields")


def settle_earnings(
    requests: pd.DataFrame,
    request_events: pd.DataFrame,
    vehicle_intervals: pd.DataFrame,
    snapshot: dict[str, Any],
    resolved: dict[str, Any],
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    """Settle this window's completion events; historical terminal records are not paid again."""
    if (
        not isinstance(resolved, dict)
        or set(resolved)
        != {"contract", "effective_fares", "policy", "compensation_version", "terms_version"}
        or resolved != resolve_compensation(resolved["contract"], resolved["policy"])
    ):
        raise ValueError("Resolved compensation terms or versions are inconsistent")
    start, end = (
        parse_timestamp(window_start, "window_start"),
        parse_timestamp(window_end, "window_end"),
    )
    if end <= start:
        raise ValueError("Earnings window must have positive duration")
    vehicles = snapshot.get("vehicles") if isinstance(snapshot, dict) else None
    if not isinstance(vehicles, list):
        raise ValueError("Earnings require an explicit vehicle/driver/shift roster")
    roster: dict[str, dict[str, Any]] = {}
    seen_drivers: set[str] = set()
    seen_shifts: set[str] = set()
    for vehicle in vehicles:
        if not isinstance(vehicle, dict) or any(
            not isinstance(vehicle.get(key), str) or not vehicle[key].strip()
            for key in ("vehicle_id", "driver_id", "shift_id")
        ):
            raise ValueError("Earnings roster identifiers are invalid")
        if (
            vehicle["vehicle_id"] in roster
            or vehicle["driver_id"] in seen_drivers
            or vehicle["shift_id"] in seen_shifts
        ):
            raise ValueError("Earnings roster has duplicate vehicle, driver or shift identifiers")
        roster[vehicle["vehicle_id"]] = vehicle
        seen_drivers.add(vehicle["driver_id"])
        seen_shifts.add(vehicle["shift_id"])

    _required(
        requests,
        {
            "request_id",
            "created_at",
            "service_id",
            "state",
            "vehicle_id",
            "assigned_at",
            "completed_at",
        },
        "Requests",
    )
    _required(request_events, {"request_id", "timestamp", "state", "vehicle_id"}, "Request events")
    _required(
        vehicle_intervals,
        {"vehicle_id", "driver_id", "shift_id", "state", "start", "end", "duration_hours"},
        "Vehicle intervals",
    )
    if requests.request_id.duplicated().any():
        raise ValueError("Earnings requests contain duplicate request IDs")
    records: dict[str, dict[str, Any]] = {}
    quote_rows, term_rows, ledger_rows = [], [], []
    versions = {key: resolved[key] for key in ("compensation_version", "terms_version")}
    currency = resolved["contract"]["currency"]
    states = {
        "created",
        "queued",
        "assigned",
        "pickup",
        "on_trip",
        "completed",
        "canceled",
        "expired",
    }
    for row in requests.to_dict("records"):
        if (
            not isinstance(row["request_id"], str)
            or not row["request_id"].strip()
            or not isinstance(row["service_id"], str)
            or row["service_id"] not in ("X", "Y")
            or not isinstance(row["state"], str)
            or row["state"] not in states
        ):
            raise ValueError("Earnings request ID, service or state is invalid")
        created = parse_timestamp(row["created_at"], "created_at")
        if created >= end:
            raise ValueError("Earnings request was created outside the observed window")
        amount = resolved["effective_fares"][row["service_id"]]
        quote_rows.append(
            {
                "request_id": row["request_id"],
                "service_id": row["service_id"],
                "quote_at": created.isoformat(),
                "displayed_fare": amount,
                "currency": currency,
                **versions,
            }
        )
        vehicle_id = row["vehicle_id"]
        assigned = (
            None
            if pd.isna(row["assigned_at"])
            else parse_timestamp(row["assigned_at"], "assigned_at")
        )
        if assigned is not None:
            if (
                not isinstance(vehicle_id, str)
                or vehicle_id not in roster
                or not created <= assigned <= end
            ):
                raise ValueError("Assigned driver terms have unknown vehicle or invalid time")
            vehicle = roster[vehicle_id]
            term_rows.append(
                {
                    "request_id": row["request_id"],
                    "vehicle_id": vehicle_id,
                    "driver_id": vehicle["driver_id"],
                    "shift_id": vehicle["shift_id"],
                    "service_id": row["service_id"],
                    "offer_at": assigned.isoformat(),
                    "offered_driver_pay": amount,
                    "currency": currency,
                    **versions,
                }
            )
        elif pd.notna(vehicle_id):
            raise ValueError("Request vehicle has no assignment time")
        if row["state"] in {"assigned", "pickup", "on_trip"} and assigned is None:
            raise ValueError("Active request is missing its driver assignment")
        completed = (
            None
            if pd.isna(row["completed_at"])
            else parse_timestamp(row["completed_at"], "completed_at")
        )
        if row["state"] == "completed":
            if completed is None or assigned is None or not assigned <= completed <= end:
                raise ValueError("Completed request has inconsistent assignment/completion times")
        elif completed is not None:
            raise ValueError("Noncompleted request has a completion time")
        records[row["request_id"]] = row

    settled: set[str] = set()
    for event in request_events.to_dict("records"):
        request_id = event["request_id"]
        if (
            not isinstance(request_id, str)
            or request_id not in records
            or not isinstance(event["state"], str)
            or event["state"] not in states
        ):
            raise ValueError("Earnings event has unknown request or invalid state")
        timestamp = parse_timestamp(event["timestamp"], "event timestamp")
        if not start <= timestamp <= end:
            raise ValueError("Earnings event is outside the settlement window")
        if pd.notna(event["vehicle_id"]) and (
            not isinstance(event["vehicle_id"], str) or event["vehicle_id"] not in roster
        ):
            raise ValueError("Earnings event has an unknown vehicle")
        if event["state"] != "completed":
            continue
        row = records[request_id]
        if request_id in settled:
            raise ValueError("Duplicate completed event would settle driver earnings twice")
        if (
            row["state"] != "completed"
            or parse_timestamp(row["completed_at"], "completed_at") != timestamp
            or event["vehicle_id"] != row["vehicle_id"]
        ):
            raise ValueError("Completion event differs from the request record")
        vehicle = roster[row["vehicle_id"]]
        amount = resolved["effective_fares"][row["service_id"]]
        ledger_rows.append(
            {
                "ledger_id": fingerprint(
                    {
                        "request_id": request_id,
                        "completed_at": timestamp.isoformat(),
                        "terms_version": resolved["terms_version"],
                    }
                ),
                "request_id": request_id,
                "vehicle_id": row["vehicle_id"],
                "driver_id": vehicle["driver_id"],
                "shift_id": vehicle["shift_id"],
                "service_id": row["service_id"],
                "completed_at": timestamp.isoformat(),
                "settled_at": timestamp.isoformat(),
                "rider_payment": amount,
                "driver_pay": amount,
                "currency": currency,
                **versions,
            }
        )
        settled.add(request_id)
    if any(
        row["state"] == "completed"
        and (
            start < parse_timestamp(row["completed_at"], "completed_at") <= end
            or parse_timestamp(row["created_at"], "created_at") >= start
        )
        and request_id not in settled
        for request_id, row in records.items()
    ):
        raise ValueError("Completed request is missing its settlement event")

    presence = dict.fromkeys(roster, 0.0)
    intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {key: [] for key in roster}
    for row in vehicle_intervals.to_dict("records"):
        vehicle_id = row["vehicle_id"]
        if not isinstance(vehicle_id, str) or vehicle_id not in roster:
            raise ValueError("Income interval has an unknown vehicle")
        vehicle = roster[vehicle_id]
        if (
            row["driver_id"] != vehicle["driver_id"]
            or row["shift_id"] != vehicle["shift_id"]
            or not isinstance(row["state"], str)
            or row["state"]
            not in {"idle", "dispatch", "to_pickup", "on_trip", "offline", "unavailable"}
        ):
            raise ValueError("Income interval driver/shift/state differs from the roster")
        beginning, ending = (
            parse_timestamp(row["start"], "interval start"),
            parse_timestamp(row["end"], "interval end"),
        )
        duration = row["duration_hours"]
        if (
            type(duration) not in (int, float)
            or not np.isfinite(duration)
            or not start <= beginning < ending <= end
            or not np.isclose(
                duration, (ending.value - beginning.value) / 3.6e12, rtol=1e-10, atol=1e-10
            )
        ):
            raise ValueError("Income interval duration is invalid or inconsistent")
        intervals[vehicle_id].append((beginning, ending))
        if row["state"] != "offline":
            presence[vehicle_id] += float(duration)
    income_rows = []
    for vehicle_id, vehicle in sorted(roster.items()):
        periods = sorted(intervals[vehicle_id])
        if (
            not periods
            or periods[0][0] != start
            or periods[-1][1] != end
            or any(a[1] != b[0] for a, b in zip(periods, periods[1:], strict=False))
        ):
            raise ValueError("Income intervals leave gaps or overlap within the window")
        payments = [row["driver_pay"] for row in ledger_rows if row["vehicle_id"] == vehicle_id]
        total = float(sum(payments))
        if not np.isfinite(total):
            raise ValueError("Driver payment total overflows its monetary units")
        hours = presence[vehicle_id]
        rate = total / hours if hours > 0 else None
        if rate is not None and not np.isfinite(rate):
            raise ValueError("Driver income rate overflows its monetary units")
        income_rows.append(
            {
                "vehicle_id": vehicle_id,
                "driver_id": vehicle["driver_id"],
                "shift_id": vehicle["shift_id"],
                "completed_trips": len(payments),
                "total_driver_pay": total,
                "presence_hours": hours,
                "pay_per_presence_hour": rate,
                "income_rate_status": "ok" if hours > 0 else "unavailable_zero_presence",
                "currency": currency,
                **versions,
            }
        )

    columns = {
        "quote_terms": [
            "request_id",
            "service_id",
            "quote_at",
            "displayed_fare",
            "currency",
            *versions,
        ],
        "driver_pay_terms": [
            "request_id",
            "vehicle_id",
            "driver_id",
            "shift_id",
            "service_id",
            "offer_at",
            "offered_driver_pay",
            "currency",
            *versions,
        ],
        "earnings_ledger": [
            "ledger_id",
            "request_id",
            "vehicle_id",
            "driver_id",
            "shift_id",
            "service_id",
            "completed_at",
            "settled_at",
            "rider_payment",
            "driver_pay",
            "currency",
            *versions,
        ],
        "driver_income": [
            "vehicle_id",
            "driver_id",
            "shift_id",
            "completed_trips",
            "total_driver_pay",
            "presence_hours",
            "pay_per_presence_hour",
            "income_rate_status",
            "currency",
            *versions,
        ],
    }
    frames = {
        name: pd.DataFrame(rows, columns=pd.Index(columns[name]))
        for name, rows in zip(
            columns,
            (
                sorted(quote_rows, key=lambda r: r["request_id"]),
                sorted(term_rows, key=lambda r: r["request_id"]),
                sorted(ledger_rows, key=lambda r: (r["completed_at"], r["request_id"])),
                income_rows,
            ),
            strict=True,
        )
    }
    total_pay = float(sum(row["driver_pay"] for row in ledger_rows))
    total_hours = float(sum(presence.values()))
    if (
        not np.isfinite(total_pay)
        or not np.isfinite(total_hours)
        or (total_hours > 0 and not np.isfinite(total_pay / total_hours))
    ):
        raise ValueError("Earnings summary overflows its declared units")
    result = {
        "schema_version": 1,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "currency": currency,
        **versions,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "settlement_scope": "completion events in this window; carry-in history is not paid again",
        "income_denominator": (
            "all roster drivers; nonoffline presence hours including zero-trip idle time"
        ),
        "summary": {
            "quoted_requests": len(quote_rows),
            "assigned_driver_terms": len(term_rows),
            "settled_completed_trips": len(ledger_rows),
            "simulated_completed_fare_value": total_pay,
            "total_driver_pay": total_pay,
            "presence_hours": total_hours,
            "pay_per_presence_hour": total_pay / total_hours if total_hours > 0 else None,
        },
        "units": {
            "fare_and_pay": currency,
            "presence": "hours",
            "income_rate": f"{currency}/presence_hour",
        },
        "profit_status": "not_evaluated",
        "roi_status": "not_evaluated",
        "income_elasticity_status": "not_identified",
        "interval_status": "interval_unavailable",
        "interpretation": (
            "Realized synthetic gross driver pay, before costs; "
            "not GSM policy, net income or an income response estimate"
        ),
    }
    return frames | {"result": result}
