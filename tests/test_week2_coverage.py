from __future__ import annotations

import dataclasses
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from gsm_poc.artifacts import Run, read_json, write_frame, write_json
from gsm_poc.config import Config, EvaluationConfig

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_week2_coverage.py"
SPEC = importlib.util.spec_from_file_location("week2_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_batches_cover_exact_protocol_without_probe_or_overlap():
    jobs = runner.batch_jobs(5)
    assert len(jobs) == 100
    for dgp in runner.PRIORITY_DGPS:
        seeds = [
            seed
            for job in jobs
            if job["dgp"] == dgp
            for seed in range(job["seed"], job["seed"] + job["seeds"])
        ]
        assert seeds == list(range(20001, 20101))
        assert len(set(seeds)) == 100
    for invalid in (0, 6, -1):
        with pytest.raises(ValueError, match="one and five"):
            runner.batch_jobs(invalid)


def test_runner_lock_released_and_duplicate_runner_rejected(tmp_path):
    with runner.runner_lock(tmp_path):
        with pytest.raises(OSError):
            with runner.runner_lock(tmp_path):
                pytest.fail("Second runner acquired active lock")
    with runner.runner_lock(tmp_path):
        pass


def metric_rows(config):
    rows = []
    for seed in (20001, 20002):
        for estimator in config.model.estimators:
            for outcome in ("X", "Y"):
                for treatment in ("X", "Y"):
                    rows.append(
                        {
                            "dgp_id": "RCT_SYN",
                            "seed": seed,
                            "estimator": estimator,
                            "outcome": outcome,
                            "treatment": treatment,
                            "source_kind": "synthetic",
                            "evidence_level": "C",
                            "error": 0.1 if seed == 20001 else None,
                            "covered": True if seed == 20001 else None,
                            "false_positive": None,
                            "interval_status": "ok" if seed == 20001 else "interval_unstable",
                            "requested_draws": 199,
                            "successful_draws": 199 if seed == 20001 else 0,
                            "scenario_probability_rmse": 0.01 if seed == 20001 else None,
                        }
                    )
    return pd.DataFrame(rows)


def completed_batch(tmp_path, frame):
    config = Config(
        workspace=tmp_path,
        evaluation=EvaluationConfig(seeds=2, bootstrap_draws=199, dgps=("RCT_SYN",)),
    )
    config = dataclasses.replace(
        config, simulation=dataclasses.replace(config.simulation, seed=20001)
    )
    job = {"dgp": "RCT_SYN", "seed": 20001, "seeds": 2, "run_id": "test-batch"}
    run = Run(config, job["run_id"])
    with run.stage("evaluate", {}) as execute:
        assert execute
        path = run.path / "evaluation/seed_metrics.parquet"
        write_frame(path, frame)
        run.outputs("evaluate", [path])
    run.complete()
    frozen_source = tmp_path / "src/gsm_poc"
    frozen_source.mkdir(parents=True)
    shutil.copy2(SCRIPT.parents[1] / "src/gsm_poc/evaluate.py", frozen_source / "evaluate.py")
    return run, job, {"environment": run.manifest["environment"], "config": config.as_dict()}


def test_aggregate_retains_failed_seed_denominators_and_partial_status(tmp_path):
    config = Config(workspace=tmp_path)
    _, job, spec = completed_batch(tmp_path, metric_rows(config))
    status = runner.aggregate_batches(tmp_path, spec, [job])
    assert status["status"] == "partial"
    assert status["completed_seeds"]["RCT_SYN"] == 2
    table = pd.read_csv(tmp_path / runner.REPORT_DIRECTORY / "evaluation_metrics.csv")
    assert table.expected_seeds.eq(100).all()
    assert table.attempted_seeds.eq(2).all()
    assert table.valid_estimates.eq(1).all()
    assert table.failed_or_unidentified_estimates.eq(1).all()
    assert table.coverage_denominator.eq(1).all()


def test_aggregate_rejects_duplicate_cells_and_foreign_revision(tmp_path):
    config = Config(workspace=tmp_path)
    frame = metric_rows(config)
    _, job, spec = completed_batch(tmp_path, pd.concat([frame, frame.iloc[:1]], ignore_index=True))
    with pytest.raises(ValueError, match="Duplicate"):
        runner.aggregate_batches(tmp_path, spec, [job])
    spec["environment"] = {"different": "revision"}
    with pytest.raises(ValueError, match="different code"):
        runner.aggregate_batches(tmp_path, spec, [job])


def test_batch_failure_is_checkpointed_without_starting_next(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "evaluation_spec", lambda *args: {"test": "frozen"})
    monkeypatch.setattr(runner, "aggregate_batches", lambda *args: {"status": "partial"})
    calls = []

    def failed_batch(snapshot, build_id, job, timeout_seconds):
        calls.append(job)
        raise runner.subprocess.TimeoutExpired("fixture", timeout_seconds)

    monkeypatch.setattr(runner, "run_batch", failed_batch)
    with pytest.raises(runner.subprocess.TimeoutExpired):
        runner.run_protocol(tmp_path, "fixture", 5, 1)
    assert len(calls) == 1
    state = read_json(tmp_path / runner.REPORT_DIRECTORY / "status.json")
    assert state["process_status"] == "failed"
    assert state["error_type"] == "TimeoutExpired"
    assert state["active_batch"]["seed"] == 20001


def test_snapshot_changes_refuse_resume_before_any_batch(tmp_path, monkeypatch):
    root = tmp_path / runner.REPORT_DIRECTORY
    root.mkdir()
    write_json(root / "frozen_spec.json", {"test": "previous"})
    monkeypatch.setattr(runner, "evaluation_spec", lambda *args: {"test": "changed"})
    with pytest.raises(ValueError, match="Frozen protocol changed"):
        runner.run_protocol(tmp_path, "fixture", 5, 1)


def test_report_directory_does_not_shadow_numba_optional_coverage(tmp_path):
    (tmp_path / runner.REPORT_DIRECTORY).mkdir()
    result = subprocess.run(
        [sys.executable, "-c", "import numba; print('numba import ok')"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
