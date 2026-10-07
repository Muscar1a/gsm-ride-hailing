from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import check_grad

from gsm_poc.artifacts import completed_run
from gsm_poc.swissmetro import (
    fit_model,
    likelihood_gradient,
    log_probabilities,
    model_arrays,
    prepare_data,
    run_benchmark,
    score_model,
    split_people,
)


@pytest.fixture
def raw_choices():
    """Small, deterministic synthetic survey fixture, not public Swissmetro results."""
    rng = np.random.default_rng(813)
    rows = 360
    raw = pd.DataFrame(
        {
            "ID": np.repeat(np.arange(1, 61), 6),
            "SP": 1,
            "GA": 0,
            "TRAIN_AV": 1,
            "SM_AV": 1,
            "CAR_AV": rng.integers(0, 2, rows),
            "TRAIN_TT": rng.uniform(90, 250, rows),
            "SM_TT": rng.uniform(30, 100, rows),
            "CAR_TT": rng.uniform(70, 220, rows),
            "TRAIN_CO": rng.uniform(10, 70, rows),
            "SM_CO": rng.uniform(20, 90, rows),
            "CAR_CO": rng.uniform(10, 100, rows),
        }
    )
    utilities = -0.012 * raw[["TRAIN_TT", "SM_TT", "CAR_TT"]].to_numpy()
    utilities -= 0.01 * raw[["TRAIN_CO", "SM_CO", "CAR_CO"]].to_numpy()
    utilities[:, 2] = np.where(raw.CAR_AV, utilities[:, 2], -np.inf)
    utilities -= utilities.max(axis=1, keepdims=True)
    probabilities = np.exp(utilities)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    raw["CHOICE"] = [rng.choice((1, 2, 3), p=p) for p in probabilities]
    return raw


def test_unknown_choices_and_duplicate_tasks_preserved(raw_choices):
    raw_choices.loc[0, "CHOICE"] = 0
    raw = pd.concat([raw_choices, raw_choices.iloc[[1]]], ignore_index=True)
    frame, quality = prepare_data(raw)
    assert len(frame) == len(raw) - 1
    assert quality["unknown_choice_rows"] == 1
    assert quality["duplicate_attribute_rows"] == 2
    assert frame.source_row.is_unique
    assert (frame.person_id == raw_choices.loc[1, "ID"]).sum() == 6


@pytest.mark.parametrize(
    "column,value", [("GA", 2), ("ID", 1.5), ("CHOICE", 4), ("TRAIN_TT", -1), ("SM_CO", np.nan)]
)
def test_invalid_source_rejected(raw_choices, column, value):
    raw = raw_choices.astype({column: float})
    raw.loc[0, column] = value
    with pytest.raises(ValueError):
        prepare_data(raw)


def test_chosen_unavailable_and_empty_sources_rejected(raw_choices):
    raw_choices.loc[0, ["CHOICE", "CAR_AV"]] = [3, 0]
    with pytest.raises(ValueError, match="chosen alternative"):
        prepare_data(raw_choices)
    with pytest.raises(ValueError, match="empty"):
        prepare_data(raw_choices.iloc[:0])
    with pytest.raises(ValueError, match="missing columns"):
        prepare_data(raw_choices.drop(columns="GA"))


def test_person_split_disjoint_reproducible_and_complete(raw_choices):
    frame, _ = prepare_data(raw_choices)
    splits = split_people(frame, 31001)
    repeated = split_people(frame.sample(frac=1, random_state=1), 31001)
    groups = [set(part.person_id) for part in splits.values()]
    assert all(not groups[i] & groups[j] for i in range(3) for j in range(i))
    assert set.union(*groups) == set(frame.person_id)
    assert sum(map(len, splits.values())) == len(frame)
    for name in splits:
        assert set(splits[name].person_id) == set(repeated[name].person_id)


def test_ga_cost_and_masked_probabilities(raw_choices):
    raw_choices.loc[0, "GA"] = 1
    raw_choices.loc[0, ["CHOICE", "CAR_AV"]] = [2, 0]
    frame, _ = prepare_data(raw_choices)
    features, availability, _ = model_arrays(frame, True)
    assert features[0, 0, 3] == features[0, 1, 3] == 0
    assert features[0, 2, 3] == frame.loc[0, "CAR_CO"] / 100
    probabilities = np.exp(
        log_probabilities(np.array([10.0, 500.0, -1.0, -1.0]), features, availability)
    )
    assert np.allclose(probabilities.sum(axis=1), 1)
    assert (probabilities[~availability] == 0).all()


def test_gradient_matches_numerical_likelihood(raw_choices):
    frame, _ = prepare_data(raw_choices)
    features, availability, choices = model_arrays(frame, True)
    error = check_grad(
        lambda beta: likelihood_gradient(beta, features, availability, choices)[0],
        lambda beta: likelihood_gradient(beta, features, availability, choices)[1],
        np.array([0.2, -0.4, -1.1, -0.5]),
    )
    assert error < 1e-6


def test_holdout_values_cannot_change_training_fit(raw_choices):
    frame, _ = prepare_data(raw_choices)
    splits = split_people(frame, 31001)
    model = fit_model(splits["train"], True)
    held_out_ids = set(splits["validation"].person_id) | set(splits["test"].person_id)
    changed = frame.copy()
    changed.loc[changed.person_id.isin(held_out_ids), "TRAIN_CO"] *= 10
    refit = fit_model(split_people(changed, 31001)["train"], True)
    assert model["coefficients"] == refit["coefficients"]
    metrics, _ = score_model(model, splits["test"], "test", "multinomial_logit")
    assert np.isfinite(metrics["log_loss"])


def test_nonconvergence_fails_instead_of_reporting_success(raw_choices, monkeypatch):
    from gsm_poc import swissmetro

    frame, _ = prepare_data(raw_choices)
    original = swissmetro.minimize

    def failed_minimize(*args, **kwargs):
        result = original(*args, **kwargs)
        result.success = False
        return result

    monkeypatch.setattr(swissmetro, "minimize", failed_minimize)
    with pytest.raises(RuntimeError, match="did not converge"):
        fit_model(frame, True)


def test_benchmark_exports_and_verified_reuse(raw_choices, tmp_path):
    data = tmp_path / "synthetic_fixture.dat"
    raw_choices.to_csv(data, sep="\t", index=False)
    run = run_benchmark(tmp_path, data, 31001, "fixture-swissmetro", "synthetic_fixture")
    manifest = completed_run(tmp_path, run.run_id)
    assert manifest["source_kind"] == "synthetic_fixture"
    metrics = pd.read_csv(run.path / "swissmetro/metrics.csv")
    assert len(metrics) == 6
    assert metrics.unavailable_probability_violations.eq(0).all()
    resumed = run_benchmark(tmp_path, data, 31001, run.run_id, "synthetic_fixture")
    assert (
        resumed.manifest["stages"]["swissmetro"]["duration_seconds"]
        == (manifest["stages"]["swissmetro"]["duration_seconds"])
    )
