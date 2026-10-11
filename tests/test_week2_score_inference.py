from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gsm_poc.causal.estimate import fit_all, fit_estimator
from gsm_poc.causal.features import date_splits
from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.core.artifacts import fingerprint, read_json, sha256_file, write_frame, write_json
from gsm_poc.simulation.dgp import generate
from scripts import diagnose_week2_score_inference as runner


def test_opt_in_dml_capture_preserves_point_and_default_memory(config, generated):
    train = date_splits(generated.blocks, config)["train"]
    default = fit_estimator(train, config, "dml")
    captured = fit_estimator(train, config, "dml", capture_residuals=True)
    assert default.crossfit_residuals is None
    assert captured.crossfit_residuals is not None
    np.testing.assert_array_equal(default.bundle.theta, captured.bundle.theta)
    np.testing.assert_array_equal(default.bundle.baseline(train), captured.bundle.baseline(train))
    assert all(values.shape == (len(train), 2) for values in captured.crossfit_residuals)


@pytest.mark.parametrize("estimator", ["adjusted_ols", "dml"])
def test_joint_scores_reconstruct_production_point_and_scenario(config, generated, estimator):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=(estimator,), scenario_estimator=estimator
        ),
    )
    results, _ = fit_all(generated.blocks, config, capture_residuals=True)
    splits = date_splits(generated.blocks, config)
    result = results[estimator]
    point, scores, leverage, rank = runner.score_influence(result, splits["train"], splits["test"])
    np.testing.assert_allclose(scores.sum(axis=0), 0, atol=1e-8)
    np.testing.assert_array_equal(point[:4], result.bundle.theta.ravel())
    covariances = runner.score_covariances(
        scores, splits["train"].original_day_id.to_numpy(), leverage, rank, estimator
    )
    rows = runner.interval_rows(point, covariances, config)
    assert len(rows) == 76
    assert all(row["interval_available"] for row in rows)
    production = scenario(result.bundle, splits["test"], ScenarioRequest(), config, "test")
    outputs = {row["output_id"]: row["point"] for row in rows}
    for outcome in ("X", "Y", "NONE"):
        for metric in ("before_probability", "after_probability", "delta_percentage_points"):
            assert outputs[f"x_plus10:{outcome}_{metric}"] == pytest.approx(
                production["probabilities"][outcome][metric]
            )
    assert outputs["x_plus10:delta_expected_bookings"] == pytest.approx(
        production["delta_expected_bookings"]
    )


def test_ols_influence_matches_actual_weighted_outcome_perturbation(config, generated):
    train = date_splits(generated.blocks, config)["train"].copy()
    factor = np.where(np.arange(len(train)) % 3 == 0, 2, 1)
    train["n_sessions"] *= factor
    for service in ("x", "y", "none"):
        train[f"n_{service}"] *= factor
    evaluation = date_splits(generated.blocks, config)["test"]
    result = fit_estimator(train, config, "adjusted_ols")
    point, scores, _, _ = runner.score_influence(result, train, evaluation)
    index = 17
    changed = train.copy()
    changed.loc[changed.index[index], "n_x"] += 1
    changed.loc[changed.index[index], "n_none"] -= 1
    changed["q_x"] = changed.n_x / changed.n_sessions
    changed["q_none"] = changed.n_none / changed.n_sessions
    perturbed = fit_estimator(changed, config, "adjusted_ols")
    new_point, _, _, _ = runner.score_influence(perturbed, changed, evaluation)
    residual = (
        train.q_x.iloc[index]
        - result.bundle.probabilities(train, train[["log_multiplier_x", "log_multiplier_y"]])[
            index, 0
        ]
    )
    step = 1 / train.n_sessions.iloc[index]
    np.testing.assert_allclose(
        (new_point - point)[[0, 1, 4]], scores[index, [0, 1, 4]] / residual * step, atol=1e-10
    )


