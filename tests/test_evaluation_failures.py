import dataclasses

import pandas as pd
import pytest

from gsm_poc import evaluate
from gsm_poc.artifacts import read_json


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
