"""Read-only, checksum-verified operational simulation results."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import streamlit as st

from gsm_poc.core.artifacts import completed_run, read_json

TABLES = (
    "requests",
    "request_events",
    "vehicle_intervals",
    "driver_offers",
    "offer_events",
    "quote_terms",
    "driver_pay_terms",
    "earnings_ledger",
    "driver_income",
)


def load_simulation(workspace: Path, run_id: str) -> tuple[dict, dict, dict, dict]:
    manifest = completed_run(workspace, run_id, verify=True)
    if manifest.get("stages", {}).get("simulate_marketplace", {}).get("status") != "succeeded":
        raise ValueError("The selected run has no completed marketplace simulation")
    values = []
    for name in ("simulation_result.json", "simulation_spec.json", "end_snapshot.json"):
        relative = f"runs/{run_id}/{name}"
        if relative not in manifest["artifacts"]:
            raise ValueError(f"Required simulation artifact is not registered: {name}")
        value = read_json(workspace / relative)
        if not isinstance(value, dict):
            raise ValueError(f"Simulation artifact must be an object: {name}")
        values.append(value)
    result, spec, checkpoint = values
    if not isinstance(result.get("summary"), dict) or not isinstance(result.get("scope"), dict):
        raise ValueError("Simulation result is missing its summary or scope")
    for field in (
        "created_requests",
        "completed_trips",
        "open_requests_end",
        "canceled_requests",
        "expired_requests",
        "idle_hours",
        "mean_wait_seconds",
    ):
        value = result["summary"].get(field)
        if field == "mean_wait_seconds" and field in result["summary"] and value is None:
            continue
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid or missing simulation summary: {field}")
    if not {"vehicles", "horizon_start", "horizon_end"} <= set(result["scope"]):
        raise ValueError("Simulation result has an incomplete scope")
    if type(result["scope"]["vehicles"]) is not int or result["scope"]["vehicles"] < 0:
        raise ValueError("Simulation vehicle count must be nonnegative")
    if result.get("schema_version") == 3:
        if (
            type(result["scope"].get("online_drivers")) is not int
            or result["scope"]["online_drivers"] < 0
            or result["scope"].get("online_population_rule") != "fixed_roster"
        ):
            raise ValueError("Fixed-online simulation has an invalid online population")
        online_hours = result["summary"]["online_hours"]
        if (
            type(online_hours) not in (int, float)
            or not math.isfinite(online_hours)
            or online_hours < 0
        ):
            raise ValueError("Fixed-online simulation has invalid online hours")
        offers = result["offers"]
        for field in (
            "offered",
            "accepted",
            "rejected",
            "timed_out",
            "withdrawn",
            "pending_start",
            "pending_end",
            "acceptance_denominator",
        ):
            if type(offers[field]) is not int or offers[field] < 0:
                raise ValueError(f"Invalid offer count: {field}")
        denominator = offers["accepted"] + offers["rejected"] + offers["timed_out"]
        if denominator != offers["acceptance_denominator"]:
            raise ValueError("Offer acceptance denominator does not match resolved responses")
        rate = offers["acceptance_rate"]
        if (denominator == 0 and rate is not None) or (
            denominator > 0
            and (
                type(rate) not in (int, float)
                or not math.isfinite(rate)
                or not math.isclose(rate, offers["accepted"] / denominator)
            )
        ):
            raise ValueError("Invalid offer acceptance rate")
        if offers["offered"] + offers["pending_start"] != (
            denominator + offers["withdrawn"] + offers["pending_end"]
        ):
            raise ValueError("Offer accounting does not balance")
        for field in ("acceptance_population", "acceptance_status", "accounting"):
            if not isinstance(offers[field], str):
                raise ValueError(f"Offer acceptance scope is missing: {field}")
        for name in ("driver_offers.parquet", "driver_offers.csv"):
            if f"runs/{run_id}/{name}" not in manifest["artifacts"]:
                raise ValueError(f"Required driver-offer artifact is not registered: {name}")
    for field, expected in (
        ("source_kind", "synthetic"),
        ("evidence_level", "C"),
        ("calibration_status", "not_calibrated"),
        ("interval_status", "interval_unavailable"),
    ):
        if result.get(field) != expected:
            raise ValueError(f"Unexpected controlled simulation status: {field}")
    earnings = result.get("earnings")
    if earnings is not None:
        for field in ("total_driver_pay", "settled_completed_trips", "pay_per_presence_hour"):
            value = earnings["summary"][field]
            if field == "pay_per_presence_hour" and value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid driver-pay summary: {field}")
        if spec["compensation"]["contract"]["driver_fare_share"] != 1.0:
            raise ValueError("Controlled PoC requires the approved 100%-displayed-fare rule")
        for field in ("currency", "income_denominator"):
            if not isinstance(earnings[field], str):
                raise ValueError(f"Missing driver-pay units or denominator: {field}")
    return manifest, result, spec, checkpoint


def _number(value: Any, digits: int = 0) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def simulation_tab(
    workspace: Path, run_ids: list[str], initial_run_id: str | None, artifact_loader: Any
) -> None:
    st.subheader("Simulation results")
    if not run_ids:
        st.info("No completed marketplace simulation yet.")
        return
    initial = initial_run_id or st.query_params.get("simulation_run")
    selected = st.selectbox(
        "Simulation run ID", run_ids, index=run_ids.index(initial) if initial in run_ids else 0
    )
    st.query_params["simulation_run"] = selected
    try:
        manifest, result, spec, checkpoint = load_simulation(workspace, selected)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        st.error(f"Cannot display simulation: {exc}")
        return
    summary, scope = result["summary"], result["scope"]
    st.caption(
        "Evidence C · synthetic · not_calibrated · hypothetical services X/Y · "
        f"status {result.get('status', 'unavailable')}"
    )
    st.caption(f"Observation window: {scope['horizon_start']} to {scope['horizon_end']}")
    st.warning(
        "Operational confidence intervals are unavailable. Synthetic simulation does not "
        "establish GSM driver behavior or causal effects."
    )
    if result.get("schema_version") == 3:
        st.caption(
            "Fixed online roster, shared across X/Y; busy drivers are not available for a new trip."
        )
        st.caption(
            f"{scope['vehicles']} roster vehicles · "
            f"{_number(summary['online_hours'], 2)} online hours in the observation window."
        )
    else:
        st.caption(
            "Legacy fixed-supply fixture; its shift constraints are not a login/logout model."
        )
    c1, c2, c3, c4 = st.columns(4)
    if result.get("schema_version") == 3:
        c1.metric("Online drivers", _number(scope["online_drivers"]))
    else:
        c1.metric("Roster vehicles", _number(scope["vehicles"]))
    c2.metric("Created requests", _number(summary["created_requests"]))
    c3.metric("Completed trips", _number(summary["completed_trips"]))
    c4.metric("Open requests at end", _number(summary["open_requests_end"]))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean pickup wait (seconds)", _number(summary["mean_wait_seconds"], 1))
    c2.metric("Idle vehicle-hours", _number(summary["idle_hours"], 2))
    c3.metric("Canceled requests", _number(summary["canceled_requests"]))
    c4.metric("Expired requests", _number(summary["expired_requests"]))
    st.caption(result.get("wait_population", "Wait population unavailable"))
    st.caption(
        f"Observed waits: {summary.get('wait_observed_requests', 'unavailable')}; "
        f"censored waits: {summary.get('wait_censored_requests', 'unavailable')}. "
        "A missing wait is shown as unavailable, not zero."
    )
    prefix = f"runs/{selected}/"
    if result.get("schema_version") == 3:
        st.subheader("Driver offers")
        offers = result["offers"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("New offers", _number(offers["offered"]))
        c2.metric("Accepted offers", _number(offers["accepted"]))
        c3.metric("Rejected offers", _number(offers["rejected"]))
        c4.metric("Timed-out offers", _number(offers["timed_out"]))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Withdrawn offers", _number(offers["withdrawn"]))
        c2.metric("Pending offers at start", _number(offers["pending_start"]))
        c3.metric("Pending offers at end", _number(offers["pending_end"]))
        rate = offers["acceptance_rate"]
        c4.metric("Offer acceptance", "—" if rate is None else f"{rate:.1%}")
        st.caption(
            f"Acceptance denominator: {offers['acceptance_denominator']} "
            "accepted, rejected or timed-out offers; withdrawals and pending offers are excluded. "
            f"{offers['acceptance_population']}. Status: {offers['acceptance_status']}."
        )
        st.caption(offers["accounting"])
    else:
        st.info("This legacy run has no individual driver-offer records.")
    earnings = result.get("earnings")
    if earnings is not None:
        st.subheader("Gross driver pay")
        money = earnings["summary"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Gross driver pay", _number(money["total_driver_pay"], 2))
        c2.metric("Settled completed trips", _number(money["settled_completed_trips"]))
        c3.metric("Pay per presence hour", _number(money["pay_per_presence_hour"], 2))
        share = spec["compensation"]["contract"]["driver_fare_share"]
        st.caption(
            f"{earnings['currency']} · {share:.0%} of displayed fare · completed trips only. "
            f"{earnings['income_denominator']}. Gross pay is before costs; profit and ROI "
            "are not evaluated."
        )
    else:
        st.info("Driver pay was not evaluated for this run.")
    st.subheader("Data and exports")
    tables = [name for name in TABLES if f"{prefix}{name}.csv" in manifest["artifacts"]]
    if tables:
        selected_table = st.selectbox("Simulation data", tables)
        relative = f"{prefix}{selected_table}.csv"
        table = artifact_loader(workspace, manifest, relative)
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button(
            "Export simulation CSV",
            (workspace / relative).read_bytes(),
            f"{selected}_{selected_table}.csv",
            "text/csv",
        )
    for name, value in (
        ("result", result),
        ("spec", spec),
        ("checkpoint", checkpoint),
    ):
        with st.expander(f"Frozen simulation {name}"):
            st.json(value)
            st.download_button(
                f"Export simulation {name} JSON",
                json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                f"{selected}_{name}.json",
                "application/json",
            )
    with st.expander("Simulation audit"):
        st.json(
            {
                "run_id": manifest["run_id"],
                "simulation_source": manifest.get("simulation_source"),
                "environment": manifest.get("environment"),
                "stages": manifest["stages"],
            }
        )
