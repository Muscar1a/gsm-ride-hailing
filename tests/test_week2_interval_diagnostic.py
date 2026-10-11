from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gsm_poc.core.artifacts import read_json, sha256_file, write_frame, write_json

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/diagnose_week2_intervals.py"
SPEC = importlib.util.spec_from_file_location("interval_diagnostic_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize(
    "seeds,dgps,estimators,draws",
    [
        ([20001], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([20100], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([19001], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([41001, 41001], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([-1], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([True], ["RCT_SYN"], ["adjusted_ols"], 199),
        ([41001], ["HIDDEN_CONFOUNDING"], ["adjusted_ols"], 199),
        ([41001], ["RCT_SYN", "RCT_SYN"], ["adjusted_ols"], 199),
        ([41001], ["RCT_SYN"], ["adjusted_ols", "adjusted_ols"], 199),
        ([41001], ["RCT_SYN"], ["unknown"], 199),
        ([41001], ["RCT_SYN"], ["adjusted_ols"], 0),
        ([41001], ["RCT_SYN"], ["adjusted_ols"], 2000),
    ],
)
def test_protocol_rejects_reserved_duplicate_or_invalid_inputs(
    config, seeds, dgps, estimators, draws
):
    with pytest.raises(ValueError):
        runner.validate_protocol(config, seeds, dgps, estimators, draws)


def test_source_checksums_detect_changed_and_missing_files(tmp_path):
    path = tmp_path / "context.json"
    path.write_text("source", encoding="utf-8")
    checksums = {path.name: sha256_file(path)}
    runner.verify_sources(tmp_path, checksums)
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.verify_sources(tmp_path, checksums)
    path.unlink()
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.verify_sources(tmp_path, checksums)


def diagnostic_row(seed, theta, low, high, records):
    row = {
        "dgp_id": "RCT_SYN",
        "seed": seed,
        "estimator": "adjusted_ols",
        "outcome": "Y",
        "treatment": "Y",
        "source_kind": "semi_synthetic",
        "error": theta + 0.5 if theta is not None else None,
        "theta": theta,
        "theta_lower": low,
        "theta_upper": high,
        "true_theta": -0.5,
        "covered": low <= -0.5 <= high if low is not None else None,
        "false_positive": None,
        "interval_status": "ok" if low is not None else "interval_unstable",
        "requested_draws": 4,
        "successful_draws": sum(record["status"] == "succeeded" for record in records),
        "scenario_probability_rmse": None,
    }
    return runner.add_draw_diagnostics([row], records, 0.95)[0]


def test_summary_uses_raw_sample_sd_and_retains_failure_and_miss_denominators():
    first = [{"status": "succeeded", "theta_yy": value} for value in (-0.7, -0.5, -0.3)]
    second = [{"status": "succeeded", "theta_yy": value} for value in (-0.4, -0.3)] + [
        {"status": "failed"}
    ]
    rows = [
        diagnostic_row(41001, -0.6, -0.8, -0.55, first),
        diagnostic_row(41002, -0.3, -0.4, -0.2, second),
        diagnostic_row(41003, None, None, None, []),
    ]
    summary = runner.summarize_diagnostics(pd.DataFrame(rows), 4).iloc[0]
    expected_sd = np.std([-0.6, -0.3], ddof=1)
    assert summary.empirical_estimate_sd == pytest.approx(expected_sd)
    expected_bootstrap_sd = np.sqrt(
        np.mean([np.std([-0.7, -0.5, -0.3], ddof=1) ** 2, np.std([-0.4, -0.3], ddof=1) ** 2])
    )
    assert summary.rms_bootstrap_sd == pytest.approx(expected_bootstrap_sd)
    assert summary.bootstrap_to_empirical_sd_ratio == pytest.approx(
        expected_bootstrap_sd / expected_sd
    )
    assert summary.coverage_denominator == 2
    assert summary.coverage == 0
    assert summary.miss_interval_below_truth == 1
    assert summary.miss_interval_above_truth == 1
    assert summary.attempted_seeds == 3 and summary.expected_seeds == 4
    assert summary.valid_estimates == 2 and summary.failed_or_unidentified_estimates == 1
    assert summary.failed_bootstrap_draws == 1
    assert summary.not_attempted_bootstrap_draws == 6
    assert summary.bootstrap_requested_total == 12 and summary.bootstrap_successful_total == 5
    with pytest.raises(ValueError, match="Duplicate"):
        runner.summarize_diagnostics(pd.DataFrame([rows[0], rows[0]]), 4)


def test_nested_endpoints_use_first_199_requested_draws_with_failures_retained():
    records = [
        {"draw_id": index, "status": "succeeded", "theta_yy": float(index)} for index in range(210)
    ]
    records[0] = {"draw_id": 0, "status": "failed"}
    low, high = runner.percentile_interval(np.arange(1, 210), 0.95)
    row = diagnostic_row(41001, 105, float(low), float(high), [])
    row["requested_draws"] = 210
    row = runner.add_draw_diagnostics([row], records, 0.95)[0]
    prefix_low, prefix_high = runner.percentile_interval(np.arange(1, 199), 0.95)
    assert row["prefix_199_lower"] == pytest.approx(prefix_low)
    assert row["prefix_199_upper"] == pytest.approx(prefix_high)
    assert row["prefix_199_successful_draws"] == 198
    assert row["upper_endpoint_change_from_199"] == pytest.approx(high - prefix_high)


def test_sd_ratio_unavailable_when_failed_metric_retains_draws_from_an_unmatched_seed():
    records = [{"status": "succeeded", "theta_yy": value} for value in (-0.7, -0.5, -0.3)]
    failed_metric_records = [
        {"status": "succeeded", "theta_yy": value} for value in (-1.0, 0.0, 1.0)
    ]
    rows = [
        diagnostic_row(41001, -0.6, -0.8, -0.4, records),
        diagnostic_row(41002, -0.3, -0.6, -0.2, records),
        diagnostic_row(41003, None, None, None, failed_metric_records),
    ]
    summary = runner.summarize_diagnostics(pd.DataFrame(rows), 3).iloc[0]
    assert summary.sd_comparison_status == "unmatched_seed_cohorts"
    assert pd.isna(summary.bootstrap_to_empirical_sd_ratio)
    assert summary.empirical_estimate_sd == pytest.approx(np.std([-0.6, -0.3], ddof=1))
    assert summary.rms_bootstrap_sd == pytest.approx(np.sqrt(np.mean([0.2**2, 0.2**2, 1.0])))
    assert summary.bootstrap_sd_denominator == 3
    assert summary.valid_estimates == 2 and summary.failed_or_unidentified_estimates == 1
    assert summary.coverage_denominator == 2 and summary.bootstrap_successful_total == 9


def source_context(config):
    root = config.workspace / "context"
    root.mkdir()
    rows = [
        {
            "zone_id": zone,
            "hour": hour,
            "is_weekend": weekend,
            "distance_scaled": 0.5,
            "context_id": "fixture",
            "fallback_level": 0,
        }
        for zone in config.source.zones
        for hour in range(24)
        for weekend in (0, 1)
    ]
    write_frame(root / "context_templates.parquet", pd.DataFrame(rows))
    write_json(
        root / "context_templates.json",
        {
            "fit_start": config.source.start,
            "fit_end_exclusive": config.source.train_end,
            "context_version": "fixture",
        },
    )
    return root


def test_small_diagnostic_freezes_protocol_draws_and_refuses_overwrite(config):
    context_root = source_context(config)
    checksums = {path.name: sha256_file(path) for path in context_root.iterdir()}
    output = config.workspace / "diagnostic"
    status = runner.run_diagnostic(
        config, context_root, output, [41001], ["RCT_SYN"], ["adjusted_ols"], 3
    )
    assert status["status"] == "completed"
    protocol = read_json(output / "protocol.json")
    assert runner.fingerprint(protocol["source_config"]) == runner.fingerprint(config.as_dict())
    assert protocol["context_sha256"] == checksums
    assert protocol["reporting_min_draws"] == 199
    assert protocol["maximum_bootstrap_refits"] == 3
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    raw_draws = pd.read_parquet(output / "RCT_SYN-41001-adjusted_ols-draws.parquet")
    assert len(raw_draws) == 3 and len(metrics) == 4
    assert metrics.interval_status.eq("interval_unstable").all()
    assert metrics.interval_scope.eq("individual").all()
    assert metrics.interval_calibration_status.eq("not_evaluated_for_this_run").all()
    assert raw_draws.status.eq("succeeded").all()
    assert metrics.loc[metrics.outcome.eq("Y") & metrics.treatment.eq("Y"), "bootstrap_sd"].iloc[
        0
    ] == pytest.approx(raw_draws.theta_yy.std(ddof=1))
    assert all(
        sha256_file(output / name) == expected for name, expected in status["artifacts"].items()
    )
    with pytest.raises(FileExistsError):
        runner.run_diagnostic(
            config, context_root, output, [41002], ["RCT_SYN"], ["adjusted_ols"], 3
        )
    assert read_json(output / "protocol.json")["seeds"] == [41001]
    assert {path.name: sha256_file(path) for path in context_root.iterdir()} == checksums


def test_wrong_training_context_rejected_before_creating_output(config):
    context_root = source_context(config)
    metadata_path = context_root / "context_templates.json"
    metadata = read_json(metadata_path)
    metadata["fit_end_exclusive"] = "2024-01-22"
    write_json(metadata_path, metadata)
    output = config.workspace / "diagnostic"
    with pytest.raises(ValueError, match="training dates"):
        runner.run_diagnostic(
            config, context_root, output, [41001], ["RCT_SYN"], ["adjusted_ols"], 3
        )
    assert not output.exists()


def test_metric_failure_retains_successful_raw_draws_and_failed_estimate_denominators(
    config, monkeypatch
):
    context_root = source_context(config)
    output = config.workspace / "diagnostic"

    def fail_metrics(*args):
        raise ValueError("deliberate metric failure")

    monkeypatch.setattr(runner, "method_metrics", fail_metrics)
    status = runner.run_diagnostic(
        config, context_root, output, [41001], ["RCT_SYN"], ["adjusted_ols"], 3
    )
    assert status["status"] == "completed_with_failures"
    raw_draws = pd.read_parquet(output / "RCT_SYN-41001-adjusted_ols-draws.parquet")
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    summary = pd.read_csv(output / "summary.csv")
    assert len(raw_draws) == 3 and raw_draws.status.eq("succeeded").all()
    assert metrics.successful_draws.eq(3).all()
    assert metrics.bootstrap_attempted_draws.eq(3).all()
    assert summary.coverage_denominator.eq(0).all()
    assert summary.valid_estimates.eq(0).all()
    assert summary.failed_or_unidentified_estimates.eq(1).all()
    assert summary.failed_bootstrap_draws.eq(0).all()
    assert metrics.error_message.eq("deliberate metric failure").all()
