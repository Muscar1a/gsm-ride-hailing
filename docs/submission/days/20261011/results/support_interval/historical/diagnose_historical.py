"""Read-only diagnosis of the immutable 2026-10-07 final reporting pool."""

import argparse
import hashlib
import importlib.util
import json
import platform
import subprocess
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from gsm_poc.core.config import Config


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo-root", type=Path, default=Path.cwd())
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
root = args.repo_root.resolve()
output_dir = args.output_dir.resolve()
if output_dir.exists():
    parser.error("--output-dir must be a new directory; existing evidence is never overwritten")
results_dir = root / "docs/submission/days/20261007/results/week2"
snapshot = root / ".cache/week2-evaluation-574cf501-20261007"
review_path = root / "scripts/review_week2_statistics.py"
module_spec = importlib.util.spec_from_file_location("historical_review", review_path)
assert module_spec is not None and module_spec.loader is not None
review = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(review)
cells, _, audit = review.review_results(results_dir)
spec = json.loads((results_dir / "frozen_spec.json").read_text())
live_config = json.loads(json.dumps(Config.load(root / "configs/default.toml").as_dict()))
frozen_config = spec["config"]
config_differences = {
    section: {
        key: {"historical": frozen_config[section][key], "live": value}
        for key, value in live_config[section].items()
        if value != frozen_config[section][key]
    }
    for section in live_config
}
assert not any(
    config_differences[section] for section in ("source", "model", "simulation", "evaluation")
)
training_days = (
    date.fromisoformat(frozen_config["source"]["train_end"])
    - date.fromisoformat(frozen_config["source"]["start"])
).days
assert training_days == 20

# Verify the frozen source and context, independent of the live repository revision.
source_checksums = {
    str(path.relative_to(snapshot)): file_hash(path)
    for path in sorted((snapshot / "src/gsm_poc").rglob("*.py"))
}
snapshot_source_hash = hashlib.sha256(
    json.dumps(source_checksums, sort_keys=True, allow_nan=False).encode()
).hexdigest()
assert snapshot_source_hash == spec["environment"]["source_code_sha256"]
assert file_hash(snapshot / "uv.lock") == spec["environment"]["lock_sha256"]
context_dir = snapshot / "data/gold" / spec["build_id"]
assert file_hash(context_dir / "context_templates.parquet") == spec["context_sha256"]
assert file_hash(context_dir / "context_templates.json") == spec["context_metadata_sha256"]
assert (
    file_hash(snapshot / "week2_reporting/seed_metrics.parquet")
    == audit["source_checksums_verified"]["seed_metrics.parquet"]
)

# Verify the previous audit records without rewriting them.
previous_dir = results_dir / "statistical_review"
previous_hashes = {
    name: checksum
    for checksum, name in (
        line.split("  ", 1) for line in (previous_dir / "checksums.sha256").read_text().splitlines()
    )
}
for name, checksum in previous_hashes.items():
    assert file_hash(previous_dir / name) == checksum, name
previous_audit = json.loads((previous_dir / "audit.json").read_text())
assert previous_audit["frozen_source_sha256"] == snapshot_source_hash
assert previous_audit["counts"] == audit["counts"]

rows = pd.read_parquet(results_dir / "seed_metrics.parquet")
cell_keys = ["dgp_id", "estimator", "outcome", "treatment"]
records = []
for key, group in rows.groupby(cell_keys):
    valid = group.loc[group["status"].eq("ok")]
    record = dict(zip(cell_keys, key, strict=True))
    record.update(
        attempted_seeds=int(group["seed"].nunique()),
        valid_estimates=len(valid),
        fit_rejections=int(group["status"].eq("not_identified").sum()),
        other_fit_failures=int((~group["status"].isin(["ok", "not_identified"])).sum()),
        unstable_intervals=int(valid["interval_status"].ne("ok").sum()),
    )
    if len(valid):
        errors = valid["theta"] - valid["true_theta"]
        width = valid["theta_upper"] - valid["theta_lower"]
        truth_below_lower = valid["true_theta"].lt(valid["theta_lower"])
        truth_above_upper = valid["true_theta"].gt(valid["theta_upper"])
        covered = ~(truth_below_lower | truth_above_upper)
        assert int(covered.sum()) + int(truth_below_lower.sum()) + int(
            truth_above_upper.sum()
        ) == len(valid)
        sd = float(valid["theta"].std(ddof=1))
        mean_width = float(width.mean())
        se_approximation = mean_width / (2 * 1.96)
        record.update(
            true_theta=float(valid["true_theta"].iloc[0]),
            mean_theta=float(valid["theta"].mean()),
            bias=float(errors.mean()),
            empirical_theta_sd=sd,
            bias_over_empirical_sd=float(errors.mean()) / sd,
            rmse=float(np.sqrt((errors**2).mean())),
            mean_interval_width=mean_width,
            median_interval_width=float(width.median()),
            normal_equivalent_se_approximation=se_approximation,
            normal_equivalent_se_over_empirical_sd_approximation=se_approximation / sd,
            coverage_count=int(covered.sum()),
            coverage_denominator=len(valid),
            coverage=float(covered.mean()),
            truth_below_interval_count=int(truth_below_lower.sum()),
            truth_above_interval_count=int(truth_above_upper.sum()),
            mean_interval_center_minus_estimate=float(
                ((valid["theta_lower"] + valid["theta_upper"]) / 2 - valid["theta"]).mean()
            ),
        )
        record["coverage_lower"], record["coverage_upper"] = review.exact_interval(
            int(covered.sum()), len(valid)
        )
        expected = cells.set_index(cell_keys).loc[key]
        np.testing.assert_allclose(
            [record["bias"], record["rmse"], record["coverage"]],
            expected[["bias", "rmse", "coverage"]].to_numpy(dtype=float),
            atol=1e-14,
            rtol=0,
        )
    records.append(record)

