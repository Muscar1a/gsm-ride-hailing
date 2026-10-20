from __future__ import annotations

import dataclasses

import joblib
import numpy as np
import pytest

from gsm_poc.causal.estimate import fit_estimator
from gsm_poc.causal.evaluate import effect_rows
from gsm_poc.causal.features import date_splits
from gsm_poc.causal.identification import identifies
from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.causal.uncertainty import BootstrapResult
from gsm_poc.simulation.dgp import TRUE_THETA


@pytest.fixture
def collinear_blocks(exact_blocks):
    frame = exact_blocks.copy()
    change = frame.log_multiplier_x - frame.log_multiplier_y
    for j, label in enumerate(("x", "y")):
        frame[f"q_{label}"] += change * TRUE_THETA[j, 1]
        frame[f"n_{label}"] = np.round(frame[f"q_{label}"] * frame.n_sessions).astype(int)
        frame[f"q_{label}"] = frame[f"n_{label}"] / frame.n_sessions
    frame["n_none"] = frame.n_sessions - frame.n_x - frame.n_y
    frame["q_none"] = frame.n_none / frame.n_sessions
    frame["multiplier_y"] = frame.multiplier_x
    frame["log_multiplier_y"] = frame.log_multiplier_x
    return frame


def fit_contrast(frame, config):
    splits = date_splits(frame, config)
    result = fit_estimator(splits["train"], config, "contrast_ols")
    assert result.bundle is not None
    return result, splits


def test_collinear_joint_effect_and_hidden_columns(config, collinear_blocks):
    result, splits = fit_contrast(collinear_blocks, config)
    request = ScenarioRequest(delta_price_x=0.05, delta_price_y=0.05)
    output = scenario(result.bundle, splits["test"], request, config, "contrast-test")
    assert output["status"] == "ok", output
    assert output["theta"] == [[None, None], [None, None]]
    assert output["theta_interval"] == [[None, None], [None, None]]
    expected = TRUE_THETA @ np.log([1.05, 1.05]) * 100
    actual = [output["probabilities"][label]["delta_percentage_points"] for label in ("X", "Y")]
    np.testing.assert_allclose(actual, expected, atol=1e-8)
    for row in effect_rows(result, None, splits["test"], config, "test", "dataset"):
        assert row["status"] == "not_identified" and row["theta"] is None
    assert fit_estimator(splits["train"], config, "adjusted_ols").bundle is None


@pytest.mark.parametrize("baseline", [(1, 1), (0.95, 1)])
def test_unidentified_contrast_or_absolute_level_rejected(config, collinear_blocks, baseline):
    result, splits = fit_contrast(collinear_blocks, config)
    request = ScenarioRequest(baseline_multiplier_x=baseline[0], baseline_multiplier_y=baseline[1])
    output = scenario(result.bundle, splits["test"], request, config, "contrast-test")
    assert output["status"] == "not_identified"
    assert "probabilities" not in output


def test_full_rank_matches_adjusted_ols(config, exact_blocks):
    result, splits = fit_contrast(exact_blocks, config)
    reference = fit_estimator(splits["train"], config, "adjusted_ols")
    np.testing.assert_allclose(result.bundle.theta, reference.bundle.theta, atol=1e-12)
    contexts = splits["test"].query("zone_id == 161 and is_peak == 0 and is_weekend == 0")
    first = scenario(result.bundle, contexts, ScenarioRequest(), config, "new")
    second = scenario(reference.bundle, contexts, ScenarioRequest(), config, "old")
    assert first["status"] == second["status"]
    np.testing.assert_allclose(first["delta_expected_bookings"], second["delta_expected_bookings"])
    assert first["interval"].keys() == second["interval"].keys()
    for key in first["interval"]:
        np.testing.assert_allclose(
            list(first["interval"][key].values()),
            list(second["interval"][key].values()),
            atol=1e-12,
            rtol=1e-12,
        )


