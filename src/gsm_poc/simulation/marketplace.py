"""Bounded, synthetic fixed-supply simulation of a verified demand handoff."""

from __future__ import annotations

import copy
import dataclasses
import heapq
import time
from collections import Counter
from collections.abc import Generator
from typing import Any, cast

import numpy as np
import pandas as pd
import simpy

from gsm_poc.core.artifacts import fingerprint
from gsm_poc.core.config import Config
from gsm_poc.simulation.compensation import resolve_compensation, settle_earnings
from gsm_poc.simulation.demand import DemandPlan, validate_snapshot
from gsm_poc.simulation.rules import normalize_rules

REQUEST_COLUMNS = [
    "request_id",
    "created_at",
    "origin_zone_id",
    "destination_zone_id",
    "service_id",
    "source_block_id",
    "state",
    "vehicle_id",
    "assigned_at",
    "pickup_at",
    "completed_at",
    "dispatch_eta_seconds",
    "trip_seconds",
    "wait_seconds",
    "observed_wait_seconds",
    "wait_censored",
    "completion_censored",
]
EVENT_COLUMNS = ["event_id", "request_id", "timestamp", "state", "vehicle_id"]
VEHICLE_COLUMNS = [
    "vehicle_id",
    "driver_id",
    "shift_id",
    "state",
    "start",
    "end",
    "duration_seconds",
    "duration_hours",
    "zone_id",
    "destination_zone_id",
    "request_id",
]


@dataclasses.dataclass
class SimulationResult:
    requests: pd.DataFrame
    request_events: pd.DataFrame
    vehicle_intervals: pd.DataFrame
    end_snapshot: dict[str, Any]
    result: dict[str, Any]
    spec: dict[str, Any]
    financial_tables: dict[str, pd.DataFrame] | None = None
    driver_offers: pd.DataFrame | None = None
    offer_events: pd.DataFrame | None = None


class _Budget:
    def __init__(self, rules: dict[str, Any]) -> None:
        self.started = time.perf_counter()
        self.max_seconds = rules["max_seconds"]
        self.max_events = rules["max_events"]
        self.work_units = 0

    def consume(self) -> None:
        # Includes arrival draws and candidate checks, not just SimPy queue events.
        self.work_units += 1
        if self.work_units > self.max_events:
            raise RuntimeError("Simulation max_events budget exhausted; no completed forecast")
        if time.perf_counter() - self.started > self.max_seconds:
            raise RuntimeError("Simulation max_seconds budget exhausted; no completed forecast")


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


