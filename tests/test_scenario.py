import dataclasses

import numpy as np
import pytest

from gsm_poc.estimate import fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.scenario import ScenarioRequest, scenario
from gsm_poc.uncertainty import BootstrapResult


@pytest.fixture
def fitted(config, exact_blocks):
    splits = date_splits(exact_blocks, config)
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    return bundle, splits["test"]


def test_plus10_log_ratio_orientation_and_count_conservation(config, fitted):
    bundle, context = fitted
    result = scenario(bundle, context, ScenarioRequest(), config, "test-run")
    values = result["probabilities"]
    assert values["X"]["delta_percentage_points"] == pytest.approx(-0.60 * np.log(1.1) * 100)
    assert values["Y"]["delta_percentage_points"] == pytest.approx(0.12 * np.log(1.1) * 100)
    assert result["delta_expected_bookings"] == pytest.approx(-0.48 * np.log(1.1) * 10000)
    assert sum(v["before_probability"] for v in values.values()) == pytest.approx(1)
    assert sum(v["after_expected_choices"] for v in values.values()) == pytest.approx(10000)
    assert result["evidence_level"] == "C"
    assert result["interval"] is None
    assert result["bootstrap"]["interval_status"] == "interval_unstable"


def test_price_y_is_second_column_and_unchanged_prices_zero_effect(config, fitted):
    bundle, context = fitted
    result = scenario(
        bundle, context, ScenarioRequest(delta_price_x=0, delta_price_y=0.1), config, "test-run"
    )
    assert result["probabilities"]["X"]["delta_percentage_points"] == pytest.approx(
        0.15 * np.log(1.1) * 100
    )
    result = scenario(
        bundle, context, ScenarioRequest(delta_price_x=0, delta_price_y=0), config, "test-run"
    )
    assert result["delta_expected_bookings"] == pytest.approx(0)


def test_outside_joint_support_has_no_forecast(config, fitted):
    bundle, context = fitted
    result = scenario(bundle, context, ScenarioRequest(delta_price_x=0.2), config, "test-run")
    assert result["status"] == "out_of_support"
    assert "probabilities" not in result
    bundle.train_support = bundle.train_support[
        ~((bundle.train_support.multiplier_x == 1.1) & (bundle.train_support.multiplier_y == 1.0))
    ]
    result = scenario(bundle, context, ScenarioRequest(), config, "test-run")
    assert result["status"] == "out_of_support"


def test_invalid_probability_rejected_without_clipping(config, fitted):
    bundle, context = fitted
    bundle.base_rate_model.intercept_ = np.array([-0.1, 0.5])
    result = scenario(bundle, context, ScenarioRequest(), config, "test-run")
    assert result["status"] == "invalid_probability"
    assert "probabilities" not in result


def test_bad_draws_are_counted_and_interval_withheld(config, fitted):
    bundle, context = fitted
    invalid = dataclasses.replace(bundle)
    invalid.base_rate_model = dataclasses.replace(bundle).base_rate_model.__class__()
    invalid.base_rate_model.__dict__.update(bundle.base_rate_model.__dict__)
    invalid.base_rate_model.intercept_ = np.array([-0.5, 0.5])
    draws = BootstrapResult("adjusted_ols", [], [bundle, invalid, None], "ok", 3, 0.95)
    result = scenario(bundle, context, ScenarioRequest(), config, "test-run", draws)
    assert result["bootstrap"]["invalid_probability_draws"] == 1
    assert result["bootstrap"]["fit_failed_draws"] == 1
    assert result["bootstrap"]["failure_fraction"] == pytest.approx(2 / 3)
    assert result["interval"] is None


@pytest.mark.parametrize(
    "scenario_request",
    [
        ScenarioRequest(delta_price_x=-1),
        ScenarioRequest(delta_price_x=float("nan")),
        ScenarioRequest(n_sessions=0),
    ],
)
def test_invalid_request_rejected(config, fitted, scenario_request):
    bundle, context = fitted
    with pytest.raises(ValueError):
        scenario(bundle, context, scenario_request, config, "test-run")
