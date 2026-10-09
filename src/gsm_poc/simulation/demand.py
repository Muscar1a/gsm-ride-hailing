"""Bridge frozen choice predictions to fixed-population requests per hour."""

from __future__ import annotations

import copy
import dataclasses
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.core.artifacts import fingerprint
from gsm_poc.core.config import Config

if TYPE_CHECKING:
    from gsm_poc.causal.estimate import ModelBundle


@dataclasses.dataclass
class DemandPlan:
    frame: pd.DataFrame
    result: dict[str, Any]
    snapshot: dict[str, Any]
    spec: dict[str, Any]


def _timestamp(value: Any, timezone: str, field: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp with an explicit offset")
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(f"{field} must be an ISO timestamp with an explicit offset")
    local = timestamp.tz_convert(timezone)
    if timestamp.utcoffset() != local.utcoffset():
        raise ValueError(f"{field} offset differs from snapshot timezone {timezone}")
    return timestamp.tz_convert("UTC")


def validate_snapshot(snapshot: dict[str, Any], config: Config) -> dict[str, Any]:
    """Validate the initial fixed-roster subset; this does not calibrate operations."""
    required = {
        "schema_version",
        "snapshot_id",
        "source_kind",
        "evidence_level",
        "calibration_status",
        "timezone",
        "horizon_start",
        "horizon_end",
        "zone_ids",
        "service_ids",
        "exposure_mode",
        "demand_mode",
        "vehicles",
    }
    if not isinstance(snapshot, dict) or required - snapshot.keys():
        raise ValueError("Snapshot is missing required contract fields")
    if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
        raise ValueError("Unsupported snapshot schema_version")
    if not isinstance(snapshot["snapshot_id"], str) or not snapshot["snapshot_id"].strip():
        raise ValueError("snapshot_id must be a nonempty string")
    if (
        snapshot["source_kind"] != "synthetic"
        or snapshot["evidence_level"] != "C"
        or snapshot["calibration_status"] != "not_calibrated"
    ):
        raise ValueError("The initial roster fixture must be synthetic, C and not_calibrated")
    if snapshot["exposure_mode"] != "conditional_on_quote_population":
        raise ValueError("Only conditional_on_quote_population exposure is implemented")
    if snapshot["demand_mode"] != "reduced_form_policy":
        raise ValueError("Only reduced_form_policy demand is implemented")
    timezone = snapshot["timezone"]
    if not isinstance(timezone, str) or timezone != config.source.assumed_timezone:
        raise ValueError("Snapshot timezone must match the frozen choice source timezone")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown snapshot timezone: {timezone}") from exc
    start = _timestamp(snapshot["horizon_start"], timezone, "horizon_start")
    end = _timestamp(snapshot["horizon_end"], timezone, "horizon_end")
    if end <= start:
        raise ValueError("Snapshot horizon must have positive duration")
    zones = snapshot["zone_ids"]
    if (
        not isinstance(zones, list)
        or not zones
        or any(type(zone) is not int or zone <= 0 for zone in zones)
        or len(set(zones)) != len(zones)
        or not set(zones) <= set(config.source.zones)
    ):
        raise ValueError("Snapshot zone_ids must be unique zones within the frozen source scope")
    if snapshot["service_ids"] != ["X", "Y"]:
        raise ValueError("Snapshot service_ids must be X and Y in model order")
    vehicles = snapshot["vehicles"]
    if not isinstance(vehicles, list):
        raise ValueError("Snapshot vehicles must be a roster list")
    seen: dict[str, set[str]] = {key: set() for key in ("vehicle_id", "driver_id", "shift_id")}
    for vehicle in vehicles:
        fields = {*seen, "zone_id", "state", "soc", "eligible_services", "shift_start", "shift_end"}
        if not isinstance(vehicle, dict) or fields - vehicle.keys():
            raise ValueError("Vehicle roster entry is missing required fields")
        for key, identifiers in seen.items():
            value = vehicle[key]
            if not isinstance(value, str) or not value.strip() or value in identifiers:
                raise ValueError(f"Roster {key} must be nonempty and unique across shared services")
            identifiers.add(value)
        if type(vehicle["zone_id"]) is not int or vehicle["zone_id"] not in zones:
            raise ValueError("Vehicle initial zone_id is outside snapshot scope")
        eligibility = vehicle["eligible_services"]
        if (
            not isinstance(eligibility, list)
            or not eligibility
            or any(service not in ("X", "Y") for service in eligibility)
            or len(set(eligibility)) != len(eligibility)
        ):
            raise ValueError("Vehicle eligible_services must be a unique nonempty subset of X/Y")
        soc = vehicle["soc"]
        if type(soc) not in (float, int) or not np.isfinite(soc) or not 0 <= soc <= 1:
            raise ValueError("Vehicle soc must be finite and within [0, 1]")
        shift_start = _timestamp(vehicle["shift_start"], timezone, "shift_start")
        shift_end = _timestamp(vehicle["shift_end"], timezone, "shift_end")
        if shift_end <= shift_start:
            raise ValueError("Vehicle shift must have positive duration")
        if vehicle["state"] not in ("idle", "offline"):
            raise ValueError("The initial fixture supports idle/offline vehicle states only")
        if vehicle["state"] == "idle" and not shift_start <= start < shift_end:
            raise ValueError("An initially idle vehicle must be in shift at horizon_start")
    frozen = copy.deepcopy(snapshot)
    frozen.pop("snapshot_version", None)
    frozen["snapshot_version"] = fingerprint(frozen)
    return frozen


def _select_blocks(
    contexts: pd.DataFrame, snapshot: dict[str, Any], config: Config
) -> pd.DataFrame:
    required = {"dataset_id", "block_id", "zone_id", "slot_start_local", "n_sessions"}
    if required - set(contexts.columns):
        raise ValueError("Choice contexts are missing block keys, timestamps or n_sessions")
    if contexts[list(required)].isna().any().any():
        raise ValueError("Choice block keys, timestamps and session counts cannot be missing")
    if contexts.duplicated(["dataset_id", "block_id"]).any():
        raise ValueError("Choice contexts have duplicate block keys")
    starts = pd.to_datetime(contexts.slot_start_local, errors="raise")
    if starts.dt.tz is None:
        starts = starts.dt.tz_localize(snapshot["timezone"], ambiguous="raise", nonexistent="raise")
    starts = starts.dt.tz_convert("UTC")
    ends = starts + pd.Timedelta(minutes=config.simulation.slot_minutes)
    if pd.DataFrame({"zone_id": contexts.zone_id, "start": starts}).duplicated().any():
        raise ValueError("Choice contexts have duplicate zone/time blocks")
    start = _timestamp(snapshot["horizon_start"], snapshot["timezone"], "horizon_start")
    end = _timestamp(snapshot["horizon_end"], snapshot["timezone"], "horizon_end")
    mask = contexts.zone_id.isin(snapshot["zone_ids"]) & (starts < end) & (ends > start)
    selected = contexts.loc[mask].copy()
    selected["block_start"] = starts.loc[mask]
    selected["block_end"] = ends.loc[mask]
    selected = selected.sort_values(["zone_id", "block_start"]).reset_index(drop=True)
    for zone in snapshot["zone_ids"]:
        blocks = selected[selected.zone_id == zone]
        if (
            blocks.empty
            or blocks.block_start.iloc[0] != start
            or blocks.block_end.iloc[-1] != end
            or not np.array_equal(
                blocks.block_start.iloc[1:].to_numpy(), blocks.block_end.iloc[:-1].to_numpy()
            )
        ):
            raise ValueError("Choice blocks must cover each zone and tile the snapshot horizon")
    if not pd.api.types.is_numeric_dtype(selected.n_sessions) or pd.api.types.is_bool_dtype(
        selected.n_sessions
    ):
        raise ValueError("Block n_sessions must contain numeric counts, not strings or booleans")
    sessions = selected.n_sessions.to_numpy(float)
    if (
        not np.isfinite(sessions).all()
        or (sessions < 0).any()
        or not np.equal(sessions, np.floor(sessions)).all()
    ):
        raise ValueError("Block n_sessions must be finite nonnegative integer counts")
    return selected


def prepare_demand_plan(
    bundle: ModelBundle | None,
    contexts: pd.DataFrame,
    snapshot: dict[str, Any],
    request: ScenarioRequest,
    config: Config,
    model_run_id: str,
    model_version: str | None,
    source_version: str,
) -> DemandPlan:
    snapshot = validate_snapshot(snapshot, config)
    blocks = _select_blocks(contexts, snapshot, config)
    if bundle is not None and (
        not blocks.dataset_id.eq(bundle.dataset_id).all()
        or bundle.source_kind not in ("synthetic", "semi_synthetic")
        or bundle.outcome_order != ("X", "Y")
        or bundle.treatment_order != ("X", "Y")
    ):
        raise ValueError("Choice bundle dataset, source kind or service order is incompatible")
    # Support/probability gates inspect every context. Exposure comes from each
    # frozen block, never the aggregate ScenarioRequest.n_sessions assumption.
    gate = scenario(
        bundle,
        blocks.drop(columns="n_sessions"),
        dataclasses.replace(request, n_sessions=1),
        config,
        model_run_id,
    )
    status = gate.get("support_status", gate["status"])
    if gate["status"] not in ("ok", "interval_unstable", "insufficient_support"):
        status = gate["status"]
    usable = status == "ok" and bundle is not None
    policy = dataclasses.asdict(request)
    policy.pop("n_sessions")
    spec = {
        "schema_version": 1,
        "model_run_id": model_run_id,
        "model_version": model_version,
        "source_version": source_version,
        "snapshot_version": snapshot["snapshot_version"],
        "policy": policy,
        "policy_version": fingerprint(policy),
        "exposure_mode": snapshot["exposure_mode"],
        "demand_mode": snapshot["demand_mode"],
        "units": {"request_rate": "requests/hour", "block_duration": "hours"},
        "population": "fixed quote sessions in each frozen zone/time block",
        "block_rule": "full frozen blocks only; no horizon clipping or exposure extrapolation",
        "price_application": "choice probabilities once; no additional elasticity multiplier",
        "interval_status": "interval_unavailable",
        "interval_reason": "This bridge exports point estimates, without block-rate intervals",
    }
    version = fingerprint(spec)
    source_kind = bundle.source_kind if bundle else gate["source_kind"]
    before = after = None
    if usable:
        assert bundle is not None
        baseline = np.array([request.baseline_multiplier_x, request.baseline_multiplier_y])
        target = baseline * (1 + np.array([request.delta_price_x, request.delta_price_y]))
        before = bundle.probabilities(blocks, np.log(baseline))
        after = bundle.probabilities(blocks, np.log(target))
    rows, block_results = [], []
    for index, (_, block) in enumerate(blocks.iterrows()):
        count = int(block.n_sessions)
        hours = (block.block_end - block.block_start).total_seconds() / 3600
        block_result: dict[str, Any] = {
            "zone_id": int(block.zone_id),
            "source_block_id": str(block.block_id),
            "block_start": block.block_start.isoformat(),
            "block_end": block.block_end.isoformat(),
            "quote_sessions": count,
            "status": status,
            "choices": None,
        }
        if usable:
            assert before is not None and after is not None
            block_result["choices"] = {
                service: {
                    "baseline_probability": float(before[index, j]),
                    "probability": float(after[index, j]),
                    "baseline_expected_choices": float(before[index, j] * count),
                    "expected_choices": float(after[index, j] * count),
                }
                for j, service in enumerate(("X", "Y", "NONE"))
            }
        block_results.append(block_result)
        for service in ("X", "Y"):
            choices = block_result["choices"]
            expected = choices[service]["expected_choices"] if choices else None
            baseline_expected = choices[service]["baseline_expected_choices"] if choices else None
            rows.append(
                {
                    "schema_version": 1,
                    "demand_plan_version": version,
                    "zone_id": int(block.zone_id),
                    "service_id": service,
                    "block_start": block.block_start,
                    "block_end": block.block_end,
                    "block_hours": hours,
                    "quote_sessions": count,
                    "request_rate": expected / hours if expected is not None else None,
                    "baseline_request_rate": (
                        baseline_expected / hours if baseline_expected is not None else None
                    ),
                    "expected_bookings": expected,
                    "baseline_expected_bookings": baseline_expected,
                    "source_block_id": str(block.block_id),
                    "model_run_id": model_run_id,
                    "model_version": model_version,
                    "source_version": source_version,
                    "snapshot_id": snapshot["snapshot_id"],
                    "policy_version": spec["policy_version"],
                    "exposure_mode": snapshot["exposure_mode"],
                    "demand_mode": snapshot["demand_mode"],
                    "source_kind": source_kind,
                    "evidence_level": "C",
                    "status": status,
                    "support_status": gate.get("support_status", status),
                    "interval_status": "interval_unavailable",
                }
            )
    frame = pd.DataFrame(rows)
    summary = {
        "quote_sessions": sum(block["quote_sessions"] for block in block_results),
        "baseline_expected_bookings": (
            float(frame.baseline_expected_bookings.sum()) if usable else None
        ),
        "expected_bookings": float(frame.expected_bookings.sum()) if usable else None,
        "expected_outside_choices": (
            sum(block["choices"]["NONE"]["expected_choices"] for block in block_results)
            if usable
            else None
        ),
    }
    result = {
        "schema_version": 1,
        "demand_plan_version": version,
        "status": status,
        "usable_for_simulation": usable,
        "reasons": [reason for reason in gate.get("reasons", []) if "Bootstrap" not in reason],
        "model_run_id": model_run_id,
        "snapshot_id": snapshot["snapshot_id"],
        "scope": {"zones": snapshot["zone_ids"], "blocks": len(blocks)},
        "source_kind": source_kind,
        "evidence_level": "C",
        "summary": summary,
        "interval_status": spec["interval_status"],
        "interval_reason": spec["interval_reason"],
        "interpretation": "Expected requests, not completed trips; NONE produces no requests",
        "blocks": block_results,
    }
    return DemandPlan(frame, result, snapshot, spec)
