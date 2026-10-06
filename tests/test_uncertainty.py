import dataclasses

import numpy as np
import pytest

from gsm_poc.estimate import fit_estimator
from gsm_poc.evaluate import effect_rows
from gsm_poc.features import date_splits
from gsm_poc.generate import TRUE_THETA
from gsm_poc.scenario import ScenarioRequest, scenario
from gsm_poc.uncertainty import bootstrap, bootstrap_sample


def _replace_treatment(blocks, index, replacement):
    label = ("x", "y")[index]
    old = blocks[f"log_multiplier_{label}"].to_numpy()
    # Preserve the deterministic conditional mean under the modified prices.
    blocks[["q_x", "q_y"]] += (replacement - old)[:, None] * TRUE_THETA[:, index]
    blocks["q_none"] = 1 - blocks[["q_x", "q_y"]].sum(axis=1)
    blocks[f"log_multiplier_{label}"] = replacement
    blocks[f"multiplier_{label}"] = np.exp(replacement)


def test_draw_losing_parent_treatment_is_failed_and_safe_to_report(config, exact_blocks):
    config = dataclasses.replace(
        config, evaluation=dataclasses.replace(config.evaluation, reporting_min_draws=2)
    )
    blocks = exact_blocks.copy()
    # Y varies only on Jan 1, which the second seed-42 day resample omits.
    y = np.where(blocks.day_id == "2024-01-01", blocks.log_multiplier_y, 0.0)
    _replace_treatment(blocks, 1, y)
    splits = date_splits(blocks, config)
    train, context = splits["train"], splits["test"]
    fitted = fit_estimator(train, config, "adjusted_ols")
    assert fitted.bundle.active_treatments == (0, 1)

    rng = np.random.default_rng(np.random.SeedSequence([42, 8071]))
    shapes = [
        fit_estimator(bootstrap_sample(train, rng), config, "adjusted_ols").bundle.theta.shape
        for _ in range(3)
    ]
    assert shapes == [(2, 2), (2, 1), (2, 2)]

    draws = bootstrap(train, config, "adjusted_ols", seed=42)
    assert draws.requested_draws == 3
    assert draws.successful_draws == 2
    assert draws.bundles[1] is None
    assert [record["status"] for record in draws.records] == ["succeeded", "failed", "succeeded"]
    assert "log_multiplier_y" in draws.records[1]["error"]
    assert draws.interval_status == "interval_unstable"

    effects = effect_rows(fitted, draws, context, config, "test-run", "test-data")
    assert len(effects) == 4
    for row in effects:
        j, k = ("X", "Y").index(row["outcome"]), ("X", "Y").index(row["treatment"])
        assert row["theta"] == pytest.approx(TRUE_THETA[j, k])
        assert row["theta_lower"] == pytest.approx(TRUE_THETA[j, k])
        assert row["theta_upper"] == pytest.approx(TRUE_THETA[j, k])
        assert row["successful_draws"] == 2
        assert row["interval_status"] == "interval_unstable"
    forecast = scenario(fitted.bundle, context, ScenarioRequest(), config, "test-run", draws)
    assert forecast["interval"] is None
    assert forecast["bootstrap"]["fit_failed_draws"] == 1
    assert forecast["bootstrap"]["valid_draws"] == 2
    assert forecast["bootstrap"]["failure_fraction"] == pytest.approx(1 / 3)
    assert forecast["bootstrap"]["interval_status"] == "interval_unstable"


@pytest.mark.parametrize("active", [0, 1])
def test_bootstrap_preserves_legitimate_partial_parent(config, exact_blocks, active):
    config = dataclasses.replace(
        config, evaluation=dataclasses.replace(config.evaluation, reporting_min_draws=2)
    )
    blocks = exact_blocks.copy()
    _replace_treatment(blocks, 1 - active, np.zeros(len(blocks)))
    splits = date_splits(blocks, config)
    fitted = fit_estimator(splits["train"], config, "adjusted_ols")
    draws = bootstrap(splits["train"], config, "adjusted_ols")
    assert fitted.bundle.active_treatments == (active,)
    assert draws.successful_draws == draws.requested_draws == 3
    assert draws.interval_status == "ok"
    for bundle, record in zip(draws.bundles, draws.records, strict=True):
        assert bundle.active_treatments == (active,)
        assert bundle.theta.shape == (2, 1)
        np.testing.assert_allclose(bundle.theta[:, 0], TRUE_THETA[:, active], atol=1e-10)
        assert record["status"] == "succeeded"

    effects = effect_rows(fitted, draws, splits["test"], config, "partial-run", "partial-data")
    for row in effects:
        if row["treatment"] == ("X", "Y")[active]:
            j = ("X", "Y").index(row["outcome"])
            assert row["theta_lower"] == pytest.approx(TRUE_THETA[j, active])
            assert row["theta_upper"] == pytest.approx(TRUE_THETA[j, active])
            assert row["interval_status"] == "ok"
        else:
            assert row["status"] == "not_identified"
            assert row["theta"] is None

    request = ScenarioRequest(
        delta_price_x=0.1 if active == 0 else 0.0,
        delta_price_y=0.1 if active == 1 else 0.0,
    )
    forecast = scenario(fitted.bundle, splits["test"], request, config, "partial-run", draws)
    assert forecast["bootstrap"]["valid_draws"] == 3
    assert forecast["bootstrap"]["fit_failed_draws"] == 0
    assert forecast["bootstrap"]["interval_status"] == "ok"
    for j in range(2):
        assert forecast["theta_interval"][j][1 - active] is None
        assert forecast["theta_interval"][j][active]["lower"] == pytest.approx(
            TRUE_THETA[j, active]
        )


def test_error_after_fit_does_not_count_bundle_as_successful(config, exact_blocks, monkeypatch):
    fitted = fit_estimator(date_splits(exact_blocks, config)["train"], config, "adjusted_ols")

    class InvalidCoefficients:
        def tolist(self):
            raise ValueError("Cannot serialize bootstrap coefficients")

    monkeypatch.setattr(fitted.bundle.base_rate_model, "coef_", InvalidCoefficients())
    monkeypatch.setattr("gsm_poc.uncertainty.fit_estimator", lambda *args, **kwargs: fitted)
    draws = bootstrap(date_splits(exact_blocks, config)["train"], config, "adjusted_ols")
    assert draws.successful_draws == 0
    assert draws.bundles == [None] * draws.requested_draws
    assert draws.interval_status == "interval_unstable"
    for record in draws.records:
        assert record["status"] == "failed"
        assert record["error_type"] == "ValueError"
        assert record["error"] == "Cannot serialize bootstrap coefficients"