def _validate_plan(plan: DemandPlan, config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    if plan.result.get("usable_for_simulation") is not True or plan.result.get("status") != "ok":
        raise ValueError("Demand usable_for_simulation gate is false or unavailable")
    snapshot = validate_snapshot(plan.snapshot, config)
    version = fingerprint(plan.spec)
    if (
        plan.result.get("demand_plan_version") != version
        or snapshot["snapshot_version"] != plan.snapshot.get("snapshot_version")
        or plan.spec.get("snapshot_version") != snapshot["snapshot_version"]
        or plan.spec.get("units", {}).get("request_rate") != "requests/hour"
        or plan.spec.get("policy_version") != fingerprint(plan.spec.get("policy"))
    ):
        raise ValueError("Demand plan/spec/snapshot versions or request-rate units differ")
    frame = plan.frame.copy()
    required = {
        "zone_id",
        "service_id",
        "block_start",
        "block_end",
        "block_hours",
        "request_rate",
        "expected_bookings",
        "source_block_id",
        "status",
        "support_status",
        "demand_plan_version",
        "snapshot_id",
        "model_version",
        "source_version",
        "policy_version",
        "source_kind",
        "evidence_level",
        "demand_mode",
        "exposure_mode",
    }
    if required - set(frame.columns) or frame.empty or frame[list(required)].isna().any().any():
        raise ValueError("Demand plan is empty or has missing contract values")
    for key, value in {
        "status": "ok",
        "support_status": "ok",
        "demand_plan_version": version,
        "snapshot_id": snapshot["snapshot_id"],
        "evidence_level": "C",
        "model_version": plan.spec.get("model_version"),
        "source_version": plan.spec.get("source_version"),
        "policy_version": plan.spec["policy_version"],
        "demand_mode": snapshot["demand_mode"],
        "exposure_mode": snapshot["exposure_mode"],
        "source_kind": plan.result.get("source_kind"),
    }.items():
        if not frame[key].eq(value).all():
            raise ValueError(f"Demand {key} differs from the frozen handoff")
    if plan.result.get("source_kind") not in ("synthetic", "semi_synthetic"):
        raise ValueError("Only evidence C demand is supported by the synthetic simulator")
    for key in ("block_start", "block_end"):
        parsed = pd.to_datetime(frame[key], errors="raise")
        if parsed.dt.tz is None:
            raise ValueError("Demand timestamps must have explicit offsets")
        frame[key] = parsed.dt.tz_convert("UTC")
    if not pd.api.types.is_integer_dtype(frame.zone_id) or not set(frame.zone_id) == set(
        snapshot["zone_ids"]
    ):
        raise ValueError("Demand zones differ from the snapshot")
    if (
        set(frame.service_id) != {"X", "Y"}
        or frame.duplicated(["zone_id", "service_id", "block_start"]).any()
    ):
        raise ValueError("Demand services are invalid or zone/service/block keys are duplicated")
    duration = (frame.block_end - frame.block_start).dt.total_seconds().to_numpy() / 3600
    for key in ("request_rate", "expected_bookings", "block_hours"):
        if not pd.api.types.is_numeric_dtype(frame[key]) or pd.api.types.is_bool_dtype(frame[key]):
            raise ValueError(f"Demand {key} must be numeric")
        if not np.isfinite(frame[key].to_numpy(float)).all() or (frame[key] < 0).any():
            raise ValueError(f"Demand {key} must be finite and nonnegative")
    if (
        (duration <= 0).any()
        or not np.allclose(duration, frame.block_hours, rtol=0, atol=1e-12)
        or not np.allclose(
            frame.request_rate * duration, frame.expected_bookings, rtol=1e-10, atol=1e-10
        )
    ):
        raise ValueError("Demand rate, duration and expected bookings do not reconcile")
    start, end = pd.Timestamp(snapshot["horizon_start"]), pd.Timestamp(snapshot["horizon_end"])
    for _, group in frame.groupby(["zone_id", "service_id"]):
        group = group.sort_values("block_start")
        if (
            group.block_start.iloc[0] != start
            or group.block_end.iloc[-1] != end
            or not np.array_equal(
                group.block_start.iloc[1:].to_numpy(), group.block_end.iloc[:-1].to_numpy()
            )
        ):
            raise ValueError("Demand blocks must tile the snapshot horizon for every zone/service")
    for _, group in frame.groupby("zone_id"):
        x, y = (
            group[group.service_id == service].sort_values("block_start") for service in ("X", "Y")
        )
        if not np.array_equal(x.block_end.to_numpy(), y.block_end.to_numpy()):
            raise ValueError("X/Y demand blocks must share boundaries")
    total = plan.result.get("summary", {}).get("expected_bookings")
    if (
        type(total) not in (int, float)
        or not np.isfinite(total)
        or not np.isclose(total, frame.expected_bookings.sum())
    ):
        raise ValueError("Demand expected bookings differ from the result summary")
    return frame.sort_values(["zone_id", "service_id", "block_start"]).reset_index(
        drop=True
    ), snapshot


def _rng(seed: int, key: Any) -> np.random.Generator:
    # Policy/rate are excluded so baseline/target use common exogenous streams.
    digest = fingerprint({"seed": seed, "key": key})
    return np.random.default_rng(int(digest[:16], 16))


def _sample_requests(
    frame: pd.DataFrame, rules: dict[str, Any], seed: int, budget: _Budget
) -> list[dict[str, Any]]:
    arrivals = []
    for _, row in frame.iterrows():
        key = [int(row.zone_id), row.service_id, row.block_start.isoformat()]
        arrival_rng, od_rng = _rng(seed, [key, "arrival"]), _rng(seed, [key, "destination"])
        destinations = [r for r in rules["travel_times"] if r["origin_zone_id"] == row.zone_id]
        elapsed, index = 0.0, 0
        seconds = (row.block_end - row.block_start).total_seconds()
        while row.request_rate > 0:
            budget.consume()
            elapsed += float(arrival_rng.exponential(3600 / row.request_rate))
            if elapsed >= seconds:
                break
            if len(arrivals) >= rules["max_requests"]:
                raise RuntimeError(
                    "Simulation max_requests budget exhausted; no completed forecast"
                )
            destination = destinations[
                int(
                    od_rng.choice(
                        len(destinations), p=[r["destination_probability"] for r in destinations]
                    )
                )
            ]
            arrivals.append(
                {
                    "request_id": f"request-{fingerprint(key)[:16]}-{index}",
                    "created_at": row.block_start + pd.Timedelta(seconds=elapsed),
                    "origin_zone_id": int(row.zone_id),
                    "destination_zone_id": destination["destination_zone_id"],
                    "service_id": row.service_id,
                    "source_block_id": row.source_block_id,
                }
            )
            index += 1
    return arrivals


def _prescribed_requests(
    requests: pd.DataFrame, snapshot: dict[str, Any], rules: dict[str, Any]
) -> list[dict[str, Any]]:
    fields = {"request_id", "created_at", "origin_zone_id", "destination_zone_id", "service_id"}
    if set(requests.columns) != fields or requests.isna().to_numpy().any():
        raise ValueError("Prescribed requests must contain exactly the explicit request contract")
    if len(requests) > rules["max_requests"]:
        raise RuntimeError("Simulation max_requests budget exhausted; no completed forecast")
    if requests.request_id.duplicated().any():
        raise ValueError("Duplicate prescribed request_id")
    start, end = pd.Timestamp(snapshot["horizon_start"]), pd.Timestamp(snapshot["horizon_end"])
    rows = []
    for row in requests.to_dict("records"):
        if not isinstance(row["request_id"], str) or not row["request_id"].strip():
            raise ValueError("Prescribed request_id must be a nonempty string")
        timestamp = pd.Timestamp(row["created_at"])
        if pd.isna(timestamp) or timestamp.tzinfo is None or not start <= timestamp < end:
            raise ValueError(
                "Prescribed request timestamp must be within [horizon_start, horizon_end)"
            )
        for key in ("origin_zone_id", "destination_zone_id"):
            if type(row[key]) is not int or row[key] not in snapshot["zone_ids"]:
                raise ValueError("Prescribed request zone is outside the closed cluster")
        if row["service_id"] not in ("X", "Y"):
            raise ValueError("Prescribed request service must be X or Y")
        row.update(created_at=timestamp.tz_convert("UTC"), source_block_id=None)
        rows.append(row)
    return rows


class _Marketplace:
    def __init__(self, snapshot: dict[str, Any], rules: dict[str, Any], budget: _Budget) -> None:
        self.env = simpy.Environment()
        self.snapshot, self.rules, self.budget = snapshot, rules, budget
        self.start = cast(pd.Timestamp, pd.Timestamp(snapshot["horizon_start"]).tz_convert("UTC"))
        self.seconds = (pd.Timestamp(snapshot["horizon_end"]) - self.start).total_seconds()
        self.travel = {
            (r["origin_zone_id"], r["destination_zone_id"]): r for r in rules["travel_times"]
        }
        self.requests: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.intervals: list[dict[str, Any]] = []
        self.vehicles = sorted(copy.deepcopy(snapshot["vehicles"]), key=lambda v: v["vehicle_id"])
        for vehicle in self.vehicles:
            vehicle.update(state_start=0.0, active_request=None, next_event_at=None)
            if vehicle["state"] == "idle" and vehicle["soc"] < rules["minimum_soc"]:
                vehicle["state"] = "unavailable"
            self.env.process(self._shift(vehicle))

    def _timestamp(self, seconds: float) -> str:
        timestamp = cast(pd.Timestamp, self.start + pd.Timedelta(nanoseconds=round(seconds * 1e9)))
        return timestamp.isoformat()

    def _request_state(self, request: dict[str, Any], state: str) -> None:
        request["state"] = state
        self.events.append(
            {
                "event_id": len(self.events),
                "request_id": request["request_id"],
                "timestamp": self._timestamp(float(self.env.now)),
                "state": state,
                "vehicle_id": request.get("vehicle_id"),
            }
        )

    def _close_interval(self, vehicle: dict[str, Any], end: float) -> None:
        duration = end - vehicle["state_start"]
        if duration <= 0:
            return
        request = vehicle["active_request"]
        destination = None
        if request is not None:
            destination = (
                request["origin_zone_id"]
                if vehicle["state"] == "to_pickup"
                else request["destination_zone_id"]
            )
        self.intervals.append(
            {
                "vehicle_id": vehicle["vehicle_id"],
                "driver_id": vehicle["driver_id"],
                "shift_id": vehicle["shift_id"],
                "state": vehicle["state"],
                "start": self._timestamp(vehicle["state_start"]),
                "end": self._timestamp(end),
                "duration_seconds": duration,
                "duration_hours": duration / 3600,
                "zone_id": vehicle["zone_id"],
                "destination_zone_id": destination,
                "request_id": request["request_id"] if request is not None else None,
            }
        )

    def _vehicle_state(self, vehicle: dict[str, Any], state: str) -> None:
        self._close_interval(vehicle, float(self.env.now))
        vehicle.update(state=state, state_start=float(self.env.now))

    def _shift(self, vehicle: dict[str, Any]) -> Generator:
        start = (pd.Timestamp(vehicle["shift_start"]) - self.start).total_seconds()
        end = (pd.Timestamp(vehicle["shift_end"]) - self.start).total_seconds()
        # An initially offline vehicle already inside its shift remains a nonparticipant.
        if start > 0:
            yield self.env.timeout(start)
            self._vehicle_state(
                vehicle, "idle" if vehicle["soc"] >= self.rules["minimum_soc"] else "unavailable"
            )
            self._dispatch()
        if end > float(self.env.now):
            yield self.env.timeout(end - float(self.env.now))
            if vehicle["state"] in ("idle", "unavailable"):
                self._vehicle_state(vehicle, "offline")

    def _dispatch(self) -> None:
        if self.env.now >= self.seconds:
            return
        available = [v for v in self.vehicles if v["state"] == "idle"]
        if not available:
            return
        for request in list(self.queue):
            candidates = []
            for vehicle in available:
                self.budget.consume()
                shift_end = (pd.Timestamp(vehicle["shift_end"]) - self.start).total_seconds()
                pickup = self.travel[vehicle["zone_id"], request["origin_zone_id"]][
                    "pickup_seconds"
                ]
                trip = self.travel[request["origin_zone_id"], request["destination_zone_id"]][
                    "trip_seconds"
                ]
                if (
                    request["service_id"] in vehicle["eligible_services"]
                    and pickup <= self.rules["max_pickup_seconds"]
                    and float(self.env.now) + pickup + trip <= shift_end
                ):
                    candidates.append((pickup, vehicle["vehicle_id"], vehicle, trip))
            if not candidates:
                continue
            pickup, _, vehicle, trip = min(candidates, key=lambda c: (c[0], c[1]))
            self.queue.remove(request)
            available.remove(vehicle)
            request.update(
                vehicle_id=vehicle["vehicle_id"],
                assigned_at=self._timestamp(float(self.env.now)),
                dispatch_eta_seconds=float(pickup),
                trip_seconds=float(trip),
            )
            self._request_state(request, "assigned")
            self._vehicle_state(vehicle, "to_pickup")
            vehicle["active_request"] = request
            vehicle["next_event_at"] = self._timestamp(float(self.env.now) + pickup)
            self.env.process(self._serve(vehicle, request, pickup, trip))
            if not available:
                break

    def _serve(
        self, vehicle: dict[str, Any], request: dict[str, Any], pickup: float, trip: float
    ) -> Generator:
        self._request_state(request, "pickup")
        yield self.env.timeout(pickup)
        request["pickup_at"] = self._timestamp(float(self.env.now))
        self._request_state(request, "on_trip")
        self._vehicle_state(vehicle, "on_trip")
        vehicle["zone_id"] = request["origin_zone_id"]
        vehicle["next_event_at"] = self._timestamp(float(self.env.now) + trip)
        yield self.env.timeout(trip)
        request["completed_at"] = self._timestamp(float(self.env.now))
        self._request_state(request, "completed")
        shift_end = (pd.Timestamp(vehicle["shift_end"]) - self.start).total_seconds()
        self._vehicle_state(vehicle, "idle" if self.env.now < shift_end else "offline")
        vehicle.update(
            zone_id=request["destination_zone_id"], active_request=None, next_event_at=None
        )
        self._dispatch()

    def _arrivals(self, arrivals: list[dict[str, Any]]) -> Generator:
        for request in arrivals:
            seconds = (request["created_at"].value - self.start.value) / 1e9
            yield self.env.timeout(seconds - float(self.env.now))
            request["created_at"] = request["created_at"].isoformat()
            self.requests.append(request)
            self._request_state(request, "created")
            self._request_state(request, "queued")
            self.queue.append(request)
            self._dispatch()

    def run(self, arrivals: list[dict[str, Any]]) -> None:
        arrivals.sort(key=lambda r: (r["created_at"], r["request_id"]))
        self.env.process(self._arrivals(arrivals))
        # Include completions exactly at the end; arrivals use the half-open horizon.
        while self.env.peek() <= self.seconds:
            self.budget.consume()
            self.env.step()
        for vehicle in self.vehicles:
            self._close_interval(vehicle, self.seconds)


def _simulate_marketplace_v1(
    plan: DemandPlan,
    rules: dict[str, Any],
    config: Config,
    seed: int,
    prescribed_requests: pd.DataFrame | None = None,
) -> SimulationResult:
    """Run one fixed-roster trajectory; rates already include the price policy."""
    if type(seed) is not int or seed < 0:
        raise ValueError("Simulation seed must be a nonnegative integer")
    frame, snapshot = _validate_plan(plan, config)
    rules = validate_rules(rules, snapshot)
    budget = _Budget(rules)
    arrivals = (
        _sample_requests(frame, rules, seed, budget)
        if prescribed_requests is None
        else _prescribed_requests(prescribed_requests, snapshot, rules)
    )
    request_version = fingerprint(
        [{**r, "created_at": r["created_at"].isoformat()} for r in arrivals]
    )
    engine = _Marketplace(snapshot, rules, budget)
    engine.run(arrivals)
    end = cast(pd.Timestamp, engine.start + pd.Timedelta(seconds=engine.seconds))
    rows = []
    for request in engine.requests:
        row = {key: request.get(key) for key in REQUEST_COLUMNS}
        created = pd.Timestamp(request["created_at"])
        pickup = pd.Timestamp(row["pickup_at"]) if row["pickup_at"] is not None else None
        row["wait_seconds"] = (pickup - created).total_seconds() if pickup is not None else None
        row["observed_wait_seconds"] = (
            (pickup if pickup is not None else end) - created
        ).total_seconds()
        row["wait_censored"] = pickup is None
        row["completion_censored"] = row["state"] != "completed"
        rows.append(row)
    requests = pd.DataFrame(rows, columns=pd.Index(REQUEST_COLUMNS))
    events = pd.DataFrame(engine.events, columns=pd.Index(EVENT_COLUMNS))
    intervals = pd.DataFrame(engine.intervals, columns=pd.Index(VEHICLE_COLUMNS))
    hours = {
        state: float(intervals.loc[intervals.state == state, "duration_hours"].sum())
        for state in ("idle", "to_pickup", "on_trip", "offline", "unavailable")
    }
    completed = int(requests.state.eq("completed").sum())
    open_end = len(requests) - completed
    total_hours = len(snapshot["vehicles"]) * engine.seconds / 3600
    if len(requests) != completed + open_end or not np.isclose(
        sum(hours.values()), total_hours, atol=1e-10, rtol=1e-10
    ):
        raise RuntimeError("Simulation request or vehicle-hour conservation failed")
    for vehicle_id, group in intervals.groupby("vehicle_id"):
        if not np.isclose(group.duration_seconds.sum(), engine.seconds, atol=1e-8, rtol=1e-10):
            raise RuntimeError(f"Vehicle time coverage failed: {vehicle_id}")
        starts = pd.to_datetime(group.start, format="ISO8601")
        ends = pd.to_datetime(group.end, format="ISO8601")
        if (
            starts.iloc[0] != engine.start
            or ends.iloc[-1] != end
            or not np.array_equal(starts.iloc[1:].to_numpy(), ends.iloc[:-1].to_numpy())
        ):
            raise RuntimeError(f"Vehicle states overlap or leave gaps: {vehicle_id}")
    waits = requests.loc[requests.pickup_at.notna(), "wait_seconds"].astype(float)
    active_ids = [
        v["active_request"]["request_id"]
        for v in engine.vehicles
        if v["active_request"] is not None
    ]
    busy_ids = requests.loc[requests.state.isin(["pickup", "on_trip"]), "request_id"].to_list()
    if len(set(active_ids)) != len(active_ids) or set(active_ids) != set(busy_ids):
        raise RuntimeError("Vehicle/request assignment conservation failed")
    spec = {
        "schema_version": 1,
        "simulation_mode": "fixed_supply",
        "seed": seed,
        "rules": rules,
        "rules_version": fingerprint(rules),
        "demand_plan_version": plan.result["demand_plan_version"],
        "snapshot_version": snapshot["snapshot_version"],
        "policy_version": plan.spec["policy_version"],
        "arrival_mode": "piecewise_poisson" if prescribed_requests is None else "prescribed",
        "request_version": request_version,
        "seed_rule": "per-zone/service/block arrival and OD streams; excludes policy/rate",
        "tie_rule": "time/id request order; ETA/vehicle_id ranking; SimPy FIFO event ties",
        "queue_rule": "FIFO among matchable requests; no patience/cancel/expiry mechanism",
        "horizon_rule": "arrivals [start,end); completions through end; unfinished censored",
        "initial_state_rule": (
            "Idle/offline only; offline in current shift stays offline; future shifts activate"
        ),
        "soc_rule": "constant SOC with initial minimum eligibility; energy/charging not modeled",
        "travel_rule": "deterministic OD durations shared by X/Y; closed cluster",
        "price_application": "already in request_rate; simulator never applies price effects",
        "units": {
            "wait": "seconds",
            "supply": "vehicle-hours",
            "requests": "requests",
            "trips": "trips",
        },
    }
    version = fingerprint(spec)
    summary = {
        "created_requests": len(requests),
        "completed_trips": completed,
        "open_requests_start": 0,
        "open_requests_end": open_end,
        "queued_requests_end": int(requests.state.eq("queued").sum()),
        "pickup_requests_end": int(requests.state.eq("pickup").sum()),
        "on_trip_requests_end": int(requests.state.eq("on_trip").sum()),
        "canceled_requests": 0,
        "expired_requests": 0,
        "serviceable_hours": hours["idle"] + hours["to_pickup"] + hours["on_trip"],
        "idle_hours": hours["idle"],
        "dispatch_hours": 0.0,
        "pickup_hours": hours["to_pickup"],
        "on_trip_hours": hours["on_trip"],
        "offline_hours": hours["offline"],
        "ineligible_hours": hours["unavailable"],
        "total_vehicle_hours": total_hours,
        "mean_wait_seconds": float(waits.mean()) if len(waits) else None,
        "p95_wait_seconds": float(waits.quantile(0.95, interpolation="linear"))
        if len(waits)
        else None,
        "wait_observed_requests": len(waits),
        "wait_censored_requests": len(requests) - len(waits),
    }
    result = {
        "schema_version": 1,
        "simulation_version": version,
        "status": "ok",
        "simulation_mode": "fixed_supply",
        "source_kind": "synthetic",
        "evidence_level": "C",
        "demand_source_kind": plan.result["source_kind"],
        "calibration_status": "not_calibrated",
        "scope": {
            "horizon_start": engine.start.isoformat(),
            "horizon_end": end.isoformat(),
            "zones": snapshot["zone_ids"],
            "vehicles": len(snapshot["vehicles"]),
        },
        "summary": summary,
        "by_service": {
            service: {
                "created_requests": int(requests.service_id.eq(service).sum()),
                "completed_trips": int(
                    (requests.service_id.eq(service) & requests.state.eq("completed")).sum()
                ),
                "open_requests_end": int(
                    (requests.service_id.eq(service) & ~requests.state.eq("completed")).sum()
                ),
            }
            for service in ("X", "Y")
        },
        "units": spec["units"],
        "wait_population": "created requests picked up by horizon_end; queue plus pickup travel",
        "wait_quantile_method": "linear",
        "wait_status": "ok" if len(waits) else "unavailable_no_pickups",
        "request_accounting": "open_start + created = completed + canceled + expired + open_end",
        "vehicle_accounting": "serviceable = idle + dispatch + pickup + on_trip; shared roster",
        "interval_status": "interval_unavailable",
        "interval_reason": "Single trajectory; no full-chain intervals",
        "unavailable_metrics": {
            "cancellation_rate": "No cancellation model; zero counts under this assumption",
            "charging": "Energy and charging are step 3",
            "economics": "Compensation/cost ledger unavailable",
        },
        "budget_work_units": budget.work_units,
    }
    end_vehicles = []
    for vehicle in engine.vehicles:
        active = vehicle["active_request"]
        end_vehicles.append(
            {
                **{k: v for k, v in vehicle.items() if k not in ("state_start", "active_request")},
                "active_request_id": active["request_id"] if active is not None else None,
                "remaining_phase_seconds": max(
                    0.0, (pd.Timestamp(vehicle["next_event_at"]) - end).total_seconds()
                )
                if active is not None
                else None,
            }
        )
    end_snapshot = {
        "schema_version": 1,
        "artifact_type": "simulation_end_snapshot",
        "simulation_version": version,
        "initial_snapshot_version": snapshot["snapshot_version"],
        "timestamp": end.isoformat(),
        "timezone": snapshot["timezone"],
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "vehicles": end_vehicles,
        "open_requests": [r for r in rows if r["state"] != "completed"],
        "resume_supported": False,
        "resume_reason": "Carry-out exported; busy/queued carry-in requires a later extension",
    }
    return SimulationResult(requests, events, intervals, end_snapshot, result, spec)


OPEN_STATES = frozenset({"queued", "pickup", "on_trip"})
TERMINAL_STATES = frozenset({"completed", "canceled", "expired"})
EVENT_PRIORITY = {
    "pickup_complete": 0,
    "trip_complete": 0,
    "expire": 1,
    "cancel": 1,
    "shift_start": 2,
    "shift_end": 2,
    "arrival": 3,
    "offer_response": 2,
}
EXTRA_REQUEST_COLUMNS = [
    "cancel_at",
    "deadline_at",
    "canceled_at",
    "expired_at",
    "terminal_reason",
    "wait_status",
    "created_in_window",
    "carry_in",
]


def _timestamp(value: Any, field: str) -> pd.Timestamp:
    if not isinstance(value, (str, pd.Timestamp)):
        raise ValueError(f"{field} must be an offset-aware timestamp")
    parsed = pd.Timestamp(value)
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f"{field} must be an offset-aware timestamp")
    return parsed.tz_convert("UTC")


