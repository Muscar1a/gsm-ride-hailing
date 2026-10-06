import dataclasses

import numpy as np
import pandas as pd
import pytest

from gsm_poc import evaluate
from gsm_poc.artifacts import read_json
from gsm_poc.estimate import fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.generate import TRUE_THETA


@pytest.fixture
def evaluation_config(config):
    return dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model,
            estimators=("naive_ols", "adjusted_ols"),
            scenario_estimator="adjusted_ols",
        ),
        evaluation=dataclasses.replace(
            config.evaluation, seeds=1, bootstrap_draws=0, dgps=("RCT_SYN",)
        ),
    )


def test_validation_failure_preserves_other_estimator_metrics(evaluation_config):
    config = dataclasses.replace(
        evaluation_config,
        source=dataclasses.replace(evaluation_config.source, zones=(161,)),
        simulation=dataclasses.replace(
            evaluation_config.simulation, seed=20, slot_minutes=360, sessions_per_block=1
        ),
    )
    output = config.workspace / "evaluation"
    result = evaluate.monte_carlo(config, None, "synthetic-v1", output, "validation-failure")
    metrics = pd.read_parquet(result["seed_metrics"])
    failed = metrics[metrics.estimator == "naive_ols"]
    valid = metrics[metrics.estimator == "adjusted_ols"]
    assert len(failed) == len(valid) == 4
    assert (failed.status == "failed").all()
    assert (valid.status == "ok").all()
    assert failed.error.isna().all()
    assert failed.error_message.str.contains("validation").all()
    assert valid.theta.notna().all()
    assert valid.error.notna().all()
    summary = pd.read_csv(result["summary"])
    assert (summary.attempted_seeds == 1).all()
    assert (summary[summary.estimator == "naive_ols"].valid_estimates == 0).all()
    assert (summary[summary.estimator == "adjusted_ols"].valid_estimates == 1).all()
    metadata = read_json(result["metadata"])
    assert metadata["failed_seed_runs"] == 1
    checkpoint = metadata["checkpoints"][0]
    assert checkpoint["status"] == "failed"
    assert checkpoint["estimator_results"]["naive_ols"]["status"] == "failed"
    assert "validation" in checkpoint["estimator_results"]["naive_ols"]["error"]
    assert checkpoint["estimator_results"]["adjusted_ols"]["status"] == "succeeded"


def test_bootstrap_failure_preserves_other_estimator_metrics(evaluation_config, monkeypatch):
    original_bootstrap = evaluate.bootstrap

    def fail_one_bootstrap(train, config, estimator):
        if estimator == "naive_ols":
            raise RuntimeError("naive bootstrap failure")
        return original_bootstrap(train, config, estimator)

    monkeypatch.setattr(evaluate, "bootstrap", fail_one_bootstrap)
    result = evaluate.monte_carlo(
        evaluation_config,
        None,
        "synthetic-v1",
        evaluation_config.workspace / "evaluation",
        "bootstrap-failure",
    )
    metrics = pd.read_parquet(result["seed_metrics"])
    failed = metrics[metrics.estimator == "naive_ols"]
    valid = metrics[metrics.estimator == "adjusted_ols"]
    assert len(failed) == len(valid) == 4
    assert (failed.status == "failed").all()
    assert (failed.error_type == "RuntimeError").all()
    assert (failed.error_message == "naive bootstrap failure").all()
    assert (valid.status == "ok").all()
    assert valid.error.notna().all()


