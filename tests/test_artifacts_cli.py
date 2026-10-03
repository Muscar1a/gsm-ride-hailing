import dataclasses

import pandas as pd
import pytest

from gsm_poc.artifacts import Run, completed_run, read_json, safe_id, write_json
from gsm_poc.config import Config
from gsm_poc.pipeline import Pipeline


def test_completed_run_gate_and_corrupt_artifact(config):
    run = Run(config, "checksum-test")
    path = run.path / "result.json"
    with run.stage("fixture", {"value": 1}) as execute:
        assert execute
        write_json(path, {"value": 1})
        run.outputs("fixture", [path])
    with pytest.raises(ValueError, match="not complete"):
        completed_run(config.workspace, run.run_id)
    run.complete()
    assert completed_run(config.workspace, run.run_id)["status"] == "succeeded"
    write_json(path, {"value": 2})
    with pytest.raises(ValueError, match="checksum"):
        completed_run(config.workspace, run.run_id)
    with run.stage("fixture", {"value": 1}) as execute:
        assert execute  # changed output cannot be reused based on filename alone


def test_failure_record_is_preserved(config):
    run = Run(config)
    with pytest.raises(ValueError, match="specific context"):
        with run.stage("bad", {}):
            raise ValueError("specific context")
    manifest = read_json(run.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["stages"]["bad"]["error"] == "specific context"


def test_id_traversal_and_unknown_config_rejected(tmp_path):
    for name in ("../outside", "a/b", "", "a\\b"):
        with pytest.raises(ValueError):
            safe_id(name)
    with pytest.raises(ValueError, match="Unknown config"):
        Config.from_dict({"typo": {}}, tmp_path)
    with pytest.raises(ValueError, match="slot_minutes"):
        Config.from_dict({"simulation": {"slot_minutes": 7}}, tmp_path)


def test_offline_end_to_end_and_verified_stage_reuse(config):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    pipeline = Pipeline(config, "offline-test")
    pipeline.run_all(include_evaluation=True)
    manifest = completed_run(config.workspace, pipeline.run.run_id)
    assert manifest["source_kind"] == "synthetic"
    assert not (config.workspace / "data/bronze").exists()
    result = read_json(pipeline.run.path / "scenario_result.json")
    assert "probabilities" in result
    effects = pd.read_csv(pipeline.run.path / "effects.csv")
    assert len(effects) == 4
    assert effects.evidence_level.eq("C").all()
    evaluation = pd.read_csv(pipeline.run.path / "evaluation/evaluation_metrics.csv")
    assert evaluation.attempted_seeds.eq(2).all()
    collinear = evaluation[evaluation.dgp_id == "COLLINEAR_PRICE"]
    assert collinear.valid_estimates.eq(0).all()
    assert collinear.failed_or_unidentified_estimates.eq(2).all()
    original = manifest["stages"]["fit"]["duration_seconds"]
    resumed = Pipeline(config, "offline-test")
    resumed.run_all(include_evaluation=True)
    assert resumed.run.manifest["stages"]["fit"]["duration_seconds"] == original
