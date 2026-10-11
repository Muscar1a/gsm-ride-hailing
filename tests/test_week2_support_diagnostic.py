from __future__ import annotations

import dataclasses
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from gsm_poc.scenario import ScenarioRequest

from gsm_poc.core.artifacts import completed_run, read_json, sha256_file
from gsm_poc.pipeline import Pipeline
from gsm_poc.simulation.dgp import generate, save_generated

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diagnose_week2_support.py"
SPEC = importlib.util.spec_from_file_location("week2_support", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


@pytest.fixture
def support_bundle():
    rows = []
    for zone, baseline_count, target_count in [(161, 20, 20), (162, 25, 19)]:
        for x, count in [(1.0, baseline_count), (1.1, target_count)]:
            rows.extend(
                [
                    {
                        "zone_id": zone,
                        "is_weekend": 0,
                        "is_peak": 0,
                        "multiplier_x": x,
                        "multiplier_y": 1.0,
                    }
                ]
                * count
            )
    return SimpleNamespace(train_support=pd.DataFrame(rows), diagnostics={"condition_number": 1})


@pytest.fixture
def support_config(config):
    return dataclasses.replace(
        config, model=dataclasses.replace(config.model, min_price_cell_count=20)
    )


def test_selects_training_scope_at_unchanged_threshold(support_bundle, support_config):
    table, scope = diagnostic.training_scope(support_bundle, ScenarioRequest(), support_config)
    assert scope["minimum_blocks"] == 20
    assert scope["eligible_group_count"] == 1
    assert scope["groups"][0]["eligible"] is True
    assert scope["groups"][1]["eligible"] is False
    assert "19 blocks" in scope["groups"][1]["reasons"][0]
    assert table.query("zone_id == 161").corner_status.tolist() == ["ok", "ok"]


def test_missing_global_corner_is_explicit_and_no_scope_qualifies(support_bundle, support_config):
    support_bundle.train_support = support_bundle.train_support.query("multiplier_x == 1.0")
    table, scope = diagnostic.training_scope(support_bundle, ScenarioRequest(), support_config)
    assert table.query("point == 'target'").training_blocks.tolist() == [0, 0]
    assert table.query("point == 'target'").corner_status.tolist() == ["missing", "missing"]
    assert scope["eligible_group_count"] == 0
    contexts = pd.DataFrame(
        {"zone_id": [161], "is_weekend": [0], "is_peak": [0], "n_sessions": [50]}
    )
    selected, denominator = diagnostic.scope_contexts(contexts, scope)
    assert selected.empty
    assert denominator["retained_context_blocks"] == 0
    assert denominator["excluded_context_weight_sessions"] == 50


def test_unseen_groups_excluded_and_outcomes_do_not_change_scope(support_bundle, support_config):
    _, scope = diagnostic.training_scope(support_bundle, ScenarioRequest(), support_config)
    contexts = pd.DataFrame(
        {
            "zone_id": [161, 162, 170],
            "is_weekend": [0, 0, 0],
            "is_peak": [0, 0, 0],
            "n_sessions": [50, 75, 25],
            "q_y": [0.2, 0.3, 0.4],
        }
    )
    selected, denominator = diagnostic.scope_contexts(contexts, scope)
    contexts["q_y"] = [0.9, 0, -999]
    changed, changed_denominator = diagnostic.scope_contexts(contexts, scope)
    assert selected.zone_id.tolist() == changed.zone_id.tolist() == [161]
    assert denominator == changed_denominator
    assert denominator["retained_session_fraction"] == pytest.approx(1 / 3)
    assert denominator["all_context_weight_sessions"] == 150
    assert denominator["excluded_context_weight_sessions"] == 100
    assert denominator["unseen_training_group_context_blocks"] == 1
    assert denominator["unseen_training_group_weight_sessions"] == 25


def test_condition_number_and_out_of_range_not_bypassed(support_bundle, support_config):
    support_bundle.diagnostics["condition_number"] = 1001
    _, scope = diagnostic.training_scope(support_bundle, ScenarioRequest(), support_config)
    assert scope["eligible_group_count"] == 0
    assert "poorly conditioned" in scope["groups"][0]["reasons"][-1]
    with pytest.raises(ValueError, match="outside"):
        diagnostic.training_scope(
            support_bundle, ScenarioRequest(delta_price_x=0.2), support_config
        )


@pytest.fixture
def frozen_choice(config):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    data = generate(config)
    save_generated(config, data)
    source = Pipeline(config, "support-choice-source")
    source.fit(data.dataset_id)
    source.method_evaluation()
    source.scenario()
    source.run.complete()
    package = Pipeline(config, "support-choice-package")
    package.freeze_choice(source.run.run_id)
    package.run.complete()
    return package


def test_replay_persists_scope_before_contexts_and_preserves_original(frozen_choice, monkeypatch):
    from functools import partial

    # Exercise the frozen runner's original engine against the unchanged baseline.
    monkeypatch.setattr(
        diagnostic, "scenario", partial(diagnostic.scenario, inference_method="bootstrap")
    )
    workspace = frozen_choice.config.workspace
    output_id = "support-audit"
    source_manifest = completed_run(workspace, frozen_choice.run.run_id)
    source_hashes = {**source_manifest["artifacts"]}
    source_hashes[str(frozen_choice.run.manifest_path.relative_to(workspace))] = sha256_file(
        frozen_choice.run.manifest_path
    )
    read_parquet = pd.read_parquet

    def assert_saved_scope(path, *args, **kwargs):
        if Path(path).name == "scenario_contexts.parquet":
            assert (workspace / "runs" / output_id / "candidate_scope.json").is_file()
        return read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(diagnostic.pd, "read_parquet", assert_saved_scope)
    result = diagnostic.diagnose_support(workspace, frozen_choice.run.run_id, output_id)
    manifest = completed_run(workspace, output_id)
    assert manifest["stages"]["support_diagnostic"]["status"] == "succeeded"
    assert len(manifest["artifacts"]) == 6
    assert result["source_bytes_unchanged"]
    assert result["all_context_replay_matches_frozen_current_result"]
    for relative, expected in source_hashes.items():
        assert sha256_file(workspace / relative) == expected
    scoped = read_json(workspace / "runs" / output_id / "scoped_scenario_result.json")
    assert scoped["support_status"] == "ok"
    assert scoped["target_context_set"] == "training_supported"
    denominator = result["denominators"]
    assert denominator["all_context_blocks"] == (
        denominator["retained_context_blocks"] + denominator["excluded_context_blocks"]
    )
    assert result["interval_calibration_status"] == "not_validated_by_support_diagnosis"


def test_corruption_rejected_before_joblib_load(frozen_choice, monkeypatch):
    source = frozen_choice.run.path / "models/adjusted_ols/model_bundle.joblib"
    source.write_bytes(b"corrupt")

    def unexpected_load(*args, **kwargs):
        pytest.fail("Unverified joblib was deserialized")

    monkeypatch.setattr(diagnostic.joblib, "load", unexpected_load)
    with pytest.raises(ValueError, match="checksum mismatch"):
        diagnostic.diagnose_support(
            frozen_choice.config.workspace, frozen_choice.run.run_id, "corrupt-audit"
        )


def test_existing_output_is_not_overwritten(frozen_choice):
    target = frozen_choice.config.workspace / "runs/existing-support"
    target.mkdir()
    sentinel = target / "valuable.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="new output run"):
        diagnostic.diagnose_support(
            frozen_choice.config.workspace, frozen_choice.run.run_id, target.name
        )
    assert sentinel.read_text(encoding="utf-8") == "preserve"