def test_derived_gradients_include_baseline_uncertainty_and_joint_effects():
    point = np.array([-0.6, 0.15, 0.12, -0.5, 0.31, 0.26])
    outputs = runner.derived_outputs(point, 0.01)
    for index in range(6):
        left, right = point.copy(), point.copy()
        left[index] -= 1e-6
        right[index] += 1e-6
        for row, low, high in zip(
            outputs,
            runner.derived_outputs(left, 0.01),
            runner.derived_outputs(right, 0.01),
            strict=True,
        ):
            assert row["gradient"][index] == pytest.approx(
                (high["point"] - low["point"]) / 2e-6, abs=1e-6
            )
    low_baseline = runner.derived_outputs(np.array([-0.6, 0.15, 0.12, -0.5, 0.001, 0.26]), 0.01)
    assert sum(row["gradient"] is None for row in low_baseline) == 2


def test_day_covariance_matches_group_sums_and_hc3_matches_leverage_scaling():
    scores = np.arange(72, dtype=float).reshape(12, 6) / 100
    scores -= scores.mean(axis=0)
    days, leverage = np.repeat(["a", "b", "c"], 4), np.full(12, 0.2)
    result = runner.score_covariances(scores, days, leverage, 2, "adjusted_ols")
    groups = np.array([scores[days == day].sum(axis=0) for day in ("a", "b", "c")])
    np.testing.assert_allclose(result["day_cr1_t"][0], groups.T @ groups * 3 / 2 * 11 / 10)
    np.testing.assert_allclose(result["block_hc3_t"][0], scores.T @ scores / 0.8**2)
    assert result["day_cr1_t"][1] == 2 and result["block_hc3_t"][1] == 10


@pytest.mark.parametrize(
    "problem", ["nan", "missing_day", "short_days", "unit_leverage", "bad_rank", "wrong_shape"]
)
def test_covariance_rejects_invalid_inputs(problem):
    scores, days, leverage, rank = (
        np.ones((12, 6)),
        np.repeat(["a", "b", "c"], 4),
        np.full(12, 0.2),
        2,
    )
    if problem == "nan":
        scores[0, 0] = np.nan
    if problem == "missing_day":
        days = days.astype(object)
        days[0] = None
    if problem == "short_days":
        days[:] = "a"
    if problem == "unit_leverage":
        leverage[0] = 1
    if problem == "bad_rank":
        rank = 12
    if problem == "wrong_shape":
        scores = scores[:, :5]
    with pytest.raises(ValueError):
        runner.score_covariances(scores, days, leverage, rank, "adjusted_ols")


def test_dml_requires_actual_out_of_fold_scores(config, generated):
    splits = date_splits(generated.blocks, config)
    result = fit_estimator(splits["train"], config, "dml")
    with pytest.raises(ValueError, match="captured"):
        runner.score_influence(result, splits["train"], splits["test"])


def test_dml_capture_rejects_changed_cached_row_order(config, generated, monkeypatch):
    from econml.dml import LinearDML

    original = LinearDML.residuals_.fget

    def reversed_controls(model):
        residual_y, residual_t, x, w = original(model)
        return residual_y, residual_t, x, w[::-1]

    monkeypatch.setattr(LinearDML, "residuals_", property(reversed_controls))
    with pytest.raises(ValueError, match="training order"):
        fit_estimator(
            date_splits(generated.blocks, config)["train"], config, "dml", capture_residuals=True
        )


@pytest.mark.parametrize("problem", ["nan", "asymmetric", "negative"])
def test_transformed_intervals_reject_invalid_joint_covariance(config, problem):
    covariance = np.eye(6)
    if problem == "nan":
        covariance[0, 0] = np.nan
    elif problem == "asymmetric":
        covariance[0, 1] = 1
    else:
        covariance[0, 0] = -1
    with pytest.raises(ValueError, match="covariance"):
        runner.interval_rows(
            np.array([-0.6, 0.15, 0.12, -0.5, 0.31, 0.26]), {"test": (covariance, 19)}, config
        )


def study_source(config, monkeypatch):
    root = config.workspace / "comparison"
    context_root = config.workspace / "diagnostic/source_context"
    context_root.mkdir(parents=True)
    context = (
        generate(config)
        .blocks.groupby(["zone_id", "hour", "is_weekend"], as_index=False)
        .distance_scaled.mean()
    )
    context["context_id"], context["fallback_level"] = "fixture", 0
    write_frame(context_root / "context_templates.parquet", context)
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
        context_root.parent / "protocol.json",
        {"context_version": "fixture", "context_sha256": checksums},
    )
    root.mkdir()
    write_json(root / "status.json", {"status": "completed"})
    source = {
        "source_config": config.as_dict(),
        "diagnostic_root": str(context_root.parent),
        "source_artifact_sha256": {
            f"source_context/{key}": value for key, value in checksums.items()
        },
    }
    monkeypatch.setattr(runner, "verify_comparison", lambda _: (source, {"artifacts": {}}))
    source_path = config.workspace / "src/gsm_poc/causal/estimate.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(Path("src/gsm_poc/causal/estimate.py").read_bytes())
    return root


