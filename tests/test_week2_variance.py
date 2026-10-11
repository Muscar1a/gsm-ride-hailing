from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from scipy.stats import t

from gsm_poc.core.artifacts import fingerprint, read_json, sha256_file, write_frame, write_json
from scripts import compare_week2_variance as runner


def test_mean_jackknife_matches_textbook_sample_mean_t_interval_and_original_center():
    values = np.arange(20, dtype=float)
    jackknife = np.array([np.delete(values, index).mean() for index in range(20)])
    result = runner.jackknife_interval(values.mean(), jackknife, 0.95)
    assert result["jackknife_variance"] == pytest.approx(values.var(ddof=1) / 20)
    assert result["jackknife_variance"] == pytest.approx(1.75)
    assert result["jackknife_df"] == 19 and result["jackknife_groups"] == 20
    assert result["jackknife_critical_value"] == t.ppf(0.975, 19)
    assert result["lower"] == pytest.approx(6.731189431979745)
    assert result["upper"] == pytest.approx(12.268810568020255)
    shifted = runner.jackknife_interval(100.0, jackknife, 0.95)
    assert (shifted["lower"] + shifted["upper"]) / 2 == 100
    assert shifted["jackknife_variance"] == result["jackknife_variance"]


@pytest.mark.parametrize(
    "values", [np.ones(20), [1, np.nan, 3], [1, np.inf, 3], [1, 2], [[1, 2, 3]]]
)
def test_invalid_or_degenerate_jackknife_is_unavailable_without_fallback(values):
    result = runner.jackknife_interval(0.5, np.asarray(values), 0.95)
    assert result["lower"] is None and result["upper"] is None and result["reason"] is not None


def test_invalid_level_raises_and_nonfinite_point_is_unavailable():
    with pytest.raises(ValueError):
        runner.jackknife_interval(0.5, np.arange(20), 1)
    assert (
        runner.jackknife_interval(np.nan, np.arange(20), 0.95)["reason"]
        == "missing_or_nonfinite_estimates"
    )


def jackknife_frame():
    days = [(dt.date(2024, 1, 1) + dt.timedelta(days=offset)).isoformat() for offset in range(20)]
    values = np.linspace(-0.51, -0.49, 20)
    return pd.DataFrame(
        {
            "omitted_original_day_id": days,
            "status": ["succeeded"] * 20,
            **{column: values for column in runner.COEFFICIENT_COLUMNS},
        }
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        ("missing", "incomplete_original_day_omissions"),
        ("duplicate", "missing_or_duplicate_omission_keys"),
        ("failed", "failed_original_day_refit"),
        ("nonfinite", "missing_or_nonfinite_coefficients"),
    ],
)
def test_all_twenty_unique_successful_finite_omissions_are_required(change, reason):
    frame = jackknife_frame()
    days = set(frame.omitted_original_day_id)
    if change == "missing":
        frame = frame.iloc[1:]
    elif change == "duplicate":
        frame.loc[0, "omitted_original_day_id"] = frame.loc[1, "omitted_original_day_id"]
    elif change == "failed":
        frame.loc[0, "status"] = "failed"
    else:
        frame.loc[0, "theta_xy"] = np.nan
    assert runner.jackknife_failure(frame, days) == reason


