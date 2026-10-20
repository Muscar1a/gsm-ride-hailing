import dataclasses
from pathlib import Path

import joblib
import pandas as pd
import pytest

from gsm_poc.cli import main
from gsm_poc.core.artifacts import completed_run, read_json, sha256_file, write_json
from gsm_poc.pipeline import Pipeline
from gsm_poc.simulation.dgp import generate, save_generated


@pytest.fixture
def choice_run(config):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model,
            estimators=("naive_ols", "adjusted_ols"),
            scenario_estimator="adjusted_ols",
        ),
    )
    data = generate(config)
    save_generated(config, data)
    source = Pipeline(config, "choice-source")
    source.fit(data.dataset_id)
    source.method_evaluation()
    source.scenario()
    source.run.complete()
    return source


@pytest.fixture
def frozen_choice(choice_run):
    config = dataclasses.replace(
        choice_run.config,
        model=dataclasses.replace(choice_run.config.model, estimators=("adjusted_ols",)),
    )
    package = Pipeline(config, "choice-handoff")
    package.freeze_choice(choice_run.run.run_id)
    package.run.complete()
    return package


def test_handoff_preserves_all_source_estimators_and_provenance(choice_run, frozen_choice):
    result = read_json(frozen_choice.run.path / "choice_handoff.json")
    manifest = completed_run(choice_run.config.workspace, frozen_choice.run.run_id)
    source_manifest = read_json(choice_run.run.manifest_path)
    assert set(result["model_results"]) == {"naive_ols", "adjusted_ols"}
    for estimator in choice_run.config.model.estimators:
        for name in (
            "diagnostics.json",
            "model_bundle.joblib",
            "bootstrap_bundles.joblib",
            "bootstrap_draws.parquet",
        ):
            assert f"models/{estimator}/{name}" in result["artifacts"]
    for name, checksum in result["artifacts"].items():
        assert sha256_file(frozen_choice.run.path / name) == checksum
        assert sha256_file(choice_run.run.path / name) == checksum
    assert sha256_file(frozen_choice.run.path / "source_manifest.json") == sha256_file(
        choice_run.run.manifest_path
    )
    assert result["source_manifest_sha256"] == sha256_file(choice_run.run.manifest_path)
    assert result["source_config"] == source_manifest["config"]
    assert result["source_environment"] == choice_run.run.manifest["environment"]
    assert result["packaging_environment"] == manifest["environment"]
    assert manifest["choice_source"]["source_config"] == source_manifest["config"]
    assert result["interval_qualification"]["interval_calibration_status"] == (
        "not_validated_by_packaging"
    )
    assert result["review_status"] == "pending_reviewer_acceptance"
    assert not (frozen_choice.run.path / "oracle").exists()
    assert not (frozen_choice.run.path / "observed").exists()
    assert not (frozen_choice.run.path / "demand_plan.parquet").exists()


def test_cli_reuses_handoff_and_repairs_a_changed_copy(choice_run, monkeypatch, capsys):
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: choice_run.config)
    arguments = [
        "freeze-choice",
        "--model-run-id",
        choice_run.run.run_id,
        "--run-id",
        "cli-handoff",
    ]
    source_hash = sha256_file(choice_run.run.manifest_path)
    assert main(arguments) == 0
    output = choice_run.config.workspace / "runs/cli-handoff"
    duration = read_json(output / "manifest.json")["stages"]["freeze_choice"]["duration_seconds"]
    capsys.readouterr()
    assert main(arguments) == 0
    assert "freeze_choice: reuse verified artifacts" in capsys.readouterr().out
    assert read_json(output / "manifest.json")["stages"]["freeze_choice"]["duration_seconds"] == (
        duration
    )
    (output / "effects.csv").write_bytes(b"changed copy")
    assert main(arguments) == 0
    assert "freeze_choice: running" in capsys.readouterr().out
    assert sha256_file(output / "effects.csv") == sha256_file(choice_run.run.path / "effects.csv")
    assert sha256_file(choice_run.run.manifest_path) == source_hash
    completed_run(choice_run.config.workspace, "cli-handoff")


