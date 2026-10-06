import dataclasses

import joblib
import pandas as pd
import pytest

from gsm_poc.artifacts import (
    completed_run,
    read_json,
    sha256_file,
    write_frame,
    write_json,
    write_model,
)
from gsm_poc.generate import generate, save_generated
from gsm_poc.pipeline import Pipeline


@pytest.fixture
def fitted_pipeline(config):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    # Keep the source separate from the model run, as with CLI --dataset-id.
    data = generate(config)
    save_generated(config, data)
    pipeline = Pipeline(config, "dependency-test")
    pipeline.fit(data.dataset_id)
    pipeline.method_evaluation()
    pipeline.scenario()
    pipeline.run.complete()
    return pipeline


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("seed", 142, "Dataset seed"),
        ("dgp_id", "NULL_EFFECT", "Dataset DGP"),
        ("source_kind", "semi_synthetic", "Dataset source kind"),
    ],
)
def test_fit_rejects_changed_metadata_before_reusing_model(
    fitted_pipeline, field, value, reason, capsys
):
    pipeline = fitted_pipeline
    dataset_id = pipeline.run.manifest["dataset_id"]
    metadata_path = pipeline.config.workspace / "data/synthetic" / dataset_id / "manifest.json"
    model_path = pipeline.run.path / "models/adjusted_ols/model_bundle.joblib"
    model_hash = sha256_file(model_path)
    metrics_path = pipeline.run.path / "method_metrics.csv"
    metrics_hash = sha256_file(metrics_path)
    metadata = read_json(metadata_path)
    metadata[field] = value
    write_json(metadata_path, metadata)
    capsys.readouterr()

    with pytest.raises(ValueError, match=reason):
        pipeline.fit(dataset_id)

    output = capsys.readouterr().out
    assert "fit: running" in output
    assert "fit: reuse verified artifacts" not in output
    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["stages"]["fit"]["status"] == "failed"
    assert reason in manifest["stages"]["fit"]["error"]
    assert sha256_file(model_path) == model_hash
    assert sha256_file(metrics_path) == metrics_hash
    with pytest.raises(ValueError, match="not complete"):
        completed_run(pipeline.config.workspace, pipeline.run.run_id)


def test_fit_refreshes_for_compatible_metadata_change(fitted_pipeline, capsys):
    pipeline = fitted_pipeline
    dataset_id = pipeline.run.manifest["dataset_id"]
    metadata_path = pipeline.config.workspace / "data/synthetic" / dataset_id / "manifest.json"
    metadata = read_json(metadata_path)
    capsys.readouterr()
    pipeline.fit(dataset_id)
    assert "fit: reuse verified artifacts" in capsys.readouterr().out

    metadata["provenance_note"] = "Corrected dataset provenance annotation"
    write_json(metadata_path, metadata)
    pipeline.fit(dataset_id)
    assert "fit: running" in capsys.readouterr().out
    assert pipeline.run.manifest["stages"]["fit"]["status"] == "succeeded"
    pipeline.fit(dataset_id)
    assert "fit: reuse verified artifacts" in capsys.readouterr().out


def test_refit_refreshes_method_metrics_with_same_dataset_and_oracle(fitted_pipeline):
    pipeline = fitted_pipeline
    dataset_id = pipeline.run.manifest["dataset_id"]
    root = pipeline.config.workspace / "data/synthetic" / dataset_id
    oracle_hash = sha256_file(root / "oracle/oracle_block.parquet")
    metrics_path = pipeline.run.path / "method_metrics.csv"
    before = pd.read_csv(metrics_path)
    observed = root / "observed/choice_block.parquet"
    blocks = pd.read_parquet(observed)
    train = blocks.day_id < pipeline.config.source.train_end
    # Correct the observed training proportions without changing simulated truth.
    delta_sessions = (0.04 * blocks.loc[train, "n_sessions"]).round().astype(int)
    blocks.loc[train, "n_x"] += delta_sessions
    blocks.loc[train, "n_none"] -= delta_sessions
    blocks.loc[train, "q_x"] = blocks.loc[train, "n_x"] / blocks.loc[train, "n_sessions"]
    blocks.loc[train, "q_none"] = blocks.loc[train, "n_none"] / blocks.loc[train, "n_sessions"]
    write_frame(observed, blocks)

    pipeline.fit(dataset_id)
    pipeline.method_evaluation()
    after = pd.read_csv(metrics_path)
    x_rows = after.outcome == "X"
    assert after.loc[x_rows, "baseline_probability"].to_numpy() == pytest.approx(
        before.loc[x_rows, "baseline_probability"].to_numpy() + 0.04
    )
    assert pipeline.run.manifest["dataset_id"] == dataset_id
    assert sha256_file(root / "oracle/oracle_block.parquet") == oracle_hash
    pipeline.scenario()
    pipeline.run.complete()
    assert completed_run(pipeline.config.workspace, pipeline.run.run_id)["status"] == "succeeded"


