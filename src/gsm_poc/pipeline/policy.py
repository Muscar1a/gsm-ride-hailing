"""Week 4–5 artifact lifecycle: policies, independent truth, experiments and handoff."""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from pathlib import Path, PurePosixPath

import joblib
import numpy as np
import pandas as pd

from gsm_poc.causal.experiments import plan_experiment, reconcile_experiment
from gsm_poc.core.artifacts import (
    Run,
    atomic_path,
    completed_run,
    fingerprint,
    freeze_artifacts,
    read_json,
    safe_id,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config
from gsm_poc.core.validators import valid_probabilities
from gsm_poc.simulation.compensation import validate_compensation
from gsm_poc.simulation.demand import DemandPlan
from gsm_poc.simulation.policies import (
    compare_policies,
    evaluate_frozen_decision,
    policy_record,
    summarize_policies,
    validate_policy_spec,
)


def _source(run: Run, run_id: str, stage: str) -> tuple[dict, Path]:
    if run_id == run.run_id:
        raise ValueError("Preserve the input run; use a separate output run ID")
    manifest = completed_run(run.config.workspace, safe_id(run_id))
    if manifest["stages"].get(stage, {}).get("status") != "succeeded":
        raise ValueError(f"Source requires a completed {stage} stage")
    return manifest, run.config.workspace / "runs" / run_id


def _freeze_run(run: Run, manifest: dict, destination: Path) -> list[Path]:
    run_id = manifest["run_id"]
    prefix = f"runs/{run_id}/"
    names = {
        name.removeprefix(prefix): digest
        for name, digest in manifest["artifacts"].items()
        if name.startswith(prefix)
    }
    paths = freeze_artifacts(run.config.workspace / "runs" / run_id, destination, names)
    path = destination / "source_manifest.json"
    write_json(path, manifest)
    return [*paths, path]


def compare_policies_run(
    run: Run,
    demand_run_id: str,
    rules_path: Path,
    compensation_path: Path,
    spec_path: Path,
) -> dict:
    stage = "compare_policies"
    state = {}

    def inputs():
        source, directory = _source(run, demand_run_id, "prepare_demand")
        spec = validate_policy_spec(read_json(spec_path))
        compensation = validate_compensation(read_json(compensation_path))
        state.update(
            source=source,
            directory=directory,
            spec=spec,
            compensation=compensation,
            rules=read_json(rules_path),
        )
        return {
            "source_manifest": sha256_file(directory / "manifest.json"),
            "spec": spec,
            "rules": state["rules"],
            "compensation": compensation,
        }

    with run.stage(stage, inputs) as execute:
        if execute:
            source = state["source"]
            paths = _freeze_run(run, source, run.path / "policy_inputs")
            frozen = run.path / "policy_inputs"
            bundle_root = frozen / "demand_bundle"
            source_config = Config.from_dict(
                source["demand_source"]["source_config"], run.config.workspace
            )
            estimator = source["demand_source"]["estimator"]
            prefix = bundle_root / "models" / estimator
            bundle = joblib.load(prefix / "model_bundle.joblib")
            draws = joblib.load(prefix / "bootstrap_bundles.joblib")
            if (
                bundle.estimator != estimator
                or bundle.dataset_id
                != read_json(bundle_root / "source_manifest.json")["dataset_id"]
            ):
                raise ValueError("Model identity differs from the verified demand source")
            output = compare_policies(
                bundle,
                draws,
                pd.read_parquet(bundle_root / "scenario_contexts.parquet"),
                read_json(frozen / "baseline_snapshot.json"),
                source_config,
                state["rules"],
                state["compensation"],
                state["spec"],
                demand_run_id,
                sha256_file(prefix / "model_bundle.joblib"),
                sha256_file(frozen / "source_manifest.json"),
            )
            result = output["result"]
            snapshot = next(iter(output["plans"].values())).snapshot
            result.update(
                run_id=run.run_id,
                source_runs=[demand_run_id],
                scope={
                    "zone_ids": snapshot["zone_ids"],
                    "horizon_start": snapshot["horizon_start"],
                    "horizon_end": snapshot["horizon_end"],
                    "horizon_minutes": (
                        pd.Timestamp(snapshot["horizon_end"])
                        - pd.Timestamp(snapshot["horizon_start"])
                    ).total_seconds()
                    / 60,
                    "roster_size": len(snapshot["vehicles"]),
                },
                environment=run.manifest["environment"],
                independent_evaluation_status="not_evaluated",
            )
            for name, value in (
                ("policy_spec.json", state["spec"]),
                ("policy_rules.json", state["rules"]),
                ("policy_compensation.json", state["compensation"]),
                ("policy_comparison.json", result),
            ):
                path = run.path / name
                write_json(path, value)
                paths.append(path)
            for policy_id, plan in output["plans"].items():
                root = run.path / "policy_plans" / policy_id
                frame_path = root / "demand_plan.parquet"
                write_frame(frame_path, plan.frame)
                paths.append(frame_path)
                for name, value in (
                    ("demand_result.json", plan.result),
                    ("demand_spec.json", plan.spec),
                    ("baseline_snapshot.json", plan.snapshot),
                ):
                    path = root / name
                    write_json(path, value)
                    paths.append(path)
            for name, frame in (
                ("policy_records.csv", output["records"]),
                ("policy_summary.csv", pd.DataFrame(result["summary"])),
            ):
                path = run.path / name
                write_frame(path, frame)
                paths.append(path)
            run.manifest["source_runs"] = [demand_run_id]
            run.outputs(stage, paths, output_status=result["status"])
            if result["failed_trajectories"]:
                raise RuntimeError("Policy trajectories failed; inspect retained diagnostics")
    return read_json(run.path / "policy_comparison.json")


def _load_plan(root: Path) -> DemandPlan:
    return DemandPlan(
        pd.read_parquet(root / "demand_plan.parquet"),
        read_json(root / "demand_result.json"),
        read_json(root / "baseline_snapshot.json"),
        read_json(root / "demand_spec.json"),
    )


def evaluate_policies_run(
    run: Run, comparison_run_id: str, truth_run_id: str, spec_path: Path
) -> dict:
    stage = "evaluate_policies"
    state = {}

    def inputs():
        source, directory = _source(run, comparison_run_id, "compare_policies")
        truth, truth_dir = _source(run, truth_run_id, "generate")
        spec = validate_policy_spec(read_json(spec_path))
        original = read_json(directory / "policy_spec.json")
        if any(
            spec[key] != original[key] for key in ("candidates", "criterion", "guardrails", "costs")
        ):
            raise ValueError(
                "Independent evaluation cannot change the frozen candidates or criterion"
            )
        used_end = original["seed_start"] + max(
            original["n_seeds"],
            10000 + original["bootstrap_draws"] * original["replicates_per_draw"],
        )
        if (
            spec["seed_start"] < used_end
            and spec["seed_start"] + spec["n_seeds"] > original["seed_start"]
        ):
            raise ValueError("Independent operational seeds overlap development seeds")
        if spec["bootstrap_draws"] or spec["sensitivities"]:
            raise ValueError(
                "Independent oracle evaluation uses fixed truth, without model draws or tuning"
            )
        dataset_id = safe_id(truth["dataset_id"])
        required = [
            f"data/synthetic/{dataset_id}/{name}"
            for name in ("oracle/oracle_block.parquet", "oracle/parameters.json", "manifest.json")
        ]
        if any(name not in truth["artifacts"] for name in required):
            raise ValueError("Oracle inputs are not registered by the verified generator")
        state.update(source=source, directory=directory, truth=truth, spec=spec, required=required)
        return {
            "comparison": sha256_file(directory / "manifest.json"),
            "truth": sha256_file(truth_dir / "manifest.json"),
            "spec": spec,
        }

    with run.stage(stage, inputs) as execute:
        if execute:
            paths = _freeze_run(run, state["source"], run.path / "evaluation_inputs")
            root = run.path / "evaluation_inputs"
            # The comparison, including its selection, is immutable before opening oracle files.
            forecast = read_json(root / "policy_comparison.json")
            truth_root = run.path / "truth_inputs"
            truth_names = {name: state["truth"]["artifacts"][name] for name in state["required"]}
            paths.extend(freeze_artifacts(run.config.workspace, truth_root, truth_names))
            oracle_dir = truth_root / "data/synthetic" / state["truth"]["dataset_id"]
            oracle = pd.read_parquet(oracle_dir / "oracle/oracle_block.parquet")
            theta = np.asarray(
                read_json(oracle_dir / "oracle/parameters.json")["theta"], dtype=float
            )
            if theta.shape != (2, 2) or not np.isfinite(theta).all():
                raise ValueError("Oracle theta has invalid shape or values")
            if oracle.duplicated(["dataset_id", "block_id"]).any():
                raise ValueError("Duplicate oracle keys")
            demand_manifest = read_json(root / "policy_inputs/source_manifest.json")
            config = Config.from_dict(
                demand_manifest["demand_source"]["source_config"], run.config.workspace
            )
            contexts = pd.read_parquet(
                root / "policy_inputs/demand_bundle/scenario_contexts.parquet"
            )
            if not contexts.dataset_id.eq(state["truth"]["dataset_id"]).all():
                raise ValueError("Oracle dataset differs from the frozen forecast contexts")
            truth = contexts[["block_id", "dataset_id", "n_sessions"]].merge(
                oracle, on=["block_id", "dataset_id"], how="left", validate="one_to_one"
            )
            if truth[["b_x", "b_y"]].isna().any().any():
                raise ValueError("Oracle does not cover held-out contexts")
            rules = read_json(root / "policy_rules.json")
            compensation = read_json(root / "policy_compensation.json")
            spec = state["spec"]
            deadline = time.perf_counter() + spec["max_seconds"]
            rows = []
            for candidate in spec["candidates"]:
                policy_id = candidate["policy_id"]
                plan = _load_plan(root / "policy_plans" / policy_id)
                probabilities = (
                    truth[["b_x", "b_y"]].to_numpy(float)
                    + np.log([1 + candidate["delta_x"], 1 + candidate["delta_y"]]) @ theta.T
                )
                probabilities = np.column_stack([probabilities, 1 - probabilities.sum(axis=1)])
                if not valid_probabilities(probabilities):
                    raise ValueError("Oracle probabilities violate the simplex")
                lookup = truth[["block_id", "n_sessions"]].copy()
                lookup["X"] = probabilities[:, 0] * lookup.n_sessions
                lookup["Y"] = probabilities[:, 1] * lookup.n_sessions
                lookup = lookup.set_index("block_id")
                for service in ("X", "Y"):
                    mask = plan.frame.service_id.eq(service)
                    expected = plan.frame.loc[mask, "source_block_id"].map(lookup[service])
                    if expected.isna().any():
                        raise ValueError("Oracle block keys differ from the plan")
                    plan.frame.loc[mask, "expected_bookings"] = expected
                    plan.frame.loc[mask, "request_rate"] = (
                        expected / plan.frame.loc[mask, "block_hours"]
                    )
                plan.spec.update(
                    model_version="independent_controlled_truth",
                    source_version=fingerprint(truth_names),
                )
                version = fingerprint(plan.spec)
                plan.frame["model_version"] = plan.spec["model_version"]
                plan.frame["source_version"] = plan.spec["source_version"]
                plan.frame["demand_plan_version"] = version
                plan.result["demand_plan_version"] = version
                plan.result["summary"]["expected_bookings"] = float(
                    plan.frame.expected_bookings.sum()
                )
                for index in range(spec["n_seeds"]):
                    seed = spec["seed_start"] + index
                    record = policy_record(
                        plan, config, rules, compensation, seed, deadline, spec["costs"]
                    )
                    rows.append(
                        record
                        | {
                            "policy_id": policy_id,
                            "kind": "point",
                            "draw_id": -1,
                            "sensitivity_id": "declared_rules",
                        }
                    )
            records = pd.DataFrame(rows)
            summary = summarize_policies(records, spec)
            comparisons = []
            for row in summary:
                predicted = next(
                    r
                    for r in forecast["summary"]
                    if r["policy_id"] == row["policy_id"]
                    and r["metric"] == row["metric"]
                    and r["sensitivity_id"] == "declared_rules"
                )
                comparisons.append(
                    row
                    | {
                        "forecast_delta": predicted["delta_mean"],
                        "forecast_error": predicted["delta_mean"] - row["delta_mean"]
                        if predicted["delta_mean"] is not None and row["delta_mean"] is not None
                        else None,
                    }
                )
            failed = int(records.status.ne("succeeded").sum())
            result = {
                "schema_version": 1,
                "source_kind": "synthetic",
                "evidence_level": "C",
                "status": "completed_with_failures" if failed else "completed",
                "source_runs": [comparison_run_id, truth_run_id],
                "summary": comparisons,
                "frozen_selection": forecast["selected_policy_id"],
                "decision_evaluation": evaluate_frozen_decision(
                    summary, spec, forecast["selected_policy_id"]
                ),
                "reselection": False,
                "failed_trajectories": failed,
                "attempted_trajectories": len(records),
                "scope": forecast["scope"],
                "spec": spec,
                "interpretation": (
                    "Independent controlled behavioral truth; operational rules remain synthetic"
                ),
                "gsm_validation_status": "not_evaluated",
            }
            for name, value in (("policy_evaluation.json", result), ("evaluation_spec.json", spec)):
                path = run.path / name
                write_json(path, value)
                paths.append(path)
            for name, frame in (
                ("policy_evaluation_records.csv", records),
                ("policy_evaluation_summary.csv", pd.DataFrame(comparisons)),
            ):
                path = run.path / name
                write_frame(path, frame)
                paths.append(path)
            run.manifest["source_runs"] = result["source_runs"]
            run.outputs(stage, paths, output_status=result["status"])
            if failed:
                raise RuntimeError(
                    "Independent evaluation failed; inspect retained trajectory diagnostics"
                )
    return read_json(run.path / "policy_evaluation.json")


def plan_experiment_run(run: Run, comparison_run_id: str, spec_path: Path) -> dict:
    stage = "plan_experiment"
    source, directory = _source(run, comparison_run_id, "compare_policies")
    spec = read_json(spec_path)
    with run.stage(
        stage, {"source": sha256_file(directory / "manifest.json"), "spec": spec}
    ) as execute:
        if execute:
            paths = _freeze_run(run, source, run.path / "forecast_inputs")
            forecast = read_json(run.path / "forecast_inputs/policy_comparison.json")
            plan, schedule = plan_experiment(spec, forecast)
            plan["source_runs"] = [comparison_run_id]
            for name, value in (("experiment_plan.json", plan), ("experiment_spec.json", spec)):
                path = run.path / name
                write_json(path, value)
                paths.append(path)
            path = run.path / "experiment_schedule.csv"
            write_frame(path, schedule)
            paths.append(path)
            run.manifest["source_runs"] = [comparison_run_id]
            run.outputs(stage, paths)
    return read_json(run.path / "experiment_plan.json")


def reconcile_experiment_run(run: Run, experiment_run_id: str, observations_path: Path) -> dict:
    stage = "reconcile_experiment"
    source, directory = _source(run, experiment_run_id, "plan_experiment")
    with run.stage(
        stage,
        {
            "source": sha256_file(directory / "manifest.json"),
            "observations": sha256_file(observations_path),
        },
    ) as execute:
        if execute:
            paths = _freeze_run(run, source, run.path / "experiment_inputs")
            frozen = run.path / "experiment_inputs"
            observation_hash = sha256_file(observations_path)
            paths.extend(
                freeze_artifacts(
                    observations_path.parent,
                    run.path / "observations",
                    {observations_path.name: observation_hash},
                )
            )
            result = reconcile_experiment(
                read_json(frozen / "experiment_plan.json"),
                pd.read_csv(frozen / "experiment_schedule.csv"),
                pd.read_csv(run.path / "observations" / observations_path.name),
            )
            result["source_runs"] = [experiment_run_id]
            path = run.path / "experiment_reconciliation.json"
            write_json(path, result)
            run.manifest["source_runs"] = [experiment_run_id]
            run.outputs(stage, [*paths, path], output_status=result["status"])
    return read_json(run.path / "experiment_reconciliation.json")


def export_handoff_run(run: Run, source_run_ids: list[str], max_bytes: int = 268435456) -> dict:
    """Export verified transitive runs/data plus source, lockfile and rerun instructions."""
    if type(max_bytes) is not int or not 0 < max_bytes <= 2**30:
        raise ValueError("max_bytes must be within (0, 1 GiB]")
    state = {}

    def inputs():
        pending = list(source_run_ids)
        manifests, names = {}, {}
        while pending:
            run_id = safe_id(pending.pop())
            if run_id in manifests:
                continue
            if run_id == run.run_id or len(manifests) >= 50:
                raise ValueError("Handoff source cycle includes output run or exceeds 50 runs")
            manifest = completed_run(run.config.workspace, run_id)
            manifests[run_id] = manifest
            names[f"runs/{run_id}/manifest.json"] = sha256_file(
                run.config.workspace / f"runs/{run_id}/manifest.json"
            )
            names.update(manifest["artifacts"])
            pending.extend(manifest.get("source_runs", []))
            for key in ("demand_source", "choice_source"):
                parent = manifest.get(key, {}).get("model_run_id")
                if parent:
                    pending.append(parent)
        if not manifests:
            raise ValueError("At least one handoff source is required")
        source_root = Path(__file__).resolve().parents[3]
        files = [
            *source_root.glob("src/gsm_poc/**/*.py"),
            *source_root.glob("tests/**/*.py"),
            *source_root.glob("configs/*.toml"),
            *source_root.glob("configs/*.json"),
            *source_root.glob("configs/*.csv"),
            *source_root.glob("docs/**/*.md"),
            *source_root.glob("src/gsm_poc/**/*.css"),
            *source_root.glob("src/gsm_poc/ui/static/*.html"),
            *source_root.glob("src/gsm_poc/ui/static/*.js"),
        ]
        files.extend(
            source_root / name
            for name in ("README.md", "pyproject.toml", "uv.lock", ".python-version", "tokens.css")
            if (source_root / name).exists()
        )
        payload = {name: run.config.workspace / name for name in names}
        for path in files:
            relative = path.relative_to(source_root).as_posix()
            payload[relative] = path
            names[relative] = sha256_file(path)
        total = sum(path.stat().st_size for path in payload.values())
        if total > max_bytes or len(payload) > 10000:
            raise ValueError("Handoff exceeds the declared file/byte budget")
        for name, path in payload.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
                raise ValueError("Unsafe archive entry")
            if path.is_symlink():
                raise ValueError("Handoff cannot contain symlink artifacts")
        state.update(manifests=manifests, payload=payload, names=names, total=total)
        return {"source_runs": source_run_ids, "artifacts": names, "max_bytes": max_bytes}

    with run.stage("export_handoff", inputs) as execute:
        if execute:
            inventory = {
                "schema_version": 1,
                "source_runs": sorted(state["manifests"]),
                "files": state["names"],
                "uncompressed_bytes": state["total"],
                "evidence_level": "C",
                "gsm_readiness": "not_evaluated",
            }
            archive = run.path / "handoff.zip"
            instructions = (
                "# GSM Week 4–5 controlled handoff\n\n"
                "Synthetic evidence C; no GSM deployment or reviewer acceptance is implied.\n\n"
                "Extract into a new directory. Run `uv sync --locked`, then follow "
                "`docs/WEEK4_5.md` and each frozen policy/experiment spec. "
                "Existing runs belong to their recorded code/environment; use new run IDs.\n"
                "`handoff_inventory.json` lists SHA256 hashes of all payload files. "
                "Includes transitive source runs and registered generated data; "
                "historical missing training data is not recreated.\n"
            )
            with atomic_path(archive) as temporary:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
                    for name, path in sorted(state["payload"].items()):
                        data = path.read_bytes()
                        if hashlib.sha256(data).hexdigest() != state["names"][name]:
                            raise ValueError("Source changed during handoff export")
                        entry = zipfile.ZipInfo(name)
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        output.writestr(entry, data)
                    output.writestr("handoff_inventory.json", json.dumps(inventory, indent=2))
                    output.writestr("HANDOFF.md", instructions)
                with zipfile.ZipFile(temporary) as check:
                    if check.testzip() is not None:
                        raise ValueError("Handoff archive integrity check failed")
            result = {
                "schema_version": 1,
                "status": "completed",
                "inventory": inventory,
                "archive_sha256": sha256_file(archive),
                "archive": "handoff.zip",
            }
            path = run.path / "handoff.json"
            write_json(path, result)
            run.outputs("export_handoff", [archive, path])
    return read_json(run.path / "handoff.json")
