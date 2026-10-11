from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import bootstrap, norm

from gsm_poc.core.artifacts import fingerprint, read_json, sha256_file, write_frame, write_json
from scripts import compare_week2_intervals as runner
from scripts import diagnose_week2_intervals as diagnostic


def test_bca_matches_scipy_on_same_distribution_and_delete_one_jackknife():
    data = np.arange(1, 21, dtype=float) ** 2
    scipy_result = bootstrap(
        (data,), np.mean, method="BCa", n_resamples=999, rng=np.random.default_rng(123)
    )
    jackknife = np.array([np.mean(np.delete(data, index)) for index in range(len(data))])
    result = runner.calculate_intervals(
        float(data.mean()), scipy_result.bootstrap_distribution, jackknife, 0.95
    )
    assert result["bca"]["reason"] is None
    assert result["bca"]["lower"] == pytest.approx(scipy_result.confidence_interval.low)
    assert result["bca"]["upper"] == pytest.approx(scipy_result.confidence_interval.high)
    assert result["basic"]["lower"] == 2 * data.mean() - result["percentile"]["upper"]
    assert result["basic"]["upper"] == 2 * data.mean() - result["percentile"]["lower"]
    assert result["basic"]["upper"] - result["basic"]["lower"] == pytest.approx(
        result["percentile"]["upper"] - result["percentile"]["lower"]
    )


def test_midrank_ties_and_symmetric_jackknife_give_zero_bias_and_acceleration():
    draws = np.tile(np.arange(11, dtype=float), 20)
    result = runner.calculate_intervals(5.0, draws, np.arange(20, dtype=float), 0.95)
    assert result["bca"]["bias_correction_z0"] == norm.ppf(0.5)
    assert result["bca"]["acceleration"] == 0
    assert result["bca"]["lower"] == pytest.approx(np.quantile(draws, 0.025))
    assert result["bca"]["upper"] == pytest.approx(np.quantile(draws, 0.975))


@pytest.mark.parametrize(
    "point,draws,jackknife,reason",
    [
        (0.5, np.linspace(0, 1, 199), [0.1, np.nan, 0.9], "failed_or_incomplete_jackknife"),
        (0.5, np.linspace(0, 1, 199), [0.5] * 20, "degenerate_distribution"),
        (0.5, np.full(199, 0.5), np.arange(20), "degenerate_distribution"),
        (2.0, np.linspace(0, 1, 199), np.arange(20), "nonfinite_bias_correction_or_acceleration"),
        (
            0.9,
            np.linspace(0, 1, 199),
            np.arange(20),
            "adjusted_probabilities_outside_empirical_tail_support",
        ),
    ],
)
def test_bca_unavailable_reasons_do_not_remove_baseline(point, draws, jackknife, reason):
    result = runner.calculate_intervals(point, draws, np.asarray(jackknife), 0.95)
    assert result["bca"]["reason"] == reason
    assert result["bca"]["lower"] is None and result["bca"]["upper"] is None
    assert result["percentile"]["lower"] is not None


@pytest.mark.parametrize(
    "point,draws,level",
    [
        (np.nan, [1, 2], 0.95),
        (1, [1], 0.95),
        (1, [1, np.inf], 0.95),
        (1, [[1, 2]], 0.95),
        (1, [1, 2], 1),
        (1, [1, 2], 0),
    ],
)
def test_invalid_interval_inputs_raise(point, draws, level):
    with pytest.raises(ValueError):
        runner.calculate_intervals(point, np.asarray(draws), np.arange(20), level)


def metric(seed, method, available=True, covered=True, width=1.0, theta=-0.5):
    return {
        "dgp_id": "RCT_SYN",
        "estimator": "adjusted_ols",
        "outcome": "Y",
        "treatment": "Y",
        "seed": seed,
        "interval_method": method,
        "source_kind": "semi_synthetic",
        "theta": theta,
        "error": theta + 0.5 if theta is not None else None,
        "covered": covered if available else None,
        "false_positive": None,
        "interval_available": available,
        "interval_width": width if available else None,
        "interval_status": "ok" if available else "unavailable",
        "requested_draws": 199,
        "successful_draws": 199 if theta is not None else 0,
        "scenario_probability_rmse": None,
        "bootstrap_failed_draws": 0,
        "bootstrap_not_attempted_draws": 0 if theta is not None else 199,
    }