def test_common_failure_keeps_denominators_and_retries(evaluation_config, monkeypatch):
    original_generate = evaluate.generate
    output = evaluation_config.workspace / "evaluation"

    def fail_generate(*args, **kwargs):
        raise ValueError("shared generation failure")

    monkeypatch.setattr(evaluate, "generate", fail_generate)
    result = evaluate.monte_carlo(evaluation_config, None, "synthetic-v1", output, "common-failure")
    metrics = pd.read_parquet(result["seed_metrics"])
    assert len(metrics) == 8
    assert (metrics.status == "failed").all()
    assert (metrics.error_message == "shared generation failure").all()
    summary = pd.read_csv(result["summary"])
    assert (summary.attempted_seeds == 1).all()
    assert (summary.failed_or_unidentified_estimates == 1).all()
    checkpoint = read_json(result["metadata"])["checkpoints"][0]
    assert checkpoint["status"] == "failed"
    assert checkpoint["error"] == "shared generation failure"
    assert all(method["status"] == "failed" for method in checkpoint["estimator_results"].values())

    monkeypatch.setattr(evaluate, "generate", original_generate)
    result = evaluate.monte_carlo(evaluation_config, None, "synthetic-v1", output, "common-failure")
    metrics = pd.read_parquet(result["seed_metrics"])
    assert len(metrics) == 8
    assert (metrics.status == "ok").all()
    assert metrics.error.notna().all()
    metadata = read_json(result["metadata"])
    assert metadata["failed_seed_runs"] == 0
    assert metadata["checkpoints"][0]["status"] == "succeeded"

    def unexpected_generate(*args, **kwargs):
        raise AssertionError("successful checkpoint was not reused")

    monkeypatch.setattr(evaluate, "generate", unexpected_generate)
    reused = evaluate.monte_carlo(evaluation_config, None, "synthetic-v1", output, "common-failure")
    pd.testing.assert_frame_equal(metrics, pd.read_parquet(reused["seed_metrics"]))


def _replace_treatment(blocks, index, replacement):
    label = ("x", "y")[index]
    old = blocks[f"log_multiplier_{label}"].to_numpy()
    blocks[f"log_multiplier_{label}"] = replacement
    blocks[f"multiplier_{label}"] = np.exp(replacement)
    q_xy = blocks[["q_x", "q_y"]].to_numpy() + (replacement - old)[:, None] * TRUE_THETA[:, index]
    n = blocks.n_sessions.to_numpy()
    counts = np.round(q_xy * n[:, None]).astype(int)
    n_none = n - counts.sum(axis=1)
    blocks["n_x"], blocks["n_y"], blocks["n_none"] = counts[:, 0], counts[:, 1], n_none
    blocks["q_x"], blocks["q_y"], blocks["q_none"] = counts[:, 0] / n, counts[:, 1] / n, n_none / n


@pytest.mark.parametrize("active", [0, 1])
def test_method_metrics_unidentified_price_scenario_withholds_rmse(config, generated, active):
    blocks = generated.blocks.copy()
    _replace_treatment(blocks, 1 - active, np.zeros(len(blocks)))
    partial_data = dataclasses.replace(generated, blocks=blocks)
    splits = date_splits(blocks, config)
    fitted = fit_estimator(splits["train"], config, "adjusted_ols")
    assert fitted.bundle is not None
    assert fitted.bundle.active_treatments == (active,)

    # Scenario changing the unidentified price (1 - active)
    unidentified_config = dataclasses.replace(
        config,
        scenario=dataclasses.replace(
            config.scenario,
            delta_price_x=0.10 if active == 1 else 0.0,
            delta_price_y=0.10 if active == 0 else 0.0,
        ),
    )
    rows_unidentified = evaluate.method_metrics(
        fitted, None, partial_data, unidentified_config, "unidentified-scenario"
    )
    assert all(r["scenario_probability_rmse"] is None for r in rows_unidentified)
    assert all(r["scenario_probability_valid"] is None for r in rows_unidentified)

    # Scenario changing only the identified price (active)
    identified_config = dataclasses.replace(
        config,
        scenario=dataclasses.replace(
            config.scenario,
            delta_price_x=0.10 if active == 0 else 0.0,
            delta_price_y=0.10 if active == 1 else 0.0,
        ),
    )
    rows_identified = evaluate.method_metrics(
        fitted, None, partial_data, identified_config, "identified-scenario"
    )
    assert all(r["scenario_probability_rmse"] is not None for r in rows_identified)
    assert all(r["scenario_probability_valid"] is True for r in rows_identified)


