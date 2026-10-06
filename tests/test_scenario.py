import dataclasses
from itertools import product

import numpy as np
import pandas as pd
import pytest

from gsm_poc.estimate import fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.scenario import ScenarioRequest, joint_support, scenario
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
    assert result["target_context_set"] == "all"
    assert result["scope"]["target_context_set"] == "all"
    assert result["scope"]["zones"] == sorted(context.zone_id.unique())
    assert result["scope"]["context_blocks"] == len(context)
    assert result["scope"]["context_weight_sessions"] == int(context.n_sessions.sum())
    assert result["request"]["target_context_set"] == "all"
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
        ScenarioRequest(target_context_set=""),
        ScenarioRequest(target_context_set="   "),
    ],
)
def test_invalid_request_rejected(config, fitted, scenario_request):
    bundle, context = fitted
    with pytest.raises(ValueError):
        scenario(bundle, context, scenario_request, config, "test-run")


def test_scenario_saves_custom_scope_and_selected_zone(config, fitted):
    bundle, context = fitted
    selected = context[context.zone_id == 161]
    request = ScenarioRequest(target_context_set="zone_161")
    result = scenario(bundle, selected, request, config, "test-run")
    assert result["target_context_set"] == "zone_161"
    assert result["scope"]["target_context_set"] == "zone_161"
    assert result["scope"]["zones"] == [161]
    assert result["scope"]["selected_zone"] == 161
    assert result["scope"]["context_blocks"] == len(selected)
    assert result["scope"]["context_weight_sessions"] == int(selected.n_sessions.sum())
    assert result["request"]["target_context_set"] == "zone_161"


@pytest.mark.parametrize(
    ("selected_count", "target_x"),
    [(0, 1.1), (19, 1.1), (20, 1.1), (19, 1.05), (20, 1.05)],
)
def test_support_counts_each_selected_context_at_each_price_corner(
    config, fitted, selected_count, target_x
):
    bundle, context = fitted
    config = dataclasses.replace(
        config, model=dataclasses.replace(config.model, min_price_cell_count=20)
    )
    # A fully supported synthetic table except for one selected group/corner.
    rows = []
    for zone, weekend, peak, x, y in product(
        config.source.zones, (0, 1), (0, 1), (0.9, 1.0, 1.1), (0.9, 1.0, 1.1)
    ):
        count = selected_count if (zone, weekend, peak, x, y) == (161, 0, 0, 1.1, 1.0) else 20
        rows.extend(
            [
                {
                    "zone_id": zone,
                    "is_weekend": weekend,
                    "is_peak": peak,
                    "multiplier_x": x,
                    "multiplier_y": y,
                }
            ]
            * count
        )
    bundle.train_support = pd.DataFrame(rows)
    status, reasons = joint_support(bundle, context, np.array([target_x, 1.0]), config)
    if selected_count < 20:
        assert status == "insufficient_support"
        assert any(
            "zone_id=161" in reason and f"{selected_count} blocks" in reason for reason in reasons
        )
        forecast = scenario(
            bundle, context, ScenarioRequest(delta_price_x=target_x - 1), config, "support-test"
        )
        assert forecast["status"] == "insufficient_support"
        assert forecast["support_status"] == "insufficient_support"
    else:
        assert status == "ok"
        assert not reasons
    # A thin unselected group does not penalize an independently supported zone.
    status, reasons = joint_support(
        bundle, context[context.zone_id == 162], np.array([target_x, 1.0]), config
    )
    assert status == "ok"
    assert not reasons


def test_saved_bundle_with_failed_validation_has_no_forecast(config, fitted):
    bundle, context = fitted
    # Test probabilities are valid; the validation failure must still block this model.
    bundle.diagnostics["validation_probability_valid"] = False
    result = scenario(bundle, context, ScenarioRequest(), config, "failed-validation")
    assert result["status"] == "invalid_probability"
    assert any("validation" in reason.lower() for reason in result["reasons"])
    assert "probabilities" not in result
    assert "theta" not in result
