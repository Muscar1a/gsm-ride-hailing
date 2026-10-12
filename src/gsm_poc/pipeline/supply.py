"""Supply-only stages reuse the repository's manifests, integrity checks and exports."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pandas as pd

from gsm_poc.causal.benchmarks.supply import SupplyProtocol, evaluate_supply
from gsm_poc.causal.supply import SupplySpec, fit_supply, supply_scenario
from gsm_poc.core.artifacts import (
    Run,
    completed_run,
    freeze_artifacts,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.simulation.supply import generate_supply


def _require_supply_run(run: Run, stage: str) -> None:
    if run.manifest["source_kind"] != "synthetic":
        raise ValueError("Supply stages currently require a synthetic project configuration")
    if set(run.manifest.get("stages", {})) - {stage}:
        raise ValueError(
            "Supply stage needs a separate run; preserve existing demand/choice artifacts"
        )


def generate_supply_run(run: Run, spec_path: Path) -> dict[str, Any]:
    stage = "generate_supply"
    _require_supply_run(run, stage)
    with run.stage(stage, lambda: {"spec_sha256": sha256_file(spec_path)}) as execute:
        if execute:
            spec = SupplySpec.from_dict(read_json(spec_path))
            observed, oracle = generate_supply(spec)
            directory = run.path / "supply"
            paths = [
                directory / "observed/driver_decisions.parquet",
                directory / "observed/contract.json",
                directory / "oracle/driver_expectations.parquet",
                directory / "generator_spec.json",
            ]
            write_frame(paths[0], observed)
            write_json(paths[1], spec.contract())
            write_frame(paths[2], oracle)
            write_json(paths[3], dataclasses.asdict(spec))
            run.outputs(stage, paths, eligible_drivers=spec.n_drivers, driver_shifts=len(observed))
    return {"run_id": run.run_id, "evidence_level": "C", "status": "generated"}


def fit_supply_run(run: Run, supply_run_id: str) -> dict[str, Any]:
    stage = "fit_supply"
    _require_supply_run(run, stage)
    if supply_run_id == run.run_id:
        raise ValueError("fit-supply requires a completed separate observed-data run")
    source: dict[str, Any] = {}

    def inputs() -> dict[str, Any]:
        nonlocal source
        source = completed_run(run.config.workspace, supply_run_id)
        if source["stages"].get("generate_supply", {}).get("status") != "succeeded":
            raise ValueError("Source run has no completed supply generation stage")
        return {
            "supply_run_id": supply_run_id,
            "source_manifest_sha256": sha256_file(
                run.config.workspace / "runs" / supply_run_id / "manifest.json"
            ),
        }

    with run.stage(stage, inputs) as execute:
        if execute:
            source_root = run.config.workspace / "runs" / supply_run_id
            relative = f"runs/{supply_run_id}/supply/observed/"
            copied = freeze_artifacts(
                source_root / "supply/observed",
                run.path / "supply_inputs",
                {
                    name: source["artifacts"][relative + name]
                    for name in ("driver_decisions.parquet", "contract.json")
                },
            )
            observed = pd.read_parquet(run.path / "supply_inputs/driver_decisions.parquet")
            contract = read_json(run.path / "supply_inputs/contract.json")
            bundle = fit_supply(observed, contract)
            model = run.path / "models/supply/model_bundle.json"
            effects = run.path / "supply_effects.csv"
            write_json(model, bundle)
            write_frame(
                effects,
                pd.DataFrame(
                    [
                        {
                            **row,
                            "model_id": bundle["model_id"],
                            "evidence_level": "C",
                            "population": bundle["population"],
                            "inference_unit": "driver_id",
                            "support_status": bundle["support_status"],
                            "baseline_incentive": contract["baseline_incentive"],
                            "target_incentive": contract["target_incentive"],
                            "currency": contract["currency"],
                            "interval_level": contract["interval_level"],
                        }
                        for row in bundle["effects"]
                    ]
                ),
            )
            run.outputs(stage, [*copied, model, effects], output_effects=len(bundle["effects"]))
    return read_json(run.path / "models/supply/model_bundle.json")


def supply_scenario_run(run: Run, model_run_id: str, incentive_amount: float) -> dict[str, Any]:
    stage = "supply_scenario"
    _require_supply_run(run, stage)
    if model_run_id == run.run_id:
        raise ValueError("scenario-supply requires a separate completed model run")
    source: dict[str, Any] = {}

    def inputs() -> dict[str, Any]:
        nonlocal source
        source = completed_run(run.config.workspace, model_run_id)
        if source["stages"].get("fit_supply", {}).get("status") != "succeeded":
            raise ValueError("Source run has no completed supply fit")
        return {
            "model_run_id": model_run_id,
            "incentive_amount": incentive_amount,
            "source_manifest_sha256": sha256_file(
                run.config.workspace / "runs" / model_run_id / "manifest.json"
            ),
        }

    with run.stage(stage, inputs) as execute:
        if execute:
            relative = f"runs/{model_run_id}/models/supply/model_bundle.json"
            copied = freeze_artifacts(
                run.config.workspace / "runs" / model_run_id / "models/supply",
                run.path / "supply_inputs",
                {"model_bundle.json": source["artifacts"][relative]},
            )
            result = supply_scenario(
                read_json(run.path / "supply_inputs/model_bundle.json"), incentive_amount
            )
            path = run.path / "supply_scenario.json"
            write_json(path, result)
            run.outputs(stage, [*copied, path], output_metrics=len(result["metrics"]))
    return read_json(run.path / "supply_scenario.json")


def evaluate_supply_run(run: Run, spec_path: Path, protocol_path: Path) -> dict[str, Any]:
    stage = "evaluate_supply"
    _require_supply_run(run, stage)
    with run.stage(
        stage,
        lambda: {
            "spec_sha256": sha256_file(spec_path),
            "protocol_sha256": sha256_file(protocol_path),
        },
    ) as execute:
        if execute:
            spec = SupplySpec.from_dict(read_json(spec_path))
            protocol = SupplyProtocol.from_dict(read_json(protocol_path))
            source_files = [
                "src/gsm_poc/causal/supply.py",
                "src/gsm_poc/simulation/supply.py",
                "src/gsm_poc/causal/benchmarks/supply.py",
                "src/gsm_poc/pipeline/supply.py",
                "src/gsm_poc/core/artifacts.py",
                "src/gsm_poc/core/config.py",
                "src/gsm_poc/cli.py",
                "uv.lock",
            ]
            snapshot = freeze_artifacts(
                run.config.workspace,
                run.path / "source_snapshot",
                {
                    name: sha256_file(run.config.workspace / name)
                    for name in source_files
                    if (run.config.workspace / name).is_file()
                },
            )
            spec_file = run.path / "supply_spec.json"
            protocol_file = run.path / "supply_protocol.json"
            write_json(spec_file, dataclasses.asdict(spec))
            write_json(protocol_file, dataclasses.asdict(protocol))
            records, summary = evaluate_supply(spec, protocol)
            summary["environment"] = run.manifest["environment"]
            summary["run_id"] = run.run_id
            paths = [run.path / "supply_benchmark_records.csv", run.path / "supply_benchmark.json"]
            write_frame(paths[0], records)
            write_json(paths[1], summary)
            run.outputs(
                stage,
                [*snapshot, spec_file, protocol_file, *paths],
                attempted_seed_jobs=summary["attempted_seed_jobs"],
            )
    return read_json(run.path / "supply_benchmark.json")
