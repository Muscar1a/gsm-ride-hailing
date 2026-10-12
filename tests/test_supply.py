from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from scipy.stats import ttest_ind

from gsm_poc.causal.benchmarks.supply import SupplyProtocol, evaluate_supply
from gsm_poc.causal.supply import (
    OBSERVED_COLUMNS,
    SupplySpec,
    fit_supply,
    supply_scenario,
    validate_supply_data,
)
from gsm_poc.simulation.supply import generate_supply


@pytest.fixture
def supply_spec():
    return SupplySpec(n_drivers=120, n_shifts=3, min_drivers_per_arm=10)


def test_generation_replays_and_preserves_complete_eligible_population(supply_spec):
    observed, oracle = generate_supply(supply_spec)
    second_observed, second_oracle = generate_supply(supply_spec)
    pd.testing.assert_frame_equal(observed, second_observed)
    pd.testing.assert_frame_equal(oracle, second_oracle)
    assert set(observed.columns) == set(OBSERVED_COLUMNS)
    assert not set(observed.columns) & (
        set(oracle.columns) - {"decision_id", "driver_id", "shift_id"}
    )
    assert len(observed) == 360
    assert observed.groupby("driver_id").size().eq(3).all()
    assert observed.participated.eq(0).any()
    assert (
        observed.loc[observed.participated.eq(0), ["worked_hours", "serviceable_hours"]]
        .eq(0)
        .all()
        .all()
    )
    assert (observed.serviceable_hours <= observed.worked_hours).all()


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": -1},
        {"seed": True},
        {"n_drivers": 0},
        {"n_shifts": 29},
        {"shift_hours": np.inf},
        {"target_incentive": 0},
        {"currency": "VND"},
        {"participation_effect": 1},
        {"conditional_hours_base": 0},
        {"serviceable_fraction_max": 2},
        {"interval_level": 1},
        {"start_at": "2026-01-01"},
        {"min_drivers_per_arm": 1},
    ],
)
def test_invalid_specification_is_rejected(supply_spec, changes):
    with pytest.raises(ValueError):
        dataclasses.replace(supply_spec, **changes)


def test_unknown_specification_and_real_data_contract_are_rejected(supply_spec):
    values = dataclasses.asdict(supply_spec)
    values["oracle_effect"] = 1
    with pytest.raises(ValueError, match="unknown"):
        SupplySpec.from_dict(values)
    observed, _ = generate_supply(supply_spec)
    contract = supply_spec.contract() | {"evidence_level": "A"}
    with pytest.raises(ValueError, match="synthetic"):
        fit_supply(observed, contract)


@pytest.mark.parametrize(
    "corruption",
    [
        "oracle",
        "missing",
        "duplicate",
        "nan",
        "infinite",
        "hours",
        "zero",
        "assignment",
        "probability",
        "naive_time",
        "late_terms",
        "calendar",
        "unknown_terms",
        "binary",
    ],
)
def test_observed_contract_rejects_invalid_or_leaking_inputs(supply_spec, corruption):
    observed, _ = generate_supply(supply_spec)
    if corruption == "oracle":
        observed["truth"] = 0
    elif corruption == "missing":
        observed = observed.iloc[1:].copy()
    elif corruption == "duplicate":
        observed = pd.concat([observed, observed.iloc[:1]], ignore_index=True)
    elif corruption == "nan":
        observed.loc[0, "worked_hours"] = np.nan
    elif corruption == "infinite":
        observed.loc[0, "serviceable_hours"] = np.inf
    elif corruption == "hours":
        observed.loc[0, "serviceable_hours"] = supply_spec.shift_hours + 1
    elif corruption == "zero":
        observed.loc[0, ["participated", "worked_hours", "serviceable_hours"]] = [0, 1, 1]
    elif corruption == "assignment":
        amount = observed.loc[0, "offered_incentive_amount"]
        observed.loc[0, "offered_incentive_amount"] = (
            supply_spec.target_incentive
            if amount == supply_spec.baseline_incentive
            else supply_spec.baseline_incentive
        )
    elif corruption == "probability":
        observed.loc[0, "assignment_probability"] = 0.7
    elif corruption == "naive_time":
        observed["offered_at"] = observed.offered_at.dt.tz_localize(None)
    elif corruption == "late_terms":
        observed.loc[0, "offered_at"] = observed.loc[0, "outcome_observed_at"]
    elif corruption == "calendar":
        observed["shift_start"] += pd.Timedelta(days=1)
        observed["shift_end"] += pd.Timedelta(days=1)
        observed["outcome_observed_at"] += pd.Timedelta(days=1)
    elif corruption == "unknown_terms":
        observed.loc[0, "offered_incentive_amount"] = 10
    elif corruption == "binary":
        observed.loc[0, "participated"] = 2
    with pytest.raises(ValueError):
        validate_supply_data(observed, supply_spec.contract())


def test_welch_intervals_match_independent_scipy_reference_on_driver_means(supply_spec):
    observed, _ = generate_supply(supply_spec)
    fitted = fit_supply(observed, supply_spec.contract())
    driver_means = observed.groupby("driver_id").mean(numeric_only=True)
    for row in fitted["effects"]:
        baseline = driver_means.loc[driver_means.offered_incentive_amount.eq(0), row["outcome"]]
        target = driver_means.loc[driver_means.offered_incentive_amount.eq(20), row["outcome"]]
        reference = ttest_ind(target, baseline, equal_var=False)
        interval = reference.confidence_interval(confidence_level=supply_spec.interval_level)
        assert row["effect"] == pytest.approx(target.mean() - baseline.mean())
        assert row["degrees_of_freedom"] == pytest.approx(reference.df)
        assert row["ci_low"] == pytest.approx(interval.low)
        assert row["ci_high"] == pytest.approx(interval.high)
    assert fitted["quality"]["nonparticipating_driver_shifts"] > 0
    assert all(
        "not_a_causal_effect" in row["interpretation"]
        for row in fitted["conditional_hours_description"]
    )
    assert fitted["income_elasticity_status"] == "not_identified"


