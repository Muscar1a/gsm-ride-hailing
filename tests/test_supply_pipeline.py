from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest

from gsm_poc.causal.benchmarks.supply import SupplyProtocol
from gsm_poc.causal.supply import SupplySpec
from gsm_poc.cli import main, parser
from gsm_poc.core.artifacts import Run, completed_run, read_json, write_json
from gsm_poc.pipeline.supply import (
    evaluate_supply_run,
    fit_supply_run,
    generate_supply_run,
    supply_scenario_run,
)


def test_supply_handoff_replay_does_not_load_oracle_and_exports_units(config, monkeypatch):
    spec_path = config.workspace / "supply_spec.json"
    spec = SupplySpec(n_drivers=80, n_shifts=2, min_drivers_per_arm=10)
    write_json(spec_path, dataclasses.asdict(spec))
    source = Run(config, "supply-data")
    generate_supply_run(source, spec_path)
    source.complete()
    original_artifacts = dict(completed_run(config.workspace, source.run_id)["artifacts"])
    read_parquet = pd.read_parquet

    def observed_only(path, *args, **kwargs):
        assert "oracle" not in str(path)
        return read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", observed_only)
    fitted_run = Run(config, "supply-fit")
    fitted = fit_supply_run(fitted_run, source.run_id)
    fitted_run.complete()
    second = fit_supply_run(Run(config, fitted_run.run_id), source.run_id)
    assert fitted == second
    result_run = Run(config, "supply-scenario")
    scenario = supply_scenario_run(result_run, fitted_run.run_id, 20)
    result_run.complete()
    assert scenario["status"] == "ok"
    assert scenario["eligible_drivers"] == 80
    assert scenario["n_shifts"] == 2
    assert scenario["evidence_level"] == "C"
    rows = pd.read_csv(fitted_run.path / "supply_effects.csv")
    assert len(rows) == 3
    assert rows.inference_unit.eq("driver_id").all()
    assert rows.population.str.contains("nonparticipants").all()
    assert rows.currency.eq("SYNTHETIC_UNIT").all()
    assert completed_run(config.workspace, source.run_id)["artifacts"] == original_artifacts
    completed_run(config.workspace, fitted_run.run_id)
    completed_run(config.workspace, result_run.run_id)


def test_changed_source_is_rejected_and_failure_is_recorded(config):
    path = config.workspace / "spec.json"
    write_json(path, dataclasses.asdict(SupplySpec(n_drivers=80, n_shifts=2)))
    source = Run(config, "source")
    generate_supply_run(source, path)
    source.complete()
    observed = source.path / "supply/observed/driver_decisions.parquet"
    observed.write_bytes(b"changed source")
    target = Run(config, "target")
    with pytest.raises(ValueError, match="checksum"):
        fit_supply_run(target, source.run_id)
    assert read_json(target.manifest_path)["stages"]["fit_supply"]["status"] == "failed"


def test_supply_stages_preserve_unrelated_runs_and_refuse_incomplete_sources(config):
    run = Run(config, "choice")
    run.manifest["stages"]["fit"] = {"status": "succeeded"}
    run.save()
    with pytest.raises(ValueError, match="separate run"):
        generate_supply_run(run, Path("unused"))
    assert run.manifest["stages"] == {"fit": {"status": "succeeded"}}
    source = Run(config, "incomplete")
    target = Run(config, "new-supply")
    with pytest.raises(ValueError, match="not complete"):
        fit_supply_run(target, source.run_id)


def test_benchmark_run_freezes_protocol_and_registers_outputs(config):
    spec_path, protocol_path = config.workspace / "spec.json", config.workspace / "protocol.json"
    write_json(spec_path, dataclasses.asdict(SupplySpec(n_drivers=80, n_shifts=2)))
    protocol = SupplyProtocol(phase="pilot", n_seeds=1)
    write_json(protocol_path, dataclasses.asdict(protocol))
    run = Run(config, "benchmark")
    summary = evaluate_supply_run(run, spec_path, protocol_path)
    run.complete()
    assert summary["attempted_seed_jobs"] == 2
    assert read_json(run.path / "supply_protocol.json") == dataclasses.asdict(protocol)
    manifest = completed_run(config.workspace, run.run_id)
    assert "runs/benchmark/supply_benchmark_records.csv" in manifest["artifacts"]


def test_cli_supply_flow_and_legacy_choice_defaults(tmp_path):
    config_path = tmp_path / "configs" / "demo.toml"
    config_path.parent.mkdir()
    config_path.write_text('[project]\ncontext_mode="synthetic"\n', encoding="utf-8")
    spec_path = tmp_path / "spec.json"
    write_json(spec_path, dataclasses.asdict(SupplySpec(n_drivers=80, n_shifts=2)))
    common = ["--config", str(config_path)]
    assert (
        main(["generate-supply", *common, "--run-id", "data", "--supply-spec", str(spec_path)]) == 0
    )
    assert main(["fit-supply", *common, "--run-id", "fit", "--supply-run-id", "data"]) == 0
    assert (
        main(
            [
                "scenario-supply",
                *common,
                "--run-id",
                "scenario",
                "--model-run-id",
                "fit",
                "--incentive-amount",
                "20",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "scenario-supply",
                *common,
                "--run-id",
                "missing",
                "--model-run-id",
                "absent",
                "--incentive-amount",
                "20",
            ]
        )
        == 1
    )
    assert (
        parser().parse_args(["scenario", "--model-run-id", "choice"]).inference_method == "analytic"
    )