def test_study_freezes_before_generation_and_preserves_failed_denominators(config, monkeypatch):
    root = study_source(config, monkeypatch)
    plan_path = config.workspace / "plan.json"
    plan = runner.freeze_plan(root, plan_path, config.workspace)
    assert plan["maximum_point_fits"] == 252 and plan["maximum_bootstrap_or_jackknife_fits"] == 0
    actual = runner.generate
    output = config.workspace / "study"

    def checked_generate(*args):
        assert read_json(output / "protocol.json")["plan"]["plan_hash"] == plan["plan_hash"]
        return actual(*args)

    monkeypatch.setattr(runner, "generate", checked_generate)

    def fail(*args, **kwargs):
        raise ValueError("deliberate validation failure")

    monkeypatch.setattr(runner, "fit_all", fail)
    result = runner.run_study(plan_path, output, "dml_probe", config.workspace)
    assert result["status"] == "completed_with_failures" and result["failed_point_fits"] == 2
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    assert (
        len(metrics) == 152
        and not metrics.interval_available.any()
        and metrics.covered.isna().all()
    )
    summary = pd.read_csv(output / "summary.csv")
    assert summary.covered_denominator.eq(0).all() and summary.unavailable_intervals.eq(1).all()
    with pytest.raises(FileExistsError):
        runner.run_study(plan_path, output, "dml_probe", config.workspace)
    with pytest.raises(FileExistsError):
        runner.freeze_plan(root, plan_path, config.workspace)


def test_study_verifies_sources_before_loading_or_generating(config, monkeypatch):
    root = study_source(config, monkeypatch)
    plan_path = config.workspace / "plan.json"
    runner.freeze_plan(root, plan_path, config.workspace)
    (config.workspace / "diagnostic/source_context/context_templates.json").write_text("tampered")

    def forbid(*args, **kwargs):
        raise AssertionError("Must not load corrupted source")

    monkeypatch.setattr(runner.pd, "read_parquet", forbid)
    monkeypatch.setattr(runner, "generate", forbid)
    with pytest.raises(ValueError, match="checksum"):
        runner.run_study(plan_path, config.workspace / "study", "dml_probe", config.workspace)


def test_inference_failure_keeps_successful_points_and_distinct_failure_counts(config, monkeypatch):
    root = study_source(config, monkeypatch)
    plan_path = config.workspace / "plan.json"
    runner.freeze_plan(root, plan_path, config.workspace)

    def fail(*args, **kwargs):
        raise ValueError("deliberate covariance failure")

    monkeypatch.setattr(runner, "score_covariances", fail)
    output = config.workspace / "study"
    result = runner.run_study(plan_path, output, "dml_probe", config.workspace)
    assert result["successful_point_fits"] == 2 and result["failed_point_fits"] == 0
    assert result["failed_inference_jobs"] == 2 and result["status"] == "completed_with_failures"
    metrics = pd.read_parquet(output / "seed_metrics.parquet")
    assert metrics.point.notna().all() and not metrics.interval_available.any()
    assert metrics.error.notna().all() and metrics.covered.isna().all()


def test_resigned_plan_cannot_expand_compute_or_seeds(config, monkeypatch):
    root = study_source(config, monkeypatch)
    plan_path = config.workspace / "plan.json"
    plan = runner.freeze_plan(root, plan_path, config.workspace)
    plan["stages"]["dml_probe"]["seeds"] = list(range(44001, 45001))
    plan["plan_hash"] = fingerprint(
        {key: value for key, value in plan.items() if key != "plan_hash"}
    )
    write_json(plan_path, plan)
    with pytest.raises(ValueError, match="fixed fresh-seed"):
        runner.run_study(plan_path, config.workspace / "study", "dml_probe", config.workspace)