@pytest.mark.parametrize("error_kind", ["corrupt", "unregistered"])
def test_source_integrity_failure_precedes_model_loading(choice_run, monkeypatch, error_kind):
    if error_kind == "corrupt":
        (choice_run.run.path / "effects.csv").write_bytes(b"corrupt source")
        reason = "checksum"
    else:
        relative = f"runs/{choice_run.run.run_id}/effects.csv"
        del choice_run.run.manifest["artifacts"][relative]
        choice_run.run.save()
        reason = "not registered"
    monkeypatch.setattr(
        "gsm_poc.pipeline.pipeline.joblib.load",
        lambda _: pytest.fail("Source integrity must be checked before loading a model"),
    )
    package = Pipeline(choice_run.config, "invalid-source")
    with pytest.raises(ValueError, match=reason):
        package.freeze_choice(choice_run.run.run_id)
    assert package.run.manifest["stages"]["freeze_choice"]["status"] == "failed"
    assert not (package.run.path / "choice_handoff.json").exists()


@pytest.mark.parametrize("missing_stage", ["fit", "method_evaluation", "scenario"])
def test_handoff_requires_complete_source_stages(choice_run, missing_stage):
    del choice_run.run.manifest["stages"][missing_stage]
    choice_run.run.save()
    package = Pipeline(choice_run.config, "incomplete-source")
    with pytest.raises(ValueError, match=f"completed {missing_stage} stage"):
        package.freeze_choice(choice_run.run.run_id)
    assert package.run.manifest["stages"]["freeze_choice"]["status"] == "failed"
    assert not (package.run.path / "choice_handoff.json").exists()


def test_source_run_cannot_be_overwritten_by_freezing(choice_run):
    source_hash = sha256_file(choice_run.run.manifest_path)
    with pytest.raises(ValueError, match="separate output run"):
        choice_run.freeze_choice(choice_run.run.run_id)
    assert sha256_file(choice_run.run.manifest_path) == source_hash


def test_unrelated_output_run_is_not_changed(choice_run):
    target = Pipeline(choice_run.config, "unrelated-output")
    target.scenario(model_run_id=choice_run.run.run_id)
    target.run.complete()
    original = {
        path.name: path.read_bytes() for path in target.run.path.iterdir() if path.is_file()
    }
    with pytest.raises(ValueError, match="cannot overwrite an unrelated run"):
        target.freeze_choice(choice_run.run.run_id)
    assert {
        path.name: path.read_bytes() for path in target.run.path.iterdir() if path.is_file()
    } == original


def test_saved_model_replay_does_not_require_original_run(choice_run, frozen_choice, monkeypatch):
    original = read_json(frozen_choice.run.path / "scenario_result.json")
    choice_run.run.manifest_path.unlink()
    read_contexts = pd.read_parquet
    load_bundle = joblib.load

    def completed_package(workspace, run_id):
        assert run_id == frozen_choice.run.run_id
        return completed_run(workspace, run_id)

    def read_packaged_contexts(path):
        assert Path(path).resolve().is_relative_to(frozen_choice.run.path.resolve())
        return read_contexts(path)

    def load_packaged_bundle(path):
        assert Path(path).resolve().is_relative_to(frozen_choice.run.path.resolve())
        return load_bundle(path)

    monkeypatch.setattr("gsm_poc.pipeline.pipeline.completed_run", completed_package)
    monkeypatch.setattr("gsm_poc.pipeline.pipeline.pd.read_parquet", read_packaged_contexts)
    monkeypatch.setattr("gsm_poc.pipeline.pipeline.joblib.load", load_packaged_bundle)
    replay = Pipeline(frozen_choice.config, "standalone-replay")
    result = replay.scenario(model_run_id=frozen_choice.run.run_id)
    replay.run.complete()
    assert result.get("probabilities") == original.get("probabilities")
    assert result["scope"] == original["scope"]
    assert result["bootstrap"]["interval_status"] == "interval_unstable"
    assert "fit" not in replay.run.manifest["stages"]


def test_frozen_package_can_prepare_demand_without_a_fit_stage(frozen_choice):
    snapshot = read_json(Path(__file__).parents[1] / "configs/week3_snapshot.json")
    snapshot_path = frozen_choice.config.workspace / "snapshot.json"
    write_json(snapshot_path, snapshot)
    consumer = Pipeline(frozen_choice.config, "package-demand")
    result = consumer.prepare_demand(frozen_choice.run.run_id, snapshot_path)
    consumer.run.complete()
    assert result["usable_for_simulation"]
    assert consumer.run.manifest["demand_source"]["model_run_id"] == frozen_choice.run.run_id
    assert "fit" not in frozen_choice.run.manifest["stages"]
    completed_run(frozen_choice.config.workspace, consumer.run.run_id)


