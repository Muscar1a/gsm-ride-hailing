import copy
import dataclasses
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from scipy.stats import t

from gsm_poc.causal.analytic import validate_covariance
from gsm_poc.causal.estimate import fit_estimator
from gsm_poc.causal.features import date_splits
from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.core.artifacts import completed_run, fingerprint, read_json, sha256_file, write_json
from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.ui.app import load_model
from scripts import diagnose_week2_score_inference as frozen


@pytest.mark.parametrize("estimator", ["adjusted_ols", "dml"])
@pytest.mark.parametrize("zone", [None, 161])
def test_compact_covariance_and_intervals_match_frozen_score_kernel(
    config, generated, estimator, zone
):
    splits = date_splits(generated.blocks, config)
    result = fit_estimator(splits["train"], config, estimator, capture_residuals=True)
    bundle, context = result.bundle, splits["test"]
    if zone is not None:
        context = context[context.zone_id == zone].copy()
        context["n_sessions"] *= np.arange(len(context)) % 3 + 1
    assert bundle is not None and bundle.analytic_inference is not None
    point, scores, leverage, rank = frozen.score_influence(result, splits["train"], context)
    reference = frozen.score_covariances(
        scores, splits["train"].original_day_id.to_numpy(), leverage, rank, estimator
    )
    method = bundle.analytic_inference["method"]
    covariance = validate_covariance(bundle, bundle.analytic_inference)
    size = covariance.shape[0] // 2
    mean_controls = np.r_[
        1, np.average(bundle.encoder.transform(context), axis=0, weights=context.n_sessions)
    ]
    projection = np.zeros((6, 2 * size))
    projection[:2, :2] = np.eye(2)
    projection[2:4, size : size + 2] = np.eye(2)
    projection[4, 2:size] = mean_controls
    projection[5, size + 2 :] = mean_controls
    np.testing.assert_allclose(
        projection @ covariance @ projection.T, reference[method][0], atol=1e-11, rtol=1e-8
    )
    expected = frozen.interval_rows(point, {method: reference[method]}, config)
    forecast = scenario(bundle, context, ScenarioRequest(), config, "analytic-test")
    assert forecast["inference_method"] == "analytic" and forecast["interval_status"] == "ok"
    assert "bootstrap" not in forecast
    for row in expected:
        if row["family"] == "scenario":
            if not row["output_id"].startswith("x_plus10:"):
                continue
            actual = forecast["interval"][row["output_id"].split(":")[1]]
        else:
            j, k = [("X", "Y").index(label) for label in row["output_id"].split("/")]
            key = "theta_interval" if row["family"] == "theta" else "elasticity_interval"
            actual = forecast[key][j][k]
        assert actual["lower"] == pytest.approx(row["lower"], abs=1e-10)
        assert actual["upper"] == pytest.approx(row["upper"], abs=1e-10)


def test_nonunit_baseline_elasticity_gradient_includes_price_and_context_covariance(
    config, generated
):
    splits = date_splits(generated.blocks, config)
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    context = splits["test"]
    request = ScenarioRequest(baseline_multiplier_x=0.9, delta_price_x=1.1 / 0.9 - 1)
    # Check gradients directly; this contrast's support gate may reject the target population.
    t0 = np.log([0.9, 1])
    point = np.column_stack(
        [bundle.theta, bundle.base_rate_model.intercept_, bundle.base_rate_model.coef_]
    ).ravel()
    gradient = np.zeros(len(point))
    for index in range(len(point)):
        values = []
        for step in (-1e-6, 1e-6):
            changed = copy.deepcopy(bundle)
            parameters = point.copy()
            parameters[index] += step
            parameters = parameters.reshape(2, -1)
            changed.theta = parameters[:, :2]
            changed.base_rate_model.intercept_ = parameters[:, 2]
            changed.base_rate_model.coef_ = parameters[:, 3:]
            before = np.average(
                changed.probabilities(context, t0), axis=0, weights=context.n_sessions
            )
            values.append(changed.theta[0, 0] / before[0])
        gradient[index] = (values[1] - values[0]) / 2e-6
    result = scenario(bundle, context, request, config, "nonunit")
    record = bundle.analytic_inference
    variance = gradient @ np.array(record["covariance"]) @ gradient
    half_width = t.ppf(0.975, record["degrees_of_freedom"]) * np.sqrt(variance)
    actual = result["elasticity_interval"][0][0]
    assert (actual["upper"] - actual["lower"]) / 2 == pytest.approx(half_width, rel=1e-6)