def test_no_variation_rejected(config, exact_blocks):
    frame = exact_blocks[
        np.isclose(exact_blocks.multiplier_x, 1) & np.isclose(exact_blocks.multiplier_y, 1)
    ]
    train = date_splits(frame, config)["train"]
    assert fit_estimator(train, config, "contrast_ols").bundle is None


def test_weak_residual_variation_is_not_promoted(config, exact_blocks):
    frame = exact_blocks.copy()
    frame["log_multiplier_x"] *= 1e-5
    frame["log_multiplier_y"] *= 1e-5
    frame["multiplier_x"] = np.exp(frame.log_multiplier_x)
    frame["multiplier_y"] = np.exp(frame.log_multiplier_y)
    result = fit_estimator(date_splits(frame, config)["train"], config, "contrast_ols")
    assert result.bundle is None
    assert result.diagnostics["residual_rank"] == 0


def test_estimable_change_does_not_identify_absolute_prices(config, collinear_blocks):
    result, splits = fit_contrast(collinear_blocks, config)
    request = ScenarioRequest(baseline_multiplier_x=0.95, delta_price_x=0.05, delta_price_y=0.05)
    output = scenario(result.bundle, splits["test"], request, config, "test")
    assert output["status"] == "not_identified"
    assert output["identification"]["contrast_identified"]
    assert not output["identification"]["absolute_levels_identified"]
    assert "probabilities" not in output


def test_unsupported_baseline_and_thin_context_withhold(config, collinear_blocks):
    result, splits = fit_contrast(collinear_blocks, config)
    outside = ScenarioRequest(
        baseline_multiplier_x=0.85, baseline_multiplier_y=0.85, delta_price_x=0.1, delta_price_y=0.1
    )
    output = scenario(result.bundle, splits["test"], outside, config, "test")
    assert output["status"] == "out_of_support" and "probabilities" not in output
    strict = dataclasses.replace(
        config, model=dataclasses.replace(config.model, min_price_cell_count=100000)
    )
    output = scenario(
        result.bundle, splits["test"], ScenarioRequest(delta_price_y=0.1), strict, "test"
    )
    assert output["status"] == "insufficient_support" and "probabilities" not in output


def test_bootstrap_lost_identification_withholds_interval(config, collinear_blocks, exact_blocks):
    result, splits = fit_contrast(collinear_blocks, config)
    single = exact_blocks[np.isclose(exact_blocks.multiplier_y, 1)]
    other, _ = fit_contrast(single, config)
    bundles = [result.bundle, other.bundle]
    draws = BootstrapResult("contrast_ols", [], bundles, "ok", 2, 0.95)
    reporting = dataclasses.replace(
        config,
        evaluation=dataclasses.replace(
            config.evaluation, reporting_min_draws=1, max_failure_fraction=0.9
        ),
    )
    output = scenario(
        result.bundle,
        splits["test"],
        ScenarioRequest(delta_price_y=0.1),
        reporting,
        "test",
        draws,
        inference_method="bootstrap",
    )
    assert output["interval_status"] == "interval_unstable"
    assert output["bootstrap"]["fit_failed_draws"] == 0
    assert output["bootstrap"]["lost_identification_draws"] == 1
    assert output["interval"] is None


def test_serialized_model_keeps_guards(config, collinear_blocks, tmp_path):
    result, splits = fit_contrast(collinear_blocks, config)
    path = tmp_path / "model.joblib"
    joblib.dump(result.bundle, path)
    loaded = joblib.load(path)
    assert identifies(loaded, np.log([1.1, 1.1]))
    assert not identifies(loaded, np.log([1.1, 1]))
    with pytest.raises(ValueError, match="not identified"):
        loaded.probabilities(splits["test"], np.log([1.1, 1]))


def test_invalid_probabilities_rejected(config, collinear_blocks):
    result, splits = fit_contrast(collinear_blocks, config)
    result.bundle.base_rate_model.intercept_ += 1
    output = scenario(
        result.bundle, splits["test"], ScenarioRequest(delta_price_y=0.1), config, "test"
    )
    assert output["status"] == "invalid_probability"
    assert "probabilities" not in output
