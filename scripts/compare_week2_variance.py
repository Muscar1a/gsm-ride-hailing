"""Zero-refit development sensitivity: original-point day-jackknife Wald-t intervals.

This generic sensitivity calculation is not CV3 or a DML inference guarantee.
Run with ``python -m scripts.compare_week2_variance``; no method is promoted.
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t

from gsm_poc.core.artifacts import (
    environment,
    fingerprint,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config
from scripts.compare_week2_intervals import (
    COEFFICIENT_COLUMNS,
    INTERVAL_METHODS,
    summarize_comparison,
)
from scripts.diagnose_week2_intervals import GROUP_COLUMNS, validate_protocol

INTERVAL_METHOD = "day_jackknife_t"


def jackknife_interval(point: float, estimates: np.ndarray, level: float) -> dict:
    """Use the original point, delete-day variance and t(G-1), with no oracle input."""
    values = np.asarray(estimates, dtype=float)
    groups = len(values) if values.ndim == 1 else 0
    result = {
        "lower": None,
        "upper": None,
        "reason": None,
        "jackknife_groups": groups,
        "jackknife_variance": None,
        "jackknife_se": None,
        "jackknife_df": groups - 1,
        "jackknife_critical_value": None,
    }
    if not 0 < level < 1:
        raise ValueError("Interval level must be strictly between zero and one")
    if groups < 3 or not np.isfinite(point) or not np.isfinite(values).all():
        result["reason"] = "missing_or_nonfinite_estimates"
        return result
    variance = float((groups - 1) / groups * np.sum((values - values.mean()) ** 2))
    if not np.isfinite(variance) or variance <= 0:
        result["reason"] = "degenerate_or_nonfinite_variance"
        return result
    se, critical = float(np.sqrt(variance)), float(t.ppf((1 + level) / 2, groups - 1))
    low, high = point - critical * se, point + critical * se
    if not np.isfinite([low, high, critical]).all():
        result["reason"] = "nonfinite_bounds"
        return result
    result.update(
        lower=float(low),
        upper=float(high),
        jackknife_variance=variance,
        jackknife_se=se,
        jackknife_critical_value=critical,
    )
    return result


def verify_hashes(root: Path, checksums: dict[str, str]) -> None:
    root = root.resolve()
    for name, expected in checksums.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"Source checksum mismatch: {name}")


def verify_comparison(root: Path) -> tuple[dict, dict]:
    protocol, status = read_json(root / "protocol.json"), read_json(root / "status.json")
    body = {key: value for key, value in protocol.items() if key != "protocol_hash"}
    if status.get("status") not in ("completed", "completed_with_failures") or (
        fingerprint(body) != protocol.get("protocol_hash")
        or status.get("protocol_hash") != protocol.get("protocol_hash")
        or tuple(protocol.get("interval_methods", [])) != INTERVAL_METHODS
    ):
        raise ValueError("Comparison status, methods or protocol fingerprint is invalid")
    required = {"protocol.json", "summary.csv", "seed_metrics.parquet", "runner_source.py"}
    jobs = [
        (dgp, seed, method)
        for dgp in protocol["dgps"]
        for seed in protocol["seeds"]
        for method in protocol["estimators"]
    ]
    for dgp, seed, estimator in jobs:
        name = f"{dgp}-{seed}-{estimator}"
        required.update((f"{name}.json", f"{name}-metrics.parquet", f"{name}-jackknife.parquet"))
    if not required <= set(status.get("artifacts", {})) or status.get(
        "completed_estimator_jobs"
    ) != len(jobs):
        raise ValueError("Comparison registry or completed job count is incomplete")
    verify_hashes(root, status["artifacts"])
    if sha256_file(root / "runner_source.py") != protocol.get("script_sha256"):
        raise ValueError("Frozen comparison controller differs from source protocol")
    verify_hashes(Path(protocol["diagnostic_root"]), protocol["source_artifact_sha256"])
    return protocol, status


def jackknife_failure(frame: pd.DataFrame, expected_days: set[str]) -> str | None:
    if "omitted_original_day_id" not in frame or frame.omitted_original_day_id.duplicated().any():
        return "missing_or_duplicate_omission_keys"
    if set(frame.omitted_original_day_id) != expected_days:
        return "incomplete_original_day_omissions"
    if "status" in frame and frame.status.eq("not_attempted").any():
        return "unattempted_original_day_refit"
    if "status" not in frame or not frame.status.eq("succeeded").all():
        return "failed_original_day_refit"
    if (
        not set(COEFFICIENT_COLUMNS) <= set(frame)
        or not np.isfinite(frame[list(COEFFICIENT_COLUMNS)].to_numpy(float)).all()
    ):
        return "missing_or_nonfinite_coefficients"
    return None


def variance_rows(
    baseline: pd.DataFrame, jackknife: pd.DataFrame, days: set[str], level: float
) -> list[dict]:
    reason, rows = jackknife_failure(jackknife, days), []
    for original in baseline.to_dict("records"):
        column = f"theta_{original['outcome'].lower()}{original['treatment'].lower()}"
        values = jackknife[column].to_numpy(float) if reason is None else np.full(len(days), np.nan)
        point = original["theta"] if pd.notna(original["theta"]) else np.nan
        interval = jackknife_interval(point, values, level)
        if reason is not None:
            interval["reason"] = reason
        low, high = interval.pop("lower"), interval.pop("upper")
        truth = original.get("true_theta")
        rows.append(
            {
                **original,
                **interval,
                "interval_method": INTERVAL_METHOD,
                "theta_lower": low,
                "theta_upper": high,
                "interval_width": high - low if low is not None else None,
                "interval_available": low is not None,
                "unavailable_reason": interval["reason"],
                "interval_status": "ok" if low is not None else "unavailable",
                "covered": low <= truth <= high if low is not None and pd.notna(truth) else None,
                "false_positive": not (low <= 0 <= high)
                if low is not None and truth == 0
                else None,
                "jackknife_attempted_groups": int(
                    jackknife.status.isin(["succeeded", "failed"]).sum()
                )
                if "status" in jackknife
                else 0,
                "jackknife_failed_groups": int(jackknife.status.eq("failed").sum())
                if "status" in jackknife
                else 0,
                "jackknife_not_attempted_groups": int(jackknife.status.eq("not_attempted").sum())
                if "status" in jackknife
                else 0,
                "jackknife_missing_groups": len(days - set(jackknife.omitted_original_day_id))
                if "omitted_original_day_id" in jackknife
                else len(days),
                "inference_kind": "generic day-jackknife Wald-t sensitivity; not CV3 or DML theory",
                "bootstrap_counts_role": "reference only; not a requirement for this candidate",
            }
        )
    return rows


def variance_diagnostics(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, group in metrics.loc[metrics.interval_method.eq(INTERVAL_METHOD)].groupby(
        GROUP_COLUMNS
    ):
        if not isinstance(key, tuple) or len(key) != len(GROUP_COLUMNS):
            raise ValueError("Expected four-column variance diagnostic group")
        estimates, errors = group.theta.dropna(), group.jackknife_se.dropna()
        empirical_sd = float(estimates.std(ddof=1)) if len(estimates) > 1 else None
        rms_se = float(np.sqrt(np.mean(errors**2))) if len(errors) else None
        matched = set(group.loc[group.theta.notna(), "seed"]) == set(
            group.loc[group.jackknife_se.notna(), "seed"]
        )
        state = (
            "unmatched_seed_cohorts"
            if not matched
            else "insufficient_replicates"
            if empirical_sd is None
            else "zero_variance"
            if empirical_sd == 0
            else "comparable"
        )
        rows.append(
            {
                **dict(zip(GROUP_COLUMNS, key, strict=True)),
                "interval_method": INTERVAL_METHOD,
                "empirical_estimate_sd": empirical_sd,
                "rms_jackknife_se": rms_se,
                "jackknife_se_denominator": len(errors),
                "sd_comparison_status": state,
                "jackknife_to_empirical_sd_ratio": rms_se / empirical_sd
                if state == "comparable" and rms_se is not None and empirical_sd
                else None,
                "jackknife_attempted_groups_total": int(group.jackknife_attempted_groups.sum()),
                "jackknife_failed_groups_total": int(group.jackknife_failed_groups.sum()),
                "jackknife_not_attempted_groups_total": int(
                    group.jackknife_not_attempted_groups.sum()
                ),
                "jackknife_missing_groups_total": int(group.jackknife_missing_groups.sum()),
            }
        )
    return pd.DataFrame(rows)


def run_variance(comparison_root: Path, output_root: Path, workspace: Path | None = None) -> dict:
    comparison_root, output_root = comparison_root.resolve(), output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"Output already exists: {output_root}")
    source, status = verify_comparison(comparison_root)
    workspace = workspace or Path(__file__).resolve().parents[1]
    config = Config.from_dict(source["source_config"], workspace)
    validate_protocol(
        config, source["seeds"], source["dgps"], source["estimators"], source["bootstrap_draws"]
    )
    start, end = (
        dt.date.fromisoformat(config.source.start),
        dt.date.fromisoformat(config.source.train_end),
    )
    days = {(start + dt.timedelta(days=offset)).isoformat() for offset in range((end - start).days)}
    if len(days) != 20:
        raise ValueError("This development study requires exactly 20 original training days")
    identities = {
        **status["artifacts"],
        "status.json": sha256_file(comparison_root / "status.json"),
    }
    script_path, helper_path = (
        Path(__file__),
        Path(__file__).with_name("compare_week2_intervals.py"),
    )
    if sha256_file(helper_path) != source.get("script_sha256"):
        raise ValueError("Current summary helper differs from frozen comparison controller")
    protocol = {
        "schema_version": 1,
        "purpose": "zero-refit development variance sensitivity; no promotion",
        "development_only": True,
        "source_comparison_root": str(comparison_root),
        "source_comparison_protocol_hash": source["protocol_hash"],
        "source_comparison_status": status["status"],
        "source_artifact_sha256": identities,
        "source_config": source["source_config"],
        "environment": environment(workspace),
        "script_sha256": sha256_file(script_path),
        "summary_helper_sha256": sha256_file(helper_path),
        "interval_methods": [*INTERVAL_METHODS, INTERVAL_METHOD],
        "seeds": source["seeds"],
        "dgps": source["dgps"],
        "estimators": source["estimators"],
        "original_training_days": sorted(days),
        "interval_level": config.evaluation.interval_level,
        "formula": "theta_full +/- t(G-1,(1+level)/2)*sqrt((G-1)/G*sum((theta_-g-mean_jack)^2))",
        "maximum_new_fits": 0,
        "centering": "original point; no pseudovalue or tuned scale",
    }
    protocol["protocol_hash"] = fingerprint(protocol)
    output_root.mkdir(parents=True, exist_ok=False)
    write_json(output_root / "protocol.json", protocol)
    started = time.perf_counter()
    try:
        previous = pd.read_parquet(comparison_root / "seed_metrics.parquet")
        new_rows = []
        for dgp in source["dgps"]:
            for seed in source["seeds"]:
                for estimator in source["estimators"]:
                    name = f"{dgp}-{seed}-{estimator}"
                    saved = pd.read_parquet(comparison_root / f"{name}-metrics.parquet")
                    expected_cells = {
                        (method, x, y)
                        for method in INTERVAL_METHODS
                        for x in ("X", "Y")
                        for y in ("X", "Y")
                    }
                    if (
                        len(saved) != 12
                        or set(
                            zip(saved.interval_method, saved.outcome, saved.treatment, strict=True)
                        )
                        != expected_cells
                    ):
                        raise ValueError(
                            "Expected twelve unique original method/coefficient metrics"
                        )
                    for column, value in (
                        ("dgp_id", dgp),
                        ("seed", seed),
                        ("estimator", estimator),
                    ):
                        if not saved[column].eq(value).all():
                            raise ValueError(f"Saved job has a different {column}")
                    expected = previous.loc[
                        previous.dgp_id.eq(dgp)
                        & previous.seed.eq(seed)
                        & previous.estimator.eq(estimator)
                    ]
                    pd.testing.assert_frame_equal(
                        saved.reset_index(drop=True),
                        expected.reset_index(drop=True),
                        check_dtype=False,
                    )
                    baseline = saved.loc[saved.interval_method.eq("percentile")]
                    jackknife = pd.read_parquet(comparison_root / f"{name}-jackknife.parquet")
                    new_rows.extend(
                        variance_rows(baseline, jackknife, days, config.evaluation.interval_level)
                    )
        if len(previous) != len(new_rows) * 3:
            raise ValueError("Source metrics contain missing or unexpected jobs")
        metrics = pd.concat([previous, pd.DataFrame(new_rows)], ignore_index=True)
        summary = summarize_comparison(metrics, len(source["seeds"])).merge(
            variance_diagnostics(metrics),
            on=[*GROUP_COLUMNS, "interval_method"],
            how="left",
            validate="one_to_one",
        )
        verify_hashes(comparison_root, identities)
        verify_hashes(Path(source["diagnostic_root"]), source["source_artifact_sha256"])
        if (
            sha256_file(script_path) != protocol["script_sha256"]
            or sha256_file(helper_path) != protocol["summary_helper_sha256"]
            or environment(workspace) != protocol["environment"]
        ):
            raise ValueError("Code or environment changed during variance sensitivity")
        write_frame(output_root / "seed_metrics.parquet", metrics)
        write_frame(output_root / "summary.csv", summary)
    except Exception as exc:
        write_json(
            output_root / "status.json",
            {
                "status": "failed",
                "protocol_hash": protocol["protocol_hash"],
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
    final_status = {
        "status": "completed",
        "protocol_hash": protocol["protocol_hash"],
        "duration_seconds": time.perf_counter() - started,
        "new_fits": 0,
        "unavailable_candidate_intervals": int(
            (metrics.interval_method.eq(INTERVAL_METHOD) & ~metrics.interval_available).sum()
        ),
        "interpretation": "development sensitivity only; no final calibration or method promotion",
        "artifacts": {
            path.name: sha256_file(path) for path in output_root.iterdir() if path.is_file()
        },
    }
    write_json(output_root / "status.json", final_status)
    return final_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args(argv)
    run_variance(args.comparison_root, args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