def test_missing_or_stale_covariance_is_explicit_without_bootstrap_fallback(config, generated):
    splits = date_splits(generated.blocks, config)
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    record = bundle.analytic_inference
    bundle.analytic_inference = None
    result = scenario(bundle, splits["test"], ScenarioRequest(), config, "legacy")
    assert result["interval"] is None
    assert result["interval_status"] == "interval_unavailable"
    assert "prepare inference" in result["analytic"]["reason"]
    bundle.analytic_inference = record
    bundle.theta = bundle.theta + 0.001
    with pytest.raises(ValueError, match="does not match"):
        scenario(bundle, splits["test"], ScenarioRequest(), config, "stale")
    with pytest.raises(ValueError, match="inference_method"):
        scenario(bundle, splits["test"], ScenarioRequest(), config, "bad", inference_method="auto")


def test_ui_loader_only_deserializes_bootstrap_when_selected(config, generated, monkeypatch):
    bundle = fit_estimator(
        date_splits(generated.blocks, config)["train"], config, "adjusted_ols"
    ).bundle
    prefix = "runs/ui/models/adjusted_ols"
    directory = config.workspace / prefix
    directory.mkdir(parents=True)
    (directory / "diagnostics.json").write_text('{"status":"ok"}')
    manifest = {
        "run_id": "ui",
        "artifacts": {
            f"{prefix}/model_bundle.joblib": "model",
            f"{prefix}/bootstrap_bundles.joblib": "draws",
        },
    }
    paths = []

    def reader(path, checksum):
        paths.append(Path(path).name)
        return bundle if checksum == "model" else "bootstrap-object"

    monkeypatch.setattr("gsm_poc.ui.app.read_bundle", reader)
    assert load_model(config.workspace, manifest, "adjusted_ols") == (bundle, None)
    assert paths == ["model_bundle.joblib"]
    assert (
        load_model(config.workspace, manifest, "adjusted_ols", "bootstrap")[1] == "bootstrap-object"
    )
    assert paths[-1] == "bootstrap_bundles.joblib"


@pytest.fixture
def legacy_baseline(config, monkeypatch):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    source = Pipeline(config, "legacy-source")
    dataset_id = source.generate()

    def unavailable(*args, **kwargs):
        raise ValueError("Legacy model without compact covariance")

    with monkeypatch.context() as legacy:
        legacy.setattr("gsm_poc.causal.estimate.coefficient_covariance", unavailable)
        source.fit(dataset_id)
    source.method_evaluation()
    source.scenario()
    source.run.complete()
    baseline = Pipeline(config, "legacy-baseline")
    baseline.freeze_choice(source.run.run_id)
    baseline.run.complete()
    return baseline


def test_preparation_preserves_baseline_bytes_and_replay_avoids_bootstrap_loads(
    legacy_baseline, monkeypatch
):
    baseline = legacy_baseline
    original_hash = sha256_file(baseline.run.manifest_path)
    target = Pipeline(baseline.config, "hybrid-package")
    original_loader = joblib.load
    loaded = []

    def point_only(path):
        loaded.append(Path(path).name)
        assert Path(path).name != "bootstrap_bundles.joblib"
        return original_loader(path)

    monkeypatch.setattr(joblib, "load", point_only)
    result = target.prepare_inference(baseline.run.run_id)
    target.run.complete()
    assert result["methods"] == {"adjusted_ols": "block_hc3_t"}
    assert sha256_file(baseline.run.manifest_path) == original_hash
    for relative, checksum in baseline.run.manifest["artifacts"].items():
        copied = target.run.path / relative.removeprefix(f"runs/{baseline.run.run_id}/")
        assert sha256_file(copied) == checksum
    completed_run(baseline.config.workspace, target.run.run_id)
    replay = Pipeline(baseline.config, "hybrid-scenario")
    forecast = replay.scenario(model_run_id=target.run.run_id, inference_method="analytic")
    assert forecast["interval_status"] == "ok"
    assert len(loaded) == 2
    historical = read_json(baseline.run.path / "scenario_result.json")
    assert forecast.get("probabilities") == historical.get("probabilities")
    assert forecast["theta"] == historical["theta"]


def test_legacy_preparation_rejects_modified_training_source(legacy_baseline):
    baseline = legacy_baseline
    dataset = baseline.config.workspace / "data/synthetic" / baseline.run.manifest["dataset_id"]
    metadata = dataset / "manifest.json"
    metadata.write_text(metadata.read_text() + "\n")
    target = Pipeline(baseline.config, "reject-inference")
    with pytest.raises(ValueError, match="differs from the frozen fit inputs"):
        target.prepare_inference(baseline.run.run_id)