def test_repeated_identical_shifts_do_not_create_independent_drivers(supply_spec):
    spec = dataclasses.replace(supply_spec, n_shifts=1)
    observed, _ = generate_supply(spec)
    repeated = []
    for day in range(3):
        part = observed.copy()
        part["decision_id"] += f"-repeat-{day}"
        part["shift_id"] = f"shift-{day}"
        for column in ("decision_at", "shift_start", "shift_end", "outcome_observed_at"):
            part[column] += pd.Timedelta(days=day)
        repeated.append(part)
    one = fit_supply(observed, spec.contract())
    three = fit_supply(pd.concat(repeated, ignore_index=True), supply_spec.contract())
    for before, after in zip(one["effects"], three["effects"], strict=True):
        assert before["standard_error"] == pytest.approx(after["standard_error"])
        assert before["effect"] == pytest.approx(after["effect"])
    assert one["arm_drivers"] == three["arm_drivers"]


def test_no_arm_support_withholds_effects_and_forecasts(supply_spec):
    observed, _ = generate_supply(supply_spec)
    observed["offered_incentive_amount"] = 0.0
    fitted = fit_supply(observed, supply_spec.contract())
    assert fitted["status"] == "not_identified"
    assert fitted["support_status"] == "insufficient_support"
    assert all(row["effect"] is None and row["ci_low"] is None for row in fitted["effects"])
    scenario = supply_scenario(fitted, 20)
    assert scenario["status"] == "not_identified"
    assert scenario["metrics"] == []


def test_zero_supply_is_valid_without_fabricated_interval(supply_spec):
    observed, _ = generate_supply(supply_spec)
    observed[["participated", "worked_hours", "serviceable_hours"]] = 0
    fitted = fit_supply(observed, supply_spec.contract())
    assert fitted["status"] == "ok"
    assert all(
        row["effect"] == 0 and row["interval_status"] == "interval_unavailable"
        for row in fitted["effects"]
    )
    target = supply_scenario(fitted, 20)
    assert all(row["change"] == 0 and row["ci_low"] is None for row in target["metrics"])


def test_scenarios_preserve_scope_units_and_reject_extrapolation_and_stale_models(supply_spec):
    observed, _ = generate_supply(supply_spec)
    fitted = fit_supply(observed, supply_spec.contract())
    target = supply_scenario(fitted, 20)
    baseline = supply_scenario(fitted, 0)
    assert target["physical_schedule_status"] == "not_integrated"
    assert target["currency"] == "SYNTHETIC_UNIT"
    assert all(
        row["change"] == 0 and row["ci_low"] == row["ci_high"] == 0 for row in baseline["metrics"]
    )
    for effect, metric in zip(fitted["effects"], target["metrics"], strict=True):
        scale = 1 if effect["outcome"] == "participated" else 360
        assert metric["change"] == pytest.approx(effect["effect"] * scale)
        assert metric["ci_low"] == pytest.approx(effect["ci_low"] * scale)
    unsupported = supply_scenario(fitted, 10)
    assert unsupported["status"] == "unsupported_action"
    assert unsupported["metrics"] == []
    with pytest.raises(ValueError, match="finite"):
        supply_scenario(fitted, float("nan"))
    damaged = dict(fitted)
    damaged["contract"] = fitted["contract"] | {"target_incentive": 30}
    with pytest.raises(ValueError, match="identity"):
        supply_scenario(damaged, 30)


def test_benchmark_keeps_attempted_denominators_and_does_not_certify_calibration(supply_spec):
    protocol = SupplyProtocol(phase="pilot", n_seeds=2, rct_seed_start=101, null_seed_start=201)
    records, summary = evaluate_supply(supply_spec, protocol)
    assert len(records) == 12
    assert summary["attempted_seed_jobs"] == 4
    assert summary["nominal_coverage_certified"] is False
    assert summary["status"] == "development_only"
    assert records.loc[records.dgp.eq("NULL_SUPPLY"), "truth"].eq(0).all()
    assert all(row["attempted"] == 2 for row in summary["summaries"])
    assert records.observed_id.notna().all()
    unsupported = dataclasses.replace(supply_spec, min_drivers_per_arm=120)
    _, failed = evaluate_supply(unsupported, protocol)
    assert failed["seed_jobs_with_all_intervals"] == 0
    assert all(
        row["unavailable_intervals"] == 2 and row["coverage"] is None for row in failed["summaries"]
    )


def test_benchmark_time_budget_is_bounded(supply_spec, monkeypatch):
    from gsm_poc.causal.benchmarks import supply

    values = iter([0.0, 601.0])
    monkeypatch.setattr(supply.time, "perf_counter", lambda: next(values))
    with pytest.raises(RuntimeError, match="budget exhausted"):
        evaluate_supply(supply_spec, SupplyProtocol(phase="pilot", n_seeds=1))


@pytest.mark.parametrize(
    "changes",
    [
        {"n_seeds": 0},
        {"n_seeds": 501},
        {"n_seeds": 5},
        {"rct_seed_start": -1},
        {"null_seed_start": 61001},
        {"max_seconds": 601},
        {"coverage_floor": 1},
        {"phase": "final_tuned"},
    ],
)
def test_invalid_benchmark_protocol_is_rejected(changes):
    with pytest.raises(ValueError):
        SupplyProtocol(**changes)
