"""Controlled offered-incentive effects on the complete eligible driver cohort."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import t

from gsm_poc.core.artifacts import fingerprint

OUTCOMES = ("participated", "worked_hours", "serviceable_hours")
TIME_COLUMNS = (
    "eligibility_at",
    "offered_at",
    "decision_at",
    "shift_start",
    "shift_end",
    "outcome_observed_at",
)
OBSERVED_COLUMNS = (
    "decision_id",
    "driver_id",
    "shift_id",
    *TIME_COLUMNS,
    "offered_incentive_amount",
    "assignment_probability",
    *OUTCOMES,
)
CONTRACT_FIELDS = {
    "schema_version",
    "source_kind",
    "evidence_level",
    "assignment_unit",
    "assignment_mechanism",
    "assignment_probability",
    "n_drivers",
    "n_shifts",
    "shift_hours",
    "start_at",
    "baseline_incentive",
    "target_incentive",
    "currency",
    "min_drivers_per_arm",
    "interval_level",
    "serviceable_definition",
}


def _timestamp(value: Any) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Supply timestamps must be valid and offset-aware") from exc
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError("Supply timestamps must be valid and offset-aware")
    return timestamp.tz_convert("UTC")


def _finite(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not np.isfinite(value):
        raise ValueError(f"{name} must be finite numeric data")
    return float(value)


@dataclasses.dataclass(frozen=True)
class SupplySpec:
    schema_version: int = 1
    seed: int = 51000
    n_drivers: int = 800
    n_shifts: int = 7
    shift_hours: float = 8.0
    start_at: str = "2026-01-01T08:00:00+00:00"
    baseline_incentive: float = 0.0
    target_incentive: float = 20.0
    currency: str = "SYNTHETIC_UNIT"
    participation_base: float = 0.45
    participation_effect: float = 0.15
    conditional_hours_base: float = 5.0
    conditional_hours_effect: float = 1.0
    serviceable_fraction_min: float = 0.75
    serviceable_fraction_max: float = 0.95
    min_drivers_per_arm: int = 20
    interval_level: float = 0.95

    def __post_init__(self) -> None:
        validate_contract(self.contract())
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be an integer in [0, 2**32)")
        for name in (
            "participation_base",
            "participation_effect",
            "conditional_hours_base",
            "conditional_hours_effect",
            "serviceable_fraction_min",
            "serviceable_fraction_max",
        ):
            _finite(getattr(self, name), name)
        for probability in (
            self.participation_base,
            self.participation_base + self.participation_effect,
        ):
            if not 0.1 <= probability <= 0.9:
                raise ValueError("Participation means must leave room for +/-0.1 driver effects")
        for hours in (
            self.conditional_hours_base,
            self.conditional_hours_base + self.conditional_hours_effect,
        ):
            if not 1 < hours <= self.shift_hours - 1:
                raise ValueError("Conditional hours must leave room for +/-1 hour noise")
        if not 0 <= self.serviceable_fraction_min <= self.serviceable_fraction_max <= 1:
            raise ValueError("Serviceable fractions must be ordered within [0, 1]")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SupplySpec:
        fields = {field.name for field in dataclasses.fields(cls)}
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("Supply specification has missing or unknown fields")
        return cls(**value)

    def contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_kind": "synthetic",
            "evidence_level": "C",
            "assignment_unit": "driver_id",
            "assignment_mechanism": "independent_bernoulli",
            "assignment_probability": 0.5,
            "n_drivers": self.n_drivers,
            "n_shifts": self.n_shifts,
            "shift_hours": self.shift_hours,
            "start_at": self.start_at,
            "baseline_incentive": self.baseline_incentive,
            "target_incentive": self.target_incentive,
            "currency": self.currency,
            "min_drivers_per_arm": self.min_drivers_per_arm,
            "interval_level": self.interval_level,
            "serviceable_definition": "declared_fraction_of_worked_hours",
        }


def validate_contract(contract: dict[str, Any]) -> None:
    if not isinstance(contract, dict) or set(contract) != CONTRACT_FIELDS:
        raise ValueError("Supply contract has missing or unknown fields")
    fixed = {
        "schema_version": 1,
        "source_kind": "synthetic",
        "evidence_level": "C",
        "assignment_unit": "driver_id",
        "assignment_mechanism": "independent_bernoulli",
        "assignment_probability": 0.5,
        "currency": "SYNTHETIC_UNIT",
        "serviceable_definition": "declared_fraction_of_worked_hours",
    }
    if type(contract["schema_version"]) is not int or any(
        contract[name] != value for name, value in fixed.items()
    ):
        raise ValueError(
            "Only the declared synthetic driver-randomized supply contract is supported"
        )
    for name, minimum, maximum in (
        ("n_drivers", 4, 10000),
        ("n_shifts", 1, 28),
        ("min_drivers_per_arm", 2, 5000),
    ):
        value = contract[name]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    hours = _finite(contract["shift_hours"], "shift_hours")
    baseline = _finite(contract["baseline_incentive"], "baseline_incentive")
    target = _finite(contract["target_incentive"], "target_incentive")
    level = _finite(contract["interval_level"], "interval_level")
    if not 0 < hours <= 24 or not 0 <= baseline < target or not 0 < level < 1:
        raise ValueError("Invalid hours, incentive contrast or interval level")
    if not isinstance(contract["start_at"], str):
        raise ValueError("start_at must be an offset-aware string")
    _timestamp(contract["start_at"])


def validate_supply_data(frame: pd.DataFrame, contract: dict[str, Any]) -> dict[str, Any]:
    """Require the complete predeclared cohort; missing outcomes are never zero-filled."""
    validate_contract(contract)
    if set(frame.columns) != set(OBSERVED_COLUMNS) or frame.columns.duplicated().any():
        raise ValueError("Observed supply data have missing, unknown or oracle columns")
    if frame.empty or frame.isna().to_numpy().any():
        raise ValueError("Supply data must be nonempty and fully observed")
    for column in ("driver_id", "shift_id", "decision_id"):
        if (
            not frame[column]
            .map(lambda value: isinstance(value, str) and bool(value.strip()))
            .all()
        ):
            raise ValueError(f"{column} must contain nonempty string IDs")
    if frame.decision_id.duplicated().any() or frame.duplicated(["driver_id", "shift_id"]).any():
        raise ValueError("Duplicate driver/shift decisions")
    counts = frame.groupby("driver_id", sort=True).size()
    if (
        len(counts) != contract["n_drivers"]
        or not counts.eq(contract["n_shifts"]).all()
        or frame.shift_id.nunique() != contract["n_shifts"]
    ):
        raise ValueError(
            "Incomplete eligible cohort; retain nonparticipants and all declared shifts"
        )
    for column in ("offered_incentive_amount", "assignment_probability", *OUTCOMES):
        if (
            not pd.api.types.is_numeric_dtype(frame[column])
            or not np.isfinite(frame[column].to_numpy(dtype=float)).all()
        ):
            raise ValueError(f"{column} must contain finite numeric values")
    if not frame.participated.isin([0, 1]).all():
        raise ValueError("participated must be binary")
    if not frame.assignment_probability.eq(contract["assignment_probability"]).all():
        raise ValueError("Assignment probability differs from the randomized contract")
    if not frame.offered_incentive_amount.isin(
        [contract["baseline_incentive"], contract["target_incentive"]]
    ).all():
        raise ValueError("Offered terms fall outside the declared contrast")
    if not frame.groupby("driver_id").offered_incentive_amount.nunique().eq(1).all():
        raise ValueError("Driver assignment changes across shifts")
    if (
        (frame.worked_hours < 0).any()
        or (frame.worked_hours > contract["shift_hours"]).any()
        or (frame.serviceable_hours < 0).any()
        or (frame.serviceable_hours > frame.worked_hours).any()
        or frame.loc[frame.participated.eq(0), ["worked_hours", "serviceable_hours"]]
        .ne(0)
        .to_numpy()
        .any()
    ):
        raise ValueError("Invalid labor/serviceable hours or nonparticipant outcomes")
    times = {}
    for column in TIME_COLUMNS:
        if not frame[column].astype(str).str.contains(r"(?:Z|[+-]\d{2}:\d{2})$").all():
            raise ValueError(f"{column} must be offset-aware")
        try:
            times[column] = pd.to_datetime(frame[column], utc=True, format="mixed", errors="raise")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid {column}") from exc
    for before, after in zip(TIME_COLUMNS[:-1], TIME_COLUMNS[1:], strict=True):
        if (times[before] > times[after]).any():
            raise ValueError(f"{before} must precede {after}; postdecision terms are invalid")
    if (
        (times["offered_at"] >= times["decision_at"]).any()
        or (times["shift_start"] >= times["shift_end"]).any()
        or not ((times["shift_end"] - times["shift_start"]).dt.total_seconds() / 3600)
        .eq(contract["shift_hours"])
        .all()
    ):
        raise ValueError("Offered terms must precede decisions and shifts must match the horizon")
    starts = frame.assign(parsed_start=times["shift_start"]).groupby("shift_id").parsed_start
    if not starts.nunique().eq(1).all():
        raise ValueError("A shift ID has inconsistent timestamps")
    expected_starts = {
        _timestamp(contract["start_at"]) + pd.Timedelta(days=day)
        for day in range(contract["n_shifts"])
    }
    if set(times["shift_start"]) != expected_starts:
        raise ValueError("Observed shifts differ from the declared follow-up calendar")
    return {
        "eligible_drivers": len(counts),
        "eligible_driver_shifts": len(frame),
        "nonparticipating_driver_shifts": int(frame.participated.eq(0).sum()),
        "zero_hour_driver_shifts": int(frame.worked_hours.eq(0).sum()),
    }


def fit_supply(frame: pd.DataFrame, contract: dict[str, Any]) -> dict[str, Any]:
    """Fixed randomized contrast, Welch inference on driver means, no oracle inputs."""
    quality = validate_supply_data(frame, contract)
    drivers = frame.groupby("driver_id", sort=True).agg(
        offered_incentive_amount=("offered_incentive_amount", "first"),
        **{outcome: (outcome, "mean") for outcome in OUTCOMES},
    )
    arms = [
        drivers.loc[drivers.offered_incentive_amount.eq(contract[name]), list(OUTCOMES)]
        for name in ("baseline_incentive", "target_incentive")
    ]
    n_baseline, n_target = map(len, arms)
    supported = min(n_baseline, n_target) >= contract["min_drivers_per_arm"]
    result: dict[str, Any] = {
        "schema_version": 1,
        "estimator": "randomized_driver_mean_contrast",
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "status": "ok" if supported else "not_identified",
        "support_status": "ok" if supported else "insufficient_support",
        "reasons": [] if supported else ["Too few distinct drivers in one or both incentive arms"],
        "contract": dict(contract),
        "contract_id": fingerprint(contract),
        "observed_id": fingerprint(frame.to_dict("list")),
        "inference_unit": "driver_id",
        "inference_method": "welch_t_on_driver_means",
        "interval_scope": "individual_outcome",
        "coverage_status": "not_evaluated_for_this_fit",
        "estimand": "offered_incentive_effect_per_eligible_driver_shift",
        "population": "predeclared_eligible_cohort_including_nonparticipants",
        "quality": quality,
        "arm_drivers": {"baseline": n_baseline, "target": n_target},
        "effects": [],
        "no_response_baseline": {outcome: 0.0 for outcome in OUTCOMES},
        "income_elasticity_status": "not_identified",
        "physical_schedule_status": "not_integrated",
    }
    for outcome in OUTCOMES:
        row: dict[str, Any] = {
            "outcome": outcome,
            "unit": "probability"
            if outcome == "participated"
            else "hours_per_eligible_driver_shift",
            "status": result["status"],
            "interval_status": "interval_unavailable",
            "baseline_mean": None,
            "target_mean": None,
            "effect": None,
            "standard_error": None,
            "degrees_of_freedom": None,
            "ci_low": None,
            "ci_high": None,
        }
        if supported:
            baseline, target = (arm[outcome].to_numpy(dtype=float) for arm in arms)
            effect = float(target.mean() - baseline.mean())
            row.update(
                baseline_mean=float(baseline.mean()),
                target_mean=float(target.mean()),
                effect=effect,
            )
            variance_baseline = float(baseline.var(ddof=1) / n_baseline)
            variance_target = float(target.var(ddof=1) / n_target)
            variance = variance_baseline + variance_target
            if variance > 0:
                degrees = variance**2 / (
                    variance_baseline**2 / (n_baseline - 1) + variance_target**2 / (n_target - 1)
                )
                standard_error = float(np.sqrt(variance))
                half_width = float(t.ppf((1 + contract["interval_level"]) / 2, degrees)) * (
                    standard_error
                )
                row.update(
                    standard_error=standard_error,
                    degrees_of_freedom=degrees,
                    ci_low=effect - half_width,
                    ci_high=effect + half_width,
                    interval_status="ok",
                )
            else:
                row["interval_reason"] = "Zero observed driver-level variance"
        result["effects"].append(row)
    descriptions = []
    for name in ("baseline_incentive", "target_incentive"):
        participating = frame.loc[
            frame.offered_incentive_amount.eq(contract[name]) & frame.participated.eq(1)
        ]
        descriptions.append(
            {
                "arm": name,
                "participating_shifts": len(participating),
                "conditional_worked_hours": float(participating.worked_hours.mean())
                if len(participating)
                else None,
                "interpretation": "descriptive_selected_population_not_a_causal_effect",
            }
        )
    result["conditional_hours_description"] = descriptions
    result["model_id"] = fingerprint(result)
    return result


def supply_scenario(bundle: dict[str, Any], incentive_amount: float) -> dict[str, Any]:
    """Forecast only the frozen cohort and the two identified offered-term levels."""
    amount = _finite(incentive_amount, "incentive_amount")
    identity = {key: value for key, value in bundle.items() if key != "model_id"}
    if bundle.get("model_id") != fingerprint(identity):
        raise ValueError("Supply model identity mismatch")
    contract = bundle["contract"]
    validate_contract(contract)
    if bundle["contract_id"] != fingerprint(contract):
        raise ValueError("Supply model contract identity mismatch")
    result: dict[str, Any] = {
        "schema_version": 1,
        "model_id": bundle["model_id"],
        "evidence_level": "C",
        "source_kind": "synthetic",
        "calibration_status": "not_calibrated",
        "incentive_amount": amount,
        "currency": contract["currency"],
        "status": bundle["status"],
        "support_status": bundle["support_status"],
        "reasons": list(bundle["reasons"]),
        "population": bundle["population"],
        "eligible_drivers": contract["n_drivers"],
        "n_shifts": contract["n_shifts"],
        "start_at": contract["start_at"],
        "interval_scope": "individual_outcome_fixed_cohort",
        "forecast_kind": "expected_response_not_an_admitted_physical_schedule",
        "income_elasticity_status": "not_identified",
        "physical_schedule_status": "not_integrated",
        "metrics": [],
    }
    if amount not in (contract["baseline_incentive"], contract["target_incentive"]):
        result.update(
            status="unsupported_action",
            support_status="insufficient_support",
            reasons=["Only the two randomized offered-incentive levels are identified"],
        )
        return result
    if bundle["status"] != "ok":
        return result
    baseline_policy = amount == contract["baseline_incentive"]
    exposure = contract["n_drivers"] * contract["n_shifts"]
    for row in bundle["effects"]:
        scale = 1 if row["outcome"] == "participated" else exposure
        change = 0.0 if baseline_policy else row["effect"] * scale
        interval_available = baseline_policy or row["interval_status"] == "ok"
        result["metrics"].append(
            {
                "outcome": row["outcome"],
                "unit": "probability" if row["outcome"] == "participated" else "cohort_hours",
                "baseline": row["baseline_mean"] * scale,
                "target": row["baseline_mean" if baseline_policy else "target_mean"] * scale,
                "change": change,
                "ci_low": 0.0
                if baseline_policy
                else (row["ci_low"] * scale if interval_available else None),
                "ci_high": 0.0
                if baseline_policy
                else (row["ci_high"] * scale if interval_available else None),
                "interval_status": "deterministic_identity"
                if baseline_policy
                else row["interval_status"],
                "interval_target": "policy_change_only",
            }
        )
    return result
