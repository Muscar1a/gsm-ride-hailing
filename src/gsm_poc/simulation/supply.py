"""Independent observed/oracle outputs for controlled labor-supply recovery tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from gsm_poc.causal.supply import OBSERVED_COLUMNS, SupplySpec, validate_supply_data


def generate_supply(spec: SupplySpec) -> tuple[pd.DataFrame, pd.DataFrame]:
    context_seed, assignment_seed, response_seed = np.random.SeedSequence(spec.seed).spawn(3)
    context_rng = np.random.default_rng(context_seed)
    assignment_rng = np.random.default_rng(assignment_seed)
    response_rng = np.random.default_rng(response_seed)
    n_rows = spec.n_drivers * spec.n_shifts
    driver_index = np.repeat(np.arange(spec.n_drivers), spec.n_shifts)
    shift_index = np.tile(np.arange(spec.n_shifts), spec.n_drivers)
    driver_effect = context_rng.uniform(-0.1, 0.1, spec.n_drivers)[driver_index]
    hours_effect = context_rng.uniform(-0.5, 0.5, spec.n_drivers)[driver_index]
    fraction = context_rng.uniform(
        spec.serviceable_fraction_min, spec.serviceable_fraction_max, spec.n_drivers
    )[driver_index]
    assigned = assignment_rng.binomial(1, 0.5, spec.n_drivers)[driver_index]
    participation_draw = response_rng.uniform(0, 1, n_rows)
    hours_draw = response_rng.uniform(-0.5, 0.5, n_rows)
    p_baseline = spec.participation_base + driver_effect
    p_target = p_baseline + spec.participation_effect
    h_baseline = spec.conditional_hours_base + hours_effect
    h_target = h_baseline + spec.conditional_hours_effect
    participated = participation_draw < np.where(assigned, p_target, p_baseline)
    hours = participated * (np.where(assigned, h_target, h_baseline) + hours_draw)
    initial = pd.Timestamp(spec.start_at).tz_convert("UTC")
    shift_start = initial + pd.to_timedelta(shift_index, unit="D")
    shift_end = shift_start + pd.Timedelta(hours=spec.shift_hours)
    frame = pd.DataFrame(
        {
            "decision_id": [
                f"driver-{driver}-shift-{shift}"
                for driver, shift in zip(driver_index, shift_index, strict=True)
            ],
            "driver_id": [f"driver-{driver}" for driver in driver_index],
            "shift_id": [f"shift-{shift}" for shift in shift_index],
            "eligibility_at": initial - pd.Timedelta(days=2),
            "offered_at": initial - pd.Timedelta(days=1),
            "decision_at": shift_start - pd.Timedelta(minutes=15),
            "shift_start": shift_start,
            "shift_end": shift_end,
            "outcome_observed_at": shift_end + pd.Timedelta(minutes=1),
            "offered_incentive_amount": np.where(
                assigned, spec.target_incentive, spec.baseline_incentive
            ),
            "assignment_probability": 0.5,
            "participated": participated.astype(int),
            "worked_hours": hours,
            "serviceable_hours": hours * fraction,
        },
        columns=pd.Index(OBSERVED_COLUMNS),
    )
    oracle = pd.DataFrame(
        {
            "decision_id": frame.decision_id,
            "driver_id": frame.driver_id,
            "shift_id": frame.shift_id,
            "participated_baseline": p_baseline,
            "participated_target": p_target,
            "worked_hours_baseline": p_baseline * h_baseline,
            "worked_hours_target": p_target * h_target,
            "serviceable_hours_baseline": p_baseline * h_baseline * fraction,
            "serviceable_hours_target": p_target * h_target * fraction,
            "serviceable_fraction": fraction,
        }
    )
    validate_supply_data(frame, spec.contract())
    return frame, oracle
