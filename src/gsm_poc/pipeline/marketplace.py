"""Frozen input handoff for controlled fixed-online marketplace evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from gsm_poc.core.artifacts import (
    Run,
    completed_run,
    freeze_artifacts,
    read_json,
    safe_id,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config
from gsm_poc.simulation.compensation import validate_compensation
from gsm_poc.simulation.demand import DemandPlan
from gsm_poc.simulation.evaluation import evaluate_marketplace, validate_protocol


def evaluate_marketplace_run(
    run: Run,
    baseline_run_id: str,
    target_run_id: str,
    rules_path: Path,
    compensation_path: Path,
    protocol_path: Path,
) -> dict[str, Any]:
    """Evaluate frozen supported demand plans; never refit choice or labor models."""
    stage = "evaluate_marketplace"
    if set(run.manifest["stages"]) - {stage}:
        raise ValueError("Marketplace evaluation requires a separate output run")
    if run.run_id in (baseline_run_id, target_run_id):
        raise ValueError("Preserve source demand runs; use a separate evaluation run")
    sources: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, dict[str, str]] = {}
    rules: dict[str, Any] = {}
    compensation: dict[str, Any] = {}
    protocol: dict[str, Any] = {}
    source_root = Path(__file__).resolve().parents[3]
    source_names = [
        str(path.relative_to(source_root)).replace("\\", "/")
        for path in (source_root / "src/gsm_poc/simulation").glob("*.py")
    ] + [
        "src/gsm_poc/pipeline/marketplace.py",
        "src/gsm_poc/pipeline/pipeline.py",
        "src/gsm_poc/core/artifacts.py",
        "src/gsm_poc/core/config.py",
        "src/gsm_poc/cli.py",
        "pyproject.toml",
        "uv.lock",
    ]
    source_hashes: dict[str, str] = {}

    def inputs() -> dict[str, Any]:
        nonlocal rules, compensation, protocol, source_hashes
        identities = {}
        for label, run_id in (("baseline", baseline_run_id), ("target", target_run_id)):
            source = completed_run(run.config.workspace, safe_id(run_id))
            if source["stages"].get("prepare_demand", {}).get("status") != "succeeded":
                raise ValueError("Evaluation requires completed prepare-demand sources")
            directory = run.config.workspace / "runs" / run_id
            if read_json(directory / "demand_result.json").get("usable_for_simulation") is not True:
                raise ValueError("Demand usable_for_simulation gate is false or unavailable")
            names = (
                "demand_plan.parquet",
                "demand_result.json",
                "demand_spec.json",
                "baseline_snapshot.json",
            )
            artifacts[label] = {}
            for name in names:
                relative = f"runs/{run_id}/{name}"
                if relative not in source["artifacts"]:
                    raise ValueError(f"Required evaluation input is unregistered: {relative}")
                artifacts[label][name] = source["artifacts"][relative]
            sources[label] = source
            identities[label] = {
                "run_id": run_id,
                "manifest_sha256": sha256_file(directory / "manifest.json"),
                "artifacts": artifacts[label],
            }
        rules = read_json(rules_path)
        compensation = validate_compensation(read_json(compensation_path))
        protocol = validate_protocol(read_json(protocol_path))
        source_hashes = {name: sha256_file(source_root / name) for name in source_names}
        return {
            "sources": identities,
            "rules": rules,
            "compensation": compensation,
            "protocol": protocol,
            "source_hashes": source_hashes,
        }

    with run.stage(stage, inputs) as execute:
        result_path = run.path / "marketplace_evaluation.json"
        if execute:
            paths = []
            plans = {}
            for label, run_id in (("baseline", baseline_run_id), ("target", target_run_id)):
                frozen = run.path / "evaluation_inputs" / label
                paths.extend(
                    freeze_artifacts(
                        run.config.workspace / "runs" / run_id, frozen, artifacts[label]
                    )
                )
                manifest_path = frozen / "source_manifest.json"
                write_json(manifest_path, sources[label])
                paths.append(manifest_path)
                plans[label] = DemandPlan(
                    pd.read_parquet(frozen / "demand_plan.parquet"),
                    read_json(frozen / "demand_result.json"),
                    read_json(frozen / "baseline_snapshot.json"),
                    read_json(frozen / "demand_spec.json"),
                )
            for name, value in (
                ("rules", rules),
                ("compensation", compensation),
                ("protocol", protocol),
            ):
                path = run.path / "evaluation_inputs" / f"{name}.json"
                write_json(path, value)
                paths.append(path)
            paths.extend(
                freeze_artifacts(
                    source_root,
                    run.path / "source_snapshot",
                    source_hashes,
                )
            )
            source_config = Config.from_dict(
                sources["baseline"]["demand_source"]["source_config"], run.config.workspace
            )
            evaluation = evaluate_marketplace(
                plans["baseline"], plans["target"], source_config, rules, compensation, protocol
            )
            result = evaluation["result"]
            result["run_id"] = run.run_id
            result["environment"] = run.manifest["environment"]
            result["source_runs"] = {"baseline": baseline_run_id, "target": target_run_id}
            for name in ("seed_records", "controlled_records", "workload_records"):
                path = run.path / f"marketplace_{name}.csv"
                write_frame(path, evaluation[name])
                paths.append(path)
            write_json(result_path, result)
            paths.append(result_path)
            run.outputs(stage, paths, output_status=result["status"])
            if result["execution_status"] != "completed":
                raise RuntimeError(
                    "Marketplace evaluation incomplete; inspect retained diagnostics"
                )
    return read_json(run.path / "marketplace_evaluation.json")
