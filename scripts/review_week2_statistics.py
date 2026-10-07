"""Audit frozen Week 2 outputs without fitting models or modifying source results."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.stats import beta, binomtest

cell_keys = ["dgp_id", "estimator", "outcome", "treatment"]
row_keys = ["dgp_id", "seed", "estimator", "outcome", "treatment"]
fit_keys = ["dgp_id", "seed", "estimator"]
diagnostic_dgps = ["RCT_SYN", "OBSERVED_CONFOUNDING", "NULL_EFFECT"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_interval(successes: int, trials: int) -> tuple[float, float]:
    """Two-sided Clopper-Pearson interval, independently using beta quantiles."""
    if trials == 0:
        return float("nan"), float("nan")
    lower = 0.0 if successes == 0 else beta.ppf(0.025, successes, trials - successes + 1)
    upper = 1.0 if successes == trials else beta.ppf(0.975, successes + 1, trials - successes)
    return float(lower), float(upper)


def holm_adjust(p_values: np.ndarray) -> np.ndarray:
    require(len(p_values) > 0, "Empty diagnostic family")
    require(np.isfinite(p_values).all(), "Non-finite diagnostic p-values")
    require(((p_values >= 0) & (p_values <= 1)).all(), "Invalid p-values")
    order = np.argsort(p_values, kind="stable")
    adjusted = np.empty(len(p_values), dtype=float)
    adjusted[order] = np.minimum(
        1.0, np.maximum.accumulate(p_values[order] * np.arange(len(p_values), 0, -1))
    )
    return adjusted


def review_results(results_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    manifest = json.loads((results_dir / "manifest.json").read_text(encoding="utf-8"))
    spec = json.loads((results_dir / "frozen_spec.json").read_text(encoding="utf-8"))
    status = json.loads((results_dir / "status.json").read_text(encoding="utf-8"))
    execution = json.loads((results_dir / "execution.json").read_text(encoding="utf-8"))
    checksums = dict(
        (name, checksum)
        for checksum, name in (
            line.split("  ", 1)
            for line in (results_dir / "checksums.sha256").read_text().splitlines()
        )
    )
    require(bool(checksums), "Empty source checksums")
    for name, checksum in checksums.items():
        require(file_hash(results_dir / name) == checksum, f"SHA-256 mismatch: {name}")
    for name, checksum in manifest["files"].items():
        require(checksums.get(name) == checksum, f"Manifest mismatch: {name}")
    require(status["status"] == "complete", "Incomplete computation")
    require(execution["process_status"] == "finished", "Runner has not finished")
    require(not status["failed_batches"], "Final batch errors")
    require(not status["active_batches"], "Batches still active")
    require(manifest["failed_checkpoint_seeds"] == 0, "Failed seed checkpoints")
    require(status["completed_checkpoint_seeds"] == 500, "Incomplete seed checkpoints")
    require(status["failed_checkpoint_seeds"] == 0, "Failed seed checkpoint status")
    require(spec["reporting_seeds"] == list(range(20001, 20101)), "Unexpected reporting seeds")
    require(
        status["spec_hash"] == execution["spec_hash"] == manifest["spec_hash"],
        "Protocol fingerprint mismatch",
    )

    rows = pd.read_parquet(results_dir / "seed_metrics.parquet")
    summary = pd.read_csv(results_dir / "evaluation_metrics.csv").set_index(cell_keys)
    expected_keys = pd.MultiIndex.from_product(
        [
            spec["dgps"],
            spec["reporting_seeds"],
            spec["config"]["model"]["estimators"],
            ["X", "Y"],
            ["X", "Y"],
        ],
        names=row_keys,
    )
    require(not rows.duplicated(row_keys).any(), "Duplicate seed/coefficient keys")
    require(
        pd.MultiIndex.from_frame(rows[row_keys]).sort_values().equals(expected_keys.sort_values()),
        "Missing or unexpected DGP/seed/coefficient keys",
    )
    require(summary.index.is_unique and len(summary) == 60, "Invalid summary cell keys")
    require(rows["evidence_level"].eq("C").all(), "Unexpected evidence level")
    require(rows["source_kind"].eq("semi_synthetic").all(), "Unexpected source kind")
    require(rows["theta_unit"].eq("probability / log-price").all(), "Unexpected theta units")
    require(rows["interval_level"].eq(0.95).all(), "Unexpected interval level")
    for dgp_id in spec["dgps"]:
        require(status["completed_seeds"][dgp_id] == 100, f"Incomplete DGP: {dgp_id}")

    durations = []
    with zipfile.ZipFile(results_dir / "reproducibility.zip") as archive:
        require(archive.testzip() is None, "Archive CRC mismatch")
        for dgp_id in spec["dgps"]:
            for seed in spec["reporting_seeds"]:
                first_seed = 20001 + ((seed - 20001) // 5) * 5
                run_id = f"week2-{dgp_id.lower()}-{first_seed}-{first_seed + 4}"
                base = f"runs/{run_id}/evaluation/{dgp_id}-{seed}"
                checkpoint = json.loads(archive.read(base + ".json"))
                require(checkpoint["status"] == "succeeded", f"Failed checkpoint: {base}")
                require(
                    (checkpoint["dgp_id"], checkpoint["seed"], checkpoint["run_id"])
                    == (dgp_id, seed, run_id),
                    f"Checkpoint identity mismatch: {base}",
                )
                parquet_bytes = archive.read(base + ".parquet")
                require(
                    hashlib.sha256(parquet_bytes).hexdigest() == checkpoint["metrics_sha256"],
                    f"Checkpoint hash mismatch: {base}",
                )
                checkpoint_frame = pd.read_parquet(io.BytesIO(parquet_bytes))
                pooled_frame = rows.loc[rows["dgp_id"].eq(dgp_id) & rows["seed"].eq(seed)]
                # Rejected fits omit this diagnostic; the pooled table fills it with NaN.
                allowed_missing = (
                    {"invalid_baseline_draws"} if dgp_id == "COLLINEAR_PRICE" else set()
                )
                require(
                    set(rows.columns) - set(checkpoint_frame.columns) <= allowed_missing,
                    f"Missing checkpoint columns: {base}",
                )
                require(
                    not set(checkpoint_frame.columns) - set(rows.columns),
                    f"Unexpected checkpoint columns: {base}",
                )
                pd.testing.assert_frame_equal(
                    pooled_frame.sort_values(row_keys).reset_index(drop=True),
                    checkpoint_frame.reindex(columns=rows.columns)
                    .astype(rows.dtypes.to_dict())
                    .sort_values(row_keys)
                    .reset_index(drop=True),
                    check_exact=True,
                )
                durations.append({"dgp_id": dgp_id, "seconds": checkpoint["duration_seconds"]})

    identified = rows.loc[rows["dgp_id"].ne("COLLINEAR_PRICE")]
    rejected = rows.loc[rows["dgp_id"].eq("COLLINEAR_PRICE")]
    require(identified["status"].eq("ok").all(), "Unexpected fit failures")
    require(identified["interval_status"].eq("ok").all(), "Unstable identified intervals")
    require(rejected["status"].eq("not_identified").all(), "Collinear effects not rejected")
    require(
        rejected[
            [
                "theta",
                "theta_lower",
                "theta_upper",
                "error",
                "squared_error",
                "covered",
                "false_positive",
                "scenario_probability_rmse",
                "scenario_probability_valid",
            ]
        ]
        .isna()
        .all()
        .all(),
        "Rejected estimates must remain missing, not zero",
    )
    require(
        np.isfinite(
            identified[
                [
                    "theta",
                    "theta_lower",
                    "theta_upper",
                    "true_theta",
                    "error",
                    "squared_error",
                    "scenario_probability_rmse",
                ]
            ]
        )
        .all()
        .all(),
        "Non-finite identified results",
    )
    np.testing.assert_allclose(
        identified["error"], identified["theta"] - identified["true_theta"], atol=1e-14, rtol=0
    )
    np.testing.assert_allclose(
        identified["squared_error"], identified["error"] ** 2, atol=1e-14, rtol=0
    )
    require(identified["theta_lower"].le(identified["theta_upper"]).all(), "Reversed intervals")
    covered = identified["theta_lower"].le(identified["true_theta"]) & identified["theta_upper"].ge(
        identified["true_theta"]
    )
    require(np.array_equal(identified["covered"].to_numpy(), covered), "Coverage flag mismatch")
    null_rows = identified.loc[identified["dgp_id"].eq("NULL_EFFECT")]
    require(null_rows["true_theta"].eq(0).all(), "Nonzero NULL_EFFECT truth")
    require(
        np.array_equal(null_rows["false_positive"], ~null_rows["covered"].astype(bool)),
        "Null false-positive flag mismatch",
    )
    require(
        rows.loc[rows["dgp_id"].ne("NULL_EFFECT"), "false_positive"].isna().all(),
        "False-positive denominator must be NULL_EFFECT only",
    )

    fit_columns = [
        "requested_draws",
        "successful_draws",
        "invalid_baseline_draws",
        "scenario_probability_rmse",
        "scenario_probability_valid",
    ]
    require(
        rows.groupby(fit_keys)[fit_columns].nunique(dropna=False).eq(1).all().all(),
        "Fit-level fields differ across coefficient rows",
    )
    fits = rows.drop_duplicates(fit_keys)
    valid_fits = fits.loc[fits["dgp_id"].ne("COLLINEAR_PRICE")]
    require(
        valid_fits[["requested_draws", "successful_draws"]].eq(199).all().all(),
        "Incomplete bootstrap draws",
    )
    require(valid_fits["invalid_baseline_draws"].eq(0).all(), "Invalid baseline draws")
    require(valid_fits["scenario_probability_valid"].eq(True).all(), "Invalid scenario probability")
    require(
        fits.loc[fits["dgp_id"].eq("COLLINEAR_PRICE"), ["requested_draws", "successful_draws"]]
        .eq(0)
        .all()
        .all(),
        "Rejected fits should not run bootstrap",
    )

    cell_records = []
    for key, group in rows.groupby(cell_keys):
        errors = group["error"].dropna()
        cover = group["covered"].dropna().astype(bool)
        false_positive = group["false_positive"].dropna().astype(bool)
        scenario = group["scenario_probability_rmse"].dropna()
        record = dict(zip(cell_keys, key, strict=True))
        record.update(
            expected_seeds=100,
            attempted_seeds=int(group["seed"].nunique()),
            valid_estimates=len(errors),
            failed_or_unidentified_estimates=len(group) - len(errors),
            bias=float(errors.mean()),
            rmse=float(np.sqrt((errors**2).mean())),
            coverage=float(cover.mean()),
            coverage_denominator=len(cover),
            false_positive_rate=float(false_positive.mean()),
            false_positive_denominator=len(false_positive),
            bootstrap_requested_total=int(group["requested_draws"].sum()),
            bootstrap_successful_total=int(group["successful_draws"].sum()),
            scenario_probability_rmse=float(np.sqrt((scenario**2).mean())),
        )
        record["coverage_lower"], record["coverage_upper"] = exact_interval(
            int(cover.sum()), len(cover)
        )
        record["false_positive_lower"], record["false_positive_upper"] = exact_interval(
            int(false_positive.sum()), len(false_positive)
        )
        for column, value in record.items():
            if column not in cell_keys:
                np.testing.assert_allclose(
                    summary.loc[key, column],
                    value,
                    atol=1e-12,
                    rtol=0,
                    equal_nan=True,
                    err_msg=f"Summary mismatch: {key}/{column}",
                )
        require(
            summary.loc[key, "interval_quality"]
            == (
                "reporting"
                if group["interval_status"].eq("ok").all()
                else "development_or_unstable"
            ),
            f"Interval quality mismatch: {key}",
        )
        record["covered_seeds"] = int(cover.sum())
        record["false_positive_seeds"] = int(false_positive.sum())
        cell_records.append(record)
    cells = pd.DataFrame(cell_records)
    family = cells["dgp_id"].isin(diagnostic_dgps)
    cells.loc[family, "undercoverage_p_one_sided"] = [
        binomtest(
            int(row.covered_seeds), int(row.coverage_denominator), 0.95, alternative="less"
        ).pvalue
        for row in cells.loc[family].itertuples()
    ]
    cells.loc[family, "undercoverage_p_holm_36"] = holm_adjust(
        cells.loc[family, "undercoverage_p_one_sided"].to_numpy()
    )

    overview = cells.groupby(["dgp_id", "estimator"], as_index=False).agg(
        max_abs_bias=("bias", lambda values: values.abs().max()),
        max_theta_rmse=("rmse", "max"),
        coverage_min=("coverage", "min"),
        coverage_max=("coverage", "max"),
        scenario_probability_rmse=("scenario_probability_rmse", "first"),
        null_fp_min=("false_positive_rate", "min"),
        null_fp_max=("false_positive_rate", "max"),
    )
    audit = {
        "reviewed_at_utc": datetime.now(UTC).isoformat(),
        "evaluation_finished_at_utc": execution["finished_at"],
        "review_git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "review_script_sha256": file_hash(Path(__file__)),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
        },
        "source_checksums_verified": checksums,
        "frozen_revision": spec["environment"]["git_revision"],
        "frozen_source_sha256": spec["environment"]["source_code_sha256"],
        "protocol_fingerprint": manifest["spec_hash"],
        "checks": {
            "source_hashes": "passed",
            "all_500_checkpoint_hashes": "passed",
            "all_checkpoint_rows_equal_pool": "passed",
            "row_keys_and_denominators": "passed",
            "finite_values_and_flags": "passed",
            "all_60_numeric_summary_cells": "passed",
            "binomial_intervals_independent_beta_quantiles": "passed",
        },
        "counts": {
            "seed_jobs": 500,
            "failed_seed_jobs": 0,
            "summary_cells": len(cells),
            "coefficient_rows": len(rows),
            "identified_fits": len(valid_fits),
            "rejected_collinear_fits": len(fits) - len(valid_fits),
            "requested_bootstrap_refits": int(fits["requested_draws"].sum()),
            "successful_bootstrap_refits": int(fits["successful_draws"].sum()),
            "invalid_baseline_draws": int(valid_fits["invalid_baseline_draws"].sum()),
            "invalid_scenarios": int(valid_fits["scenario_probability_valid"].eq(False).sum()),
        },
        "diagnostic_method": "Post-hoc one-sided exact binomial p<0.95, Holm over 36 cells; "
        "not a preregistered acceptance rule or sequential-monitoring adjustment",
        "undercoverage_holm_below_0_05": cells.loc[
            cells["undercoverage_p_holm_36"].lt(0.05),
            cell_keys + ["covered_seeds", "coverage_denominator", "undercoverage_p_holm_36"],
        ].to_dict("records"),
        "rct_point_accuracy": bool(
            overview.loc[overview["dgp_id"].eq("RCT_SYN"), "max_theta_rmse"]
            .le(spec["technical_targets"]["rct_theta_rmse"])
            .all()
            and overview.loc[overview["dgp_id"].eq("RCT_SYN"), "scenario_probability_rmse"]
            .le(spec["technical_targets"]["rct_scenario_probability_rmse"])
            .all()
        ),
        "interval_calibration": "undercoverage limitation; no unconditional statistical acceptance",
        "checkpoint_runtime_seconds_by_dgp": pd.DataFrame(durations)
        .groupby("dgp_id")["seconds"]
        .agg(["count", "mean", "min", "max", "sum"])
        .to_dict("index"),
        "runtime_note": "Per-job recorded durations; sums are not parallel wall-clock elapsed time",
    }
    for name, checksum in checksums.items():
        require(file_hash(results_dir / name) == checksum, f"Source modified during review: {name}")
    return cells, overview, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs/submission/days/20261007/results/week2",
    )
    args = parser.parse_args()
    cells, overview, audit = review_results(args.results_dir)
    output_dir = args.results_dir / "statistical_review"
    output_dir.mkdir(parents=True, exist_ok=True)
    cells.to_csv(output_dir / "cell_metrics.csv", index=False)
    overview.to_csv(output_dir / "dgp_estimator_summary.csv", index=False)
    (output_dir / "audit.json").write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    output_files = ["audit.json", "cell_metrics.csv", "dgp_estimator_summary.csv"]
    (output_dir / "checksums.sha256").write_text(
        "".join(f"{file_hash(output_dir / name)}  {name}\n" for name in output_files)
    )
    print(
        json.dumps(
            {
                "counts": audit["counts"],
                "rct_point_accuracy": audit["rct_point_accuracy"],
                "interval_calibration": audit["interval_calibration"],
                "output_dir": str(output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