def test_summary_retains_missing_failed_unavailable_and_matched_pair_denominators():
    rows = [
        metric(42001, "percentile", covered=False),
        metric(42002, "percentile"),
        metric(42003, "percentile", available=False, theta=None),
        metric(42001, "bca", covered=True, width=2),
        metric(42002, "bca", available=False),
        metric(42003, "bca", available=False, theta=None),
    ]
    frame = pd.DataFrame(rows)
    summary = runner.summarize_comparison(frame, 4).set_index("interval_method")
    baseline, bca = summary.loc["percentile"], summary.loc["bca"]
    assert baseline.coverage_denominator == 2 and baseline.coverage == 0.5
    assert bca.coverage_denominator == 1 and bca.coverage == 1
    assert bca.available_intervals == 1 and bca.unavailable_intervals == 2
    assert bca.valid_estimates == 2 and bca.failed_or_unidentified_estimates == 1
    assert bca.attempted_seeds == 3 and bca.missing_seed_jobs == 1
    assert bca.paired_available_seeds == 1 and bca.paired_coverage_denominator == 1
    assert bca.paired_coverage_change == 1 and bca.paired_coverage_gains == 1
    assert bca.paired_coverage_losses == 0 and bca.mean_paired_width_ratio == 2
    assert bca.not_attempted_bootstrap_draws == 199
    assert bca.coverage_lower < 1 and bca.coverage_upper == 1
    with pytest.raises(ValueError, match="Duplicate"):
        runner.summarize_comparison(pd.concat([frame, frame.iloc[[0]]]), 4)