def comparison_fixture(config, failed=False):
    root, diagnostic_root = config.workspace / "comparison", config.workspace / "diagnostic"
    root.mkdir()
    diagnostic_root.mkdir()
    (diagnostic_root / "frozen.txt").write_text("source", encoding="utf-8")
    rows = [
        {
            "dgp_id": "RCT_SYN",
            "seed": 42001,
            "estimator": "adjusted_ols",
            "outcome": outcome,
            "treatment": treatment,
            "interval_method": method,
            "source_kind": "semi_synthetic",
            "theta": -0.5,
            "error": 0.0,
            "true_theta": -0.5,
            "covered": True,
            "false_positive": None,
            "interval_available": True,
            "theta_lower": -0.51,
            "theta_upper": -0.49,
            "interval_width": 0.02,
            "interval_status": "ok",
            "source_interval_status": "interval_unstable",
            "status": "ok",
            "requested_draws": 7,
            "successful_draws": 7,
            "scenario_probability_rmse": None,
            "bootstrap_failed_draws": 0,
            "bootstrap_not_attempted_draws": 0,
            "development_only": True,
            "interval_scope": "individual theta only",
            "interval_calibration_status": "not_final_calibration",
        }
        for outcome in ("X", "Y")
        for treatment in ("X", "Y")
        for method in runner.INTERVAL_METHODS
    ]
    metrics = pd.DataFrame(rows)
    name = "RCT_SYN-42001-adjusted_ols"
    write_frame(root / f"{name}-metrics.parquet", metrics)
    write_frame(root / "seed_metrics.parquet", metrics)
    frame = jackknife_frame()
    if failed:
        frame.loc[0, "status"] = "failed"
    write_frame(root / f"{name}-jackknife.parquet", frame)
    write_json(root / f"{name}.json", {"status": "succeeded"})
    (root / "summary.csv").write_text("source-summary\n", encoding="utf-8")
    (root / "runner_source.py").write_bytes(
        runner.Path(runner.__file__).with_name("compare_week2_intervals.py").read_bytes()
    )
    protocol = {
        "interval_methods": list(runner.INTERVAL_METHODS),
        "dgps": ["RCT_SYN"],
        "seeds": [42001],
        "estimators": ["adjusted_ols"],
        "source_config": config.as_dict(),
        "bootstrap_draws": 7,
        "script_sha256": sha256_file(root / "runner_source.py"),
        "diagnostic_root": str(diagnostic_root),
        "source_artifact_sha256": {"frozen.txt": sha256_file(diagnostic_root / "frozen.txt")},
    }
    protocol["protocol_hash"] = fingerprint(protocol)
    write_json(root / "protocol.json", protocol)
    status = {
        "status": "completed_with_failures" if failed else "completed",
        "protocol_hash": protocol["protocol_hash"],
        "completed_estimator_jobs": 1,
        "artifacts": {path.name: sha256_file(path) for path in root.iterdir()},
    }
    write_json(root / "status.json", status)
    return root, metrics


def test_zero_fit_postprocessor_preserves_old_cells_freezes_hashes_and_refuses_overwrite(config):
    root, previous = comparison_fixture(config)
    original = {path.name: sha256_file(path) for path in root.iterdir()}
    output = config.workspace / "variance"
    status = runner.run_variance(root, output, workspace=config.workspace)
    assert status["status"] == "completed" and status["new_fits"] == 0
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    pd.testing.assert_frame_equal(
        metrics.iloc[:12][previous.columns].reset_index(drop=True), previous
    )
    candidate = metrics.loc[metrics.interval_method.eq(runner.INTERVAL_METHOD)]
    assert len(candidate) == 4 and candidate.interval_available.all()
    assert candidate.interval_status.eq("ok").all()
    assert candidate.source_interval_status.eq("interval_unstable").all()
    assert candidate.requested_draws.eq(7).all() and candidate.jackknife_df.eq(19).all()
    assert (candidate.theta_lower + candidate.theta_upper).eq(-1).all()
    protocol = read_json(output / "protocol.json")
    assert protocol["maximum_new_fits"] == 0 and protocol["development_only"]
    assert all(
        sha256_file(output / name) == expected for name, expected in status["artifacts"].items()
    )
    assert original == {path.name: sha256_file(path) for path in root.iterdir()}
    summary = pd.read_csv(output / "summary.csv")
    assert (
        summary.loc[summary.interval_method.eq(runner.INTERVAL_METHOD), "sd_comparison_status"]
        .eq("insufficient_replicates")
        .all()
    )
    with pytest.raises(FileExistsError):
        runner.run_variance(root, output, workspace=config.workspace)


