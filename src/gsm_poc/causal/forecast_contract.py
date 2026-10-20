"""Forecast contract definitions, context selection, and schema_version=2 conversion."""

from __future__ import annotations

import hashlib
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd


def parse_horizon_timestamp(value: Any, timezone_name: str, field_name: str) -> pd.Timestamp:
    """Validate and convert an ISO timestamp string with an explicit timezone offset."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO timestamp string with an explicit offset")
    try:
        ts = pd.Timestamp(value)
    except Exception as exc:
        raise ValueError(f"{field_name} is not a valid ISO timestamp: {exc}") from exc
    if pd.isna(ts) or ts.tzinfo is None:
        raise ValueError(f"{field_name} must be an ISO timestamp with an explicit offset")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown source timezone: {timezone_name}") from exc
    local = ts.tz_convert(timezone_name)
    if ts.utcoffset() != local.utcoffset():
        raise ValueError(
            f"{field_name} offset {ts.strftime('%z')} differs from source timezone "
            f"{timezone_name} offset {local.strftime('%z')} at this time (DST mismatch)"
        )
    return ts.tz_convert("UTC")


def select_scenario_contexts(
    contexts: pd.DataFrame,
    target_context_set: str = "all",
    zone: int | None = None,
    horizon_start: str | None = None,
    horizon_end: str | None = None,
    *,
    timezone: str = "America/New_York",
    slot_minutes: int = 60,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Select context blocks by zone and offset-aware horizon boundaries."""
    if contexts.empty:
        raise ValueError("No selected scenario context")

    resolved_zone = zone
    if target_context_set.startswith("zone_"):
        extracted = int(target_context_set.removeprefix("zone_"))
        if resolved_zone is not None and resolved_zone != extracted:
            raise ValueError("Requested zone conflicts with target_context_set")
        resolved_zone = extracted

    selected = contexts.copy()
    if resolved_zone is not None:
        if "zone_id" not in selected.columns:
            raise ValueError("Contexts lack zone_id column")
        selected = selected[selected.zone_id == resolved_zone]
        if selected.empty:
            raise ValueError(f"Selected zone {resolved_zone} has no scenario contexts")

    has_horizon = horizon_start is not None or horizon_end is not None
    if has_horizon and (horizon_start is None or horizon_end is None):
        raise ValueError("horizon_start and horizon_end must both be provided or both omitted")

    actual_start: str = "unavailable"
    actual_end: str = "unavailable"
    actual_tz: str = timezone if timezone else "unavailable"

    if "slot_start_local" in selected.columns and not selected.empty:
        try:
            raw_starts = pd.to_datetime(selected.slot_start_local, errors="raise")
            if raw_starts.dt.tz is None:
                localized_starts = raw_starts.dt.tz_localize(
                    timezone, ambiguous="raise", nonexistent="raise"
                )
            else:
                localized_starts = raw_starts.dt.tz_convert(timezone)
            starts_utc = localized_starts.dt.tz_convert("UTC")
            ends_utc = starts_utc + pd.Timedelta(minutes=slot_minutes)
            selected["_block_start_utc"] = starts_utc
            selected["_block_end_utc"] = ends_utc
            selected["_block_start_local"] = localized_starts
            selected["_block_end_local"] = localized_starts + pd.Timedelta(minutes=slot_minutes)
        except Exception as exc:
            if has_horizon:
                raise ValueError(f"Failed to parse context timestamps: {exc}") from exc
            starts_utc = None
    else:
        if has_horizon:
            raise ValueError("Filtering by horizon requires timestamp columns in scenario contexts")
        starts_utc = None

    if has_horizon:
        assert horizon_start is not None and horizon_end is not None
        req_start_utc = parse_horizon_timestamp(horizon_start, timezone, "horizon_start")
        req_end_utc = parse_horizon_timestamp(horizon_end, timezone, "horizon_end")
        if req_end_utc <= req_start_utc:
            raise ValueError("horizon_end must be strictly after horizon_start")

        if (
            pd.DataFrame({"zone_id": selected.zone_id, "start": selected._block_start_utc})
            .duplicated()
            .any()
        ):
            raise ValueError("Choice contexts have duplicate zone/time blocks")

        if resolved_zone is not None:
            expected_zones = [resolved_zone]
        else:
            expected_zones = (
                sorted(int(z) for z in selected.zone_id.unique())
                if "zone_id" in selected.columns
                else []
            )

        mask = (selected._block_start_utc >= req_start_utc) & (
            selected._block_end_utc <= req_end_utc
        )
        selected = selected.loc[mask].copy()
        if selected.empty:
            raise ValueError("No context blocks cover the requested horizon")

        selected = selected.sort_values(["zone_id", "_block_start_utc"]).reset_index(drop=True)
        for z in expected_zones:
            z_blocks = selected[selected.zone_id == z]
            if z_blocks.empty:
                raise ValueError(f"Zone {z} has no context blocks covering the requested horizon")
            if z_blocks._block_start_utc.iloc[0] != req_start_utc:
                raise ValueError(
                    f"Requested horizon_start {horizon_start} does not align with block boundary "
                    f"{z_blocks._block_start_local.iloc[0].isoformat()}"
                )
            if z_blocks._block_end_utc.iloc[-1] != req_end_utc:
                raise ValueError(
                    f"Requested horizon_end {horizon_end} does not align with block boundary "
                    f"{z_blocks._block_end_local.iloc[-1].isoformat()}"
                )
            if not np.array_equal(
                z_blocks._block_start_utc.iloc[1:].to_numpy(),
                z_blocks._block_end_utc.iloc[:-1].to_numpy(),
            ):
                raise ValueError(
                    f"Context blocks for zone {z} do not continuously tile the requested horizon"
                )

        actual_start = horizon_start
        actual_end = horizon_end
    elif starts_utc is not None and not selected.empty:
        actual_start = selected._block_start_local.min().isoformat()
        actual_end = selected._block_end_local.max().isoformat()

    cols_to_drop = [c for c in selected.columns if c.startswith("_block_")]
    cleaned = selected.drop(columns=cols_to_drop).reset_index(drop=True)

    zones_list = (
        sorted(int(z) for z in cleaned.zone_id.unique()) if "zone_id" in cleaned.columns else []
    )
    weights = (
        cleaned.n_sessions.to_numpy(float)
        if "n_sessions" in cleaned.columns
        else np.ones(len(cleaned))
    )
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Scenario context session weights must be positive and finite")

    block_ids = [str(b) for b in cleaned.block_id.tolist()] if "block_id" in cleaned.columns else []
    block_id_str = ",".join(sorted(block_ids))
    selected_blocks_sha256 = (
        hashlib.sha256(block_id_str.encode("utf-8")).hexdigest() if block_ids else "unavailable"
    )

    scope_info: dict[str, Any] = {
        "target_context_set": target_context_set,
        "zones": zones_list,
        "selected_zone": resolved_zone,
        "services": ["X", "Y"],
        "timezone": actual_tz,
        "horizon_start": actual_start,
        "horizon_end": actual_end,
        "context_blocks": int(len(cleaned)),
        "context_weight_sessions": int(weights.sum()),
        "selected_block_ids": block_ids,
        "selected_blocks_sha256": selected_blocks_sha256,
    }
    return cleaned, scope_info


