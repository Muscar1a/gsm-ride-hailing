"""Bounded fresh-seed DML/OLS pilot of individual day-jackknife Wald-t intervals.

No bootstrap, selected production method or final calibration evidence is produced.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import time
from pathlib import Path

if __name__ == "__main__":
    for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[thread_variable] = "1"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gsm_poc.causal.estimate import fit_all  # noqa: E402
from gsm_poc.causal.evaluate import aggregate_metrics  # noqa: E402
from gsm_poc.causal.features import date_splits, day_folds  # noqa: E402
from gsm_poc.core.artifacts import (  # noqa: E402
    environment,
    fingerprint,
    freeze_artifacts,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config  # noqa: E402
from gsm_poc.simulation.dgp import TRUE_THETA, generate  # noqa: E402
from scripts.compare_week2_intervals import coefficients, day_jackknife  # noqa: E402
from scripts.compare_week2_variance import (  # noqa: E402
    variance_diagnostics,
    variance_rows,
    verify_comparison,
    verify_hashes,
)
from scripts.diagnose_week2_intervals import GROUP_COLUMNS  # noqa: E402

ESTIMATORS = ("adjusted_ols", "dml")
FRESH_SEEDS = set(range(43001, 43006))


def validate_pilot(seed_start: int, seeds: int, dgps: list[str]) -> list[int]:
    if type(seed_start) is not int or type(seeds) is not int or not 1 <= seeds <= 5:
        raise ValueError("Pilot requires one to five integer seeds")
    selected = list(range(seed_start, seed_start + seeds))
    if not set(selected) <= FRESH_SEEDS:
        raise ValueError("Only fresh development seeds 43001 through 43005 are allowed")
    if not dgps or len(set(dgps)) != len(dgps) or not set(dgps) <= {"RCT_SYN", "NULL_EFFECT"}:
        raise ValueError("Pilot DGPs must be unique RCT_SYN and/or NULL_EFFECT")
    return selected


def fold_record(train: pd.DataFrame, config: Config) -> list[dict]:
    return [
        {
            "fold": index,
            "train_original_days": sorted(set(train.original_day_id.iloc[left])),
            "validation_original_days": sorted(set(train.original_day_id.iloc[right])),
        }
        for index, (left, right) in enumerate(day_folds(train, config.model.folds))
    ]


def paired_estimators(metrics: pd.DataFrame) -> pd.DataFrame:
    records = []
    for key, group in metrics.groupby(["dgp_id", "outcome", "treatment"]):
        if not isinstance(key, tuple) or len(key) != 3:
            raise ValueError("Expected DGP/outcome/treatment group")
        paired = group.loc[group.estimator.eq("dml")].merge(
            group.loc[group.estimator.eq("adjusted_ols")],
            on="seed",
            suffixes=("_dml", "_ols"),
            validate="one_to_one",
        )
        points = paired.loc[paired.theta_dml.notna() & paired.theta_ols.notna()]
        intervals = paired.loc[paired.interval_available_dml & paired.interval_available_ols]
        valid_width = intervals.loc[intervals.interval_width_ols.gt(0)]
        dml_covered, ols_covered = (
            intervals.covered_dml.astype(bool),
            intervals.covered_ols.astype(bool),
        )
        records.append(
            {
                "dgp_id": key[0],
                "outcome": key[1],
                "treatment": key[2],
                "paired_point_seeds": len(points),
                "paired_available_intervals": len(intervals),
                "mean_paired_error_difference_dml_minus_ols": float(
                    (points.error_dml - points.error_ols).mean()
                )
                if len(points)
                else None,
                "paired_coverage_change_dml_minus_ols": float(
                    (dml_covered.astype(int) - ols_covered.astype(int)).mean()
                )
                if len(intervals)
                else None,
                "paired_coverage_gains_dml": int((dml_covered & ~ols_covered).sum()),
                "paired_coverage_losses_dml": int((~dml_covered & ols_covered).sum()),
                "width_ratio_denominator": len(valid_width),
                "mean_paired_width_ratio_dml_over_ols": float(
                    (valid_width.interval_width_dml / valid_width.interval_width_ols).mean()
                )
                if len(valid_width)
                else None,
                "development_only": True,
                "interval_method": "day_jackknife_t",
            }
        )
    return pd.DataFrame(records)


def run_pilot(
    comparison_root: Path,
    output_root: Path,
    seed_start: int,
    seeds: int,
    dgps: list[str],
    workspace: Path | None = None,
) -> dict:
    selected = validate_pilot(seed_start, seeds, dgps)
    comparison_root, output_root = comparison_root.resolve(), output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"Pilot output already exists: {output_root}")
    source, source_status = verify_comparison(comparison_root)
    workspace = workspace or Path(__file__).resolve().parents[1]
    config = Config.from_dict(source["source_config"], workspace)
    if not set(ESTIMATORS) <= set(config.model.estimators):
        raise ValueError("Source configuration must include both adjusted_ols and dml")
    runtime = environment(workspace)
    for key in ("python", "packages", "source_code_sha256", "lock_sha256"):
        if runtime[key] != source["environment"][key]:
            raise ValueError(f"Source comparison differs from current {key}")
    start, end = (
        dt.date.fromisoformat(config.source.start),
        dt.date.fromisoformat(config.source.train_end),
    )
    days = {(start + dt.timedelta(days=offset)).isoformat() for offset in range((end - start).days)}
    if len(days) != 20:
        raise ValueError("Pilot requires exactly 20 original training days")
    diagnostic_root = Path(source["diagnostic_root"])
    diagnostic_protocol = read_json(diagnostic_root / "protocol.json")
    context_root = diagnostic_root / "source_context"
    metadata = read_json(context_root / "context_templates.json")
    if (
        metadata.get("fit_start") != config.source.start
        or metadata.get("fit_end_exclusive") != config.source.train_end
        or metadata.get("context_version") != diagnostic_protocol["context_version"]
    ):
        raise ValueError("Frozen context metadata differs from training source configuration")
    identities = {
        **source_status["artifacts"],
        "status.json": sha256_file(comparison_root / "status.json"),
    }
    helper_hashes = {
        name: sha256_file(Path(__file__).with_name(name))
        for name in (
            "compare_week2_intervals.py",
            "compare_week2_variance.py",
            "diagnose_week2_intervals.py",
        )
    }
    if helper_hashes["compare_week2_intervals.py"] != source["script_sha256"]:
        raise ValueError("Comparison helper differs from frozen source controller")
    jobs = len(selected) * len(dgps) * len(ESTIMATORS)
    protocol = {
        "schema_version": 1,
        "purpose": "fresh development DML/OLS variance pilot; no promotion",
        "development_only": True,
        "source_comparison_root": str(comparison_root),
        "source_protocol_hash": source["protocol_hash"],
        "source_artifact_sha256": identities,
        "source_diagnostic_root": str(diagnostic_root),
        "source_diagnostic_sha256": source["source_artifact_sha256"],
        "source_config": config.as_dict(),
        "environment": runtime,
        "script_sha256": sha256_file(Path(__file__)),
        "helper_sha256": helper_hashes,
        "context_version": metadata["context_version"],
        "context_sha256": diagnostic_protocol["context_sha256"],
        "seeds": selected,
        "dgps": dgps,
        "estimators": list(ESTIMATORS),
        "interval_method": "day_jackknife_t",
        "interval_level": config.evaluation.interval_level,
        "original_training_days": sorted(days),
        "maximum_estimator_jobs": jobs,
        "maximum_point_fits": jobs,
        "maximum_jackknife_fits": jobs * 20,
        "maximum_total_fits": jobs * 21,
        "maximum_bootstrap_fits": 0,
        "formula": "theta_full +/- t(G-1,(1+level)/2)*sqrt((G-1)/G*sum((theta_-g-mean_jack)^2))",
        "point_gate": "fit_all singleton: identified finite point and existing validation gate",
        "limits": "Theta only; generic Wald-t, no DML guarantee; omission rebuilds folds",
        "native_threads": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
    }
    protocol["protocol_hash"] = fingerprint(protocol)
    output_root.mkdir(parents=True, exist_ok=False)
    write_json(output_root / "protocol.json", protocol)
    (output_root / "runner_source.py").write_bytes(Path(__file__).read_bytes())
    freeze_artifacts(context_root, output_root / "source_context", protocol["context_sha256"])
    started, all_rows, states = time.perf_counter(), [], []
    progress = {
        "status": "running",
        "protocol_hash": protocol["protocol_hash"],
        "expected_estimator_jobs": jobs,
        "completed_estimator_jobs": 0,
        "point_attempted": 0,
        "point_successful": 0,
        "point_failed": 0,
        "jackknife_attempted": 0,
        "jackknife_successful": 0,
        "jackknife_failed": 0,
        "jackknife_not_attempted": 0,
        "bootstrap_attempted": 0,
    }
    write_json(output_root / "status.json", progress)
    try:
        context = pd.read_parquet(output_root / "source_context/context_templates.parquet")
        for dgp in dgps:
            for seed in selected:
                verify_hashes(comparison_root, identities)
                verify_hashes(diagnostic_root, protocol["source_diagnostic_sha256"])
                if environment(workspace) != runtime:
                    raise ValueError("Source code or environment changed during pilot")
                seed_config = dataclasses.replace(
                    config, simulation=dataclasses.replace(config.simulation, dgp=dgp, seed=seed)
                )
                data = generate(seed_config, context, metadata["context_version"])
                splits = date_splits(data.blocks, seed_config)
                train = splits["train"]
                if set(train.original_day_id) != days:
                    raise ValueError("Generated training days differ from frozen pilot")
                for estimator in ESTIMATORS:
                    job_start, name = time.perf_counter(), f"{dgp}-{seed}-{estimator}"
                    print(f"pilot: {name}, 1 point + 20 original-day omissions", flush=True)
                    method_config = dataclasses.replace(
                        seed_config,
                        model=dataclasses.replace(
                            seed_config.model, estimators=(estimator,), scenario_estimator=estimator
                        ),
                    )
                    error, diagnostic, point = None, {}, None
                    try:
                        results, _ = fit_all(data.blocks, method_config)
                        diagnostic = results[estimator].diagnostics
                        point = coefficients(results[estimator])
                    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                        error = {"error_type": type(exc).__name__, "error": str(exc)}
                    baseline = pd.DataFrame(
                        [
                            {
                                "dgp_id": dgp,
                                "seed": seed,
                                "dataset_id": data.dataset_id,
                                "estimator": estimator,
                                "outcome": outcome,
                                "treatment": treatment,
                                "source_kind": data.metadata["source_kind"],
                                "evidence_level": "C",
                                "theta": float(point[index]) if point is not None else None,
                                "status": "ok" if point is not None else "failed",
                                "error_type": error["error_type"] if error else None,
                                "error_message": error["error"] if error else None,
                                "requested_draws": 0,
                                "successful_draws": 0,
                                "bootstrap_failed_draws": 0,
                                "bootstrap_not_attempted_draws": 0,
                                "source_interval_status": "not_applicable",
                                "scenario_probability_rmse": None,
                                "development_only": True,
                                "interval_scope": "individual theta only",
                                "interval_calibration_status": "not_final_calibration",
                            }
                            for index, (outcome, treatment) in enumerate(
                                (x, y) for x in ("X", "Y") for y in ("X", "Y")
                            )
                        ]
                    )
                    jackknife = (
                        day_jackknife(train, method_config, estimator)
                        if point is not None
                        else pd.DataFrame(
                            [
                                {
                                    "omitted_original_day_id": day,
                                    "status": "not_attempted",
                                    "error": "point_fit_failed",
                                }
                                for day in sorted(days)
                            ]
                        )
                    )
                    rows = variance_rows(
                        baseline, jackknife, days, config.evaluation.interval_level
                    )
                    # Fixed DGP truth is consulted only after the candidate bounds are complete.
                    truth = np.zeros((2, 2)) if dgp == "NULL_EFFECT" else TRUE_THETA
                    for row in rows:
                        target = float(
                            truth[
                                ("X", "Y").index(row["outcome"]), ("X", "Y").index(row["treatment"])
                            ]
                        )
                        low, high = row["theta_lower"], row["theta_upper"]
                        row.update(
                            true_theta=target,
                            error=row["theta"] - target if row["theta"] is not None else None,
                            covered=low <= target <= high if low is not None else None,
                            false_positive=not (low <= 0 <= high)
                            if low is not None and target == 0
                            else None,
                            bootstrap_counts_role="not_applicable; no bootstrap attempted",
                        )
                    paths = [
                        output_root / f"{name}-{suffix}.parquet"
                        for suffix in ("point", "jackknife", "metrics")
                    ]
                    for path, frame in zip(
                        paths, (baseline, jackknife, pd.DataFrame(rows)), strict=True
                    ):
                        write_frame(path, frame)
                    folds = (
                        {
                            "full": fold_record(train, method_config),
                            "omissions": {
                                day: fold_record(
                                    train.loc[train.original_day_id.ne(day)], method_config
                                )
                                for day in sorted(days)
                            },
                        }
                        if estimator == "dml"
                        else None
                    )
                    state = {
                        "dgp_id": dgp,
                        "seed": seed,
                        "estimator": estimator,
                        "dataset_id": data.dataset_id,
                        "status": "succeeded"
                        if point is not None and jackknife.status.eq("succeeded").all()
                        else "failed",
                        "point_successful": point is not None,
                        "point_error": error,
                        "point_diagnostics": diagnostic,
                        "jackknife_successful": int(jackknife.status.eq("succeeded").sum()),
                        "jackknife_failed": int(jackknife.status.eq("failed").sum()),
                        "jackknife_not_attempted": int(jackknife.status.eq("not_attempted").sum()),
                        "splits": {
                            key: {"blocks": len(part), "days": sorted(set(part.day_id))}
                            for key, part in splits.items()
                        },
                        "day_folds": folds,
                        "fold_record_scope": "plan; fit statuses identify executed omissions",
                        "duration_seconds": time.perf_counter() - job_start,
                        "artifacts": {path.name: sha256_file(path) for path in paths},
                    }
                    write_json(output_root / f"{name}.json", state)
                    all_rows.extend(rows)
                    states.append(state)
                    progress.update(
                        completed_estimator_jobs=len(states),
                        point_attempted=len(states),
                        point_successful=sum(item["point_successful"] for item in states),
                        point_failed=sum(not item["point_successful"] for item in states),
                        **{
                            f"jackknife_{kind}": sum(item[f"jackknife_{kind}"] for item in states)
                            for kind in ("successful", "failed", "not_attempted")
                        },
                        duration_seconds=time.perf_counter() - started,
                    )
                    progress["jackknife_attempted"] = (
                        progress["jackknife_successful"] + progress["jackknife_failed"]
                    )
                    write_json(output_root / "status.json", progress)
                    write_frame(output_root / "seed_metrics.parquet", pd.DataFrame(all_rows))
                    print(
                        f"done: {name}, {state['duration_seconds']:.2f}s, {state['status']}",
                        flush=True,
                    )
        metrics = pd.DataFrame(all_rows)
        summary = aggregate_metrics(metrics, len(selected))
        summary["interval_method"] = "day_jackknife_t"
        summary["development_only"] = True
        summary = summary.merge(
            variance_diagnostics(metrics),
            on=[*GROUP_COLUMNS, "interval_method"],
            validate="one_to_one",
        )
        counts = (
            metrics.groupby(GROUP_COLUMNS)
            .agg(
                available_intervals=("interval_available", "sum"),
                unavailable_intervals=("interval_available", lambda values: int((~values).sum())),
                mean_interval_width=("interval_width", "mean"),
            )
            .reset_index()
        )
        summary = summary.merge(counts, on=GROUP_COLUMNS, validate="one_to_one")
        write_frame(output_root / "summary.csv", summary)
        write_frame(output_root / "paired_estimators.csv", paired_estimators(metrics))
        verify_hashes(comparison_root, identities)
        verify_hashes(diagnostic_root, protocol["source_diagnostic_sha256"])
        verify_hashes(output_root / "source_context", protocol["context_sha256"])
        if (
            environment(workspace) != runtime
            or sha256_file(Path(__file__)) != protocol["script_sha256"]
        ):
            raise ValueError("Code or environment changed during pilot")
        verify_hashes(Path(__file__).parent, helper_hashes)
    except Exception as exc:
        progress.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        write_json(output_root / "status.json", progress)
        raise
    progress.update(
        status="completed"
        if all(state["status"] == "succeeded" for state in states)
        else "completed_with_failures",
        unavailable_intervals=int((~metrics.interval_available).sum()),
        interpretation="fresh development only; no final calibration or method promotion",
        artifacts={
            path.relative_to(output_root).as_posix(): sha256_file(path)
            for path in output_root.rglob("*")
            if path.is_file() and path.name != "status.json"
        },
    )
    write_json(output_root / "status.json", progress)
    return progress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--seed-start", type=int, default=43001)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--dgps", nargs="+", default=["RCT_SYN", "NULL_EFFECT"])
    args = parser.parse_args(argv)
    run_pilot(args.comparison_root, args.output_root, args.seed_start, args.seeds, args.dgps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
