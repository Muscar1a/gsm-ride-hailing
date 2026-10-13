"""Bounded development diagnosis of the existing individual day-bootstrap intervals.

This keeps fitting and interval formulas unchanged. Fresh development seeds and
raw coefficient draws diagnose variability; they are not final calibration evidence.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import time
from pathlib import Path

if __name__ == "__main__":
    for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[thread_variable] = "1"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gsm_poc.causal.estimate import fit_all  # noqa: E402
from gsm_poc.causal.evaluate import (  # noqa: E402
    _failed_method_rows,
    aggregate_metrics,
    method_metrics,
)
from gsm_poc.causal.features import date_splits  # noqa: E402
from gsm_poc.causal.uncertainty import bootstrap, percentile_interval  # noqa: E402
from gsm_poc.core.artifacts import (  # noqa: E402
    code_hash,
    environment,
    fingerprint,
    freeze_artifacts,
    read_json,
    sha256_file,
    utc_now,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config  # noqa: E402
from gsm_poc.simulation.dgp import generate  # noqa: E402

DEVELOPMENT_DGPS = ("RCT_SYN", "NULL_EFFECT")
RESERVED_SEEDS = {19001, *range(20001, 20101)}
GROUP_COLUMNS = ["dgp_id", "estimator", "outcome", "treatment"]


def validate_protocol(
    config: Config, seeds: list[int], dgps: list[str], estimators: list[str], draws: int
) -> None:
    if not 1 <= len(seeds) <= 50 or len(set(seeds)) != len(seeds):
        raise ValueError("Development seeds must be unique, with between one and 50 seeds")
    if any(type(seed) is not int or seed < 0 or seed in RESERVED_SEEDS for seed in seeds):
        raise ValueError("Seeds must be nonnegative integers outside historical probe/final seeds")
    if not dgps or len(set(dgps)) != len(dgps) or not set(dgps) <= set(DEVELOPMENT_DGPS):
        raise ValueError("Development DGPs must be unique RCT_SYN and/or NULL_EFFECT")
    if (
        not estimators
        or len(set(estimators)) != len(estimators)
        or not set(estimators) <= set(config.model.estimators)
    ):
        raise ValueError("Estimators must be unique selections from the source configuration")
    if type(draws) is not int or not 2 <= draws <= 1999:
        raise ValueError("Development bootstrap_draws must be between two and 1999")


def verify_sources(source_dir: Path, checksums: dict[str, str]) -> None:
    for name, expected in checksums.items():
        path = source_dir / name
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"Source checksum mismatch: {path}")


def summarize_diagnostics(metrics: pd.DataFrame, expected_seeds: int) -> pd.DataFrame:
    """Use actual within-seed sample SD, never width divided by a normal quantile."""
    if metrics.duplicated([*GROUP_COLUMNS, "seed"]).any():
        raise ValueError("Duplicate development seed/effect metric")
    summary = aggregate_metrics(metrics, expected_seeds)
    diagnostic_rows = []
    for group_key, group in metrics.groupby(GROUP_COLUMNS):
        if not isinstance(group_key, tuple) or len(group_key) != len(GROUP_COLUMNS):
            raise ValueError("Expected a four-column diagnostic group key")
        estimates = group.theta.dropna().astype(float)
        standard_deviations = group.bootstrap_sd.dropna().astype(float)
        empirical_sd = float(estimates.std(ddof=1)) if len(estimates) > 1 else None
        rms_bootstrap_sd = (
            float(np.sqrt(np.mean(standard_deviations**2))) if len(standard_deviations) else None
        )
        estimate_seeds = set(group.loc[group.theta.notna(), "seed"])
        bootstrap_seeds = set(group.loc[group.bootstrap_sd.notna(), "seed"])
        comparison_status = (
            "unmatched_seed_cohorts"
            if estimate_seeds != bootstrap_seeds
            else "insufficient_replicates"
            if empirical_sd is None
            else "zero_variance"
            if empirical_sd == 0
            else "comparable"
        )
        diagnostic_rows.append(
            {
                **dict(zip(GROUP_COLUMNS, group_key, strict=True)),
                "empirical_estimate_sd": empirical_sd,
                "mean_bootstrap_sd": float(standard_deviations.mean())
                if len(standard_deviations)
                else None,
                "rms_bootstrap_sd": rms_bootstrap_sd,
                "bootstrap_to_empirical_sd_ratio": rms_bootstrap_sd / empirical_sd
                if comparison_status == "comparable"
                and empirical_sd
                and rms_bootstrap_sd is not None
                else None,
                "sd_comparison_status": comparison_status,
                "bootstrap_sd_denominator": len(standard_deviations),
                "mean_interval_width": float(group.interval_width.dropna().mean())
                if group.interval_width.notna().any()
                else None,
                "miss_interval_below_truth": int(group.miss_interval_below_truth.dropna().sum()),
                "miss_interval_above_truth": int(group.miss_interval_above_truth.dropna().sum()),
                "unstable_intervals": int(group.interval_status.ne("ok").sum()),
                "failed_bootstrap_draws": int(group.bootstrap_failed_draws.sum()),
                "not_attempted_bootstrap_draws": int(group.bootstrap_not_attempted_draws.sum()),
                "development_only": True,
            }
        )
    return summary.merge(pd.DataFrame(diagnostic_rows), on=GROUP_COLUMNS, validate="one_to_one")


def add_draw_diagnostics(rows: list[dict], records: list[dict], level: float) -> list[dict]:
    for row in rows:
        column = f"theta_{row['outcome'].lower()}{row['treatment'].lower()}"
        values = np.array(
            [
                record[column]
                for record in records
                if record["status"] == "succeeded" and column in record
            ],
            dtype=float,
        )
        row.update(
            theta=row.get("theta"),
            bootstrap_attempted_draws=len(records),
            bootstrap_failed_draws=sum(record["status"] != "succeeded" for record in records),
            bootstrap_not_attempted_draws=row["requested_draws"] - len(records),
            bootstrap_sd=float(values.std(ddof=1)) if len(values) > 1 else None,
            interval_width=None,
            miss_interval_below_truth=None,
            miss_interval_above_truth=None,
            prefix_199_lower=None,
            prefix_199_upper=None,
            prefix_199_successful_draws=sum(
                record["status"] == "succeeded" and column in record for record in records[:199]
            ),
            lower_endpoint_change_from_199=None,
            upper_endpoint_change_from_199=None,
        )
        if row.get("theta_lower") is not None:
            low, high, truth = row["theta_lower"], row["theta_upper"], row["true_theta"]
            row.update(
                interval_width=high - low,
                miss_interval_below_truth=high < truth,
                miss_interval_above_truth=low > truth,
            )
            if len(records) > 199:
                prefix = np.array(
                    [
                        record[column]
                        for record in records[:199]
                        if record["status"] == "succeeded" and column in record
                    ]
                )
                if len(prefix) >= 2:
                    prefix_low, prefix_high = percentile_interval(prefix, level)
                    row.update(
                        prefix_199_lower=float(prefix_low),
                        prefix_199_upper=float(prefix_high),
                        lower_endpoint_change_from_199=float(low - prefix_low),
                        upper_endpoint_change_from_199=float(high - prefix_high),
                    )
    return rows


def run_diagnostic(
    config: Config,
    context_root: Path,
    output_root: Path,
    seeds: list[int],
    dgps: list[str],
    estimators: list[str],
    draws: int,
) -> dict:
    validate_protocol(config, seeds, dgps, estimators, draws)
    context_root, output_root = context_root.resolve(), output_root.resolve()
    metadata = read_json(context_root / "context_templates.json")
    if (
        metadata.get("fit_start") != config.source.start
        or metadata.get("fit_end_exclusive") != config.source.train_end
    ):
        raise ValueError("Context templates must be fitted on the source training dates")
    checksums = {
        name: sha256_file(context_root / name)
        for name in ("context_templates.parquet", "context_templates.json")
    }
    runtime = environment(config.workspace)
    script_sha = sha256_file(Path(__file__))
    protocol = {
        "schema_version": 1,
        "purpose": "development diagnosis; existing method unchanged; not final calibration",
        "source_config": config.as_dict(),
        "environment": runtime,
        "script_sha256": script_sha,
        "context_root": str(context_root),
        "context_sha256": checksums,
        "context_version": metadata["context_version"],
        "seeds": seeds,
        "dgps": dgps,
        "estimators": estimators,
        "bootstrap_draws": draws,
        "reserved_seeds": sorted(RESERVED_SEEDS),
        "interval_kind": "day-bootstrap percentile; individual intervals",
        "interval_level": config.evaluation.interval_level,
        "reporting_min_draws": config.evaluation.reporting_min_draws,
        "maximum_estimator_jobs": len(seeds) * len(dgps) * len(estimators),
        "maximum_bootstrap_refits": len(seeds) * len(dgps) * len(estimators) * draws,
        "native_threads": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "nested_draw_comparison": "same RNG prefix: first 199 requested draws vs all"
        if draws > 199
        else "not_requested",
    }
    protocol["protocol_hash"] = fingerprint(protocol)
    # Refuse existing directories: no stale checkpoints or incompatible results are reused.
    output_root.mkdir(parents=True, exist_ok=False)
    write_json(output_root / "protocol.json", protocol)
    frozen_context = output_root / "source_context"
    freeze_artifacts(context_root, frozen_context, checksums)
    verify_sources(frozen_context, checksums)
    context = pd.read_parquet(frozen_context / "context_templates.parquet")
    all_rows, states = [], []
    started = time.perf_counter()
    try:
        for dgp in dgps:
            for seed in seeds:
                verify_sources(context_root, checksums)
                if code_hash(config.workspace) != runtime["source_code_sha256"]:
                    raise ValueError("Source code changed during diagnostic; start a new run")
                seed_config = dataclasses.replace(
                    config,
                    simulation=dataclasses.replace(config.simulation, seed=seed, dgp=dgp),
                    evaluation=dataclasses.replace(config.evaluation, bootstrap_draws=draws),
                )
                data = generate(seed_config, context, metadata["context_version"])
                splits = date_splits(data.blocks, seed_config)
                for estimator in estimators:
                    job_start = time.perf_counter()
                    name = f"{dgp}-{seed}-{estimator}"
                    print(f"diagnose: {name}, {draws} requested draws", flush=True)
                    method_config = dataclasses.replace(
                        seed_config,
                        model=dataclasses.replace(
                            seed_config.model, estimators=(estimator,), scenario_estimator=estimator
                        ),
                    )
                    state = {
                        "dgp_id": dgp,
                        "seed": seed,
                        "estimator": estimator,
                        "dataset_id": data.dataset_id,
                        "generated_metadata": data.metadata,
                        "splits": {
                            key: {"blocks": len(value), "days": sorted(set(value.day_id))}
                            for key, value in splits.items()
                        },
                    }
                    records = []
                    try:
                        results, _ = fit_all(data.blocks, method_config)
                        result = results[estimator]
                        sampled = (
                            bootstrap(splits["train"], method_config, estimator)
                            if result.bundle is not None
                            else None
                        )
                        records = sampled.records if sampled else []
                        rows = method_metrics(
                            result, sampled, data, method_config, output_root.name
                        )
                        state.update(
                            status="succeeded",
                            diagnostics=result.diagnostics,
                            bootstrap_stability=sampled.stability if sampled else None,
                        )
                    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                        rows = _failed_method_rows(
                            method_config,
                            output_root.name,
                            estimator,
                            data.metadata["source_kind"],
                            exc,
                        )
                        for row in rows:
                            row["successful_draws"] = sum(
                                record["status"] == "succeeded" for record in records
                            )
                        state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
                    rows = add_draw_diagnostics(rows, records, config.evaluation.interval_level)
                    paths = [
                        output_root / f"{name}-metrics.parquet",
                        output_root / f"{name}-draws.parquet",
                    ]
                    write_frame(paths[0], pd.DataFrame(rows))
                    raw_records = [
                        {
                            key: value
                            for key, value in record.items()
                            if key not in ("baseline_coefficients", "baseline_intercepts")
                        }
                        for record in records
                    ]
                    write_frame(
                        paths[1],
                        pd.DataFrame(raw_records)
                        if records
                        else pd.DataFrame({"draw_id": [], "status": []}),
                    )
                    state.update(
                        duration_seconds=time.perf_counter() - job_start,
                        artifacts={path.name: sha256_file(path) for path in paths},
                    )
                    write_json(output_root / f"{name}.json", state)
                    all_rows.extend(rows)
                    states.append(state)
                    metrics = pd.DataFrame(all_rows)
                    write_frame(output_root / "seed_metrics.parquet", metrics)
                    write_frame(
                        output_root / "summary.csv", summarize_diagnostics(metrics, len(seeds))
                    )
                    print(
                        f"done: {name}, {state['duration_seconds']:.2f}s, {state['status']}",
                        flush=True,
                    )
        verify_sources(context_root, checksums)
        if (
            code_hash(config.workspace) != runtime["source_code_sha256"]
            or sha256_file(Path(__file__)) != script_sha
        ):
            raise ValueError("Code changed during diagnostic; results do not match frozen protocol")
    except Exception as exc:
        write_json(
            output_root / "status.json",
            {
                "status": "failed",
                "protocol_hash": protocol["protocol_hash"],
                "error_type": type(exc).__name__,
                "error": str(exc),
                "completed_estimator_jobs": len(states),
                "duration_seconds": time.perf_counter() - started,
            },
        )
        raise
    status = {
        "status": "completed"
        if all(state["status"] == "succeeded" for state in states)
        else "completed_with_failures",
        "completed_at": utc_now(),
        "protocol_hash": protocol["protocol_hash"],
        "completed_estimator_jobs": len(states),
        "duration_seconds": time.perf_counter() - started,
        "interpretation": "development pilot; no method change or empirical calibration acceptance",
    }
    status["artifacts"] = {
        path.relative_to(output_root).as_posix(): sha256_file(path)
        for path in output_root.rglob("*")
        if path.is_file()
    }
    write_json(output_root / "status.json", status)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.toml"))
    parser.add_argument("--build-id", default="214dd5a1184bd3705e66")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--seed-start", required=True, type=int)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--dgps", nargs="+", default=["RCT_SYN"])
    parser.add_argument("--estimators", nargs="+", default=["adjusted_ols"])
    parser.add_argument("--bootstrap-draws", type=int, default=199)
    args = parser.parse_args(argv)
    config = Config.load(args.config)
    run_diagnostic(
        config,
        config.workspace / "data/gold" / args.build_id,
        args.output_root,
        list(range(args.seed_start, args.seed_start + args.seeds)),
        args.dgps,
        args.estimators,
        args.bootstrap_draws,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