def test_monte_carlo_aggregates_none_scenario_rmse_when_unidentified(config, monkeypatch):
    original_generate = evaluate.generate

    def partial_generate(cfg, *args, **kwargs):
        gen = original_generate(cfg, *args, **kwargs)
        blocks = gen.blocks.copy()
        _replace_treatment(blocks, 0, np.zeros(len(blocks)))
        return dataclasses.replace(gen, blocks=blocks)

    monkeypatch.setattr(evaluate, "generate", partial_generate)
    eval_config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
        evaluation=dataclasses.replace(
            config.evaluation, seeds=1, bootstrap_draws=0, dgps=("RCT_SYN",)
        ),
    )
    output = eval_config.workspace / "eval_partial"
    result = evaluate.monte_carlo(eval_config, None, "synthetic-v1", output, "partial-y-mc")
    summary = pd.read_csv(result["summary"])
    assert summary["scenario_probability_rmse"].isna().all()


def makeConsistentBlocks(baseData, fixedIndex: int, fixedMultiplier: float):
    blocks = baseData.blocks.copy()
    truth = blocks[["block_id"]].merge(baseData.oracle, on="block_id", validate="one_to_one")
    fixedLog = np.full(len(blocks), np.log(fixedMultiplier))
    fixedLabel = ("x", "y")[fixedIndex]
    varyingIndex = 1 - fixedIndex
    varyingLabel = ("x", "y")[varyingIndex]
    blocks[f"log_multiplier_{fixedLabel}"] = fixedLog
    blocks[f"multiplier_{fixedLabel}"] = float(fixedMultiplier)
    p_xy = (
        truth[["b_x", "b_y"]].to_numpy()
        + blocks[[f"log_multiplier_{varyingLabel}"]].to_numpy() * TRUE_THETA[:, varyingIndex]
        + fixedLog[:, None] * TRUE_THETA[:, fixedIndex]
    )
    n = 100_000_000
    counts = np.round(p_xy * n).astype(int)
    n_none = n - counts.sum(axis=1)
    blocks["n_sessions"] = n
    blocks["n_x"], blocks["n_y"], blocks["n_none"] = counts[:, 0], counts[:, 1], n_none
    blocks["q_x"], blocks["q_y"], blocks["q_none"] = counts[:, 0] / n, counts[:, 1] / n, n_none / n
    return blocks


@pytest.mark.parametrize("fixedIndex", [1, 0])
def testFixedConstantPriceBenchmarkPreserved(config, generated, fixedIndex: int):
    blocks = makeConsistentBlocks(generated, fixedIndex, 1.1)
    partialData = dataclasses.replace(generated, blocks=blocks)
    splits = date_splits(blocks, config)
    fitted = fit_estimator(splits["train"], config, "adjusted_ols")

    varyingIndex = 1 - fixedIndex
    assert fitted.bundle is not None
    assert fitted.bundle.active_treatments == (varyingIndex,)
    fixedName = ("X", "Y")[fixedIndex]
    assert np.isclose(fitted.bundle.diagnostics["constant_log_prices"][fixedName], np.log(1.1))
    assert (np.abs(fitted.bundle.theta.squeeze() - TRUE_THETA[:, varyingIndex]) < 1e-7).all()

    # Valid scenario: only changes identified varying price, keeps fixed price unchanged
    validConfig = dataclasses.replace(
        config,
        scenario=dataclasses.replace(
            config.scenario,
            delta_price_x=0.10 if varyingIndex == 0 else 0.0,
            delta_price_y=0.10 if varyingIndex == 1 else 0.0,
        ),
    )
    rowsValid = evaluate.method_metrics(fitted, None, partialData, validConfig, "fixed-valid-run")
    assert rowsValid[0]["scenario_probability_rmse"] is not None
    assert rowsValid[0]["scenario_probability_rmse"] < 1e-6
    assert rowsValid[0]["scenario_probability_valid"] is True

    # Invalid scenario: attempts to change unidentified fixed price
    invalidConfig = dataclasses.replace(
        config,
        scenario=dataclasses.replace(
            config.scenario,
            delta_price_x=0.10 if fixedIndex == 0 else 0.0,
            delta_price_y=0.10 if fixedIndex == 1 else 0.0,
        ),
    )
    rowsInvalid = evaluate.method_metrics(
        fitted, None, partialData, invalidConfig, "fixed-invalid-run"
    )
    assert all(r["scenario_probability_rmse"] is None for r in rowsInvalid)
    assert all(r["scenario_probability_valid"] is None for r in rowsInvalid)
