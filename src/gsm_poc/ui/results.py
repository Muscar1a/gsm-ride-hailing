"""Checksum-verified operational results, independent of the web framework."""

from __future__ import annotations

import math
from pathlib import Path

from gsm_poc.core.artifacts import completed_run, read_json


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
