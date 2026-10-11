from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from test_week2_variance import comparison_fixture

from gsm_poc.core.artifacts import (
    environment,
    fingerprint,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from scripts import pilot_week2_dml_variance as runner


@pytest.mark.parametrize(
    "seed_start,seeds,dgps",
    [
        (20001, 1, ["RCT_SYN"]),
        (41001, 1, ["RCT_SYN"]),
        (42001, 1, ["RCT_SYN"]),
        (43000, 1, ["RCT_SYN"]),
        (43005, 2, ["RCT_SYN"]),
        (43001, 0, ["RCT_SYN"]),
        (43001, 6, ["RCT_SYN"]),
        (True, 1, ["RCT_SYN"]),
        (43001, True, ["RCT_SYN"]),
        (43001, 1, []),
        (43001, 1, ["RCT_SYN", "RCT_SYN"]),
        (43001, 1, ["HIDDEN_CONFOUNDING"]),
    ],
)
def test_pilot_rejects_old_seeds_invalid_bounds_and_dgps(seed_start, seeds, dgps):
    with pytest.raises(ValueError):
        runner.validate_pilot(seed_start, seeds, dgps)


def pilot_source(config):
    root, _ = comparison_fixture(config)
    source = read_json(root / "protocol.json")
    diagnostic_root = runner.Path(source["diagnostic_root"])
    context_root = diagnostic_root / "source_context"
    context_root.mkdir()
    write_frame(
        context_root / "context_templates.parquet",
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
        context_root / "context_templates.json",
        {
            "fit_start": config.source.start,
            "fit_end_exclusive": config.source.train_end,
            "context_version": "fixture",
        },
    )
    checksums = {path.name: sha256_file(path) for path in context_root.iterdir()}
    write_json(
        diagnostic_root / "protocol.json",
        {"context_sha256": checksums, "context_version": "fixture"},
    )
    source["environment"] = environment(config.workspace)
    source["source_artifact_sha256"] = {
        path.relative_to(diagnostic_root).as_posix(): sha256_file(path)
        for path in diagnostic_root.rglob("*")
        if path.is_file()
    }
    source["protocol_hash"] = fingerprint(
        {key: value for key, value in source.items() if key != "protocol_hash"}
    )
    write_json(root / "protocol.json", source)
    state = read_json(root / "status.json")
    state["protocol_hash"] = source["protocol_hash"]
    state["artifacts"]["protocol.json"] = sha256_file(root / "protocol.json")
    write_json(root / "status.json", state)
    return root


def fake_fitters(monkeypatch, fail_point=False, fail_jackknife=False):
    calls = []

    def point_fit(blocks, config):
        estimator = config.model.estimators[0]
        assert config.model.estimators == (estimator,)
        calls.append(("point", estimator, config.simulation.seed, set(blocks.seed)))
        if fail_point and estimator == "dml":
            raise ValueError("deliberate point validation failure")
        result = SimpleNamespace(
            bundle=SimpleNamespace(
                active_treatments=(0, 1), theta=np.array([[-0.6, 0.15], [0.10, -0.5]])
            ),
            diagnostics={"status": "ok", "validation_probability_valid": True},
        )
        return {estimator: result}, {}

    def omission_fit(train, config, estimator):
        assert set(train.day_id) == set(train.original_day_id)
        assert len(set(train.original_day_id)) == 20
        assert train.seed.eq(config.simulation.seed).all()
        calls.append(("jackknife", estimator, config.simulation.seed, set(train.original_day_id)))
        frame = pd.DataFrame(
            {
                "omitted_original_day_id": sorted(set(train.original_day_id)),
                "status": ["succeeded"] * 20,
                **{
                    name: center + np.linspace(-0.01, 0.01, 20)
                    for name, center in zip(
                        ("theta_xx", "theta_xy", "theta_yx", "theta_yy"),
                        (-0.6, 0.15, 0.10, -0.5),
                        strict=True,
                    )
                },
            }
        )
        if fail_jackknife and estimator == "dml":
            frame.loc[0, "status"] = "failed"
            frame.loc[0, "error"] = "deliberate omission failure"
        return frame

    monkeypatch.setattr(runner, "fit_all", point_fit)
    monkeypatch.setattr(runner, "day_jackknife", omission_fit)
    return calls


def test_fresh_pilot_freezes_before_generation_preserves_source_and_never_bootstraps(
    config, monkeypatch
):
    root = pilot_source(config)
    checksums = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    calls = fake_fitters(monkeypatch)
    output = config.workspace / "pilot"
    actual_generate = runner.generate

    def checked_generate(actual_config, context, context_version):
        protocol = read_json(output / "protocol.json")
        assert protocol["maximum_bootstrap_fits"] == 0
        assert protocol["maximum_total_fits"] == 42
        assert protocol["seeds"] == [43001]
        data = actual_generate(actual_config, context, context_version)
        data.oracle = None
        return data

    monkeypatch.setattr(runner, "generate", checked_generate)
    status = runner.run_pilot(root, output, 43001, 1, ["RCT_SYN"], workspace=config.workspace)
    assert status["status"] == "completed"
    assert status["point_attempted"] == 2 and status["point_successful"] == 2
    assert status["jackknife_attempted"] == 40 and status["jackknife_successful"] == 40
    assert status["bootstrap_attempted"] == 0
    assert {call[2] for call in calls} == {43001}
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    assert (
        len(metrics) == 8
        and metrics.requested_draws.eq(0).all()
        and metrics.successful_draws.eq(0).all()
    )
    assert metrics.jackknife_df.eq(19).all() and metrics.interval_available.all()
    assert (
        metrics.development_only.all() and metrics.source_interval_status.eq("not_applicable").all()
    )
    state = read_json(output / "RCT_SYN-43001-dml.json")
    assert len(state["day_folds"]["full"]) == config.model.folds
    assert len(state["day_folds"]["omissions"]) == 20
    for omitted, folds in state["day_folds"]["omissions"].items():
        assert all(
            omitted not in fold["train_original_days"] + fold["validation_original_days"]
            for fold in folds
        )
    summary = pd.read_csv(output / "summary.csv")
    assert summary.interval_method.eq("day_jackknife_t").all()
    assert summary.sd_comparison_status.eq("insufficient_replicates").all()
    paired = pd.read_csv(output / "paired_estimators.csv")
    assert paired.paired_available_intervals.eq(1).all()
    assert paired.mean_paired_width_ratio_dml_over_ols.eq(1).all()
    assert all(sha256_file(output / name) == digest for name, digest in status["artifacts"].items())
    assert checksums == {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(FileExistsError):
        runner.run_pilot(root, output, 43001, 1, ["RCT_SYN"], workspace=config.workspace)


def test_point_failure_retains_four_failed_cells_twenty_unattempted_omissions_and_ols(
    config, monkeypatch
):
    root = pilot_source(config)
    calls = fake_fitters(monkeypatch, fail_point=True)
    output = config.workspace / "pilot"
    status = runner.run_pilot(root, output, 43001, 1, ["RCT_SYN"], workspace=config.workspace)
    assert status["status"] == "completed_with_failures"
    assert status["point_attempted"] == 2 and status["point_failed"] == 1
    assert status["jackknife_attempted"] == 20 and status["jackknife_failed"] == 0
    assert status["jackknife_not_attempted"] == 20
    assert not any(call[0] == "jackknife" and call[1] == "dml" for call in calls)
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    dml = metrics.loc[metrics.estimator.eq("dml")]
    assert len(dml) == 4 and dml.theta.isna().all() and dml.covered.isna().all()
    assert not dml.interval_available.any() and dml.jackknife_not_attempted_groups.eq(20).all()
    assert metrics.loc[metrics.estimator.eq("adjusted_ols"), "interval_available"].all()
    summary = pd.read_csv(output / "summary.csv")
    assert summary.loc[summary.estimator.eq("dml"), "coverage_denominator"].eq(0).all()


def test_failed_omission_makes_dml_unavailable_without_dropping_point_or_null_denominators(
    config, monkeypatch
):
    root = pilot_source(config)
    fake_fitters(monkeypatch, fail_jackknife=True)
    output = config.workspace / "pilot"
    status = runner.run_pilot(root, output, 43001, 1, ["NULL_EFFECT"], workspace=config.workspace)
    assert status["point_successful"] == 2 and status["jackknife_attempted"] == 40
    assert status["jackknife_failed"] == 1 and status["jackknife_successful"] == 39
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    dml = metrics.loc[metrics.estimator.eq("dml")]
    assert dml.theta.notna().all() and not dml.interval_available.any()
    assert dml.false_positive.isna().all() and dml.covered.isna().all()
    assert metrics.loc[metrics.estimator.eq("adjusted_ols"), "false_positive"].notna().all()
    summary = pd.read_csv(output / "summary.csv")
    assert (
        summary.loc[summary.estimator.eq("dml"), "sd_comparison_status"]
        .eq("unmatched_seed_cohorts")
        .all()
    )
    paired = pd.read_csv(output / "paired_estimators.csv")
    assert paired.paired_point_seeds.eq(1).all() and paired.paired_available_intervals.eq(0).all()


def test_all_source_hashes_precede_context_load_and_generation(config, monkeypatch):
    root = pilot_source(config)
    (root / "summary.csv").write_text("tampered", encoding="utf-8")

    def forbid(*args, **kwargs):
        raise AssertionError("No load or generation before source integrity")

    monkeypatch.setattr(runner.pd, "read_parquet", forbid)
    monkeypatch.setattr(runner, "generate", forbid)
    output = config.workspace / "pilot"
    with pytest.raises(ValueError, match="checksum mismatch"):
        runner.run_pilot(root, output, 43001, 1, ["RCT_SYN"], workspace=config.workspace)
    assert not output.exists()
