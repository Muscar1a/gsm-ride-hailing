"""Validation and normalization of simulation operational rules and OD matrices."""

from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pandas as pd


def parse_timestamp(value: Any, field: str) -> pd.Timestamp:
    if not isinstance(value, (str, pd.Timestamp)):
        raise ValueError(f"{field} must be an offset-aware timestamp")
    parsed = pd.Timestamp(value)
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f"{field} must be an offset-aware timestamp")
    return parsed.tz_convert("UTC")


def validate_rules(rules: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "rules_id",
        "source_kind",
        "evidence_level",
        "calibration_status",
        "arrival_process",
        "matching_rule",
        "acceptance_rule",
        "shift_end_rule",
        "boundary_rule",
        "max_pickup_seconds",
        "minimum_soc",
        "max_requests",
        "max_events",
        "max_seconds",
        "travel_times",
    }
    if not isinstance(rules, dict) or set(rules) != required:
        raise ValueError("Simulation rules have missing or unknown contract fields")
    fixed = {
        "schema_version": 1,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "arrival_process": "piecewise_poisson",
        "matching_rule": "fifo_min_pickup_eta",
        "acceptance_rule": "immediate",
        "shift_end_rule": "finish_within_shift",
        "boundary_rule": "closed_cluster",
    }
    if type(rules["schema_version"]) is not int or any(rules[k] != v for k, v in fixed.items()):
        raise ValueError("Unsupported synthetic fixed-supply simulation rules")
    if not isinstance(rules["rules_id"], str) or not rules["rules_id"].strip():
        raise ValueError("rules_id must be a nonempty string")
    for key in ("max_pickup_seconds", "minimum_soc", "max_seconds"):
        value = rules[key]
        if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be finite and nonnegative")
    if rules["minimum_soc"] > 1 or not 0 < rules["max_seconds"] <= 600:
        raise ValueError("minimum_soc must be within [0, 1]; max_seconds must be in (0, 600]")
    for key in ("max_requests", "max_events"):
        if type(rules[key]) is not int or rules[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    travel = rules["travel_times"]
    if not isinstance(travel, list):
        raise ValueError("travel_times must be an explicit OD matrix")
    seen = set()
    probabilities = {zone: 0.0 for zone in snapshot["zone_ids"]}
    for row in travel:
        fields = {
            "origin_zone_id",
            "destination_zone_id",
            "pickup_seconds",
            "trip_seconds",
            "destination_probability",
        }
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("Travel rows have missing or unknown fields")
        for key in ("origin_zone_id", "destination_zone_id"):
            if type(row[key]) is not int or row[key] not in probabilities:
                raise ValueError("Travel zone is outside the closed cluster")
        pair = (row["origin_zone_id"], row["destination_zone_id"])
        if pair in seen:
            raise ValueError("Duplicate travel OD pair")
        seen.add(pair)
        for key in ("pickup_seconds", "trip_seconds", "destination_probability"):
            value = row[key]
            if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
                raise ValueError(f"Travel {key} must be finite and nonnegative")
        if row["trip_seconds"] <= 0 or row["destination_probability"] > 1:
            raise ValueError(
                "Trip duration must be positive; OD probabilities must be within [0, 1]"
            )
        probabilities[pair[0]] += row["destination_probability"]
    expected = {(a, b) for a in probabilities for b in probabilities}
    if seen != expected or any(
        not np.isclose(p, 1, rtol=0, atol=1e-12) for p in probabilities.values()
    ):
        raise ValueError("Travel matrix must cover all OD pairs and probabilities must sum to one")
    normalized = copy.deepcopy(rules)
    normalized["travel_times"] = sorted(
        travel, key=lambda r: (r["origin_zone_id"], r["destination_zone_id"])
    )
    return normalized


def normalize_rules(rules: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rules, dict):
        raise ValueError("Simulation rules must be an object")
    base = copy.deepcopy(rules)
    version = base.get("schema_version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported simulation rules schema_version")
    if version == 2:
        if "max_wait_seconds" not in base or "cancel_policy" not in base:
            raise ValueError("Version 2 rules require max_wait_seconds and cancel_policy")
        maximum_wait = base.pop("max_wait_seconds")
        cancel_policy = base.pop("cancel_policy")
    else:
        maximum_wait, cancel_policy = None, "before_pickup_finish_leg"
    if maximum_wait is not None and (
        type(maximum_wait) not in (int, float) or not np.isfinite(maximum_wait) or maximum_wait < 0
    ):
        raise ValueError("max_wait_seconds must be null or finite and nonnegative")
    if cancel_policy != "before_pickup_finish_leg":
        raise ValueError("Unsupported cancel_policy")
    if (
        maximum_wait is not None
        and maximum_wait
        > (
            pd.Timestamp.max.value
            - parse_timestamp(snapshot["horizon_end"], "horizon_end").value
        )
        / 1e9
    ):
        raise ValueError("max_wait_seconds exceeds the supported timestamp range")
    base["schema_version"] = 1
    normalized = validate_rules(base, snapshot)
    normalized.update(schema_version=2, max_wait_seconds=maximum_wait, cancel_policy=cancel_policy)
    return normalized