def test_test_context_refit_refreshes_scenario_with_identical_model(fitted_pipeline):
    pipeline = fitted_pipeline
    dataset_id = pipeline.run.manifest["dataset_id"]
    model = pipeline.run.path / "models/adjusted_ols/model_bundle.joblib"
    model_hash = sha256_file(model)
    before = read_json(pipeline.run.path / "scenario_result.json")
    observed = (
        pipeline.config.workspace / "data/synthetic" / dataset_id / "observed/choice_block.parquet"
    )
    blocks = pd.read_parquet(observed)
    test = blocks.day_id >= pipeline.config.source.validation_end
    blocks.loc[test, "distance_scaled"] = 0.0
    write_frame(observed, blocks)

    pipeline.fit(dataset_id)
    assert sha256_file(model) == model_hash
    result = pipeline.scenario()
    bundle = joblib.load(model)
    expected = bundle.probabilities(blocks.loc[test], [0.0, 0.0])[:, 0].mean()
    assert result["probabilities"]["X"]["before_probability"] == pytest.approx(expected)
    assert expected != pytest.approx(before["probabilities"]["X"]["before_probability"])
    pipeline.method_evaluation()
    pipeline.run.complete()
    assert completed_run(pipeline.config.workspace, pipeline.run.run_id)["status"] == "succeeded"


@pytest.mark.parametrize(
    "changed_input", ["observed", "metadata", "oracle", "diagnostics", "model", "bootstrap"]
)
def test_method_evaluation_refreshes_for_each_consumed_artifact(
    fitted_pipeline, changed_input, capsys
):
    pipeline = fitted_pipeline
    root = pipeline.config.workspace / "data/synthetic" / pipeline.run.manifest["dataset_id"]
    models = pipeline.run.path / "models/adjusted_ols"
    before = pd.read_csv(pipeline.run.path / "method_metrics.csv")
    old_scenario = read_json(pipeline.run.path / "scenario_result.json")
    capsys.readouterr()
    pipeline.method_evaluation()
    pipeline.scenario()
    output = capsys.readouterr().out
    assert "method_evaluation: reuse verified artifacts" in output
    assert "scenario: reuse verified artifacts" in output

    if changed_input == "observed":
        path = root / "observed/choice_block.parquet"
        frame = pd.read_parquet(path)
        test = frame.day_id >= pipeline.config.source.validation_end
        frame.loc[test, ["n_sessions", "n_x", "n_y", "n_none"]] *= 2
        write_frame(path, frame)
        column = "baseline_context_sessions"
        expected = before[column].to_numpy() * 2
    elif changed_input == "metadata":
        path = root / "manifest.json"
        metadata = read_json(path)
        metadata["seed"] += 1
        write_json(path, metadata)
        column = "seed"
        expected = before[column].to_numpy() + 1
    elif changed_input == "oracle":
        path = root / "oracle/oracle_block.parquet"
        frame = pd.read_parquet(path)
        frame["b_x"] += 0.01
        write_frame(path, frame)
        column = "scenario_probability_rmse"
        expected = None
    elif changed_input == "diagnostics":
        path = models / "diagnostics.json"
        diagnostic = read_json(path)
        diagnostic["train_blocks"] += 1
        write_json(path, diagnostic)
        column = "train_blocks"
        expected = before[column].to_numpy() + 1
    elif changed_input == "model":
        path = models / "model_bundle.joblib"
        bundle = joblib.load(path)
        bundle.theta += 0.01
        write_model(path, bundle)
        column = "theta"
        expected = before[column].to_numpy() + 0.01
    else:
        path = models / "bootstrap_bundles.joblib"
        draws = joblib.load(path)
        assert draws.bundles[-1] is not None
        draws.bundles[-1] = None
        draws.records[-1]["status"] = "failed"
        write_model(path, draws)
        column = "successful_draws"
        expected = before[column].to_numpy() - 1

    # The stored manifest digests are deliberately unchanged: reuse must inspect bytes.
    pipeline.method_evaluation()
    assert "method_evaluation: running" in capsys.readouterr().out
    after = pd.read_csv(pipeline.run.path / "method_metrics.csv")
    if expected is None:
        assert after[column].iloc[0] != pytest.approx(before[column].iloc[0])
    else:
        assert after[column].to_numpy() == pytest.approx(expected)
    if changed_input == "bootstrap":
        result = pipeline.scenario()
        assert "scenario: running" in capsys.readouterr().out
        assert result["bootstrap"]["fit_failed_draws"] == (
            old_scenario["bootstrap"]["fit_failed_draws"] + 1
        )
        assert result["bootstrap"]["valid_draws"] == old_scenario["bootstrap"]["valid_draws"] - 1


