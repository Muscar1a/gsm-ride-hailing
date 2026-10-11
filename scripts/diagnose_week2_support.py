"""Audit frozen choice support and replay a scope selected from training counts only."""

from __future__ import annotations

import argparse
import dataclasses
from itertools import product
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from gsm_poc.causal.estimate import ModelBundle
from gsm_poc.causal.scenario import ScenarioRequest, _adjacent, joint_support, scenario
from gsm_poc.core.artifacts import (
    Run,
    completed_run,
    read_json,
    safe_id,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config

GROUP_COLUMNS = ["zone_id", "is_weekend", "is_peak"]


def training_scope(
    bundle: ModelBundle, request: ScenarioRequest, config: Config
) -> tuple[pd.DataFrame, dict]:
    """Freeze eligibility without consulting scenario contexts, outcomes or interval widths."""
    request.validate()
    support = bundle.train_support
    required_columns = GROUP_COLUMNS + ["multiplier_x", "multiplier_y"]
    if support.empty or not set(required_columns) <= set(support):
        raise ValueError("Training support is empty or missing required columns")
    if not np.isfinite(support[required_columns].to_numpy(float)).all():
        raise ValueError("Training support keys and price multipliers must be finite")
    baseline = np.array([request.baseline_multiplier_x, request.baseline_multiplier_y])
    target = baseline * (1 + np.array([request.delta_price_x, request.delta_price_y]))
    groups = support[GROUP_COLUMNS].drop_duplicates().sort_values(GROUP_COLUMNS)
    points = {"baseline": baseline, "target": target}
    rows = []
    for point_name, point in points.items():
        status, reasons = joint_support(bundle, groups, point, config)
        if status == "out_of_support" and "outside" in reasons[0]:
            raise ValueError(reasons[0])
        for x, y in product(_adjacent(point[0]), _adjacent(point[1])):
            selected = support[
                np.isclose(support.multiplier_x, x) & np.isclose(support.multiplier_y, y)
            ]
            counts = selected.groupby(GROUP_COLUMNS).size().rename("training_blocks")
            table = groups.merge(counts.reset_index(), on=GROUP_COLUMNS, how="left")
            table["training_blocks"] = table.training_blocks.fillna(0).astype(int)
            table["point"] = point_name
            table["multiplier_x"], table["multiplier_y"] = x, y
            table["minimum_blocks"] = config.model.min_price_cell_count
            table["corner_status"] = np.where(
                table.training_blocks == 0,
                "missing",
                np.where(
                    table.training_blocks < config.model.min_price_cell_count,
                    "insufficient",
                    "ok",
                ),
            )
            rows.append(table)
    counts_table = pd.concat(rows, ignore_index=True)
    decisions = []
    for group_values in groups.itertuples(index=False, name=None):
        context = pd.DataFrame([group_values], columns=pd.Index(GROUP_COLUMNS))
        reasons = []
        for point in points.values():
            status, point_reasons = joint_support(bundle, context, point, config)
            if status != "ok":
                reasons.extend(point_reasons)
        decisions.append(
            {
                **dict(zip(GROUP_COLUMNS, group_values, strict=True)),
                "eligible": not reasons,
                "reasons": reasons,
            }
        )
    scope = {
        "schema_version": 1,
        "selection_rule": "all training strata passing unchanged joint_support at both prices",
        "selection_inputs": "model_bundle.train_support and frozen training diagnostics only",
        "uses_test_outcomes": False,
        "uses_interval_widths": False,
        "request": dataclasses.asdict(request),
        "minimum_blocks": config.model.min_price_cell_count,
        "group_columns": GROUP_COLUMNS,
        "groups": decisions,
        "eligible_group_count": sum(1 for row in decisions if row["eligible"]),
        "training_group_count": len(decisions),
    }
    return counts_table, scope


def scope_contexts(contexts: pd.DataFrame, scope: dict) -> tuple[pd.DataFrame, dict]:
    """Apply the saved training rule; report excluded and unseen context denominators."""
    if not set(GROUP_COLUMNS + ["n_sessions"]) <= set(contexts):
        raise ValueError("Scenario contexts lack support keys or session weights")
    if not np.isfinite(contexts[GROUP_COLUMNS + ["n_sessions"]].to_numpy(float)).all():
        raise ValueError("Scenario context keys and session weights must be finite")
    if (contexts.n_sessions <= 0).any():
        raise ValueError("Scenario context session weights must be positive")
    decisions = pd.DataFrame(scope["groups"])
    marked = contexts.merge(
        decisions[GROUP_COLUMNS + ["eligible"]],
        on=GROUP_COLUMNS,
        how="left",
        validate="many_to_one",
    )
    unseen = marked.eligible.isna()
    retained = marked.eligible.eq(True)
    selected = marked.loc[retained, contexts.columns].copy()
    denominators = {
        "all_context_blocks": len(contexts),
        "all_context_weight_sessions": int(contexts.n_sessions.sum()),
        "retained_context_blocks": len(selected),
        "retained_context_weight_sessions": int(selected.n_sessions.sum()),
        "excluded_context_blocks": int((~retained).sum()),
        "excluded_context_weight_sessions": int(marked.loc[~retained, "n_sessions"].sum()),
        "unseen_training_group_context_blocks": int(unseen.sum()),
        "unseen_training_group_weight_sessions": int(marked.loc[unseen, "n_sessions"].sum()),
        "retained_session_fraction": (
            float(selected.n_sessions.sum() / contexts.n_sessions.sum()) if len(contexts) else 0.0
        ),
        "hypothetical_forecast_sessions": scope["request"]["n_sessions"],
        "forecast_population": "fixed hypothetical quote sessions within retained scope",
        "extrapolates_to_excluded_scope": False,
    }
    coverage = marked.assign(retained=retained.astype(int))
    grouped_coverage = []
    for group_key, group in coverage.groupby(["is_weekend", "is_peak"]):
        if not isinstance(group_key, tuple) or len(group_key) != 2:
            raise ValueError("Weekend/peak grouping must yield a pair of flags")
        weekend, peak = group_key
        grouped_coverage.append(
            {
                "is_weekend": int(weekend),
                "is_peak": int(peak),
                "all_context_blocks": len(group),
                "all_context_weight_sessions": int(group.n_sessions.sum()),
                "retained_context_blocks": int(group.retained.sum()),
                "retained_context_weight_sessions": int(
                    group.loc[group.retained.eq(1), "n_sessions"].sum()
                ),
            }
        )
    denominators["context_coverage_by_weekend_peak"] = grouped_coverage
    return selected, denominators


def diagnose_support(workspace: Path, model_run_id: str, run_id: str) -> dict:
    workspace = workspace.resolve()
    source = workspace / "runs" / safe_id(model_run_id)
    target = workspace / "runs" / safe_id(run_id)
    if target.exists():
        raise ValueError("Support diagnosis requires a new output run ID")
    manifest = completed_run(workspace, model_run_id)
    if manifest.get("stages", {}).get("freeze_choice", {}).get("status") != "succeeded":
        raise ValueError("Support diagnosis requires a completed freeze-choice package")
    config = Config.from_dict(manifest["choice_source"]["source_config"], workspace)
    estimator = config.model.scenario_estimator
    required_paths = [
        source / "current_scenario_result.json",
        source / "scenario_contexts.parquet",
        source / "choice_handoff.json",
        source / "models" / estimator / "model_bundle.joblib",
        source / "models" / estimator / "bootstrap_bundles.joblib",
    ]
    for path in required_paths:
        if path.relative_to(workspace).as_posix() not in manifest["artifacts"]:
            raise ValueError(f"Required artifact is not registered: {path.name}")
    input_hashes = dict(manifest["artifacts"])
    input_hashes[(source.relative_to(workspace) / "manifest.json").as_posix()] = sha256_file(
        source / "manifest.json"
    )
    current = read_json(required_paths[0])
    request = ScenarioRequest(**current["request"])
    bundle = joblib.load(required_paths[3])
    if (
        bundle.dataset_id != manifest["dataset_id"]
        or bundle.estimator != estimator
        or bundle.source_kind != manifest["source_kind"]
        or bundle.dgp_id != config.simulation.dgp
        or bundle.seed != config.simulation.seed
    ):
        raise ValueError("Model provenance differs from frozen package")
    run = Run(config, run_id)
    with run.stage("support_diagnostic", input_hashes):
        table, scope = training_scope(bundle, request, config)
        scope_path = run.path / "candidate_scope.json"
        table_path = run.path / "training_support.csv"
        write_json(scope_path, scope)
        write_frame(table_path, table)
        # Persist the training-only decision before opening any scenario contexts.
        contexts = pd.read_parquet(required_paths[1])
        selected, denominators = scope_contexts(contexts, read_json(scope_path))
        selected_path = run.path / "scoped_contexts.parquet"
        write_frame(selected_path, selected)
        draws = joblib.load(required_paths[4])
        all_result = scenario(bundle, contexts, request, config, run_id, draws)
        all_path = run.path / "all_scenario_result.json"
        write_json(all_path, all_result)
        scoped_path = run.path / "scoped_scenario_result.json"
        if selected.empty:
            scoped_result = {
                "run_id": run_id,
                "status": "unavailable",
                "support_status": "insufficient_support",
                "reasons": ["No scenario context passes the saved training-only support rule"],
                "interval_calibration_status": "not_evaluated_for_this_run",
            }
        else:
            scoped_request = dataclasses.replace(request, target_context_set="training_supported")
            scoped_result = scenario(bundle, selected, scoped_request, config, run_id, draws)
        write_json(scoped_path, scoped_result)
        unchanged_all = {key: value for key, value in all_result.items() if key != "run_id"} == {
            key: value for key, value in current.items() if key != "run_id"
        }
        if not unchanged_all:
            raise ValueError("All-context replay differs from frozen current scenario")
        for relative, expected in input_hashes.items():
            if sha256_file(workspace / relative) != expected:
                raise ValueError(f"Source changed during diagnosis: {relative}")
        report = {
            "schema_version": 1,
            "run_id": run_id,
            "source_package_run_id": model_run_id,
            "source_model_run_id": manifest["choice_source"]["model_run_id"],
            "dataset_id": bundle.dataset_id,
            "source_kind": bundle.source_kind,
            "evidence_level": "C",
            "estimator": estimator,
            "source_environment": manifest["choice_source"]["source_environment"],
            "diagnostic_environment": run.manifest["environment"],
            "diagnostic_script_sha256": sha256_file(Path(__file__)),
            "source_artifacts_sha256": input_hashes,
            "source_bytes_unchanged": True,
            "all_context_replay_matches_frozen_current_result": unchanged_all,
            "all_context_status": all_result["status"],
            "scoped_status": scoped_result["status"],
            "scoped_support_status": scoped_result.get("support_status", scoped_result["status"]),
            "candidate_scope_sha256": sha256_file(scope_path),
            "eligible_training_groups": scope["eligible_group_count"],
            "all_training_groups": scope["training_group_count"],
            "denominators": denominators,
            "interval_calibration_status": "not_validated_by_support_diagnosis",
            "limitation": "Restricted-scope semi-synthetic replay; no GSM or CI calibration claim",
        }
        report_path = run.path / "support_diagnostic.json"
        write_json(report_path, report)
        run.manifest.update(dataset_id=bundle.dataset_id, source_kind=bundle.source_kind)
        run.outputs(
            "support_diagnostic",
            [scope_path, table_path, selected_path, all_path, scoped_path, report_path],
            **denominators,
        )
    run.complete()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--model-run-id", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    report = diagnose_support(args.workspace, args.model_run_id, args.run_id)
    print(f"Support: {report['all_context_status']} -> {report['scoped_status']}")
    print(f"Artifacts: {args.workspace / 'runs' / args.run_id}")


if __name__ == "__main__":
    main()
