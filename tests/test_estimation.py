import dataclasses

import numpy as np
import pytest

from gsm_poc.estimate import fit_all, fit_estimator
from gsm_poc.evaluate import effect_rows
from gsm_poc.features import date_splits, require_observed
from gsm_poc.generate import TRUE_THETA, generate
from gsm_poc.scenario import ScenarioRequest, scenario
from gsm_poc.uncertainty import bootstrap


def testAdjustedOlsRecoversAnalyticMatrix(config, exact_blocks):
    train = date_splits(exact_blocks, config)["train"]
    result = fit_estimator(train, config, "adjusted_ols")
    assert result.bundle is not None
    np.testing.assert_allclose(result.bundle.theta, TRUE_THETA, atol=1e-10)
    assert result.diagnostics["residual_rank"] == 2


def testHoldoutOutcomesCannotChangeFit(config, exact_blocks):
    before, _ = fit_all(exact_blocks, config)
    modified = exact_blocks.copy()
    test = modified.day_id >= config.source.validation_end
    n_test = modified.loc[test, "n_sessions"]
    nx = np.round(0.01 * n_test).astype(int)
    ny = np.round(0.01 * n_test).astype(int)
    nnone = n_test - nx - ny
    modified.loc[test, "n_x"] = nx
    modified.loc[test, "n_y"] = ny
    modified.loc[test, "n_none"] = nnone
    modified.loc[test, "q_x"] = nx / n_test
    modified.loc[test, "q_y"] = ny / n_test
    modified.loc[test, "q_none"] = nnone / n_test
    after, _ = fit_all(modified, config)
    for estimator in config.model.estimators:
        before_bundle = before[estimator].bundle
        after_bundle = after[estimator].bundle
        assert before_bundle is not None and after_bundle is not None
        np.testing.assert_array_equal(before_bundle.theta, after_bundle.theta)
        np.testing.assert_array_equal(
            before_bundle.base_rate_model.coef_,
            after_bundle.base_rate_model.coef_,
        )


@pytest.mark.parametrize("estimator", ["naive_ols", "adjusted_ols", "dml"])
def testCollinearPricesRejected(config, estimator):
    config = dataclasses.replace(
        config, simulation=dataclasses.replace(config.simulation, dgp="COLLINEAR_PRICE")
    )
    blocks = generate(config).blocks
    result = fit_estimator(date_splits(blocks, config)["train"], config, estimator)
    assert result.bundle is None
    assert result.diagnostics["status"] == "not_identified"
    assert result.diagnostics["residual_rank"] == 1


def testDmlUsesDayFoldsAndCorrectMatrixShape(config, generated):
    train = date_splits(generated.blocks, config)["train"]
    result = fit_estimator(train, config, "dml")
    assert result.bundle is not None
    assert result.bundle.theta.shape == (2, 2)
    assert len(result.diagnostics["folds"]) == 5
    for fold in result.diagnostics["folds"]:
        assert not set(fold["train_original_days"]) & set(fold["validation_original_days"])
    np.testing.assert_allclose(result.bundle.theta, TRUE_THETA, atol=0.18)


def testBootstrapDevelopmentStatusAndReproducibility(config, exact_blocks):
    train = date_splits(exact_blocks, config)["train"]
    first, second = (
        bootstrap(train, config, "adjusted_ols"),
        bootstrap(train, config, "adjusted_ols"),
    )
    assert first.interval_status == "interval_unstable"
    assert first.successful_draws == first.requested_draws == 3
    for a, b in zip(first.bundles, second.bundles, strict=True):
        assert a is not None and b is not None
        np.testing.assert_array_equal(a.theta, b.theta)
        np.testing.assert_allclose(a.theta, TRUE_THETA, atol=1e-10)


def testOneVaryingPriceExportsOnlyIdentifiedColumn(config, exact_blocks):
    blocks = exact_blocks.copy()
    # Remove the Y treatment's contribution from the deterministic fixture.
    contribution = blocks.log_multiplier_y.to_numpy()[:, None] * TRUE_THETA[:, 1]
    blocks[["q_x", "q_y"]] -= contribution
    blocks["log_multiplier_y"] = 0.0
    blocks["multiplier_y"] = 1.0

    n = blocks["n_sessions"]
    blocks["n_x"] = np.round(blocks["q_x"] * n).astype(int)
    blocks["n_y"] = np.round(blocks["q_y"] * n).astype(int)
    blocks["n_none"] = n - blocks["n_x"] - blocks["n_y"]
    blocks["q_x"] = blocks["n_x"] / n
    blocks["q_y"] = blocks["n_y"] / n
    blocks["q_none"] = blocks["n_none"] / n

    splits = date_splits(blocks, config)
    result = fit_estimator(splits["train"], config, "adjusted_ols")
    assert result.bundle is not None
    assert result.bundle.active_treatments == (0,)
    np.testing.assert_allclose(result.bundle.theta[:, 0], TRUE_THETA[:, 0], atol=1e-10)
    effects = effect_rows(result, None, splits["test"], config, "partial-run", "partial-data")
    assert all(row["theta"] is None for row in effects if row["treatment"] == "Y")
    forecast = scenario(
        result.bundle, splits["test"], ScenarioRequest(delta_price_y=0.1), config, "partial-run"
    )
    assert forecast["status"] == "not_identified"


def testRequireObservedRejectsCountMismatch(generated):
    blocks = generated.blocks.copy()
    blocks.loc[0, "n_x"] += 1
    with pytest.raises(ValueError, match="Choice counts do not conserve sessions"):
        require_observed(blocks)


def testRequireObservedRejectsNegativeCounts(generated):
    blocks = generated.blocks.copy()
    blocks.loc[0, "n_x"] = -1
    blocks.loc[0, "n_none"] += 1
    with pytest.raises(ValueError, match="Choice counts must be non-negative"):
        require_observed(blocks)


def testRequireObservedRejectsMissingCountColumns(generated):
    for col in ("n_x", "n_y", "n_none"):
        with pytest.raises(ValueError, match="Missing observed block columns"):
            require_observed(generated.blocks.drop(columns=col))


def testFitEstimatorRejectsCountMismatch(config, exact_blocks):
    train = date_splits(exact_blocks, config)["train"]
    corrupted = train.copy()
    corrupted.loc[corrupted.index[0], "n_x"] += 2
    with pytest.raises(ValueError, match="Choice counts do not conserve sessions"):
        fit_estimator(corrupted, config, "adjusted_ols")


def testRequireObservedRejectsNonIntegerCounts(generated):
    blocks = generated.blocks.copy()
    blocks["n_x"] = blocks["n_x"].astype(float)
    blocks["n_none"] = blocks["n_none"].astype(float)
    blocks.loc[0, "n_x"] = 10.5
    blocks.loc[0, "n_none"] = 39.5
    with pytest.raises(ValueError, match="must be integers"):
        require_observed(blocks)


def testRequireObservedRejectsNonIntegerSessions(generated):
    blocks = generated.blocks.copy()
    blocks["n_sessions"] = blocks["n_sessions"].astype(float)
    blocks.loc[0, "n_sessions"] = 50.5
    with pytest.raises(ValueError, match="must be integers"):
        require_observed(blocks)


def testRequireObservedRejectsProportionMismatch(generated):
    blocks = generated.blocks.copy()
    blocks.loc[0, "q_x"] += 0.05
    blocks.loc[0, "q_none"] -= 0.05
    with pytest.raises(ValueError, match="does not match count ratio"):
        require_observed(blocks)