def source_context(config):
    root = config.workspace / "context"
    root.mkdir()
    write_frame(
        root / "context_templates.parquet",
        pd.DataFrame(
            [
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
        ),
    )
    write_json(
        root / "context_templates.json",
        {
            "fit_start": config.source.start,
            "fit_end_exclusive": config.source.train_end,
            "context_version": "fixture",
        },
    )
    return root


def test_small_comparison_preserves_percentile_refits_every_day_and_refuses_overwrite(config):
    diagnostic_root, output_root = config.workspace / "diagnostic", config.workspace / "comparison"
    diagnostic.run_diagnostic(
        config, source_context(config), diagnostic_root, [42001], ["RCT_SYN"], ["adjusted_ols"], 199
    )
    status = runner.run_comparison(diagnostic_root, output_root, workspace=config.workspace)
    assert status["status"] == "completed"
    baseline = pd.read_parquet(diagnostic_root / "seed_metrics.parquet")
    metrics = pd.read_parquet(output_root / "seed_metrics.parquet")
    assert len(metrics) == 12 and set(metrics.interval_method) == set(runner.INTERVAL_METHODS)
    assert metrics.development_only.all()
    assert not any(column.startswith("elasticity") for column in metrics)
    actual = metrics.loc[metrics.interval_method.eq("percentile")].reset_index(drop=True)
    for column in ("theta", "theta_lower", "theta_upper", "covered", "false_positive", "error"):
        assert actual[column].tolist() == baseline[column].tolist()
    jackknife = pd.read_parquet(output_root / "RCT_SYN-42001-adjusted_ols-jackknife.parquet")
    assert len(jackknife) == 20 and jackknife.status.eq("succeeded").all()
    protocol = read_json(output_root / "protocol.json")
    body = {key: value for key, value in protocol.items() if key != "protocol_hash"}
    assert fingerprint(body) == protocol["protocol_hash"] == status["protocol_hash"]
    assert (
        protocol["source_config"] == read_json(diagnostic_root / "protocol.json")["source_config"]
    )
    assert protocol["maximum_point_refits"] == 1
    assert protocol["maximum_jackknife_refits"] == 20
    assert all(
        sha256_file(output_root / name) == expected
        for name, expected in status["artifacts"].items()
    )
    with pytest.raises(FileExistsError):
        runner.run_comparison(diagnostic_root, output_root, workspace=config.workspace)


def test_checksum_failure_precedes_dataframe_load_or_output_creation(config, monkeypatch):
    root = config.workspace / "diagnostic"
    diagnostic.run_diagnostic(
        config, source_context(config), root, [42001], ["RCT_SYN"], ["adjusted_ols"], 199
    )
    (root / "summary.csv").write_text("tampered", encoding="utf-8")

    def forbid_load(*args, **kwargs):
        raise AssertionError("Dataframe must not be loaded before checksums pass")

    monkeypatch.setattr(runner.pd, "read_parquet", forbid_load)
    output = config.workspace / "comparison"
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.run_comparison(root, output, workspace=config.workspace)
    assert not output.exists()


def test_failed_day_refit_is_retained_and_makes_bca_unavailable(config, generated, monkeypatch):
    calls = []
    actual_fit = runner.fit_estimator
    train = runner.date_splits(generated.blocks, config)["train"]

    def fail_first(train_subset, actual_config, estimator, seed=None):
        calls.append(set(train_subset.original_day_id))
        if len(calls) == 1:
            raise ValueError("deliberate jackknife failure")
        return actual_fit(train_subset, actual_config, estimator, seed=seed)

    monkeypatch.setattr(runner, "fit_estimator", fail_first)
    jackknife = runner.day_jackknife(train, config, "adjusted_ols")
    assert len(calls) == 20 and all(len(days) == 19 for days in calls)
    assert jackknife.status.eq("failed").sum() == 1
    assert jackknife.iloc[0].error == "deliberate jackknife failure"
    draws = np.linspace(-0.6, -0.4, 199)
    low, high = runner.percentile_interval(draws, 0.95)
    saved = pd.DataFrame(
        [
            {
                **metric(42001, "percentile"),
                "theta_lower": low,
                "theta_upper": high,
                "true_theta": -0.5,
            }
        ]
    )
    raw = pd.DataFrame({"status": ["succeeded"] * 199, "theta_yy": draws})
    rows = runner.comparison_rows(saved, raw, jackknife, 0.95)
    bca = next(row for row in rows if row["interval_method"] == "bca")
    assert not bca["interval_available"]
    assert bca["unavailable_reason"] == "failed_or_incomplete_jackknife"
    assert all(row["theta"] == -0.5 for row in rows)


def test_comparison_rejects_insufficient_draw_budget_before_output(config):
    root = config.workspace / "diagnostic"
    diagnostic.run_diagnostic(
        config, source_context(config), root, [42001], ["RCT_SYN"], ["adjusted_ols"], 3
    )
    with pytest.raises(ValueError, match="at least 199"):
        runner.run_comparison(root, config.workspace / "comparison", workspace=config.workspace)


def test_failed_source_metrics_preserve_completed_draws_and_all_unavailable_methods():
    saved = pd.DataFrame(
        [
            {
                **metric(42001, "percentile", available=False, theta=None),
                "outcome": outcome,
                "treatment": treatment,
                "successful_draws": 199,
                "status": "failed",
                "interval_status": "interval_unstable",
            }
            for outcome in ("X", "Y")
            for treatment in ("X", "Y")
        ]
    )
    raw = pd.DataFrame(
        {
            "status": ["succeeded"] * 199,
            **{column: np.linspace(-0.6, -0.4, 199) for column in runner.COEFFICIENT_COLUMNS},
        }
    )
    jackknife = pd.DataFrame({"status": ["not_attempted"] * 20})
    rows = pd.DataFrame(runner.comparison_rows(saved, raw, jackknife, 0.95))
    assert len(rows) == 12 and not rows.interval_available.any()
    assert rows.successful_draws.eq(199).all() and rows.status.eq("failed").all()
    assert rows.source_interval_status.eq("interval_unstable").all()
    assert rows.covered.isna().all()