def _iso(nanoseconds: int) -> str:
    timestamp = pd.Timestamp(nanoseconds, tz="UTC")
    if not isinstance(timestamp, pd.Timestamp):
        raise ValueError("Operational event timestamp is unavailable")
    return timestamp.isoformat()


def _normalize_rules(rules: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    return normalize_rules(rules, snapshot)


def _arrival_schedule(
    frame: pd.DataFrame,
    snapshot: dict[str, Any],
    rules: dict[str, Any],
    seed: int,
    prescribed: pd.DataFrame | None,
    budget: _Budget,
) -> list[dict[str, Any]]:
    if prescribed is None:
        rows = _sample_requests(frame, rules, seed, budget)
    else:
        optional = {"cancel_at"}
        fields = {"request_id", "created_at", "origin_zone_id", "destination_zone_id", "service_id"}
        if fields - set(prescribed) or set(prescribed) - fields - optional:
            raise ValueError("Prescribed request contract has missing or unknown fields")
        rows = _prescribed_requests(prescribed[list(sorted(fields))], snapshot, rules)
        if "cancel_at" in prescribed:
            for row, cancel_at in zip(rows, prescribed.cancel_at, strict=True):
                if pd.notna(cancel_at):
                    timestamp = _timestamp(cancel_at, "cancel_at")
                    if timestamp < row["created_at"]:
                        raise ValueError("cancel_at precedes created_at")
                    row["cancel_at"] = timestamp.isoformat()
    return sorted(
        [
            {**r, "created_at": r["created_at"].isoformat(), "cancel_at": r.get("cancel_at")}
            for r in rows
        ],
        key=lambda r: (r["created_at"], r["request_id"]),
    )


def _checkpoint_payload(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in checkpoint.items() if key != "checkpoint_version"}


class _WindowMarketplace:
    def __init__(
        self,
        snapshot: dict[str, Any],
        rules: dict[str, Any],
        schedule: list[dict[str, Any]],
        start: pd.Timestamp,
        end: pd.Timestamp,
        budget: _Budget,
        checkpoint: dict[str, Any] | None,
    ) -> None:
        self.env = simpy.Environment()
        self.start, self.end = start.value, end.value
        self.now = self.start
        self.rules, self.budget = rules, budget
        self.schedule = {r["request_id"]: r for r in schedule}
        self.travel = {
            (r["origin_zone_id"], r["destination_zone_id"]): r for r in rules["travel_times"]
        }
        self.records: dict[str, dict[str, Any]] = {}
        self.vehicles: dict[str, dict[str, Any]] = {}
        self.pending: list[tuple[int, int, int, str, str]] = []
        self.events: list[dict[str, Any]] = []
        self.intervals: list[dict[str, Any]] = []
        self.next_sequence = 0
        self.next_event_id = 0
        if checkpoint is not None:
            self.records = {
                r["request_id"]: copy.deepcopy(r) for r in checkpoint["request_records"]
            }
            self.vehicles = {v["vehicle_id"]: copy.deepcopy(v) for v in checkpoint["vehicles"]}
            self.next_sequence = checkpoint["next_sequence"]
            self.next_event_id = checkpoint["next_event_id"]
            for event in checkpoint["pending_events"]:
                timestamp, sequence, kind, entity_id = event
                heapq.heappush(
                    self.pending, (timestamp, EVENT_PRIORITY[kind], sequence, kind, entity_id)
                )
        else:
            for vehicle in sorted(snapshot["vehicles"], key=lambda v: v["vehicle_id"]):
                vehicle = copy.deepcopy(vehicle)
                vehicle.update(active_request_id=None, pending_action=None, next_event_at=None)
                if vehicle["state"] == "idle" and vehicle["soc"] < rules["minimum_soc"]:
                    vehicle["state"] = "unavailable"
                self.vehicles[vehicle["vehicle_id"]] = vehicle
                shift_start = _timestamp(vehicle["shift_start"], "shift_start").value
                shift_end = _timestamp(vehicle["shift_end"], "shift_end").value
                if shift_start > self.start:
                    self._push(shift_start, "shift_start", vehicle["vehicle_id"])
                if shift_end >= self.start:
                    self._push(shift_end, "shift_end", vehicle["vehicle_id"])
            for request in schedule:
                self._push(
                    _timestamp(request["created_at"], "created_at").value,
                    "arrival",
                    request["request_id"],
                )
        self.open_start = {key for key, r in self.records.items() if r["state"] in OPEN_STATES}
        self.created_ids: set[str] = set()
        for vehicle in self.vehicles.values():
            vehicle["state_start_ns"] = self.start

    def _push(self, timestamp: int, kind: str, entity_id: str) -> None:
        if timestamp < self.now:
            raise ValueError("Cannot schedule an operational event in the past")
        heapq.heappush(
            self.pending, (timestamp, EVENT_PRIORITY[kind], self.next_sequence, kind, entity_id)
        )
        self.next_sequence += 1

    def _request_state(self, request: dict[str, Any], state: str) -> None:
        request["state"] = state
        self.events.append(
            {
                "event_id": self.next_event_id,
                "request_id": request["request_id"],
                "timestamp": _iso(self.now),
                "state": state,
                "vehicle_id": request.get("vehicle_id"),
            }
        )
        self.next_event_id += 1

    def _close_interval(self, vehicle: dict[str, Any]) -> None:
        beginning = vehicle["state_start_ns"]
        if self.now <= beginning:
            return
        action = vehicle.get("pending_action")
        request_id = vehicle.get("active_request_id") or (action["request_id"] if action else None)
        request = self.records.get(request_id) if request_id else None
        destination = None
        if request:
            destination = (
                request["origin_zone_id"]
                if vehicle["state"] == "to_pickup"
                else request["destination_zone_id"]
            )
        self.intervals.append(
            {
                "vehicle_id": vehicle["vehicle_id"],
                "driver_id": vehicle["driver_id"],
                "shift_id": vehicle["shift_id"],
                "state": vehicle["state"],
                "start": _iso(beginning),
                "end": _iso(self.now),
                "duration_seconds": (self.now - beginning) / 1e9,
                "duration_hours": (self.now - beginning) / 3.6e12,
                "zone_id": vehicle["zone_id"],
                "destination_zone_id": destination,
                "request_id": request_id,
                "activity_kind": "aborted_pickup" if action else vehicle["state"],
            }
        )
        vehicle["state_start_ns"] = self.now

    def _set_vehicle_state(self, vehicle: dict[str, Any], state: str) -> None:
        self._close_interval(vehicle)
        vehicle["state"] = state

    def _release(self, vehicle: dict[str, Any], zone_id: int) -> None:
        shift_end = _timestamp(vehicle["shift_end"], "shift_end").value
        state = (
            "offline"
            if self.now >= shift_end
            else ("idle" if vehicle["soc"] >= self.rules["minimum_soc"] else "unavailable")
        )
        self._set_vehicle_state(vehicle, state)
        vehicle.update(
            zone_id=zone_id, active_request_id=None, pending_action=None, next_event_at=None
        )

    def _dispatch(self) -> None:
        if self.now >= self.end:
            return
        queued = sorted(
            (r for r in self.records.values() if r["state"] == "queued"),
            key=lambda r: (r["created_at"], r["request_id"]),
        )
        for request in queued:
            candidates = []
            for vehicle in self.vehicles.values():
                if vehicle["state"] != "idle":
                    continue
                self.budget.consume()
                pickup = self.travel[vehicle["zone_id"], request["origin_zone_id"]][
                    "pickup_seconds"
                ]
                trip = self.travel[request["origin_zone_id"], request["destination_zone_id"]][
                    "trip_seconds"
                ]
                shift_end = _timestamp(vehicle["shift_end"], "shift_end").value
                remaining_seconds = (shift_end - self.now) / 1e9
                if (
                    request["service_id"] in vehicle["eligible_services"]
                    and pickup <= self.rules["max_pickup_seconds"]
                    and pickup <= remaining_seconds
                    and trip <= remaining_seconds
                    and self.now + round(pickup * 1e9) + round(trip * 1e9) <= shift_end
                ):
                    candidates.append((pickup, vehicle["vehicle_id"], trip))
            if not candidates:
                continue
            pickup, vehicle_id, trip = min(candidates)
            vehicle = self.vehicles[vehicle_id]
            request.update(
                vehicle_id=vehicle_id,
                assigned_at=_iso(self.now),
                dispatch_eta_seconds=float(pickup),
                trip_seconds=float(trip),
            )
            self._request_state(request, "assigned")
            self._set_vehicle_state(vehicle, "to_pickup")
            vehicle.update(
                active_request_id=request["request_id"],
                pending_action=None,
                next_event_at=_iso(self.now + round(pickup * 1e9)),
            )
            self._request_state(request, "pickup")
            self._push(self.now + round(pickup * 1e9), "pickup_complete", vehicle_id)

    def _handle(self, kind: str, entity_id: str) -> None:
        if kind == "arrival":
            if entity_id in self.records:
                raise ValueError("Request arrival was replayed twice")
            request = copy.deepcopy(self.schedule[entity_id])
            request.update(
                vehicle_id=None,
                assigned_at=None,
                pickup_at=None,
                completed_at=None,
                dispatch_eta_seconds=None,
                trip_seconds=None,
                canceled_at=None,
                expired_at=None,
                terminal_reason=None,
            )
            self.records[entity_id] = request
            self.created_ids.add(entity_id)
            self._request_state(request, "created")
            self._request_state(request, "queued")
            maximum_wait = self.rules["max_wait_seconds"]
            request["deadline_at"] = None
            if maximum_wait is not None:
                deadline = self.now + round(maximum_wait * 1e9)
                request["deadline_at"] = _iso(deadline)
                self._push(deadline, "expire", entity_id)
            if request.get("cancel_at") is not None:
                self._push(_timestamp(request["cancel_at"], "cancel_at").value, "cancel", entity_id)
            return
        if kind in ("cancel", "expire"):
            request = self.records.get(entity_id)
            if request is None or request["state"] not in ("queued", "pickup"):
                return
            terminal = "canceled" if kind == "cancel" else "expired"
            request["canceled_at" if kind == "cancel" else "expired_at"] = _iso(self.now)
            request["terminal_reason"] = (
                "customer_cancel" if kind == "cancel" else "pickup_deadline"
            )
            self._request_state(request, terminal)
            if request.get("vehicle_id"):
                vehicle = self.vehicles[request["vehicle_id"]]
                self._close_interval(vehicle)
                vehicle["active_request_id"] = None
                vehicle["pending_action"] = {
                    "kind": "finish_aborted_pickup",
                    "request_id": entity_id,
                }
            return
        vehicle = self.vehicles[entity_id]
        if kind == "shift_start":
            if vehicle["state"] in ("offline", "unavailable"):
                self._set_vehicle_state(
                    vehicle,
                    "idle" if vehicle["soc"] >= self.rules["minimum_soc"] else "unavailable",
                )
            return
        if kind == "shift_end":
            if vehicle["state"] in ("idle", "unavailable"):
                self._set_vehicle_state(vehicle, "offline")
            return
        action = vehicle.get("pending_action")
        request_id = vehicle.get("active_request_id") or (action["request_id"] if action else None)
        if request_id is None:
            raise RuntimeError("A phase-completion event has no vehicle activity")
        request = self.records[request_id]
        if kind == "pickup_complete":
            if action:
                self._release(vehicle, request["origin_zone_id"])
                return
            request["pickup_at"] = _iso(self.now)
            self._request_state(request, "on_trip")
            self._set_vehicle_state(vehicle, "on_trip")
            vehicle["zone_id"] = request["origin_zone_id"]
            ending = self.now + round(request["trip_seconds"] * 1e9)
            vehicle["next_event_at"] = _iso(ending)
            self._push(ending, "trip_complete", entity_id)
        elif kind == "trip_complete":
            request["completed_at"] = _iso(self.now)
            self._request_state(request, "completed")
            self._release(vehicle, request["destination_zone_id"])

    def run(self) -> None:
        while self.now <= self.end:
            while self.pending and self.pending[0][0] == self.now:
                if self.now == self.end and self.pending[0][3] == "arrival":
                    break
                _, _, _, kind, entity_id = heapq.heappop(self.pending)
                self.budget.consume()
                self._handle(kind, entity_id)
            self._dispatch()
            if self.pending and self.pending[0][0] == self.now and self.now < self.end:
                continue
            if self.now == self.end:
                break
            next_time = min(self.pending[0][0] if self.pending else self.end, self.end)
            self.budget.consume()
            self.env.run(until=self.env.timeout((next_time - self.now) / 1e9))
            self.now = next_time
        for vehicle in self.vehicles.values():
            self._close_interval(vehicle)


OFFER_COLUMNS = [
    "offer_id",
    "request_id",
    "vehicle_id",
    "driver_id",
    "service_id",
    "offered_at",
    "response_at",
    "resolved_at",
    "state",
    "pickup_seconds",
    "trip_seconds",
    "vehicle_zone_id",
    "origin_zone_id",
    "destination_zone_id",
    "displayed_fare",
    "offered_driver_pay",
    "currency",
    "terms_version",
]
OFFER_EVENT_COLUMNS = ["offer_event_id", *OFFER_COLUMNS, "timestamp"]
OFFER_DTYPES = {
    key: "int64" for key in ("vehicle_zone_id", "origin_zone_id", "destination_zone_id")
} | {
    key: "float64"
    for key in ("pickup_seconds", "trip_seconds", "displayed_fare", "offered_driver_pay")
}


def _offer_id(seed: int, request_id: str, vehicle_id: str) -> str:
    return fingerprint({"seed": seed, "request_id": request_id, "vehicle_id": vehicle_id})


def _offer_outcome(offer_id: str, rules: dict[str, Any]) -> str:
    if rules["response_seconds"] >= rules["response_timeout_seconds"]:
        return "timed_out"
    # shortcut: acceptance is synthetic and price-independent; fit behavior only with decision data.
    draw = int(offer_id[:16], 16) / 2**64
    return "accepted" if draw < rules["acceptance_probability"] else "rejected"


class _OfferMarketplace(_WindowMarketplace):
    def __init__(
        self,
        snapshot: dict[str, Any],
        rules: dict[str, Any],
        schedule: list[dict[str, Any]],
        start: pd.Timestamp,
        end: pd.Timestamp,
        budget: _Budget,
        checkpoint: dict[str, Any] | None,
        seed: int,
        compensation: dict[str, Any] | None,
    ) -> None:
        super().__init__(snapshot, rules, schedule, start, end, budget, checkpoint)
        self.seed, self.compensation = seed, compensation
        self.offers = (
            {row["offer_id"]: copy.deepcopy(row) for row in checkpoint["offer_records"]}
            if checkpoint
            else {}
        )
        self.offer_events: list[dict[str, Any]] = []
        self.next_offer_event_id = checkpoint["next_offer_event_id"] if checkpoint else 0
        self.open_offers_start = {
            key for key, row in self.offers.items() if row["state"] == "offered"
        }
        self.new_offer_ids: set[str] = set()
        if checkpoint is None:
            self.pending = [
                event for event in self.pending if event[3] not in ("shift_start", "shift_end")
            ]
            heapq.heapify(self.pending)
            for vehicle in self.vehicles.values():
                vehicle["pending_offer_id"] = None

    def _close_interval(self, vehicle: dict[str, Any]) -> None:
        offer_id = vehicle.get("pending_offer_id")
        if offer_id:
            vehicle["active_request_id"] = self.offers[offer_id]["request_id"]
        super()._close_interval(vehicle)
        if offer_id:
            vehicle["active_request_id"] = None

    def _release(self, vehicle: dict[str, Any], zone_id: int) -> None:
        self._set_vehicle_state(vehicle, "idle")
        vehicle.update(
            zone_id=zone_id,
            active_request_id=None,
            pending_action=None,
            next_event_at=None,
            pending_offer_id=None,
        )

    def _offer_state(self, offer: dict[str, Any], state: str) -> None:
        offer.update(state=state, resolved_at=None if state == "offered" else _iso(self.now))
        self.offer_events.append(
            {
                "offer_event_id": self.next_offer_event_id,
                **copy.deepcopy(offer),
                "timestamp": _iso(self.now),
            }
        )
        self.next_offer_event_id += 1

    def _dispatch(self) -> None:
        if self.now >= self.end:
            return
        pending_requests = {
            row["request_id"] for row in self.offers.values() if row["state"] == "offered"
        }
        attempts: dict[str, set[str]] = {}
        for offer in self.offers.values():
            attempts.setdefault(offer["request_id"], set()).add(offer["vehicle_id"])
        for request in sorted(
            (row for row in self.records.values() if row["state"] == "queued"),
            key=lambda row: (row["created_at"], row["request_id"]),
        ):
            request_id = request["request_id"]
            tried = attempts.get(request_id, set())
            if request_id in pending_requests or len(tried) >= self.rules["max_offer_attempts"]:
                continue
            candidates = []
            for vehicle in self.vehicles.values():
                if vehicle["state"] != "idle" or vehicle["vehicle_id"] in tried:
                    continue
                self.budget.consume()
                pickup = self.travel[vehicle["zone_id"], request["origin_zone_id"]][
                    "pickup_seconds"
                ]
                if (
                    request["service_id"] in vehicle["eligible_services"]
                    and pickup <= self.rules["max_pickup_seconds"]
                ):
                    candidates.append((pickup, vehicle["vehicle_id"]))
            if not candidates:
                continue
            pickup, vehicle_id = min(candidates)
            vehicle = self.vehicles[vehicle_id]
            offer_id = _offer_id(self.seed, request_id, vehicle_id)
            compensation = self.compensation
            amount = (
                compensation["effective_fares"][request["service_id"]] if compensation else None
            )
            due = self.now + round(
                min(self.rules["response_seconds"], self.rules["response_timeout_seconds"]) * 1e9
            )
            if due > pd.Timestamp.max.value:
                raise ValueError("Offer response exceeds the supported timestamp range")
            offer = {
                "offer_id": offer_id,
                "request_id": request_id,
                "vehicle_id": vehicle_id,
                "driver_id": vehicle["driver_id"],
                "service_id": request["service_id"],
                "offered_at": _iso(self.now),
                "response_at": _iso(due),
                "resolved_at": None,
                "state": "offered",
                "pickup_seconds": float(pickup),
                "trip_seconds": float(
                    self.travel[request["origin_zone_id"], request["destination_zone_id"]][
                        "trip_seconds"
                    ]
                ),
                "displayed_fare": amount,
                "offered_driver_pay": amount,
                "vehicle_zone_id": vehicle["zone_id"],
                "origin_zone_id": request["origin_zone_id"],
                "destination_zone_id": request["destination_zone_id"],
                "currency": compensation["contract"]["currency"] if compensation else None,
                "terms_version": compensation["terms_version"] if compensation else None,
            }
            self.offers[offer_id] = offer
            self.new_offer_ids.add(offer_id)
            self._offer_state(offer, "offered")
            self._set_vehicle_state(vehicle, "dispatch")
            vehicle["pending_offer_id"] = offer_id
            self._push(due, "offer_response", offer_id)

    def _handle(self, kind: str, entity_id: str) -> None:
        if kind == "offer_response":
            offer = self.offers[entity_id]
            if offer["state"] != "offered":
                return
            vehicle = self.vehicles[offer["vehicle_id"]]
            request = self.records[offer["request_id"]]
            outcome = _offer_outcome(entity_id, self.rules)
            self._offer_state(offer, outcome)
            self._set_vehicle_state(vehicle, "idle")
            vehicle["pending_offer_id"] = None
            if outcome != "accepted":
                return
            request.update(
                vehicle_id=vehicle["vehicle_id"],
                assigned_at=_iso(self.now),
                dispatch_eta_seconds=offer["pickup_seconds"],
                trip_seconds=offer["trip_seconds"],
            )
            self._request_state(request, "assigned")
            self._set_vehicle_state(vehicle, "to_pickup")
            pickup_at = self.now + round(offer["pickup_seconds"] * 1e9)
            vehicle.update(
                active_request_id=request["request_id"],
                pending_action=None,
                next_event_at=_iso(pickup_at),
            )
            self._request_state(request, "pickup")
            self._push(pickup_at, "pickup_complete", vehicle["vehicle_id"])
            return
        if kind in ("cancel", "expire"):
            for offer in self.offers.values():
                if offer["request_id"] == entity_id and offer["state"] == "offered":
                    self._offer_state(offer, "withdrawn")
                    vehicle = self.vehicles[offer["vehicle_id"]]
                    self._set_vehicle_state(vehicle, "idle")
                    vehicle["pending_offer_id"] = None
        super()._handle(kind, entity_id)


def _validate_offers(
    offers: Any,
    vehicles: dict[str, dict[str, Any]],
    requests: dict[str, dict[str, Any]],
    rules: dict[str, Any],
    seed: int,
    start: pd.Timestamp,
    compensation: dict[str, Any] | None,
) -> None:
    if not isinstance(offers, list) or len(offers) > rules["max_requests"] * min(
        len(vehicles), rules["max_offer_attempts"]
    ):
        raise ValueError("Carry-in offer history exceeds its bounded cohort")
    ids, pairs, accepted = set(), set(), set()
    pending: dict[str, dict[str, Any]] = {}
    periods: dict[str, list[tuple[int, int]]] = {}
    request_periods: dict[str, list[tuple[int, int]]] = {}
    attempts: Counter = Counter()
    travel = {
        (row["origin_zone_id"], row["destination_zone_id"]): row for row in rules["travel_times"]
    }
    for offer in offers:
        if not isinstance(offer, dict) or set(offer) != set(OFFER_COLUMNS):
            raise ValueError("Carry-in offer record is malformed")
        offer_id, request_id, vehicle_id = (
            offer[key] for key in ("offer_id", "request_id", "vehicle_id")
        )
        if (
            not all(isinstance(key, str) for key in (offer_id, request_id, vehicle_id))
            or request_id not in requests
            or vehicle_id not in vehicles
            or offer_id != _offer_id(seed, request_id, vehicle_id)
            or offer_id in ids
            or (request_id, vehicle_id) in pairs
        ):
            raise ValueError("Carry-in offer identity is invalid or repeated")
        ids.add(offer_id)
        pairs.add((request_id, vehicle_id))
        attempts[request_id] += 1
        if attempts[request_id] > rules["max_offer_attempts"]:
            raise ValueError("Carry-in request exceeds its offer attempt budget")
        request, vehicle = requests[request_id], vehicles[vehicle_id]
        if (
            offer["driver_id"] != vehicle["driver_id"]
            or offer["service_id"] != request["service_id"]
            or request["service_id"] not in vehicle["eligible_services"]
            or any(
                type(offer[key]) is not int
                for key in ("vehicle_zone_id", "origin_zone_id", "destination_zone_id")
            )
            or offer["origin_zone_id"] != request["origin_zone_id"]
            or offer["destination_zone_id"] != request["destination_zone_id"]
            or (offer["vehicle_zone_id"], offer["origin_zone_id"]) not in travel
            or any(
                type(offer[key]) not in (int, float)
                or not np.isfinite(offer[key])
                or offer[key] < 0
                for key in ("pickup_seconds", "trip_seconds")
            )
            or offer["pickup_seconds"]
            != travel[offer["vehicle_zone_id"], offer["origin_zone_id"]]["pickup_seconds"]
            or offer["pickup_seconds"] > rules["max_pickup_seconds"]
            or offer["trip_seconds"]
            != travel[offer["origin_zone_id"], offer["destination_zone_id"]]["trip_seconds"]
        ):
            raise ValueError("Carry-in offer changed its eligible driver, route or durations")
        expected = {
            "displayed_fare": compensation["effective_fares"][request["service_id"]]
            if compensation
            else None,
            "offered_driver_pay": compensation["effective_fares"][request["service_id"]]
            if compensation
            else None,
            "currency": compensation["contract"]["currency"] if compensation else None,
            "terms_version": compensation["terms_version"] if compensation else None,
        }
        if any(offer[key] != value for key, value in expected.items()):
            raise ValueError("Carry-in offer compensation terms changed")
        if compensation and any(
            type(offer[key]) not in (int, float) or not np.isfinite(offer[key]) or offer[key] < 0
            for key in ("displayed_fare", "offered_driver_pay")
        ):
            raise ValueError("Carry-in offer monetary amounts are invalid")
        offered = _timestamp(offer["offered_at"], "offered_at")
        due = _timestamp(offer["response_at"], "response_at")
        if not _timestamp(
            request["created_at"], "created_at"
        ) <= offered <= start or due.value != offered.value + round(
            min(rules["response_seconds"], rules["response_timeout_seconds"]) * 1e9
        ):
            raise ValueError("Carry-in offer timestamp or original response deadline changed")
        state = offer["state"]
        if state not in ("offered", "accepted", "rejected", "timed_out", "withdrawn"):
            raise ValueError("Carry-in offer state is invalid")
        if state == "offered":
            if (
                offer["resolved_at"] is not None
                or due <= start
                or request["state"] != "queued"
                or request_id in pending
            ):
                raise ValueError("Carry-in pending offer/request is inconsistent")
            pending[request_id] = offer
            stopping = start
        else:
            stopping = _timestamp(offer["resolved_at"], "resolved_at")
            if not offered <= stopping <= start:
                raise ValueError("Carry-in offer decision time is inconsistent")
            if state == "withdrawn":
                terminal_at = request["canceled_at"] or request["expired_at"]
                if (
                    terminal_at is None
                    or stopping != _timestamp(terminal_at, "terminal_at")
                    or stopping > due
                ):
                    raise ValueError("Carry-in withdrawn offer has no original cancellation/expiry")
            elif stopping != due or state != _offer_outcome(offer_id, rules):
                raise ValueError("Carry-in offer decision changed its frozen draw or response time")
        request_periods.setdefault(request_id, []).append((offered.value, stopping.value))
        if state == "accepted":
            if (
                request_id in accepted
                or request["vehicle_id"] != vehicle_id
                or request["assigned_at"] != offer["resolved_at"]
                or request["dispatch_eta_seconds"] != offer["pickup_seconds"]
                or request["trip_seconds"] != offer["trip_seconds"]
            ):
                raise ValueError("Carry-in accepted offer and request assignment differ")
            accepted.add(request_id)
            occupancy_end = due.value + round(offer["pickup_seconds"] * 1e9)
            if request["state"] not in ("canceled", "expired"):
                occupancy_end += round(offer["trip_seconds"] * 1e9)
            periods.setdefault(vehicle_id, []).append((offered.value, occupancy_end))
        elif request["assigned_at"] is not None and stopping > _timestamp(
            request["assigned_at"], "assigned_at"
        ):
            raise ValueError("Carry-in offer occurred after driver assignment")
        if state != "accepted":
            periods.setdefault(vehicle_id, []).append((offered.value, stopping.value))
    if any(
        request["assigned_at"] is not None and key not in accepted
        for key, request in requests.items()
    ):
        raise ValueError("Carry-in driver assignment has no accepted offer")
    for groups in (periods, request_periods):
        for group in groups.values():
            ordered = sorted(group)
            if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:], strict=False)):
                raise ValueError("Carry-in offer reservations overlap")
    reservations = {offer["vehicle_id"]: offer for offer in pending.values()}
    if len(reservations) != len(pending):
        raise ValueError("Carry-in pending offers reserve a vehicle twice")
    for vehicle_id, vehicle in vehicles.items():
        offer = reservations.get(vehicle_id)
        if offer:
            if vehicle["state"] != "dispatch" or vehicle["pending_offer_id"] != offer["offer_id"]:
                raise ValueError("Carry-in offer and vehicle reservation differ")
        elif vehicle["state"] == "dispatch" or vehicle["pending_offer_id"] is not None:
            raise ValueError("Carry-in vehicle reservation has no pending offer")