def test_failed_omission_keeps_four_unavailable_candidates_and_failure_denominators(config):
    root, _ = comparison_fixture(config, failed=True)
    output = config.workspace / "variance"
    status = runner.run_variance(root, output, workspace=config.workspace)
    assert status["unavailable_candidate_intervals"] == 4
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    candidate = metrics.loc[metrics.interval_method.eq(runner.INTERVAL_METHOD)]
    assert candidate.unavailable_reason.eq("failed_original_day_refit").all()
    assert candidate.jackknife_failed_groups.eq(1).all() and candidate.jackknife_groups.eq(20).all()
    summary = pd.read_csv(output / "summary.csv")
    candidate_summary = summary.loc[summary.interval_method.eq(runner.INTERVAL_METHOD)]
    assert candidate_summary.unavailable_intervals.eq(1).all()
    assert candidate_summary.paired_available_seeds.eq(0).all()
    assert candidate_summary.jackknife_failed_groups_total.eq(1).all()
    assert candidate_summary.sd_comparison_status.eq("unmatched_seed_cohorts").all()
    assert candidate_summary.jackknife_to_empirical_sd_ratio.isna().all()


def test_checksum_validation_precedes_dataframes_and_output_creation(config, monkeypatch):
    root, _ = comparison_fixture(config)
    (root / "summary.csv").write_text("tampered", encoding="utf-8")

    def forbid_load(*args, **kwargs):
        raise AssertionError("No dataframe load before all hashes pass")

    monkeypatch.setattr(runner.pd, "read_parquet", forbid_load)
    output = config.workspace / "variance"
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.run_variance(root, output, workspace=config.workspace)
    assert not output.exists()


def test_outside_root_artifact_path_is_rejected(config):
    root, _ = comparison_fixture(config)
    path = root / "status.json"
    status = read_json(path)
    status["artifacts"]["../diagnostic/frozen.txt"] = sha256_file(
        config.workspace / "diagnostic/frozen.txt"
    )
    write_json(path, status)
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.run_variance(root, config.workspace / "variance", workspace=config.workspace)


def test_unattempted_refits_are_not_counted_as_attempts_or_fit_failures():
    frame = jackknife_frame()
    frame["status"] = "not_attempted"
    baseline = pd.DataFrame(
        [
            {
                "theta": -0.5,
                "outcome": "Y",
                "treatment": "Y",
                "true_theta": -0.5,
                "interval_method": "percentile",
                "source_interval_status": "interval_unstable",
            }
        ]
    )
    row = runner.variance_rows(baseline, frame, set(frame.omitted_original_day_id), 0.95)[0]
    assert not row["interval_available"]
    assert row["unavailable_reason"] == "unattempted_original_day_refit"
    assert row["jackknife_groups"] == 20
    assert row["jackknife_attempted_groups"] == 0 and row["jackknife_failed_groups"] == 0
    assert row["jackknife_not_attempted_groups"] == 20 and row["jackknife_missing_groups"] == 0


def test_all_three_source_methods_require_the_full_coefficient_cartesian_product(config):
    root, metrics = comparison_fixture(config)
    metrics.loc[
        metrics.interval_method.eq("basic") & metrics.outcome.eq("Y") & metrics.treatment.eq("Y"),
        "outcome",
    ] = "Z"
    write_frame(root / "seed_metrics.parquet", metrics)
    write_frame(root / "RCT_SYN-42001-adjusted_ols-metrics.parquet", metrics)
    state = read_json(root / "status.json")
    for name in ("seed_metrics.parquet", "RCT_SYN-42001-adjusted_ols-metrics.parquet"):
        state["artifacts"][name] = sha256_file(root / name)
    write_json(root / "status.json", state)
    with pytest.raises(ValueError, match="twelve unique"):
        runner.run_variance(root, config.workspace / "variance", workspace=config.workspace)
