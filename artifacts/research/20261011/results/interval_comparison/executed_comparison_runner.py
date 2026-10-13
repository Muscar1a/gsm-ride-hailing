"""Paired development comparison of saved percentile, basic and BCa theta intervals.

Run with ``python -m scripts.compare_week2_intervals``. No production method is
selected or changed; the development comparison is not final calibration.
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
from scipy.stats import norm  # noqa: E402

from gsm_poc.causal.estimate import FitResult, fit_all, fit_estimator  # noqa: E402
from gsm_poc.causal.evaluate import aggregate_metrics  # noqa: E402
from gsm_poc.causal.features import date_splits  # noqa: E402
from gsm_poc.causal.uncertainty import percentile_interval  # noqa: E402
from gsm_poc.core.artifacts import (  # noqa: E402
    code_hash,
    environment,
    fingerprint,
    read_json,
    sha256_file,
    utc_now,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config  # noqa: E402
from gsm_poc.simulation.dgp import generate  # noqa: E402
from scripts.diagnose_week2_intervals import GROUP_COLUMNS, validate_protocol  # noqa: E402

INTERVAL_METHODS = ("percentile", "basic", "bca")
COEFFICIENT_COLUMNS = ("theta_xx", "theta_xy", "theta_yx", "theta_yy")


def calculate_intervals(
    point: float, draws: np.ndarray, jackknife: np.ndarray, level: float
) -> dict[str, dict]:
    """Interval mathematics uses estimates only, with no oracle or outcome labels."""
    draws, jackknife = np.asarray(draws, dtype=float), np.asarray(jackknife, dtype=float)
    if not np.isfinite(point) or not 0 < level < 1:
        raise ValueError("Point must be finite and interval level strictly between zero and one")
    if draws.ndim != 1 or len(draws) < 2 or not np.isfinite(draws).all():
        raise ValueError("At least two finite scalar bootstrap estimates are required")
    low, high = percentile_interval(draws, level)
    if not np.isfinite([low, high, 2 * point - high, 2 * point - low]).all():
        raise ValueError("Interval calculation produced nonfinite bounds")
    results = {
        "percentile": {"lower": float(low), "upper": float(high), "reason": None},
        "basic": {
            "lower": float(2 * point - high),
            "upper": float(2 * point - low),
            "reason": None,
        },
        "bca": {
            "lower": None,
            "upper": None,
            "reason": None,
            "bias_correction_z0": None,
            "acceleration": None,
            "adjusted_lower_probability": None,
            "adjusted_upper_probability": None,
        },
    }
    bca = results["bca"]
    if jackknife.ndim != 1 or len(jackknife) < 3 or not np.isfinite(jackknife).all():
        bca["reason"] = "failed_or_incomplete_jackknife"
        return results
    delta = jackknife.mean() - jackknife
    sum_squares = float(np.sum(delta**2))
    if not np.isfinite(sum_squares):
        bca["reason"] = "nonfinite_bias_correction_or_acceleration"
        return results
    if sum_squares == 0 or np.ptp(draws) == 0:
        bca["reason"] = "degenerate_distribution"
        return results
    acceleration = float(np.sum(delta**3) / (6 * sum_squares**1.5))
    rank = float((np.sum(draws < point) + np.sum(draws <= point)) / (2 * len(draws)))
    z0 = float(norm.ppf(rank))
    bca["acceleration"] = acceleration if np.isfinite(acceleration) else None
    if not np.isfinite(z0) or not np.isfinite(acceleration):
        bca["reason"] = "nonfinite_bias_correction_or_acceleration"
        return results
    bca["bias_correction_z0"] = z0
    tail = (1 - level) / 2
    z = norm.ppf([tail, 1 - tail])
    numerator = z0 + z
    denominator = 1 - acceleration * numerator
    if not np.isfinite(denominator).all() or np.any(denominator <= 0):
        bca["reason"] = "invalid_bca_transformation"
        return results
    probabilities = norm.cdf(z0 + numerator / denominator)
    if not np.isfinite(probabilities).all() or probabilities[0] >= probabilities[1]:
        bca["reason"] = "invalid_adjusted_probabilities"
        return results
    bca.update(
        adjusted_lower_probability=float(probabilities[0]),
        adjusted_upper_probability=float(probabilities[1]),
    )
    resolution = 1 / (len(draws) + 1)
    if probabilities[0] < resolution or probabilities[1] > 1 - resolution:
        bca["reason"] = "adjusted_probabilities_outside_empirical_tail_support"
        return results
    low, high = np.quantile(draws, probabilities)
    bca.update(lower=float(low), upper=float(high))
    return results


def verify_diagnostic(root: Path) -> tuple[dict, dict]:
    """Verify the complete registry before reading any dataframe."""
    root = root.resolve()
    status = read_json(root / "status.json")
    protocol = read_json(root / "protocol.json")
    body = {key: value for key, value in protocol.items() if key != "protocol_hash"}
    if (
        status.get("status") not in ("completed", "completed_with_failures")
        or status.get("protocol_hash") != protocol.get("protocol_hash")
        or fingerprint(body) != protocol.get("protocol_hash")
    ):
        raise ValueError("Diagnostic status or protocol fingerprint is invalid")
    checksums = status.get("artifacts", {})
    required = {
        "protocol.json",
        "seed_metrics.parquet",
        "summary.csv",
        "source_context/context_templates.json",
        "source_context/context_templates.parquet",
    }
    for dgp in protocol["dgps"]:
        for seed in protocol["seeds"]:
            for estimator in protocol["estimators"]:
                name = f"{dgp}-{seed}-{estimator}"
                required.update(
                    (f"{name}.json", f"{name}-metrics.parquet", f"{name}-draws.parquet")
                )
    if not required <= set(checksums):
        raise ValueError("Diagnostic artifact registry is incomplete")
    for name, expected in checksums.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"Diagnostic checksum mismatch: {name}")
    for name, expected in protocol["context_sha256"].items():
        if checksums.get(f"source_context/{name}") != expected:
            raise ValueError("Frozen context hashes differ from the diagnostic protocol")
    expected_jobs = len(protocol["dgps"]) * len(protocol["seeds"]) * len(protocol["estimators"])
    if status.get("completed_estimator_jobs") != expected_jobs:
        raise ValueError("Diagnostic estimator job count is incomplete")
    return protocol, status


def coefficients(result: FitResult) -> np.ndarray:
    bundle = result.bundle
    if (
        bundle is None
        or bundle.active_treatments != (0, 1)
        or bundle.theta.shape != (2, 2)
        or not np.isfinite(bundle.theta).all()
    ):
        raise ValueError("Refit must identify both price treatments with finite 2x2 coefficients")
    return bundle.theta.reshape(-1)


def day_jackknife(train: pd.DataFrame, config: Config, estimator: str) -> pd.DataFrame:
    records = []
    days = sorted(train.original_day_id.unique())
    for day in days:
        record = {"omitted_original_day_id": str(day), "status": "failed", "error": None}
        try:
            result = fit_estimator(
                train.loc[train.original_day_id.ne(day)].copy(),
                config,
                estimator,
                seed=config.simulation.seed,
            )
            values = coefficients(result)
            record.update(status="succeeded", **dict(zip(COEFFICIENT_COLUMNS, values, strict=True)))
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            record.update(error_type=type(exc).__name__, error=str(exc))
        records.append(record)
    return pd.DataFrame(records)


def comparison_rows(
    saved: pd.DataFrame, raw: pd.DataFrame, jackknife: pd.DataFrame, level: float
) -> list[dict]:
    rows = []
    for original in saved.to_dict("records"):
        point = original.get("theta")
        column = f"theta_{original['outcome'].lower()}{original['treatment'].lower()}"
        successful = raw.loc[raw.status.eq("succeeded")]
        values = successful[column].to_numpy(float) if column in successful else np.array([])
        jack_values = (
            jackknife[column].to_numpy(float)
            if column in jackknife and jackknife.status.eq("succeeded").all()
            else np.full(len(jackknife), np.nan)
        )
        available = point is not None and np.isfinite(point) and len(values) >= 2
        candidates: dict[str, dict] = (
            calculate_intervals(float(point), values, jack_values, level)
            if available
            else {
                method: {
                    "lower": None,
                    "upper": None,
                    "reason": "source_estimate_or_draws_unavailable",
                }
                for method in INTERVAL_METHODS
            }
        )
        if available:
            baseline = candidates["percentile"]
            if baseline["lower"] != original.get("theta_lower") or baseline[
                "upper"
            ] != original.get("theta_upper"):
                raise ValueError("Recomputed percentile bounds differ from saved baseline")
        for method, interval in candidates.items():
            row = {
                key: original.get(key)
                for key in (
                    "dataset_id",
                    "dgp_id",
                    "seed",
                    "estimator",
                    "outcome",
                    "treatment",
                    "source_kind",
                    "status",
                    "theta",
                    "true_theta",
                    "error",
                    "requested_draws",
                    "successful_draws",
                    "scenario_probability_rmse",
                    "bootstrap_failed_draws",
                    "bootstrap_not_attempted_draws",
                    "error_type",
                    "error_message",
                )
            }
            low, high = interval["lower"], interval["upper"]
            # Oracle truth is consulted only after every candidate's bounds are fixed.
            truth = original.get("true_theta")
            row.update(
                interval_method=method,
                theta_lower=low,
                theta_upper=high,
                interval_width=high - low if low is not None else None,
                interval_available=low is not None,
                unavailable_reason=interval.get("reason"),
                interval_status=original["interval_status"] if low is not None else "unavailable",
                source_interval_status=original["interval_status"],
                interval_level=level,
                covered=low <= truth <= high if low is not None and truth is not None else None,
                false_positive=not (low <= 0 <= high) if low is not None and truth == 0 else None,
                development_only=True,
                interval_scope="individual theta only",
                interval_calibration_status="not_final_calibration",
                **{
                    key: interval.get(key)
                    for key in (
                        "bias_correction_z0",
                        "acceleration",
                        "adjusted_lower_probability",
                        "adjusted_upper_probability",
                    )
                },
            )
            rows.append(row)
    return rows


def summarize_comparison(metrics: pd.DataFrame, expected_seeds: int) -> pd.DataFrame:
    if metrics.duplicated([*GROUP_COLUMNS, "seed", "interval_method"]).any():
        raise ValueError("Duplicate seed/effect/interval method")
    summaries = []
    for method, frame in metrics.groupby("interval_method"):
        summary = aggregate_metrics(frame, expected_seeds)
        for index, row in summary.iterrows():
            mask = np.ones(len(frame), dtype=bool)
            baseline_mask = metrics.interval_method.eq("percentile")
            for column in GROUP_COLUMNS:
                mask &= frame[column].eq(row[column]).to_numpy()
                baseline_mask &= metrics[column].eq(row[column])
            group = frame.loc[mask]
            pairs = group.merge(
                metrics.loc[baseline_mask],
                on=[*GROUP_COLUMNS, "seed"],
                suffixes=("", "_baseline"),
                validate="one_to_one",
            )
            pairs = pairs.loc[pairs.interval_available & pairs.interval_available_baseline]
            widths = group.interval_width.dropna()
            paired_covered = pairs.loc[pairs.covered.notna() & pairs.covered_baseline.notna()]
            candidate_covered = paired_covered.covered.astype(bool)
            baseline_covered = paired_covered.covered_baseline.astype(bool)
            ratios = pairs.loc[pairs.interval_width_baseline.gt(0)]
            summary.loc[index, "available_intervals"] = int(group.interval_available.sum())
            summary.loc[index, "unavailable_intervals"] = int((~group.interval_available).sum())
            summary.loc[index, "unstable_available_intervals"] = int(
                (group.interval_available & group.interval_status.ne("ok")).sum()
            )
            summary.loc[index, "missing_seed_jobs"] = expected_seeds - int(group.seed.nunique())
            summary.loc[index, "mean_interval_width"] = (
                float(widths.mean()) if len(widths) else np.nan
            )
            summary.loc[index, "paired_available_seeds"] = len(pairs)
            summary.loc[index, "paired_coverage_denominator"] = len(paired_covered)
            summary.loc[index, "paired_coverage_change"] = (
                float(
                    (
                        paired_covered.covered.astype(int)
                        - paired_covered.covered_baseline.astype(int)
                    ).mean()
                )
                if len(paired_covered)
                else np.nan
            )
            summary.loc[index, "paired_coverage_gains"] = int(
                (candidate_covered & ~baseline_covered).sum()
            )
            summary.loc[index, "paired_coverage_losses"] = int(
                (~candidate_covered & baseline_covered).sum()
            )
            summary.loc[index, "paired_width_ratio_denominator"] = len(ratios)
            summary.loc[index, "mean_paired_width_ratio"] = (
                float((ratios.interval_width / ratios.interval_width_baseline).mean())
                if len(ratios)
                else np.nan
            )
            summary.loc[index, "failed_bootstrap_draws"] = int(
                group.bootstrap_failed_draws.fillna(0).sum()
            )
            summary.loc[index, "not_attempted_bootstrap_draws"] = int(
                group.bootstrap_not_attempted_draws.fillna(0).sum()
            )
        summary["interval_method"] = method
        summary["development_only"] = True
        summaries.append(summary)
    return pd.concat(summaries, ignore_index=True)


def run_comparison(diagnostic_root: Path, output_root: Path, workspace: Path | None = None) -> dict:
    diagnostic_root, output_root = diagnostic_root.resolve(), output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"Comparison output already exists: {output_root}")
    source_protocol, source_status = verify_diagnostic(diagnostic_root)
    workspace = workspace or Path(__file__).resolve().parents[1]
    config = Config.from_dict(source_protocol["source_config"], workspace)
    seeds, dgps, estimators, draws = (
        source_protocol[key] for key in ("seeds", "dgps", "estimators", "bootstrap_draws")
    )
    validate_protocol(config, seeds, dgps, estimators, draws)
    if draws < 199:
        raise ValueError("Comparison requires at least 199 requested bootstrap draws")
    runtime = environment(workspace)
    for key in ("python", "packages", "source_code_sha256", "lock_sha256"):
        if runtime[key] != source_protocol["environment"][key]:
            raise ValueError(f"Diagnostic environment differs from current {key}")
    context_metadata = read_json(diagnostic_root / "source_context/context_templates.json")
    if (
        context_metadata.get("fit_start") != config.source.start
        or context_metadata.get("fit_end_exclusive") != config.source.train_end
        or context_metadata.get("context_version") != source_protocol["context_version"]
    ):
        raise ValueError("Frozen context metadata differs from source training configuration")
    script_sha = sha256_file(Path(__file__))
    training_days = (
        dt.date.fromisoformat(config.source.train_end) - dt.date.fromisoformat(config.source.start)
    ).days
    estimator_jobs = len(seeds) * len(dgps) * len(estimators)
    identities = {
        **source_status["artifacts"],
        "status.json": sha256_file(diagnostic_root / "status.json"),
    }
    protocol = {
        "schema_version": 1,
        "purpose": "paired development comparison; no winner or production change",
        "development_only": True,
        "source_protocol_hash": source_protocol["protocol_hash"],
        "diagnostic_root": str(diagnostic_root),
        "source_artifact_sha256": identities,
        "source_config": config.as_dict(),
        "environment": runtime,
        "script_sha256": script_sha,
        "interval_methods": list(INTERVAL_METHODS),
        "interval_level": config.evaluation.interval_level,
        "seeds": seeds,
        "dgps": dgps,
        "estimators": estimators,
        "bootstrap_draws": draws,
        "original_training_days_per_job": training_days,
        "maximum_point_refits": estimator_jobs,
        "maximum_jackknife_refits": estimator_jobs * training_days,
        "jackknife_unit": "delete one original training day; refit every learned component",
        "jackknife_seed": "original dataset seed; DML folds rebuilt on remaining original days",
        "bca_tail_guard": "adjusted probabilities within [1/(B+1), B/(B+1)]; never clipped",
        "paired_unit": "same seed, DGP, estimator and coefficient; same saved bootstrap draws",
        "scope": "individual theta intervals only; no elasticity or scenario candidate intervals",
        "native_threads": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
    }
    protocol["protocol_hash"] = fingerprint(protocol)
    output_root.mkdir(parents=True, exist_ok=False)
    write_json(output_root / "protocol.json", protocol)
    started = time.perf_counter()
    states, rows = [], []
    try:
        context = pd.read_parquet(diagnostic_root / "source_context/context_templates.parquet")
        for dgp in dgps:
            for seed in seeds:
                verify_diagnostic(diagnostic_root)
                if code_hash(workspace) != runtime["source_code_sha256"]:
                    raise ValueError("Source code changed during comparison")
                seed_config = dataclasses.replace(
                    config,
                    simulation=dataclasses.replace(config.simulation, seed=seed, dgp=dgp),
                    evaluation=dataclasses.replace(config.evaluation, bootstrap_draws=draws),
                )
                data = generate(seed_config, context, source_protocol["context_version"])
                train = date_splits(data.blocks, seed_config)["train"]
                if train.original_day_id.nunique() != training_days:
                    raise ValueError("Training day count differs from frozen jackknife budget")
                for estimator in estimators:
                    name = f"{dgp}-{seed}-{estimator}"
                    print(
                        f"compare: {name}, {train.original_day_id.nunique()} training days",
                        flush=True,
                    )
                    saved_state = read_json(diagnostic_root / f"{name}.json")
                    for key, expected_identity in (
                        ("dgp_id", dgp),
                        ("seed", seed),
                        ("estimator", estimator),
                    ):
                        if saved_state.get(key) != expected_identity:
                            raise ValueError(f"Saved diagnostic job has a different {key}")
                    if data.dataset_id != saved_state["dataset_id"]:
                        raise ValueError(
                            "Regenerated dataset identity differs from saved diagnostic"
                        )
                    saved = pd.read_parquet(diagnostic_root / f"{name}-metrics.parquet")
                    raw = pd.read_parquet(diagnostic_root / f"{name}-draws.parquet")
                    if len(saved) != 4 or saved.duplicated(["outcome", "treatment"]).any():
                        raise ValueError("Expected exactly four unique saved coefficient metrics")
                    for key, expected_identity in (
                        ("dgp_id", dgp),
                        ("seed", seed),
                        ("estimator", estimator),
                    ):
                        if not saved[key].eq(expected_identity).all():
                            raise ValueError(f"Saved coefficient metrics have a different {key}")
                    if set(zip(saved.outcome, saved.treatment, strict=True)) != {
                        (outcome, treatment) for outcome in ("X", "Y") for treatment in ("X", "Y")
                    }:
                        raise ValueError("Saved coefficient labels differ from the 2x2 model")
                    if raw.draw_id.duplicated().any() or len(raw) > draws:
                        raise ValueError("Invalid saved bootstrap draw IDs or count")
                    successful_draws = int(raw.status.eq("succeeded").sum())
                    if not saved.successful_draws.eq(successful_draws).all():
                        raise ValueError("Saved successful bootstrap draw counts differ")
                    method_config = dataclasses.replace(
                        seed_config,
                        model=dataclasses.replace(
                            seed_config.model, estimators=(estimator,), scenario_estimator=estimator
                        ),
                    )
                    if saved_state["status"] == "succeeded" and saved.theta.notna().all():
                        results, _ = fit_all(data.blocks, method_config)
                        refitted = coefficients(results[estimator])
                        ordered = saved.set_index(["outcome", "treatment"])
                        expected = np.array(
                            [
                                ordered.loc[(outcome, treatment), "theta"]
                                for outcome in ("X", "Y")
                                for treatment in ("X", "Y")
                            ],
                            dtype=float,
                        )
                        if not np.allclose(refitted, expected, rtol=0, atol=1e-12):
                            raise ValueError("Point refit differs from saved diagnostic")
                        jackknife = day_jackknife(train, method_config, estimator)
                    else:
                        jackknife = pd.DataFrame(
                            [
                                {
                                    "omitted_original_day_id": str(day),
                                    "status": "not_attempted",
                                    "error": "source_fit_or_metric_failed",
                                }
                                for day in sorted(train.original_day_id.unique())
                            ]
                        )
                    paths = [
                        output_root / f"{name}-jackknife.parquet",
                        output_root / f"{name}-metrics.parquet",
                    ]
                    write_frame(paths[0], jackknife)
                    job_rows = comparison_rows(
                        saved, raw, jackknife, config.evaluation.interval_level
                    )
                    write_frame(paths[1], pd.DataFrame(job_rows))
                    state = {
                        "dgp_id": dgp,
                        "seed": seed,
                        "estimator": estimator,
                        "dataset_id": data.dataset_id,
                        "source_job_status": saved_state["status"],
                        "jackknife_requested": len(jackknife),
                        "jackknife_successful": int(jackknife.status.eq("succeeded").sum()),
                        "jackknife_failed": int(jackknife.status.eq("failed").sum()),
                        "jackknife_not_attempted": int(jackknife.status.eq("not_attempted").sum()),
                        "status": "succeeded"
                        if jackknife.status.eq("succeeded").all()
                        else "failed",
                        "artifacts": {path.name: sha256_file(path) for path in paths},
                    }
                    write_json(output_root / f"{name}.json", state)
                    states.append(state)
                    rows.extend(job_rows)
        verify_diagnostic(diagnostic_root)
        if (
            code_hash(workspace) != runtime["source_code_sha256"]
            or sha256_file(Path(__file__)) != script_sha
        ):
            raise ValueError("Code changed during comparison; restart with fresh output")
        if sha256_file(diagnostic_root / "status.json") != identities["status.json"]:
            raise ValueError("Diagnostic source status changed during comparison")
        metrics = pd.DataFrame(rows)
        write_frame(output_root / "seed_metrics.parquet", metrics)
        write_frame(output_root / "summary.csv", summarize_comparison(metrics, len(seeds)))
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
        "protocol_hash": protocol["protocol_hash"],
        "completed_at": utc_now(),
        "completed_estimator_jobs": len(states),
        "duration_seconds": time.perf_counter() - started,
        "interpretation": "development only; no selected method or final calibration acceptance",
        "unavailable_bca_intervals": int(
            (metrics.interval_method.eq("bca") & ~metrics.interval_available).sum()
        ),
        "artifacts": {
            path.relative_to(output_root).as_posix(): sha256_file(path)
            for path in output_root.rglob("*")
            if path.is_file()
        },
    }
    write_json(output_root / "status.json", status)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    run_comparison(args.diagnostic_root, args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