def test_unidentified_stages_reuse_without_model_or_bootstrap_files(config, capsys):
    config = dataclasses.replace(
        config,
        simulation=dataclasses.replace(config.simulation, dgp="COLLINEAR_PRICE"),
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    pipeline = Pipeline(config, "unidentified-dependencies")
    pipeline.run_all(include_evaluation=False)
    models = pipeline.run.path / "models/adjusted_ols"
    assert not (models / "model_bundle.joblib").exists()
    assert not (models / "bootstrap_bundles.joblib").exists()
    metrics = pd.read_csv(pipeline.run.path / "method_metrics.csv")
    assert metrics.status.eq("not_identified").all()
    capsys.readouterr()
    pipeline.method_evaluation()
    assert pipeline.scenario()["status"] == "not_identified"
    output = capsys.readouterr().out
    assert "method_evaluation: reuse verified artifacts" in output
    assert "scenario: reuse verified artifacts" in output


def testFitRecordsPrerequisiteFailureInLifecycleWhenDatasetMissing(config):
    pipeline = Pipeline(config, "missing-dataset-prerequisite")
    assert pipeline.run.manifest["status"] == "pending"
    assert "fit" not in pipeline.run.manifest["stages"]

    with pytest.raises(FileNotFoundError, match="not found"):
        pipeline.fit("non_existent_dataset")

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert "fit" in manifest["stages"]
    assert manifest["stages"]["fit"]["status"] == "failed"
    assert manifest["stages"]["fit"]["error_type"] == "FileNotFoundError"
    assert "not found" in manifest["stages"]["fit"]["error"].lower()
    assert manifest["stages"]["fit"]["started_at"] is not None
    assert manifest["stages"]["fit"]["ended_at"] is not None


def testFitRecordsPrerequisiteFailureInLifecycleWhenDatasetIdEmpty(config):
    pipeline = Pipeline(config, "empty-dataset-prerequisite")
    assert pipeline.run.manifest["status"] == "pending"

    with pytest.raises(ValueError, match="Dataset ID is required"):
        pipeline.fit("")

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert "fit" in manifest["stages"]
    assert manifest["stages"]["fit"]["status"] == "failed"
    assert manifest["stages"]["fit"]["error_type"] == "ValueError"
    assert "Dataset ID is required" in manifest["stages"]["fit"]["error"]


def testGenerateRecordsPrerequisiteFailureWhenTlcContextMissing(config):
    tlcConfig = dataclasses.replace(
        config,
        project=dataclasses.replace(config.project, context_mode="tlc"),
    )
    pipeline = Pipeline(tlcConfig, "missing-tlc-context-generate")
    assert pipeline.run.manifest["status"] == "pending"
    assert "generate" not in pipeline.run.manifest["stages"]

    with pytest.raises(ValueError, match="TLC context is missing"):
        pipeline.generate()

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert "generate" in manifest["stages"]
    assert manifest["stages"]["generate"]["status"] == "failed"
    assert manifest["stages"]["generate"]["error_type"] == "ValueError"
    assert "TLC context is missing" in manifest["stages"]["generate"]["error"]
    assert manifest["stages"]["generate"]["started_at"] is not None
    assert manifest["stages"]["generate"]["ended_at"] is not None


def testEvaluateRecordsPrerequisiteFailureWhenTlcContextMissing(config):
    tlcConfig = dataclasses.replace(
        config,
        project=dataclasses.replace(config.project, context_mode="tlc"),
    )
    pipeline = Pipeline(tlcConfig, "missing-tlc-context-evaluate")
    assert pipeline.run.manifest["status"] == "pending"
    assert "evaluate" not in pipeline.run.manifest["stages"]

    with pytest.raises(ValueError, match="TLC context is missing"):
        pipeline.evaluate()

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert "evaluate" in manifest["stages"]
    assert manifest["stages"]["evaluate"]["status"] == "failed"
    assert manifest["stages"]["evaluate"]["error_type"] == "ValueError"
    assert "TLC context is missing" in manifest["stages"]["evaluate"]["error"]
    assert manifest["stages"]["evaluate"]["started_at"] is not None
    assert manifest["stages"]["evaluate"]["ended_at"] is not None


def testScenarioRecordsPrerequisiteFailureWhenModelMissing(config):
    pipeline = Pipeline(config, "missing-model-scenario")
    assert pipeline.run.manifest["status"] == "pending"
    assert "scenario" not in pipeline.run.manifest["stages"]

    with pytest.raises(FileNotFoundError, match="diagnostics"):
        pipeline.scenario()

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert "scenario" in manifest["stages"]
    assert manifest["stages"]["scenario"]["status"] == "failed"
    assert manifest["stages"]["scenario"]["error_type"] == "FileNotFoundError"
    assert "diagnostics" in manifest["stages"]["scenario"]["error"].lower()
    assert manifest["stages"]["scenario"]["started_at"] is not None
    assert manifest["stages"]["scenario"]["ended_at"] is not None


def testScenarioRecordsPrerequisiteFailureWhenModelRunIdMissingOrIncomplete(config):
    pipeline = Pipeline(config, "missing-model-run-id-scenario")
    assert pipeline.run.manifest["status"] == "pending"

    with pytest.raises((FileNotFoundError, ValueError)):
        pipeline.scenario(modelRunId="non-existent-model-run")

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert "scenario" in manifest["stages"]
    assert manifest["stages"]["scenario"]["status"] == "failed"
    assert manifest["stages"]["scenario"]["started_at"] is not None
    assert manifest["stages"]["scenario"]["ended_at"] is not None