def test_replay_preserves_frozen_support_threshold(choice_run):
    assert choice_run.scenario(zone=161)["support_status"] == "ok"
    choice_run.run.complete()
    strict_config = dataclasses.replace(
        choice_run.config,
        model=dataclasses.replace(choice_run.config.model, min_price_cell_count=10000),
    )
    strict = Pipeline(strict_config, "strict-source")
    strict.fit(choice_run.run.manifest["dataset_id"])
    strict.method_evaluation()
    strict.scenario(zone=161)
    strict.run.complete()
    package = Pipeline(choice_run.config, "strict-handoff")
    package.freeze_choice(strict.run.run_id)
    package.run.complete()
    replay = Pipeline(choice_run.config, "strict-replay")
    result = replay.scenario(model_run_id=package.run.run_id, zone=161)
    assert result["status"] == "insufficient_support"
    assert any("minimum 10000" in reason for reason in result["reasons"])


def test_replay_rejects_an_estimator_absent_from_the_handoff(frozen_choice):
    config = dataclasses.replace(
        frozen_choice.config,
        model=dataclasses.replace(
            frozen_choice.config.model, estimators=("dml",), scenario_estimator="dml"
        ),
    )
    replay = Pipeline(config, "absent-estimator")
    with pytest.raises(ValueError, match="not present"):
        replay.scenario(model_run_id=frozen_choice.run.run_id)
    assert replay.run.manifest["stages"]["scenario"]["status"] == "failed"


@pytest.mark.parametrize("zone", [None, 161])
def test_legacy_scenario_gets_a_separate_current_replay(choice_run, zone):
    if zone is not None:
        choice_run.scenario(zone=zone)
        choice_run.run.complete()
    historical_path = choice_run.run.path / "scenario_result.json"
    historical = read_json(historical_path)
    del historical["scope"]
    write_json(historical_path, historical)
    choice_run.run.register([historical_path])
    historical_hash = sha256_file(historical_path)
    source_hash = sha256_file(choice_run.run.manifest_path)
    package = Pipeline(choice_run.config, "legacy-handoff")
    result = package.freeze_choice(choice_run.run.run_id)
    package.run.complete()
    current = read_json(package.run.path / "current_scenario_result.json")
    assert current["scope"]["zones"] == ([zone] if zone is not None else [161, 162])
    assert current.get("probabilities") == historical.get("probabilities")
    assert current.get("delta_expected_bookings") == historical.get("delta_expected_bookings")
    assert current["context_blocks"] == historical["context_blocks"]
    assert result["scope"] == current["scope"]
    assert sha256_file(package.run.path / "scenario_result.json") == historical_hash
    assert sha256_file(historical_path) == historical_hash
    assert sha256_file(choice_run.run.manifest_path) == source_hash
    completed_run(choice_run.config.workspace, package.run.run_id)


def test_freeze_choice_replays_horizon_filtered_scenario_and_exports_csv(choice_run):
    from gsm_poc.causal.scenario import ScenarioRequest

    contexts = pd.read_parquet(choice_run.run.path / "scenario_contexts.parquet")
    first_time = contexts.slot_start_local.min()
    slot_hours = int(choice_run.config.simulation.slot_minutes / 60.0)
    start_ts = pd.Timestamp(first_time).tz_localize("America/New_York")
    end_ts = start_ts + pd.Timedelta(hours=2 * slot_hours)
    h_start = start_ts.isoformat()
    h_end = end_ts.isoformat()

    req = ScenarioRequest(horizon_start=h_start, horizon_end=h_end)
    target = Pipeline(choice_run.config, "horizon-scenario-source")
    target.fit(choice_run.run.manifest["dataset_id"])
    target.method_evaluation()
    res = target.scenario(request=req)
    target.run.complete()

    # Regression test for Issue 3: scenario_metrics.csv must not be empty
    csv_path = target.run.path / "scenario_metrics.csv"
    assert csv_path.exists()
    csv_lines = [
        line.strip() for line in csv_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(csv_lines) > 5, "scenario_metrics.csv should contain rows, not just header/empty"
    assert "probability_baseline_x" in csv_path.read_text(encoding="utf-8")

    # Regression test for Issue 5: freeze_choice must succeed without scope mismatch error
    pkg = Pipeline(choice_run.config, "horizon-freeze-package")
    pkg.freeze_choice(target.run.run_id)
    pkg.run.complete()

    current = read_json(pkg.run.path / "current_scenario_result.json")
    assert current["scope"]["context_blocks"] == res["scope"]["context_blocks"]
    assert current["scope"]["horizon_start"] == h_start
