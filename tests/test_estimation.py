import dataclasses

import numpy as np
import pytest

from gsm_poc.estimate import fit_all, fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.generate import TRUE_THETA, generate
from gsm_poc.uncertainty import bootstrap


def test_adjusted_ols_recovers_analytic_matrix(config, exact_blocks):
    train = date_splits(exact_blocks, config)["train"]
    result = fit_estimator(train, config, "adjusted_ols")
    assert result.bundle is not None
    np.testing.assert_allclose(result.bundle.theta, TRUE_THETA, atol=1e-10)
    assert result.diagnostics["residual_rank"] == 2


def test_holdout_outcomes_cannot_change_fit(config, exact_blocks):
    before, _ = fit_all(exact_blocks, config)
    modified = exact_blocks.copy()
    test = modified.day_id >= config.source.validation_end
    modified.loc[test, ["q_x", "q_y", "q_none"]] = [0.01, 0.01, 0.98]
    after, _ = fit_all(modified, config)
    for estimator in config.model.estimators:
        np.testing.assert_array_equal(before[estimator].bundle.theta, after[estimator].bundle.theta)
        np.testing.assert_array_equal(
            before[estimator].bundle.base_rate_model.coef_,
            after[estimator].bundle.base_rate_model.coef_,
        )


@pytest.mark.parametrize("estimator", ["naive_ols", "adjusted_ols", "dml"])
def test_collinear_prices_rejected(config, estimator):
    config = dataclasses.replace(
        config, simulation=dataclasses.replace(config.simulation, dgp="COLLINEAR_PRICE")
    )
    blocks = generate(config).blocks
    result = fit_estimator(date_splits(blocks, config)["train"], config, estimator)
    assert result.bundle is None
    assert result.diagnostics["status"] == "not_identified"
    assert result.diagnostics["residual_rank"] == 1


def test_dml_uses_day_folds_and_correct_matrix_shape(config, generated):
    train = date_splits(generated.blocks, config)["train"]
    result = fit_estimator(train, config, "dml")
    assert result.bundle.theta.shape == (2, 2)
    assert len(result.diagnostics["folds"]) == 5
    for fold in result.diagnostics["folds"]:
        assert not set(fold["train_original_days"]) & set(fold["validation_original_days"])
    np.testing.assert_allclose(result.bundle.theta, TRUE_THETA, atol=0.18)


def test_bootstrap_development_status_and_reproducibility(config, exact_blocks):
    train = date_splits(exact_blocks, config)["train"]
    first, second = (
        bootstrap(train, config, "adjusted_ols"),
        bootstrap(train, config, "adjusted_ols"),
    )
    assert first.interval_status == "interval_unstable"
    assert first.successful_draws == first.requested_draws == 3
    for a, b in zip(first.bundles, second.bundles, strict=True):
        np.testing.assert_array_equal(a.theta, b.theta)
        np.testing.assert_allclose(a.theta, TRUE_THETA, atol=1e-10)


def test_one_varying_price_exports_only_identified_column(config, exact_blocks):
    from gsm_poc.evaluate import effect_rows
    from gsm_poc.scenario import ScenarioRequest, scenario

    blocks = exact_blocks.copy()
    # Remove the Y treatment's contribution from the deterministic fixture.
    contribution = blocks.log_multiplier_y.to_numpy()[:, None] * TRUE_THETA[:, 1]
    blocks[["q_x", "q_y"]] -= contribution
    blocks["log_multiplier_y"] = 0.0
    blocks["multiplier_y"] = 1.0
    splits = date_splits(blocks, config)
    result = fit_estimator(splits["train"], config, "adjusted_ols")
    assert result.bundle.active_treatments == (0,)
    np.testing.assert_allclose(result.bundle.theta[:, 0], TRUE_THETA[:, 0], atol=1e-10)
    effects = effect_rows(result, None, splits["test"], config, "partial-run", "partial-data")
    assert all(row["theta"] is None for row in effects if row["treatment"] == "Y")
    forecast = scenario(
        result.bundle, splits["test"], ScenarioRequest(delta_price_y=0.1), config, "partial-run"
    )
    assert forecast["status"] == "not_identified"