diagnostics = pd.DataFrame(records)
assert len(diagnostics) == 60
rct_yy = diagnostics.loc[
    diagnostics["dgp_id"].eq("RCT_SYN")
    & diagnostics["outcome"].eq("Y")
    & diagnostics["treatment"].eq("Y")
]
assert rct_yy.loc[rct_yy["estimator"].isin(["adjusted_ols", "dml"]), "coverage_count"].eq(86).all()
csv_path = output_dir / "cell_diagnostics.csv"
output_dir.mkdir(parents=True, exist_ok=False)
diagnostics.to_csv(csv_path, index=False)
with zipfile.ZipFile(results_dir / "reproducibility.zip") as archive:
    raw_bootstrap_names = [name for name in archive.namelist() if "bootstrap" in name]
assert not raw_bootstrap_names

metadata = {
    "generated_at_utc": datetime.now(UTC).isoformat(),
    "purpose": "Read-only post-hoc diagnostics; no refit, method selection, or acceptance retuning",
    "source_results_dir": str(results_dir),
    "snapshot": str(snapshot),
    "frozen_revision": spec["environment"]["git_revision"],
    "frozen_source_sha256_verified": snapshot_source_hash,
    "frozen_protocol_hash": audit["protocol_fingerprint"],
    "reporting_seeds": [20001, 20100],
    "resolved_config_comparison": {
        "historical": frozen_config,
        "live": live_config,
        "differences": config_differences,
        "model_simulation_source_evaluation_settings_identical": True,
        "historical_training_calendar_days": training_days,
        "training_start_inclusive": frozen_config["source"]["start"],
        "training_end_exclusive": frozen_config["source"]["train_end"],
    },
    "source_checksums_verified": audit["source_checksums_verified"],
    "previous_statistical_review_checksums_verified": previous_hashes,
    "source_hashes_verified_again_after_diagnosis": True,
    "checks": audit["checks"],
    "counts": audit["counts"],
    "metric_definitions": {
        "empirical_theta_sd": "Sample SD across 100 independently seeded point estimates, ddof=1",
        "normal_equivalent_se_approximation": (
            "Mean percentile CI width / (2*1.96); approximation, not measured bootstrap SD"
        ),
        "truth_below_interval_count": "true_theta < theta_lower; interval wholly above truth",
        "truth_above_interval_count": "true_theta > theta_upper; interval wholly below truth",
    },
    "rct_y_y": rct_yy.replace({np.nan: None}).to_dict("records"),
    "limitations": [
        "Historical final reporting seeds are diagnostic evidence only; no development tuning.",
        (
            "Raw bootstrap draws were not saved for the 500 reporting jobs; actual bootstrap "
            "SD/skewness and quantile Monte Carlo error cannot be reconstructed."
        ),
        (
            "Width-derived normal-equivalent SE approximates percentile interval variability "
            "and cannot establish the mechanism of undercoverage."
        ),
        (
            "20 fixed TLC-context training days, five zones and 50 synthetic sessions/block; "
            "this is synthetic validation, not GSM evidence."
        ),
        "No new fit, bootstrap, or full benchmark rerun occurred.",
    ],
    "analysis_environment": {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "live_git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "analysis_script_sha256": file_hash(Path(__file__)),
        "validation_script_sha256": file_hash(review_path),
    },
    "output_checksums": {csv_path.name: file_hash(csv_path)},
}
for name, checksum in audit["source_checksums_verified"].items():
    assert file_hash(results_dir / name) == checksum, name
json_path = output_dir / "diagnostic.json"
json_path.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"counts": audit["counts"], "rct_y_y": metadata["rct_y_y"]}, indent=2))
print(f"OUTPUT {json_path} sha256={file_hash(json_path)}")