def make_metric_record(
    *,
    metric_id: str,
    service: str,
    period: str,
    estimate: float | None,
    unit: str,
    status: str,
    identification_status: str,
    support_status: str,
    interval_status: str,
    interval: dict[str, float] | None,
    reasons: list[str],
) -> dict[str, Any]:
    """Build a standardized metric item."""
    return {
        "metric_id": metric_id,
        "service": service,
        "period": period,
        "estimate": estimate if estimate is not None and np.isfinite(estimate) else None,
        "unit": unit,
        "status": status,
        "identification_status": identification_status,
        "support_status": support_status,
        "interval_status": interval_status,
        "interval": interval,
        "reasons": list(reasons),
    }


def metrics_to_frame(forecast_result: dict[str, Any]) -> pd.DataFrame:
    """Convert forecast_result['metrics'] into a tabular DataFrame for scenario_metrics.csv."""
    metrics_dict = forecast_result.get("metrics")
    if metrics_dict is None and isinstance(forecast_result, dict):
        if any(isinstance(v, dict) and "unit" in v for v in forecast_result.values()):
            metrics_dict = forecast_result
    if metrics_dict is None:
        metrics_dict = {}
    scope = forecast_result.get("scope", {})
    prov = forecast_result.get("provenance", {})
    rows = []
    level = forecast_result.get("interval_level", 0.95)

    for metric_id, item in metrics_dict.items():
        interval = item.get("interval") or {}
        lower = interval.get("lower")
        upper = interval.get("upper")
        est = item.get("estimate")

        rows.append(
            {
                "metric_id": metric_id,
                "service": item.get("service", ""),
                "period": item.get("period", ""),
                "estimate": f"{est:.8f}" if est is not None else "",
                "unit": item.get("unit", ""),
                "status": item.get("status", ""),
                "identification_status": item.get("identification_status", ""),
                "support_status": item.get("support_status", ""),
                "interval_status": item.get("interval_status", ""),
                "ci_lower": f"{lower:.8f}" if lower is not None else "",
                "ci_upper": f"{upper:.8f}" if upper is not None else "",
                "interval_level": str(level),
                "reasons": "; ".join(item.get("reasons", [])),
                "zone_id": str(scope.get("selected_zone") or scope.get("target_context_set", "")),
                "horizon_start": str(scope.get("horizon_start", "")),
                "horizon_end": str(scope.get("horizon_end", "")),
                "run_id": str(prov.get("run_id") or forecast_result.get("run_id", "")),
                "estimator": str(prov.get("estimator") or forecast_result.get("estimator", "")),
            }
        )
    return pd.DataFrame(rows)


def format_scenario_metrics_csv(forecast_result: dict[str, Any]) -> str:
    """Return CSV text representation of scenario_metrics."""
    return metrics_to_frame(forecast_result).to_csv(index=False)