def test_early_manifest_verifies_observed_fit_hash_and_registered_metadata(legacy_baseline):
    baseline = legacy_baseline
    path = baseline.run.path / "source_manifest.json"
    original = read_json(path)
    dataset = baseline.config.workspace / "data/synthetic" / original["dataset_id"]
    original["stages"]["fit"]["input_hash"] = fingerprint(
        {
            "inputs": {
                "dataset_id": original["dataset_id"],
                "observed_sha256": sha256_file(dataset / "observed/choice_block.parquet"),
            },
            "config": original["config_hash"],
            "code": original["environment"]["source_code_sha256"],
        }
    )
    write_json(path, original)
    baseline.run.register([path])
    target = Pipeline(baseline.config, "early-manifest-inference")
    result = target.prepare_inference(baseline.run.run_id)
    assert result["input_verification"] == "legacy_fit_observed_hash_and_registered_metadata_hash"
    metadata = dataset / "manifest.json"
    metadata.write_text(metadata.read_text() + "\n")
    rejected = Pipeline(baseline.config, "early-manifest-rejected")
    with pytest.raises(ValueError, match="differs from the frozen fit inputs"):
        rejected.prepare_inference(baseline.run.run_id)


def test_prepare_demand_keeps_point_rate_contract_with_optional_covariance(
    legacy_baseline, monkeypatch
):
    baseline = legacy_baseline
    target = Pipeline(baseline.config, "demand-hybrid-choice")
    target.prepare_inference(baseline.run.run_id)
    target.run.complete()
    snapshot = Path(__file__).parents[1] / "configs/week3_snapshot.json"
    original_loader = joblib.load

    def point_only(path):
        assert Path(path).name != "bootstrap_bundles.joblib"
        return original_loader(path)

    monkeypatch.setattr(joblib, "load", point_only)
    results, frames = [], []
    for source, name in ((baseline, "baseline-demand"), (target, "hybrid-demand")):
        pipeline = Pipeline(baseline.config, name)
        results.append(pipeline.prepare_demand(source.run.run_id, snapshot))
        pipeline.run.complete()
        frames.append(pd.read_parquet(pipeline.run.path / "demand_plan.parquet"))
    assert results[0]["usable_for_simulation"] == results[1]["usable_for_simulation"] is True
    assert results[0]["summary"] == results[1]["summary"]
    assert results[0]["reasons"] == results[1]["reasons"] == []
    assert results[0]["interval_status"] == results[1]["interval_status"] == "interval_unavailable"
    assert list(frames[0]) == list(frames[1])
    pd.testing.assert_frame_equal(
        frames[0].drop(columns=["model_run_id", "source_version", "demand_plan_version"]),
        frames[1].drop(columns=["model_run_id", "source_version", "demand_plan_version"]),
    )
    sidecar = target.run.path / "models/adjusted_ols/analytic_inference.json"
    copied = (
        baseline.config.workspace
        / "runs/hybrid-demand/demand_bundle/models/adjusted_ols/analytic_inference.json"
    )
    assert sha256_file(copied) == sha256_file(sidecar)


@pytest.mark.parametrize("active", [0, 1])
def test_analytic_preserves_unidentified_columns_and_elasticity_threshold(
    config, generated, active
):
    blocks = generated.blocks.copy()
    inactive = ("x", "y")[1 - active]
    blocks[f"log_multiplier_{inactive}"] = 0
    blocks[f"multiplier_{inactive}"] = 1
    splits = date_splits(blocks, config)
    config = dataclasses.replace(
        config, model=dataclasses.replace(config.model, elasticity_min_probability=0.99)
    )
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    result = scenario(
        bundle,
        splits["test"],
        ScenarioRequest(
            delta_price_x=0.1 if active == 0 else 0, delta_price_y=0.1 if active == 1 else 0
        ),
        config,
        "partial-analytic",
    )
    assert result["interval_status"] == "ok"
    assert result["elasticity_interval"] == [[None, None], [None, None]]
    for row in range(2):
        assert result["theta"][row][1 - active] is None
        assert result["theta_interval"][row][1 - active] is None
        bounds = result["theta_interval"][row][active]
        assert bounds["lower"] <= result["theta"][row][active] <= bounds["upper"]