def validate_carry_in(
    checkpoint: dict[str, Any],
    snapshot: dict[str, Any],
    rules: dict[str, Any],
    plan_version: str,
    seed: int,
    start: pd.Timestamp,
    resolved_compensation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixed_online = rules["schema_version"] == 3
    required = {
        "schema_version",
        "artifact_type",
        "timestamp",
        "timezone",
        "source_kind",
        "evidence_level",
        "calibration_status",
        "initial_snapshot_version",
        "demand_plan_version",
        "rules_version",
        "seed",
        "arrival_mode",
        "arrival_schedule",
        "request_version",
        "request_records",
        "vehicles",
        "pending_events",
        "next_sequence",
        "next_event_id",
        "open_requests",
        "resume_supported",
        "checkpoint_version",
    }
    if fixed_online:
        required |= {"offer_records", "next_offer_event_id"}
    if not isinstance(checkpoint, dict) or set(checkpoint) != required:
        raise ValueError("Carry-in has missing or unknown checkpoint fields")
    fixed = {
        "schema_version": 3 if fixed_online else 2,
        "artifact_type": "operational_checkpoint",
        "timezone": snapshot["timezone"],
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "initial_snapshot_version": snapshot["snapshot_version"],
        "demand_plan_version": plan_version,
        "rules_version": fingerprint(rules),
        "seed": seed,
        "resume_supported": True,
    }
    if (
        type(checkpoint["schema_version"]) is not int
        or type(checkpoint["seed"]) is not int
        or checkpoint["resume_supported"] is not True
        or any(checkpoint[key] != value for key, value in fixed.items())
        or checkpoint["checkpoint_version"] != fingerprint(_checkpoint_payload(checkpoint))
    ):
        raise ValueError("Carry-in checkpoint hash, versions, scope or seed differ")
    if _timestamp(checkpoint["timestamp"], "checkpoint timestamp") != start:
        raise ValueError("Carry-in timestamp must equal window_start")
    schedule = checkpoint["arrival_schedule"]
    if not isinstance(schedule, list) or len(schedule) > rules["max_requests"]:
        raise ValueError("Carry-in arrival schedule exceeds its declared budget")
    if fingerprint(schedule) != checkpoint["request_version"]:
        raise ValueError("Carry-in arrival schedule checksum differs")
    if checkpoint["arrival_mode"] not in ("prescribed", "piecewise_poisson"):
        raise ValueError("Carry-in arrival_mode is invalid")
    schedule_fields = {
        "request_id",
        "created_at",
        "origin_zone_id",
        "destination_zone_id",
        "service_id",
        "source_block_id",
        "cancel_at",
    }
    for row in schedule:
        if not isinstance(row, dict) or set(row) != schedule_fields:
            raise ValueError("Carry-in arrival schedule row is malformed")
        if not isinstance(row["request_id"], str) or not row["request_id"].strip():
            raise ValueError("Carry-in request ID is invalid")
        created = _timestamp(row["created_at"], "created_at")
        if (
            not _timestamp(snapshot["horizon_start"], "horizon_start")
            <= created
            < _timestamp(snapshot["horizon_end"], "horizon_end")
        ):
            raise ValueError("Carry-in arrival is outside the demand horizon")
        if any(
            type(row[key]) is not int or row[key] not in snapshot["zone_ids"]
            for key in ("origin_zone_id", "destination_zone_id")
        ) or row["service_id"] not in ("X", "Y"):
            raise ValueError("Carry-in arrival zone/service is invalid")
        if row["cancel_at"] is not None and _timestamp(row["cancel_at"], "cancel_at") < created:
            raise ValueError("Carry-in cancellation precedes creation")
    if schedule != sorted(schedule, key=lambda r: (r["created_at"], r["request_id"])):
        raise ValueError("Carry-in arrival schedule ordering differs")
    source = {r["request_id"]: r for r in schedule}
    if len(source) != len(schedule):
        raise ValueError("Carry-in arrival schedule has duplicate request IDs")
    records = checkpoint["request_records"]
    if not isinstance(records, list):
        raise ValueError("Carry-in request_records must be a list")
    record_fields = schedule_fields | {
        "state",
        "deadline_at",
        "vehicle_id",
        "assigned_at",
        "pickup_at",
        "completed_at",
        "dispatch_eta_seconds",
        "trip_seconds",
        "canceled_at",
        "expired_at",
        "terminal_reason",
    }
    if any(not isinstance(r, dict) or set(r) != record_fields for r in records):
        raise ValueError("Carry-in request record is malformed")
    requests = {r["request_id"]: r for r in records}
    if len(requests) != len(records) or not set(requests) <= set(source):
        raise ValueError("Carry-in request IDs are duplicate or absent from the schedule")
    if set(requests) != {
        key for key, row in source.items() if _timestamp(row["created_at"], "created_at") < start
    }:
        raise ValueError("Carry-in request history omits or replays arrivals")
    travel = {(r["origin_zone_id"], r["destination_zone_id"]): r for r in rules["travel_times"]}
    roster = {v["vehicle_id"]: v for v in snapshot["vehicles"]}
    for request_id, request in requests.items():
        original = source[request_id]
        if (
            not isinstance(request.get("state"), str)
            or request["state"] not in OPEN_STATES | TERMINAL_STATES
        ):
            raise ValueError("Carry-in request has an invalid state")
        if any(
            request.get(key) != original.get(key)
            for key in (
                "created_at",
                "origin_zone_id",
                "destination_zone_id",
                "service_id",
                "source_block_id",
                "cancel_at",
            )
        ):
            raise ValueError("Carry-in changed a request's frozen attributes")
        if _timestamp(request["created_at"], "created_at") >= start:
            raise ValueError("Carry-in request was not created before the checkpoint")
        previous = _timestamp(request["created_at"], "created_at")
        for key in ("assigned_at", "pickup_at", "completed_at"):
            if request.get(key) is not None:
                timestamp = _timestamp(request[key], key)
                if not previous <= timestamp <= start:
                    raise ValueError("Carry-in request timestamps are inconsistent")
                previous = timestamp
        if (
            request["state"] in ("pickup", "on_trip", "completed")
            and request.get("assigned_at") is None
        ):
            raise ValueError("Carry-in busy request has no assignment")
        if request["state"] in ("on_trip", "completed") and request.get("pickup_at") is None:
            raise ValueError("Carry-in on-trip request has no pickup")
        created = _timestamp(request["created_at"], "created_at")
        deadline = (
            None
            if rules["max_wait_seconds"] is None
            else _iso(created.value + round(rules["max_wait_seconds"] * 1e9))
        )
        if request["deadline_at"] != deadline:
            raise ValueError("Carry-in pickup deadline changed")
        assigned_at = request["assigned_at"]
        if assigned_at is None:
            if any(
                request[key] is not None
                for key in (
                    "vehicle_id",
                    "dispatch_eta_seconds",
                    "trip_seconds",
                    "pickup_at",
                    "completed_at",
                )
            ):
                raise ValueError("Carry-in unassigned request has trip fields")
        else:
            vehicle = roster.get(request["vehicle_id"])
            if vehicle is None or request["service_id"] not in vehicle["eligible_services"]:
                raise ValueError("Carry-in request assignment is ineligible")
            eta, trip = request["dispatch_eta_seconds"], request["trip_seconds"]
            if (
                type(eta) not in (int, float)
                or not np.isfinite(eta)
                or not 0 <= eta <= rules["max_pickup_seconds"]
                or type(trip) not in (int, float)
                or trip
                != travel[request["origin_zone_id"], request["destination_zone_id"]]["trip_seconds"]
            ):
                raise ValueError("Carry-in request durations are invalid")
            assigned_time = _timestamp(assigned_at, "assigned_at")
            pickup_time = assigned_time.value + round(eta * 1e9)
            if not fixed_online and (
                not _timestamp(vehicle["shift_start"], "shift_start") <= assigned_time
                or pickup_time + round(trip * 1e9)
                > _timestamp(vehicle["shift_end"], "shift_end").value
            ):
                raise ValueError("Carry-in assignment is outside its shift")
            if (
                request["pickup_at"] is not None
                and _timestamp(request["pickup_at"], "pickup_at").value != pickup_time
            ):
                raise ValueError("Carry-in pickup time changed")
            if request["completed_at"] is not None and _timestamp(
                request["completed_at"], "completed_at"
            ).value != pickup_time + round(trip * 1e9):
                raise ValueError("Carry-in completion time changed")
        if request["state"] == "queued" and assigned_at is not None:
            raise ValueError("Carry-in queued request was already assigned")
        if (
            request["state"] in ("queued", "pickup")
            and request["pickup_at"] is not None
            or request["state"] != "completed"
            and request["completed_at"] is not None
            or request["state"] == "completed"
            and request["completed_at"] is None
        ):
            raise ValueError("Carry-in state and trip timestamps differ")
        for state, field, reason, timer in (
            ("canceled", "canceled_at", "customer_cancel", "cancel_at"),
            ("expired", "expired_at", "pickup_deadline", "deadline_at"),
        ):
            if request["state"] == state:
                if (
                    request[field] is None
                    or request[field] != request[timer]
                    or request["terminal_reason"] != reason
                    or request["pickup_at"] is not None
                ):
                    raise ValueError("Carry-in terminal request is inconsistent")
                terminal_time = _timestamp(request[field], field)
                if not previous <= terminal_time <= start:
                    raise ValueError("Carry-in terminal timestamp is inconsistent")
            elif request[field] is not None:
                raise ValueError("Carry-in nonterminal request has a termination timestamp")
        if (
            request["state"] not in ("canceled", "expired")
            and request["terminal_reason"] is not None
        ):
            raise ValueError("Carry-in request has an unexpected terminal reason")
    if checkpoint["open_requests"] != [r for r in records if r["state"] in OPEN_STATES]:
        raise ValueError("Carry-in open_requests does not match request states")
    vehicles = checkpoint["vehicles"]
    if not isinstance(vehicles, list) or len(vehicles) != len(roster):
        raise ValueError("Carry-in shared roster differs")
    if any(
        not isinstance(v, dict)
        or not isinstance(v.get("vehicle_id"), str)
        or v.get("vehicle_id") not in roster
        or set(v)
        != set(roster[v["vehicle_id"]])
        | {"active_request_id", "pending_action", "next_event_at"}
        | ({"pending_offer_id"} if fixed_online else set())
        for v in vehicles
    ):
        raise ValueError("Carry-in vehicle row is malformed")
    restored = {v["vehicle_id"]: v for v in vehicles}
    if set(restored) != set(roster):
        raise ValueError("Carry-in vehicle IDs are duplicate or outside the roster")
    assigned = set()
    for vehicle_id, vehicle in restored.items():
        original = roster[vehicle_id]
        if any(
            vehicle.get(key) != original[key]
            for key in (
                "driver_id",
                "shift_id",
                "eligible_services",
                "soc",
                "shift_start",
                "shift_end",
            )
        ):
            raise ValueError("Carry-in changed fixed roster/shift/SOC attributes")
        if vehicle.get("zone_id") not in snapshot["zone_ids"] or vehicle.get("state") not in (
            "idle",
            "offline",
            "unavailable",
            "to_pickup",
            "on_trip",
            *(("dispatch",) if fixed_online else ()),
        ):
            raise ValueError("Carry-in vehicle state or zone is invalid")
        in_shift = (
            _timestamp(vehicle["shift_start"], "shift_start")
            <= start
            < _timestamp(vehicle["shift_end"], "shift_end")
        )
        if vehicle["state"] != "offline" and not in_shift and not fixed_online:
            raise ValueError("Carry-in active vehicle is outside its shift")
        if fixed_online and vehicle["state"] in ("offline", "unavailable"):
            raise ValueError("Fixed-online checkpoint removed an online driver")
        if vehicle["state"] == "idle" and vehicle["soc"] < rules["minimum_soc"]:
            raise ValueError("Carry-in idle vehicle has ineligible SOC")
        active, action = vehicle.get("active_request_id"), vehicle.get("pending_action")
        if active is not None and not isinstance(active, str):
            raise ValueError("Carry-in active request ID must be a string or null")
        if action is not None and (
            not isinstance(action, dict) or not isinstance(action.get("request_id"), str)
        ):
            raise ValueError("Carry-in pending vehicle action is malformed")
        if active and action:
            raise ValueError("Carry-in vehicle has both passenger and aborted activity")
        request_id = active or (action.get("request_id") if isinstance(action, dict) else None)
        if vehicle["state"] in ("to_pickup", "on_trip"):
            if request_id not in requests or request_id in assigned:
                raise ValueError("Carry-in busy vehicle/request link is missing or duplicated")
            assigned.add(request_id)
            request = requests[request_id]
            if request.get("vehicle_id") != vehicle_id:
                raise ValueError("Carry-in assignment is not reciprocal")
            expected_state = "pickup" if vehicle["state"] == "to_pickup" else "on_trip"
            if action:
                if (
                    action != {"kind": "finish_aborted_pickup", "request_id": request_id}
                    or vehicle["state"] != "to_pickup"
                    or request["state"] not in ("canceled", "expired")
                ):
                    raise ValueError("Carry-in aborted pickup is inconsistent")
            elif request["state"] != expected_state:
                raise ValueError("Carry-in vehicle and request phases differ")
            finish = _timestamp(vehicle.get("next_event_at"), "next_event_at")
            if not start < finish or (
                not fixed_online and finish > _timestamp(vehicle["shift_end"], "shift_end")
            ):
                raise ValueError("Carry-in next phase event is invalid")
            base_time = (
                request["assigned_at"] if vehicle["state"] == "to_pickup" else request["pickup_at"]
            )
            duration = (
                request["dispatch_eta_seconds"]
                if vehicle["state"] == "to_pickup"
                else request["trip_seconds"]
            )
            if finish.value != _timestamp(base_time, "phase start").value + round(duration * 1e9):
                raise ValueError("Carry-in phase completion time changed")
        elif active or action or vehicle.get("next_event_at") is not None:
            raise ValueError("Carry-in nonbusy vehicle has an active phase")
    offers: list[dict[str, Any]] = []
    if fixed_online:
        offers = checkpoint["offer_records"]
        _validate_offers(offers, restored, requests, rules, seed, start, resolved_compensation)
        expected_offer_events = sum(1 + (offer["state"] != "offered") for offer in offers)
        if (
            type(checkpoint["next_offer_event_id"]) is not int
            or checkpoint["next_offer_event_id"] != expected_offer_events
        ):
            raise ValueError("Carry-in offer event counter differs from history")
    if any(r["request_id"] not in assigned for r in records if r["state"] in ("pickup", "on_trip")):
        raise ValueError("Carry-in busy request has no vehicle")
    sequences = set()
    phase_events: dict[str, list[tuple[int, str]]] = {}
    actual_events: Counter = Counter()
    expected_events: Counter = Counter()
    for request_id, row in source.items():
        if request_id not in requests:
            expected_events[
                (_timestamp(row["created_at"], "created_at").value, "arrival", request_id)
            ] += 1
    for request_id, request in requests.items():
        for kind, field in (("expire", "deadline_at"), ("cancel", "cancel_at")):
            if request[field] is not None:
                timestamp = _timestamp(request[field], field).value
                if timestamp > start.value:
                    expected_events[(timestamp, kind, request_id)] += 1
    for vehicle_id, vehicle in restored.items():
        for kind in () if fixed_online else ("shift_start", "shift_end"):
            timestamp = _timestamp(vehicle[kind], kind).value
            if timestamp > start.value:
                expected_events[(timestamp, kind, vehicle_id)] += 1
        if vehicle["state"] in ("to_pickup", "on_trip"):
            kind = "pickup_complete" if vehicle["state"] == "to_pickup" else "trip_complete"
            expected_events[
                (_timestamp(vehicle["next_event_at"], "next_event_at").value, kind, vehicle_id)
            ] += 1
    for offer in offers:
        timestamp = _timestamp(offer["response_at"], "offer response_at").value
        if timestamp > start.value:
            expected_events[(timestamp, "offer_response", offer["offer_id"])] += 1
    if not isinstance(checkpoint["pending_events"], list):
        raise ValueError("Carry-in pending_events must be a list")
    for event in checkpoint["pending_events"]:
        if not isinstance(event, list) or len(event) != 4:
            raise ValueError("Carry-in pending event is malformed")
        timestamp, sequence, kind, entity_id = event
        if (
            type(timestamp) is not int
            or type(sequence) is not int
            or sequence < 0
            or sequence in sequences
            or not isinstance(kind, str)
            or kind not in EVENT_PRIORITY
            or not isinstance(entity_id, str)
            or timestamp < start.value
            or (timestamp == start.value and kind != "arrival")
        ):
            raise ValueError("Carry-in pending event time/order is invalid")
        sequences.add(sequence)
        actual_events[(timestamp, kind, entity_id)] += 1
        if kind == "arrival":
            if (
                entity_id not in source
                or entity_id in requests
                or timestamp != _timestamp(source[entity_id]["created_at"], "created_at").value
            ):
                raise ValueError("Carry-in arrival event differs from the frozen schedule")
        elif kind in ("pickup_complete", "trip_complete"):
            phase_events.setdefault(entity_id, []).append((timestamp, kind))
        elif kind in ("shift_start", "shift_end"):
            if entity_id not in restored:
                raise ValueError("Carry-in shift event has no vehicle")
        elif kind == "offer_response":
            if entity_id not in {offer["offer_id"] for offer in offers}:
                raise ValueError("Carry-in offer response has no offer")
        elif entity_id not in requests:
            raise ValueError("Carry-in request timer has no request")
    if actual_events != expected_events:
        raise ValueError("Carry-in pending events are missing, duplicated or changed")
    for key in ("next_sequence", "next_event_id"):
        if type(checkpoint[key]) is not int or checkpoint[key] < 0:
            raise ValueError("Carry-in event counters must be nonnegative integers")
    if sequences and max(sequences) >= checkpoint["next_sequence"]:
        raise ValueError("Carry-in next sequence reuses an event ID")
    expected_event_id = sum(
        2
        + 2 * (r["assigned_at"] is not None)
        + (r["pickup_at"] is not None)
        + (r["state"] in TERMINAL_STATES)
        for r in records
    )
    if checkpoint["next_event_id"] != expected_event_id:
        raise ValueError("Carry-in request event counter differs from history")
    for vehicle_id, vehicle in restored.items():
        expected = (
            []
            if vehicle["state"] not in ("to_pickup", "on_trip")
            else [
                (
                    _timestamp(vehicle["next_event_at"], "next_event_at").value,
                    "pickup_complete" if vehicle["state"] == "to_pickup" else "trip_complete",
                )
            ]
        )
        if phase_events.pop(vehicle_id, []) != expected:
            raise ValueError("Carry-in vehicle phase event is missing or duplicated")
    if phase_events:
        raise ValueError("Carry-in phase event has no vehicle")
    return copy.deepcopy(checkpoint)


def simulate_marketplace_continuation(
    plan: DemandPlan,
    rules: dict[str, Any],
    config: Config,
    seed: int,
    prescribed_requests: pd.DataFrame | None = None,
    *,
    window_start: str | None = None,
    window_end: str | None = None,
    carry_in: dict[str, Any] | None = None,
    resolved_compensation: dict[str, Any] | None = None,
) -> SimulationResult:
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    frame, snapshot = _validate_plan(plan, config)
    rules = _normalize_rules(rules, snapshot)
    fixed_online = rules["schema_version"] == 3
    source_start = _timestamp(snapshot["horizon_start"], "horizon_start")
    source_end = _timestamp(snapshot["horizon_end"], "horizon_end")
    start = _timestamp(window_start, "window_start") if window_start is not None else source_start
    end = _timestamp(window_end, "window_end") if window_end is not None else source_end
    if not source_start <= start < end <= source_end:
        raise ValueError("Simulation window must lie within the frozen demand horizon")
    if carry_in is None and start != source_start:
        raise ValueError("A later window_start requires carry_in")
    budget = _Budget(rules)
    plan_version = plan.result["demand_plan_version"]
    checkpoint = None
    if carry_in is not None:
        checkpoint = validate_carry_in(
            carry_in, snapshot, rules, plan_version, seed, start, resolved_compensation
        )
        schedule = checkpoint["arrival_schedule"]
        arrival_mode = checkpoint["arrival_mode"]
        if prescribed_requests is not None:
            supplied = _arrival_schedule(frame, snapshot, rules, seed, prescribed_requests, budget)
            if supplied != schedule:
                raise ValueError("Prescribed schedule differs from carry-in")
    else:
        schedule = _arrival_schedule(frame, snapshot, rules, seed, prescribed_requests, budget)
        arrival_mode = "prescribed" if prescribed_requests is not None else "piecewise_poisson"
    engine = (
        _OfferMarketplace(
            snapshot, rules, schedule, start, end, budget, checkpoint, seed, resolved_compensation
        )
        if fixed_online
        else _WindowMarketplace(snapshot, rules, schedule, start, end, budget, checkpoint)
    )
    engine.run()
    window_ids = engine.open_start | engine.created_ids
    rows = []
    picked_up = {e["request_id"] for e in engine.events if e["state"] == "on_trip"}
    for request_id in sorted(window_ids):
        request = engine.records[request_id]
        row = {key: request.get(key) for key in REQUEST_COLUMNS + EXTRA_REQUEST_COLUMNS}
        created = _timestamp(request["created_at"], "created_at")
        pickup = _timestamp(request["pickup_at"], "pickup_at") if request.get("pickup_at") else None
        stopping = (
            pickup
            or (
                _timestamp(request["canceled_at"], "canceled_at")
                if request.get("canceled_at")
                else None
            )
            or (
                _timestamp(request["expired_at"], "expired_at")
                if request.get("expired_at")
                else end
            )
        )
        row.update(
            wait_seconds=(pickup - created).total_seconds() if pickup is not None else None,
            observed_wait_seconds=(stopping - created).total_seconds(),
            wait_censored=pickup is None and request["state"] in OPEN_STATES,
            completion_censored=request["state"] in OPEN_STATES,
            wait_status="picked_up"
            if pickup is not None
            else (
                "open_censored" if request["state"] in OPEN_STATES else "terminated_before_pickup"
            ),
            created_in_window=request_id in engine.created_ids,
            carry_in=request_id in engine.open_start,
        )
        rows.append(row)
    requests = pd.DataFrame(rows, columns=pd.Index(REQUEST_COLUMNS + EXTRA_REQUEST_COLUMNS))
    events = pd.DataFrame(engine.events, columns=pd.Index(EVENT_COLUMNS)).astype(
        {"event_id": "int64"}
    )
    intervals = pd.DataFrame(
        engine.intervals, columns=pd.Index(VEHICLE_COLUMNS + ["activity_kind"])
    )
    counts = {
        state: sum(e["state"] == state for e in engine.events)
        for state in ("created", "completed", "canceled", "expired")
    }
    open_end = sum(r["state"] in OPEN_STATES for r in engine.records.values())
    if (
        len(engine.open_start) + counts["created"]
        != sum(counts[s] for s in TERMINAL_STATES) + open_end
    ):
        raise RuntimeError("Simulation request conservation failed")
    hours = {
        state: float(intervals.loc[intervals.state.eq(state), "duration_hours"].sum())
        for state in ("idle", "dispatch", "to_pickup", "on_trip", "offline", "unavailable")
    }
    total_hours = len(engine.vehicles) * (end - start).total_seconds() / 3600
    if not np.isclose(sum(hours.values()), total_hours, rtol=1e-10, atol=1e-10):
        raise RuntimeError("Simulation vehicle-hour conservation failed")
    for vehicle_id, group in intervals.groupby("vehicle_id"):
        beginnings = pd.to_datetime(group.start, format="ISO8601")
        endings = pd.to_datetime(group.end, format="ISO8601")
        if (
            beginnings.iloc[0] != start
            or endings.iloc[-1] != end
            or beginnings.iloc[1:].to_list() != endings.iloc[:-1].to_list()
        ):
            raise RuntimeError(f"Vehicle state intervals overlap or leave gaps: {vehicle_id}")
    waits = [
        (
            _timestamp(engine.records[key]["pickup_at"], "pickup_at")
            - _timestamp(engine.records[key]["created_at"], "created_at")
        ).total_seconds()
        for key in sorted(picked_up)
    ]
    wait_series = pd.Series(waits, dtype=float)
    summary = {
        "created_requests": counts["created"],
        "completed_trips": counts["completed"],
        "canceled_requests": counts["canceled"],
        "expired_requests": counts["expired"],
        "open_requests_start": len(engine.open_start),
        "open_requests_end": open_end,
        **{
            f"{state}_requests_end": sum(r["state"] == state for r in engine.records.values())
            for state in ("queued", "pickup", "on_trip")
        },
        "serviceable_hours": hours["idle"]
        + hours["dispatch"]
        + hours["to_pickup"]
        + hours["on_trip"],
        "idle_hours": hours["idle"],
        "dispatch_hours": hours["dispatch"],
        "pickup_hours": hours["to_pickup"],
        "on_trip_hours": hours["on_trip"],
        "offline_hours": hours["offline"],
        "ineligible_hours": hours["unavailable"],
        "total_vehicle_hours": total_hours,
        "aborted_pickup_hours": float(
            intervals.loc[intervals.activity_kind.eq("aborted_pickup"), "duration_hours"].sum()
        ),
        "mean_wait_seconds": float(wait_series.mean()) if waits else None,
        "p95_wait_seconds": float(wait_series.quantile(0.95, interpolation="linear"))
        if waits
        else None,
        "wait_observed_requests": len(waits),
        "wait_censored_requests": int(requests.wait_censored.sum()),
        "terminated_before_pickup_requests": int(
            requests.wait_status.eq("terminated_before_pickup").sum()
        ),
    }
    spec = {
        "schema_version": 3 if fixed_online else 2,
        "simulation_mode": "fixed_online_offers" if fixed_online else "fixed_supply_continuation",
        "seed": seed,
        "rules": rules,
        "rules_version": fingerprint(rules),
        "demand_plan_version": plan_version,
        "snapshot_version": snapshot["snapshot_version"],
        "policy_version": plan.spec["policy_version"],
        "arrival_mode": arrival_mode,
        "request_version": fingerprint(schedule),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "carry_in_version": checkpoint["checkpoint_version"] if checkpoint else None,
        "tie_rule": (
            "phase completion, expiry/cancel, shifts, arrivals, then FIFO matching; "
            "zero-time phases settled"
        ),
        "horizon_rule": (
            "new arrivals [start,end); other events through end; "
            "operational continuation preserves pending events"
        ),
        "cancel_rule": "before pickup only; aborted pickup leg finishes before vehicle release",
        "price_application": "already in request_rate; simulator never reapplies price effects",
        "soc_rule": "fixed SOC; energy and charging unavailable",
        "units": {
            "wait": "seconds",
            "supply": "vehicle-hours",
            "requests": "requests",
            "trips": "trips",
        },
    }
    version = fingerprint(spec)
    result = {
        "schema_version": 3 if fixed_online else 2,
        "simulation_version": version,
        "status": "ok",
        "simulation_mode": spec["simulation_mode"],
        "source_kind": "synthetic",
        "evidence_level": "C",
        "demand_source_kind": plan.result["source_kind"],
        "calibration_status": "not_calibrated",
        "scope": {
            "horizon_start": start.isoformat(),
            "horizon_end": end.isoformat(),
            "zones": snapshot["zone_ids"],
            "vehicles": len(engine.vehicles),
        },
        "summary": summary,
        "by_service": {
            service: {
                "created_requests": sum(
                    e["state"] == "created"
                    and engine.records[e["request_id"]]["service_id"] == service
                    for e in engine.events
                ),
                "completed_trips": sum(
                    e["state"] == "completed"
                    and engine.records[e["request_id"]]["service_id"] == service
                    for e in engine.events
                ),
                "open_requests_end": sum(
                    r["state"] in OPEN_STATES and r["service_id"] == service
                    for r in engine.records.values()
                ),
            }
            for service in ("X", "Y")
        },
        "units": spec["units"],
        "wait_population": "pickups occurring in this window, using original creation times",
        "wait_quantile_method": "linear",
        "wait_status": "ok" if waits else "unavailable_no_pickups",
        "request_accounting": "open_start + created = completed + canceled + expired + open_end",
        "vehicle_accounting": (
            "serviceable = idle + dispatch + pickup + on_trip; shared fleet counted once"
        ),
        "interval_status": "interval_unavailable",
        "interval_reason": "Single synthetic trajectory",
        "unavailable_metrics": {
            "cancellation_rate": "Counts supplied; cohort/time-window rate estimand not defined",
            "charging": "Energy/charging not modeled",
            "economics": "No compensation/cost ledger",
        },
        "budget_work_units": budget.work_units,
    }
    records = [copy.deepcopy(engine.records[key]) for key in sorted(engine.records)]
    end_vehicles = [
        {key: value for key, value in vehicle.items() if key != "state_start_ns"}
        for _, vehicle in sorted(engine.vehicles.items())
    ]
    end_snapshot = {
        "schema_version": 3 if fixed_online else 2,
        "artifact_type": "operational_checkpoint",
        "timestamp": end.isoformat(),
        "timezone": snapshot["timezone"],
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "initial_snapshot_version": snapshot["snapshot_version"],
        "demand_plan_version": plan_version,
        "rules_version": fingerprint(rules),
        "seed": seed,
        "arrival_mode": arrival_mode,
        "arrival_schedule": schedule,
        "request_version": fingerprint(schedule),
        "request_records": records,
        "vehicles": end_vehicles,
        "pending_events": [
            [timestamp, sequence, kind, entity_id]
            for timestamp, _, sequence, kind, entity_id in sorted(engine.pending)
        ],
        "next_sequence": engine.next_sequence,
        "next_event_id": engine.next_event_id,
        "open_requests": [r for r in records if r["state"] in OPEN_STATES],
        "resume_supported": True,
    }
    end_snapshot["checkpoint_version"] = fingerprint(end_snapshot)
    simulation = SimulationResult(requests, events, intervals, end_snapshot, result, spec)
    if isinstance(engine, _OfferMarketplace):
        offer_ids = engine.open_offers_start | engine.new_offer_ids
        simulation.driver_offers = pd.DataFrame(
            [engine.offers[key] for key in sorted(offer_ids)], columns=pd.Index(OFFER_COLUMNS)
        ).astype(OFFER_DTYPES)
        simulation.offer_events = pd.DataFrame(
            engine.offer_events, columns=pd.Index(OFFER_EVENT_COLUMNS)
        ).astype(OFFER_DTYPES | {"offer_event_id": "int64"})
        outcomes = {
            state: sum(row["state"] == state for row in engine.offer_events)
            for state in ("offered", "accepted", "rejected", "timed_out", "withdrawn")
        }
        pending_end = sum(row["state"] == "offered" for row in engine.offers.values())
        if (
            len(engine.open_offers_start) + outcomes["offered"]
            != sum(outcomes[state] for state in ("accepted", "rejected", "timed_out", "withdrawn"))
            + pending_end
        ):
            raise RuntimeError("Simulation offer conservation failed")
        denominator = outcomes["accepted"] + outcomes["rejected"] + outcomes["timed_out"]
        result["offers"] = {
            **outcomes,
            "pending_start": len(engine.open_offers_start),
            "pending_end": pending_end,
            "acceptance_rate": outcomes["accepted"] / denominator if denominator else None,
            "acceptance_denominator": denominator,
            "acceptance_population": (
                "accepted + rejected + timed_out response events in this window; "
                "withdrawals excluded"
            ),
            "acceptance_status": "ok" if denominator else "unavailable_no_responses",
            "accounting": (
                "pending_start + offered = accepted + rejected + timed_out "
                "+ withdrawn + pending_end"
            ),
        }
        result["scope"].update(
            online_drivers=len(engine.vehicles), online_population_rule="fixed_roster"
        )
        summary["online_hours"] = total_hours
        summary["online_drivers"] = len(engine.vehicles)
        spec.update(
            online_population_rule="fixed_roster",
            acceptance_model="declared_synthetic_price_independent",
            tie_rule=(
                "phase completion; request expiry/cancel; offer response; arrivals; FIFO matching"
            ),
            horizon_rule=(
                "observation only; unfinished trips/offers remain censored with resumable state"
            ),
        )
        result["simulation_version"] = fingerprint(spec)
        end_snapshot.update(
            offer_records=[copy.deepcopy(engine.offers[key]) for key in sorted(engine.offers)],
            next_offer_event_id=engine.next_offer_event_id,
        )
        end_snapshot["checkpoint_version"] = fingerprint(_checkpoint_payload(end_snapshot))
    return simulation


def simulate_marketplace(
    plan: DemandPlan,
    rules: dict[str, Any],
    config: Config,
    seed: int,
    prescribed_requests: pd.DataFrame | None = None,
    *,
    window_start: str | None = None,
    window_end: str | None = None,
    carry_in: dict[str, Any] | None = None,
    compensation: dict[str, Any] | None = None,
) -> SimulationResult:
    """Run a legacy trajectory or a resumable operational window."""
    resolved = (
        resolve_compensation(compensation, plan.spec["policy"])
        if compensation is not None
        else None
    )
    source_checkpoint_version = None
    if carry_in is not None:
        if not isinstance(carry_in, dict):
            raise ValueError("Carry-in checkpoint must be an object")
        context = carry_in.get("compensation_context")
        if context is not None:
            if fingerprint(_checkpoint_payload(carry_in)) != carry_in.get("checkpoint_version"):
                raise ValueError("Compensation checkpoint checksum differs")
            if resolved is None or context != {
                "compensation_version": resolved["compensation_version"],
                "terms_version": resolved["terms_version"],
            }:
                raise ValueError(
                    "Continuation requires the same frozen compensation and fare terms"
                )
            source_checkpoint_version = carry_in["checkpoint_version"]
            carry_in = copy.deepcopy(carry_in)
            carry_in.pop("compensation_context")
            carry_in["checkpoint_version"] = fingerprint(_checkpoint_payload(carry_in))
        elif resolved is not None:
            raise ValueError("Cannot add compensation to a checkpoint without frozen fare terms")
    if (
        window_start is not None
        or window_end is not None
        or carry_in is not None
        or (isinstance(rules, dict) and rules.get("schema_version") in (2, 3))
    ):
        simulation = simulate_marketplace_continuation(
            plan,
            rules,
            config,
            seed,
            prescribed_requests,
            window_start=window_start,
            window_end=window_end,
            carry_in=carry_in,
            resolved_compensation=resolved,
        )
    else:
        simulation = _simulate_marketplace_v1(plan, rules, config, seed, prescribed_requests)
    if resolved is not None:
        # shortcut: fixed attendance; add identified income response before changing labor hours.
        scope = simulation.result["scope"]
        financial = settle_earnings(
            simulation.requests,
            simulation.request_events,
            simulation.vehicle_intervals,
            plan.snapshot,
            resolved,
            scope["horizon_start"],
            scope["horizon_end"],
        )
        simulation.financial_tables = {
            name: financial[name]
            for name in ("quote_terms", "driver_pay_terms", "earnings_ledger", "driver_income")
        }
        simulation.spec["compensation"] = resolved
        if source_checkpoint_version is not None:
            simulation.spec["carry_in_version"] = source_checkpoint_version
        simulation.result["simulation_version"] = fingerprint(simulation.spec)
        simulation.result["earnings"] = financial["result"]
        simulation.result["unavailable_metrics"]["economics"] = (
            "Gross fare and driver pay supplied; costs, GSM profit and ROI not evaluated"
        )
        if simulation.end_snapshot.get("resume_supported") is True:
            simulation.end_snapshot["compensation_context"] = {
                "compensation_version": resolved["compensation_version"],
                "terms_version": resolved["terms_version"],
            }
            simulation.end_snapshot["checkpoint_version"] = fingerprint(
                _checkpoint_payload(simulation.end_snapshot)
            )
    return simulation
