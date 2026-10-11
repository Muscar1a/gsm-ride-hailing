"""Frozen development study of block and day score inference, never production promotion."""

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
from scipy.stats import binomtest, norm, t  # noqa: E402

from gsm_poc.causal.estimate import FitResult, fit_all  # noqa: E402
from gsm_poc.causal.features import (  # noqa: E402
    OUTCOME_COLUMNS,
    TREATMENT_COLUMNS,
    date_splits,
    require_observed,
)
from gsm_poc.causal.scenario import joint_support  # noqa: E402
from gsm_poc.core.artifacts import (  # noqa: E402
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
from gsm_poc.core.validators import valid_probabilities  # noqa: E402
from gsm_poc.simulation.dgp import TRUE_THETA, generate  # noqa: E402
from scripts.compare_week2_variance import verify_comparison, verify_hashes  # noqa: E402

SCENARIOS = {"x_plus10": (0.1, 0.0), "y_plus10": (0.0, 0.1), "both_plus10": (0.1, 0.1)}
SUMMARY_KEYS = ["dgp_id", "estimator", "interval_method", "family", "output_id"]


def score_influence(
    result: FitResult, train: pd.DataFrame, contexts: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Joint influence of theta XX/XY/YX/YY and the two frozen-context baselines."""
    require_observed(train)
    bundle = result.bundle
    if bundle is None or bundle.active_treatments != (0, 1):
        raise ValueError("Both treatments must be identified")
    if (
        contexts.empty
        or not np.isfinite(contexts.n_sessions).all()
        or (contexts.n_sessions <= 0).any()
    ):
        raise ValueError("Evaluation contexts require positive finite session weights")
    weights = train.n_sessions.to_numpy(float)
    treatment = train[list(TREATMENT_COLUMNS)].to_numpy(float)
    outcome = train[list(OUTCOME_COLUMNS)].to_numpy(float)
    controls = np.column_stack([np.ones(len(train)), bundle.encoder.transform(train)])
    evaluation = np.column_stack([np.ones(len(contexts)), bundle.encoder.transform(contexts)])
    mean_controls = np.average(evaluation, axis=0, weights=contexts.n_sessions)
    before = bundle.probabilities(contexts, np.zeros(2))
    if not valid_probabilities(before):
        raise ValueError("Invalid evaluation baseline probabilities")
    baseline = np.average(before[:, :2], axis=0, weights=contexts.n_sessions)
    point = np.r_[bundle.theta.ravel(), baseline]
    design = np.column_stack([treatment, controls])
    rank = int(np.linalg.matrix_rank(design * np.sqrt(weights[:, None])))
    if len(train) <= rank:
        raise ValueError("No residual degrees of freedom")
    if bundle.estimator == "adjusted_ols":
        inverse = np.linalg.pinv(design.T @ (weights[:, None] * design), hermitian=True)
        fitted = (inverse @ design.T @ (weights[:, None] * outcome)).T
        if not np.allclose(fitted[:, :2], bundle.theta, atol=1e-10, rtol=1e-9):
            raise ValueError("OLS score reconstruction differs from production point")
        residual = outcome - design @ fitted.T
        loadings = (weights[:, None] * design) @ inverse
        influence = loadings[:, None, :] * residual[:, :, None]
        theta_score = influence[:, :, :2].reshape(len(train), 4)
        baseline_score = influence[:, :, 2:] @ mean_controls
        leverage = np.sum(design * loadings, axis=1)
    elif bundle.estimator == "dml":
        if result.crossfit_residuals is None:
            raise ValueError("DML inference requires captured out-of-fold residuals")
        residual_y, residual_t = result.crossfit_residuals
        if residual_y.shape != (len(train), 2) or residual_t.shape != (len(train), 2):
            raise ValueError("DML residuals must match all original training rows")
        if not np.isfinite(residual_y).all() or not np.isfinite(residual_t).all():
            raise ValueError("Nonfinite DML residuals")
        gram = residual_t.T @ (weights[:, None] * residual_t)
        if np.linalg.matrix_rank(gram) != 2:
            raise ValueError("Rank-deficient DML score Jacobian")
        inverse = np.linalg.inv(gram)
        reconstructed = (inverse @ residual_t.T @ (weights[:, None] * residual_y)).T
        if not np.allclose(reconstructed, bundle.theta, atol=1e-10, rtol=1e-9):
            raise ValueError("DML orthogonal score differs from production point")
        residual = residual_y - residual_t @ bundle.theta.T
        theta_score = (
            ((weights[:, None] * residual_t) @ inverse)[:, None, :] * residual[:, :, None]
        ).reshape(len(train), 4)
        control_inverse = np.linalg.pinv(controls.T @ (weights[:, None] * controls), hermitian=True)
        baseline_loading = (weights[:, None] * controls) @ control_inverse @ mean_controls
        coupling = mean_controls @ control_inverse @ controls.T @ (weights[:, None] * treatment)
        baseline_residual = outcome - treatment @ bundle.theta.T - bundle.baseline(train)
        baseline_score = baseline_loading[:, None] * baseline_residual - (
            theta_score.reshape(len(train), 2, 2) @ coupling
        )
        leverage = np.zeros(len(train))
    else:
        raise ValueError("Only adjusted_ols and dml are supported")
    scores = np.column_stack([theta_score, baseline_score])
    if not np.isfinite(point).all() or not np.isfinite(scores).all():
        raise ValueError("Nonfinite joint point or score")
    if not np.allclose(scores.sum(axis=0), 0, atol=1e-8):
        raise ValueError("Joint estimating equations do not sum to zero")
    return point, scores, leverage, rank


def score_covariances(
    scores: np.ndarray, days: np.ndarray, leverage: np.ndarray, rank: int, estimator: str
) -> dict[str, tuple[np.ndarray, int | None]]:
    scores = np.asarray(scores, dtype=float)
    days, leverage = np.asarray(days), np.asarray(leverage, dtype=float)
    if (
        scores.ndim != 2
        or scores.shape[1] != 6
        or len(days) != len(scores)
        or leverage.shape != (len(scores),)
        or not np.isfinite(scores).all()
        or not np.isfinite(leverage).all()
        or pd.isna(days).any()
        or type(rank) is not int
        or not 1 <= rank < len(scores)
    ):
        raise ValueError("Invalid score, day, leverage or rank inputs")
    groups = pd.DataFrame(scores).groupby(days, sort=True).sum().to_numpy()
    count, n = len(groups), len(scores)
    if count < 3:
        raise ValueError("Day sensitivity requires at least three original-day groups")
    correction = count / (count - 1) * (n - 1) / (n - rank)
    results = {"day_cr1_t": (correction * groups.T @ groups, count - 1)}
    if estimator == "adjusted_ols":
        if (leverage < -1e-10).any() or (leverage >= 1 - 1e-10).any():
            raise ValueError("Invalid or unit OLS leverage")
        adjusted = scores / (1 - leverage[:, None])
        results["block_hc3_t"] = (adjusted.T @ adjusted, n - rank)
    elif estimator == "dml":
        results["block_score_normal"] = (scores.T @ scores, None)
    else:
        raise ValueError("Unknown estimator")
    return results


def derived_outputs(point: np.ndarray, minimum_probability: float) -> list[dict]:
    point = np.asarray(point, dtype=float)
    if point.shape != (6,) or not np.isfinite(point).all():
        raise ValueError("Expected finite joint theta/baseline point")
    if not 0 < minimum_probability < 1:
        raise ValueError("Baseline threshold must be between zero and one")
    identity, outputs = np.eye(6), []
    theta, baseline = point[:4].reshape(2, 2), point[4:]
    for j, outcome in enumerate(("X", "Y")):
        for k, treatment in enumerate(("X", "Y")):
            index = 2 * j + k
            outputs.append(
                {
                    "family": "theta",
                    "output_id": f"{outcome}/{treatment}",
                    "point": point[index],
                    "gradient": identity[index],
                }
            )
            gradient = None
            if baseline[j] >= minimum_probability:
                gradient = identity[index] / baseline[j] - (
                    theta[j, k] / baseline[j] ** 2 * identity[4 + j]
                )
            outputs.append(
                {
                    "family": "elasticity",
                    "output_id": f"{outcome}/{treatment}",
                    "point": theta[j, k] / baseline[j] if gradient is not None else None,
                    "gradient": gradient,
                }
            )
    for scenario_id, changes in SCENARIOS.items():
        log_change = np.log1p(changes)
        effect = theta @ log_change
        before = np.r_[baseline, 1 - baseline.sum()]
        after = before + np.r_[effect, -effect.sum()]
        baseline_gradients = [identity[4], identity[5], -identity[4] - identity[5]]
        effect_gradients = [log_change @ identity[:2], log_change @ identity[2:4]]
        effect_gradients.append(-effect_gradients[0] - effect_gradients[1])
        for j, outcome in enumerate(("X", "Y", "NONE")):
            for metric, value, gradient in (
                ("before_probability", before[j], baseline_gradients[j]),
                ("after_probability", after[j], baseline_gradients[j] + effect_gradients[j]),
                (
                    "delta_percentage_points",
                    100 * (after[j] - before[j]),
                    100 * effect_gradients[j],
                ),
            ):
                outputs.append(
                    {
                        "family": "scenario",
                        "output_id": f"{scenario_id}:{outcome}_{metric}",
                        "point": value,
                        "gradient": gradient,
                    }
                )
        outputs.append(
            {
                "family": "scenario",
                "output_id": f"{scenario_id}:delta_expected_bookings",
                "point": 10000 * effect.sum(),
                "gradient": 10000 * (effect_gradients[0] + effect_gradients[1]),
            }
        )
    return outputs


def interval_rows(point: np.ndarray, covariances: dict, config: Config) -> list[dict]:
    rows = []
    for method, (covariance, degrees) in covariances.items():
        if covariance.shape != (6, 6) or not np.isfinite(covariance).all():
            raise ValueError("Invalid joint covariance")
        if not np.allclose(covariance, covariance.T, atol=1e-12) or (
            np.linalg.eigvalsh(covariance).min() < -1e-10
        ):
            raise ValueError("Joint covariance must be symmetric positive semidefinite")
        critical = float(
            norm.ppf((1 + config.evaluation.interval_level) / 2)
            if degrees is None
            else t.ppf((1 + config.evaluation.interval_level) / 2, degrees)
        )
        for output in derived_outputs(point, config.model.elasticity_min_probability):
            gradient = output.pop("gradient")
            variance = float(gradient @ covariance @ gradient) if gradient is not None else None
            if variance is not None and (not np.isfinite(variance) or variance < -1e-12):
                raise ValueError("Invalid transformed variance")
            se = np.sqrt(max(variance, 0)) if variance is not None else None
            rows.append(
                {
                    **output,
                    "interval_method": method,
                    "standard_error": se,
                    "lower": output["point"] - critical * se if se is not None else None,
                    "upper": output["point"] + critical * se if se is not None else None,
                    "degrees_of_freedom": degrees,
                    "critical_value": critical,
                    "interval_available": se is not None,
                    "unavailable_reason": "baseline_below_threshold" if se is None else None,
                }
            )
    return rows


def summarize_scores(metrics: pd.DataFrame, expected_seeds: dict[str, int]) -> pd.DataFrame:
    if metrics.duplicated([*SUMMARY_KEYS, "seed"]).any():
        raise ValueError("Duplicate output/seed metrics")
    rows = []
    for key, group in metrics.groupby(SUMMARY_KEYS):
        if not isinstance(key, tuple) or len(key) != len(SUMMARY_KEYS):
            raise ValueError("Expected complete output group key")
        row = dict(zip(SUMMARY_KEYS, key, strict=True))
        points, available = group.loc[group.point.notna()], group.loc[group.interval_available]
        matched = set(points.seed) == set(available.seed)
        empirical = float(points.point.std(ddof=1)) if len(points) > 1 else None
        rms_se = float(np.sqrt(np.mean(available.standard_error**2))) if len(available) else None
        errors = points.error
        row.update(
            expected_seeds=expected_seeds[row["estimator"]],
            attempted_seeds=len(group),
            available_intervals=len(available),
            unavailable_intervals=len(group) - len(available),
            bias=float(errors.mean()) if len(errors) else None,
            rmse=float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
            empirical_point_sd=empirical,
            rms_standard_error=rms_se,
            se_to_empirical_sd_ratio=rms_se / empirical
            if matched and empirical and rms_se is not None
            else None,
            mean_width=float((available.upper - available.lower).mean())
            if len(available)
            else None,
            supported_intervals=int(available.support_status.eq("ok").sum()),
            development_only=True,
            interval_calibration_status="not_final_calibration",
        )
        for label in ("covered", "false_positive"):
            values = available[label].dropna().astype(bool)
            bounds = (
                binomtest(int(values.sum()), len(values)).proportion_ci(method="exact")
                if len(values)
                else None
            )
            row.update(
                {
                    f"{label}_count": int(values.sum()),
                    f"{label}_denominator": len(values),
                    f"{label}_rate": float(values.mean()) if len(values) else None,
                    f"{label}_lower": bounds.low if bounds else None,
                    f"{label}_upper": bounds.high if bounds else None,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def stage_specs() -> dict:
    return {
        "ols": {"estimator": "adjusted_ols", "seeds": list(range(44001, 44101)), "folds": [5]},
        "dml_probe": {"estimator": "dml", "seeds": [44001], "folds": [5]},
        "dml_remainder": {"estimator": "dml", "seeds": list(range(44002, 44021)), "folds": [5]},
        "fold_probe": {"estimator": "dml", "seeds": [44001, 44002, 44003], "folds": [4, 10]},
    }


def verify_plan(plan: dict, workspace: Path) -> None:
    if fingerprint({key: value for key, value in plan.items() if key != "plan_hash"}) != plan.get(
        "plan_hash"
    ):
        raise ValueError("Plan fingerprint is invalid")
    if plan.get("stages") != stage_specs() or plan.get("dgps") != ["RCT_SYN", "NULL_EFFECT"]:
        raise ValueError("Plan exceeds the fixed fresh-seed development design")
    verify_hashes(Path(plan["source_comparison_root"]), plan["source_artifact_sha256"])
    verify_hashes(Path(plan["source_diagnostic_root"]), plan["source_diagnostic_sha256"])
    if (
        environment(workspace) != plan["environment"]
        or sha256_file(Path(__file__)) != plan["script_sha256"]
    ):
        raise ValueError("Frozen code or environment changed")
    if (
        sha256_file(Path(__file__).with_name("compare_week2_variance.py"))
        != plan["verification_helper_sha256"]
    ):
        raise ValueError("Source verification helper changed")


def freeze_plan(source_root: Path, plan_path: Path, workspace: Path | None = None) -> dict:
    if plan_path.exists():
        raise FileExistsError("Development plan already exists")
    workspace = workspace or Path(__file__).resolve().parents[1]
    source_root = source_root.resolve()
    source, status = verify_comparison(source_root)
    diagnostic = read_json(Path(source["diagnostic_root"]) / "protocol.json")
    plan = {
        "created_at_utc": utc_now(),
        "purpose": "undercoverage diagnosis; development only",
        "source_comparison_root": str(source_root),
        "source_artifact_sha256": {
            **status["artifacts"],
            "status.json": sha256_file(source_root / "status.json"),
        },
        "source_diagnostic_root": source["diagnostic_root"],
        "source_diagnostic_sha256": source["source_artifact_sha256"],
        "source_config": source["source_config"],
        "context_version": diagnostic["context_version"],
        "context_sha256": diagnostic["context_sha256"],
        "environment": environment(workspace),
        "script_sha256": sha256_file(Path(__file__)),
        "verification_helper_sha256": sha256_file(
            Path(__file__).with_name("compare_week2_variance.py")
        ),
        "dgps": ["RCT_SYN", "NULL_EFFECT"],
        "stages": stage_specs(),
        "expected_seeds": {"adjusted_ols": 100, "dml": 20},
        "maximum_point_fits": 252,
        "maximum_bootstrap_or_jackknife_fits": 0,
        "native_threads": 1,
        "maximum_concurrent_processes": 2,
        "probe_expansion_guard_seconds_per_dml_fit": 30,
        "methods": {
            "adjusted_ols": ["block_hc3_t", "day_cr1_t"],
            "dml": ["block_score_normal", "day_cr1_t"],
        },
        "formula": (
            "joint influence(theta, p0); block outer-products or day-summed CR1; "
            "delta-method elasticity/scenario"
        ),
        "day_correction": (
            "G/(G-1)*(N-1)/(N-rank(full weighted design)); t(G-1); "
            "DML sensitivity, no small-G guarantee"
        ),
        "sampling_target": (
            "fixed calendar/context; generator assignments/counts independent by block; "
            "day grouping is sensitivity"
        ),
        "scenario_sessions": 10000,
        "scenario_changes": SCENARIOS,
        "interpretation": (
            "individual intervals; no simultaneous guarantee; delta-method ratios are approximate"
        ),
        "decision": (
            "no automatic winner or promotion; reject strong undercoverage if exact coverage "
            "upper < .95 or exact FP lower > .05; other results are inconclusive, not acceptance"
        ),
        "reserved_final_seeds": [45001, 45100],
        "multiplicity": "flags are exploratory per-output; no family-wide rejection or acceptance",
        "source_difference": (
            "only optional DML residual capture; old archives immutable; "
            "numeric point and production intervals unchanged"
        ),
    }
    plan["plan_hash"] = fingerprint(plan)
    verify_plan(plan, workspace)
    write_json(plan_path, plan)
    return plan


def run_study(
    plan_path: Path, output_root: Path, stage: str, workspace: Path | None = None
) -> dict:
    workspace = workspace or Path(__file__).resolve().parents[1]
    plan = read_json(plan_path)
    if stage not in plan["stages"]:
        raise ValueError("Unknown frozen stage")
    if output_root.exists():
        raise FileExistsError("Study output already exists")
    verify_plan(plan, workspace)
    config = Config.from_dict(plan["source_config"], workspace)
    selected = plan["stages"][stage]
    output_root.mkdir(parents=True, exist_ok=False)
    write_json(output_root / "protocol.json", {"plan": plan, "stage": stage})
    (output_root / "runner_source.py").write_bytes(Path(__file__).read_bytes())
    (output_root / "estimate_source.py").write_bytes(
        (workspace / "src/gsm_poc/causal/estimate.py").read_bytes()
    )
    freeze_artifacts(
        Path(plan["source_diagnostic_root"]) / "source_context",
        output_root / "source_context",
        plan["context_sha256"],
    )
    context = pd.read_parquet(output_root / "source_context/context_templates.parquet")
    metadata = read_json(output_root / "source_context/context_templates.json")
    if (
        metadata.get("fit_start") != config.source.start
        or metadata.get("fit_end_exclusive") != config.source.train_end
    ):
        raise ValueError("Context training period differs from frozen configuration")
    started, metrics, states, day_rows = time.perf_counter(), [], [], []
    progress = {
        "status": "running",
        "plan_hash": plan["plan_hash"],
        "stage": stage,
        "expected_point_fits": len(plan["dgps"]) * len(selected["seeds"]) * len(selected["folds"]),
        "attempted_point_fits": 0,
        "successful_point_fits": 0,
        "failed_point_fits": 0,
        "failed_inference_jobs": 0,
        "bootstrap_or_jackknife_fits": 0,
    }
    write_json(output_root / "status.json", progress)
    try:
        for dgp in plan["dgps"]:
            for seed in selected["seeds"]:
                seed_config = dataclasses.replace(
                    config, simulation=dataclasses.replace(config.simulation, dgp=dgp, seed=seed)
                )
                data = generate(seed_config, context, metadata["context_version"])
                splits = date_splits(data.blocks, seed_config)
                train, evaluation = splits["train"], splits["test"]
                for folds in selected["folds"]:
                    verify_plan(plan, workspace)
                    method_config = dataclasses.replace(
                        seed_config,
                        model=dataclasses.replace(
                            seed_config.model,
                            estimators=(selected["estimator"],),
                            scenario_estimator=selected["estimator"],
                            folds=folds,
                        ),
                    )
                    name = f"{dgp}-{seed}-{selected['estimator']}-{folds}fold"
                    print(f"score study: {name}", flush=True)
                    job_start = time.perf_counter()
                    state = {
                        "dgp_id": dgp,
                        "seed": seed,
                        "estimator": selected["estimator"],
                        "folds": folds,
                        "dataset_id": data.dataset_id,
                        "status": "failed",
                        "point_successful": False,
                    }
                    point = None
                    rows: list[dict]
                    progress["attempted_point_fits"] += 1
                    try:
                        results, _ = fit_all(data.blocks, method_config, capture_residuals=True)
                        result = results[selected["estimator"]]
                        bundle = result.bundle
                        if bundle is None or bundle.active_treatments != (0, 1):
                            raise ValueError("Both point treatments must be identified")
                        baseline_probabilities = bundle.probabilities(evaluation, np.zeros(2))
                        if not valid_probabilities(baseline_probabilities):
                            raise ValueError("Invalid point baseline probabilities")
                        point = np.r_[
                            bundle.theta.ravel(),
                            np.average(
                                baseline_probabilities[:, :2], axis=0, weights=evaluation.n_sessions
                            ),
                        ]
                        state.update(
                            point_successful=True,
                            point=point.tolist(),
                            diagnostics=result.diagnostics,
                        )
                        progress["successful_point_fits"] += 1
                        point, scores, leverage, rank = score_influence(result, train, evaluation)
                        covariances = score_covariances(
                            scores,
                            train.original_day_id.to_numpy(),
                            leverage,
                            rank,
                            selected["estimator"],
                        )
                        rows = interval_rows(point, covariances, method_config)
                        bundle = result.bundle
                        if bundle is None:
                            raise ValueError("No model bundle")
                        support = {}
                        for scenario_id, changes in SCENARIOS.items():
                            support[scenario_id] = "ok"
                            for multipliers in (np.ones(2), 1 + np.array(changes)):
                                status, _ = joint_support(
                                    bundle, evaluation, multipliers, method_config
                                )
                                if status != "ok":
                                    support[scenario_id] = status
                            if not valid_probabilities(
                                bundle.probabilities(evaluation, np.log1p(changes))
                            ):
                                raise ValueError("Invalid scenario probabilities")
                        daily = (
                            pd.DataFrame(scores)
                            .groupby(train.original_day_id.to_numpy(), sort=True)
                            .sum()
                        )
                        for day, values in daily.iterrows():
                            day_rows.append(
                                {
                                    **state,
                                    "status": "succeeded",
                                    "original_day_id": day,
                                    **{f"score_{i}": value for i, value in enumerate(values)},
                                }
                            )
                        write_frame(
                            output_root / f"{name}-influence.parquet",
                            pd.DataFrame({f"score_{i}": scores[:, i] for i in range(6)}).assign(
                                original_day_id=train.original_day_id.to_numpy(),
                                block_id=train.block_id.to_numpy(),
                                n_sessions=train.n_sessions.to_numpy(),
                                leverage=leverage,
                            ),
                        )
                        state.update(
                            status="succeeded",
                            point=point.tolist(),
                            rank=rank,
                            train_blocks=len(train),
                            train_days=int(train.original_day_id.nunique()),
                            diagnostics=result.diagnostics,
                            scenario_support=support,
                            covariance={
                                key: value[0].tolist() for key, value in covariances.items()
                            },
                            maximum_day_score_norm=float(
                                np.linalg.norm(daily.to_numpy(), axis=1).max()
                            ),
                        )
                    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                        if state["point_successful"]:
                            progress["failed_inference_jobs"] += 1
                        else:
                            progress["failed_point_fits"] += 1
                        state.update(error_type=type(exc).__name__, error=str(exc))
                        rows = [
                            {
                                **{
                                    key: value for key, value in output.items() if key != "gradient"
                                },
                                "point": output["point"] if point is not None else None,
                                "interval_method": method,
                                "standard_error": None,
                                "lower": None,
                                "upper": None,
                                "interval_available": False,
                                "unavailable_reason": str(exc),
                            }
                            for method in plan["methods"][selected["estimator"]]
                            for output in derived_outputs(
                                point if point is not None else np.r_[np.zeros(4), 0.3, 0.25],
                                config.model.elasticity_min_probability,
                            )
                        ]
                        support = dict.fromkeys(SCENARIOS, "unavailable")
                    # Oracle enters only after all points and interval endpoints have been fixed.
                    oracle = evaluation[["block_id", "n_sessions"]].merge(
                        data.oracle[["block_id", "b_x", "b_y"]],
                        on="block_id",
                        validate="one_to_one",
                    )
                    if len(oracle) != len(evaluation):
                        raise ValueError("Oracle context cardinality differs")
                    true_baseline = np.average(
                        oracle[["b_x", "b_y"]], axis=0, weights=oracle.n_sessions
                    )
                    truth = np.zeros(4) if dgp == "NULL_EFFECT" else TRUE_THETA.ravel()
                    true_outputs = {
                        (row["family"], row["output_id"]): row["point"]
                        for row in derived_outputs(
                            np.r_[truth, true_baseline], config.model.elasticity_min_probability
                        )
                    }
                    for row in rows:
                        target = true_outputs[row["family"], row["output_id"]]
                        row.update(
                            dgp_id=dgp,
                            seed=seed,
                            estimator=selected["estimator"],
                            folds=folds,
                            dataset_id=data.dataset_id,
                            source_kind=data.metadata["source_kind"],
                            true_value=target,
                            error=row["point"] - target if row["point"] is not None else None,
                            covered=row["lower"] <= target <= row["upper"]
                            if row["interval_available"]
                            else None,
                            false_positive=not (row["lower"] <= 0 <= row["upper"])
                            if row["interval_available"] and target == 0
                            else None,
                            support_status=support[row["output_id"].split(":")[0]]
                            if row["family"] == "scenario"
                            else "not_applicable",
                            development_only=True,
                            interval_calibration_status="not_final_calibration",
                        )
                    state["duration_seconds"] = time.perf_counter() - job_start
                    states.append(state)
                    metrics.extend(rows)
                    write_json(output_root / f"{name}.json", state)
                    write_json(output_root / "status.json", progress)
        verify_plan(plan, workspace)
        write_frame(output_root / "seed_metrics.parquet", pd.DataFrame(metrics))
        write_frame(output_root / "day_scores.csv", pd.DataFrame(day_rows))
        if stage != "fold_probe":
            expected = {selected["estimator"]: len(selected["seeds"])}
            write_frame(
                output_root / "summary.csv", summarize_scores(pd.DataFrame(metrics), expected)
            )
    except Exception as exc:
        write_json(
            output_root / "status.json",
            {**progress, "status": "failed", "error": str(exc), "error_type": type(exc).__name__},
        )
        raise
    progress.update(
        status="completed_with_failures"
        if progress["failed_point_fits"] or progress["failed_inference_jobs"]
        else "completed",
        duration_seconds=time.perf_counter() - started,
        artifacts={
            path.relative_to(output_root).as_posix(): sha256_file(path)
            for path in output_root.rglob("*")
            if path.is_file() and path.name != "status.json"
        },
    )
    write_json(output_root / "status.json", progress)
    return progress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--freeze-source", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--stage", choices=("ols", "dml_probe", "dml_remainder", "fold_probe"))
    args = parser.parse_args(argv)
    if args.freeze_source:
        freeze_plan(args.freeze_source, args.plan)
    elif args.output_root is not None and args.stage is not None:
        run_study(args.plan, args.output_root, args.stage)
    else:
        parser.error("Use --freeze-source or both --output-root and --stage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
