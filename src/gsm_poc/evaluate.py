"""Oracle access is confined to method evaluation, never estimation or scenarios."""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from gsm_poc.artifacts import (
    fingerprint,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.config import Config
from gsm_poc.estimate import FitResult, ModelBundle, fit_all
from gsm_poc.features import date_splits
from gsm_poc.generate import TRUE_THETA, Generated, generate
from gsm_poc.uncertainty import (
    BootstrapResult,
    bootstrap,
    interval_sensitivity,
    percentile_interval,
)
from gsm_poc.validate import valid_probabilities


def effect_rows(
    result: FitResult,
    draws: BootstrapResult | None,
    contexts: pd.DataFrame,
    config: Config,
    run_id: str,
    dataset_id: str,
) -> list[dict]:
    bundle = result.bundle
    baseline = None
    if bundle is not None:
        probabilities = bundle.probabilities(contexts, np.zeros(2))
        if valid_probabilities(probabilities):
            baseline = np.average(probabilities[:, :2], axis=0, weights=contexts.n_sessions)
    rows = []
    for j, outcome in enumerate(("X", "Y")):
        for treatment in range(2):
            row = {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "estimator": result.diagnostics["estimator"],
                "outcome": outcome,
                "treatment": ("X", "Y")[treatment],
                "source_kind": bundle.source_kind
                if bundle
                else ("semi_synthetic" if config.project.context_mode == "tlc" else "synthetic"),
                "evidence_level": "C",
                "status": result.diagnostics["status"],
                "theta": None,
                "theta_lower": None,
                "theta_upper": None,
                "elasticity": None,
                "elasticity_lower": None,
                "elasticity_upper": None,
                "baseline_probability": float(baseline[j]) if baseline is not None else None,
                "baseline_context": "frozen test contexts",
                "baseline_context_sessions": int(contexts.n_sessions.sum()),
                "theta_unit": "probability / log-price",
                "elasticity_unit": "dimensionless",
                "interval_kind": "day-bootstrap percentile; individual intervals",
                "interval_level": config.evaluation.interval_level,
                "interval_status": draws.interval_status if draws else "interval_unstable",
                "requested_draws": draws.requested_draws if draws else 0,
                "successful_draws": draws.successful_draws if draws else 0,
                "train_blocks": result.diagnostics["train_blocks"],
                "train_days": result.diagnostics["train_days"],
            }
            if bundle is None or treatment not in bundle.active_treatments:
                row["status"] = "not_identified"
                rows.append(row)
                continue
            k = bundle.active_treatments.index(treatment)
            row["theta"] = float(bundle.theta[j, k])
            if baseline is not None and baseline[j] >= config.model.elasticity_min_probability:
                row["elasticity"] = float(bundle.theta[j, k] / baseline[j])
            successful = [b for b in draws.bundles if b is not None] if draws else []
            if len(successful) >= 2:
                theta_values = np.array([b.theta[j, k] for b in successful])
                low, high = percentile_interval(theta_values, config.evaluation.interval_level)
                row.update(theta_lower=float(low), theta_upper=float(high))
                sensitivity = interval_sensitivity(theta_values, config.evaluation.interval_level)
                if sensitivity.get("unstable"):
                    row["interval_status"] = "interval_unstable"
                elasticities, invalid = [], 0
                for draw in successful:
                    p = draw.probabilities(contexts, np.zeros(2))
                    if not valid_probabilities(p):
                        invalid += 1
                        continue
                    mean = np.average(p[:, j], weights=contexts.n_sessions)
                    if mean < config.model.elasticity_min_probability:
                        invalid += 1
                    else:
                        elasticities.append(draw.theta[j, k] / mean)
                row["invalid_baseline_draws"] = invalid
                if invalid:
                    row["interval_status"] = "interval_unstable"
                elif len(elasticities) >= 2:
                    low, high = percentile_interval(
                        np.array(elasticities), config.evaluation.interval_level
                    )
                    row.update(elasticity_lower=float(low), elasticity_upper=float(high))
            rows.append(row)
    return rows


def resolve_target_log_price(model_bundle: ModelBundle, run_config: Config) -> np.ndarray | None:
    delta_price = np.array(
        [run_config.scenario.delta_price_x, run_config.scenario.delta_price_y], dtype=float
    )
    if (delta_price <= -1).any():
        return None
    delta_log_price = np.log(1 + delta_price)
    inactive = set(range(2)) - set(model_bundle.active_treatments)
    if any(abs(delta_log_price[k]) > 1e-12 for k in inactive):
        return None
    target_log_price = np.zeros(2, dtype=float)
    for k in range(2):
        if k in model_bundle.active_treatments:
            target_log_price[k] = delta_log_price[k]
        else:
            observed_key = ("X", "Y")[k]
            target_log_price[k] = model_bundle.diagnostics.get("constant_log_prices", {}).get(
                observed_key, 0.0
            )
    return target_log_price


def method_metrics(
    result: FitResult, draws: BootstrapResult | None, data: Generated, config: Config, run_id: str
) -> list[dict]:
    test = date_splits(data.blocks, config)["test"]
    effects = effect_rows(result, draws, test, config, run_id, data.dataset_id)
    theta = np.zeros((2, 2)) if data.metadata["dgp_id"] == "NULL_EFFECT" else TRUE_THETA
    bundle = result.bundle
    scenario_rmse = None
    probability_valid = None
    if bundle is not None and bundle.diagnostics.get("validation_probability_valid") is not False:
        target_log_price = resolve_target_log_price(bundle, config)
        if target_log_price is not None:
            truth = test[["block_id"]].merge(data.oracle, on="block_id", validate="one_to_one")
            true_xy = truth[["b_x", "b_y"]].to_numpy() + target_log_price @ theta.T
            prediction = bundle.probabilities(test, target_log_price)
            probability_valid = valid_probabilities(prediction)
            if probability_valid:
                scenario_rmse = float(
                    np.sqrt(
                        np.average(
                            np.mean((prediction[:, :2] - true_xy) ** 2, axis=1),
                            weights=test.n_sessions,
                        )
                    )
                )
    rows = []
    for effect in effects:
        j, k = ("X", "Y").index(effect["outcome"]), ("X", "Y").index(effect["treatment"])
        target = float(theta[j, k])
        error = effect["theta"] - target if effect["theta"] is not None else None
        covered = (
            effect["theta_lower"] <= target <= effect["theta_upper"]
            if effect["theta_lower"] is not None
            else None
        )
        false_positive = (
            not (effect["theta_lower"] <= 0 <= effect["theta_upper"])
            if effect["theta_lower"] is not None and target == 0
            else None
        )
        rows.append(
            {
                **effect,
                "dgp_id": data.metadata["dgp_id"],
                "seed": data.metadata["seed"],
                "true_theta": target,
                "error": error,
                "squared_error": error**2 if error is not None else None,
                "covered": covered,
                "false_positive": false_positive,
                "scenario_probability_rmse": scenario_rmse,
                "scenario_probability_valid": probability_valid,
                "evaluation_kind": "controlled DGP oracle comparison",
            }
        )
    return rows


def saved_method_evaluation(
    config: Config,
    dataset_id: str,
    results: dict[str, FitResult],
    draws: dict[str, BootstrapResult],
    run_id: str,
) -> pd.DataFrame:
    root = config.workspace / "data/synthetic" / dataset_id
    metadata = read_json(root / "manifest.json")
    blocks = pd.read_parquet(root / "observed/choice_block.parquet")
    oracle = pd.read_parquet(root / "oracle/oracle_block.parquet")
    # No session materialization is necessary for evaluation.
    data = Generated(dataset_id, pd.DataFrame(), pd.DataFrame(), blocks, oracle, metadata)
    rows = [
        row
        for name, result in results.items()
        for row in method_metrics(result, draws.get(name), data, config, run_id)
    ]
    return pd.DataFrame(rows)


def aggregate_metrics(seed_metrics: pd.DataFrame, expected_seeds: int) -> pd.DataFrame:
    rows = []
    for group_key, group in seed_metrics.groupby(
        ["dgp_id", "estimator", "outcome", "treatment"], dropna=False
    ):
        if not isinstance(group_key, tuple) or len(group_key) != 4:
            raise ValueError("Expected a four-column metric group key")
        dgp, estimator, outcome, treatment = group_key
        errors = group.error.dropna().astype(float)
        covered = group.covered.dropna().astype(bool)
        fp = group.false_positive.dropna().astype(bool)
        row = {
            "dgp_id": dgp,
            "estimator": estimator,
            "outcome": outcome,
            "treatment": treatment,
            "source_kind": group.source_kind.iloc[0],
            "evidence_level": "C",
            "expected_seeds": expected_seeds,
            "attempted_seeds": int(group.seed.nunique()),
            "valid_estimates": len(errors),
            "failed_or_unidentified_estimates": len(group) - len(errors),
            "bias": float(errors.mean()) if len(errors) else None,
            "rmse": float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
            "coverage": float(covered.mean()) if len(covered) else None,
            "coverage_denominator": len(covered),
            "false_positive_rate": float(fp.mean()) if len(fp) else None,
            "false_positive_denominator": len(fp),
            "interval_quality": "reporting"
            if (group.interval_status == "ok").all()
            else "development_or_unstable",
            "bootstrap_requested_total": int(group.requested_draws.sum()),
            "bootstrap_successful_total": int(group.successful_draws.sum()),
            "scenario_probability_rmse": (
                float(np.sqrt(np.mean(group.scenario_probability_rmse.dropna() ** 2)))
                if group.scenario_probability_rmse.notna().any()
                else None
            ),
        }
        for label, values in (("coverage", covered), ("false_positive", fp)):
            if len(values):
                low, high = binomtest(int(values.sum()), len(values)).proportion_ci(
                    confidence_level=0.95, method="exact"
                )
                row[f"{label}_lower"], row[f"{label}_upper"] = low, high
            else:
                row[f"{label}_lower"], row[f"{label}_upper"] = None, None
        rows.append(row)
    return pd.DataFrame(rows)


def _failed_method_rows(
    config: Config, run_id: str, estimator: str, source_kind: str, error: Exception
) -> list[dict]:
    return [
        {
            "run_id": run_id,
            "dgp_id": config.simulation.dgp,
            "seed": config.simulation.seed,
            "estimator": estimator,
            "outcome": outcome,
            "treatment": treatment,
            "status": "failed",
            "source_kind": source_kind,
            "evidence_level": "C",
            "error": None,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "covered": None,
            "false_positive": None,
            "scenario_probability_rmse": None,
            "interval_status": "interval_unstable",
            "requested_draws": config.evaluation.bootstrap_draws,
            "successful_draws": 0,
        }
        for outcome in ("X", "Y")
        for treatment in ("X", "Y")
    ]


def monte_carlo(
    config: Config, context: pd.DataFrame | None, context_version: str, output: Path, run_id: str
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    all_metrics, checkpoints = [], []
    for dgp in config.evaluation.dgps:
        for offset in range(config.evaluation.seeds):
            seed = config.simulation.seed + offset
            seed_config = dataclasses.replace(
                config, simulation=dataclasses.replace(config.simulation, dgp=dgp, seed=seed)
            )
            key = fingerprint(
                {"config": seed_config.as_dict(), "context": context_version, "run_id": run_id}
            )
            checkpoint = output / f"{dgp}-{seed}.json"
            metrics_path = output / f"{dgp}-{seed}.parquet"
            if checkpoint.exists():
                previous = read_json(checkpoint)
                if (
                    previous.get("status") == "succeeded"
                    and previous["input_hash"] == key
                    and metrics_path.exists()
                    and sha256_file(metrics_path) == previous.get("metrics_sha256")
                ):
                    all_metrics.append(pd.read_parquet(metrics_path))
                    checkpoints.append(previous)
                    continue
            started = time.perf_counter()
            state = {
                "input_hash": key,
                "run_id": run_id,
                "dgp_id": dgp,
                "seed": seed,
                "status": "running",
                "bootstrap_draws": config.evaluation.bootstrap_draws,
                "estimator_results": {},
            }
            write_json(checkpoint, state)
            print(f"evaluate: {dgp}, seed {seed}", flush=True)
            try:
                data = generate(seed_config, context, context_version)
                train = date_splits(data.blocks, seed_config)["train"]
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                state.update(status="failed", error_type=type(exc).__name__, error=str(exc))
                rows = []
                for name in config.model.estimators:
                    state["estimator_results"][name] = {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                    rows.extend(
                        _failed_method_rows(
                            seed_config,
                            run_id,
                            name,
                            "semi_synthetic" if context is not None else "synthetic",
                            exc,
                        )
                    )
            else:
                state["status"] = "succeeded"
                rows = []
                for name in config.model.estimators:
                    method_config = dataclasses.replace(
                        seed_config,
                        model=dataclasses.replace(
                            seed_config.model, estimators=(name,), scenario_estimator=name
                        ),
                    )
                    try:
                        # The fit-stage validation gate applies separately to each method.
                        results, _ = fit_all(data.blocks, method_config)
                        result = results[name]
                        draws = (
                            bootstrap(train, method_config, name)
                            if result.bundle is not None
                            else None
                        )
                        rows.extend(method_metrics(result, draws, data, method_config, run_id))
                        state["estimator_results"][name] = {
                            "status": "succeeded",
                            "model_status": result.diagnostics["status"],
                        }
                    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                        state["status"] = "failed"
                        state.setdefault("error_type", type(exc).__name__)
                        state.setdefault("error", str(exc))
                        state["estimator_results"][name] = {
                            "status": "failed",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                        rows.extend(
                            _failed_method_rows(
                                method_config, run_id, name, data.metadata["source_kind"], exc
                            )
                        )
            frame = pd.DataFrame(rows)
            write_frame(metrics_path, frame)
            state.update(
                duration_seconds=time.perf_counter() - started,
                metrics_sha256=sha256_file(metrics_path),
            )
            write_json(checkpoint, state)
            all_metrics.append(frame)
            checkpoints.append(state)
    seed_metrics = pd.DataFrame.from_records(
        [row for frame in all_metrics for row in frame.to_dict("records")]
    )
    summary = aggregate_metrics(seed_metrics, config.evaluation.seeds)
    metrics_file = output / "evaluation_metrics.csv"
    seed_file = output / "seed_metrics.parquet"
    metadata_file = output / "evaluation_summary.json"
    write_frame(metrics_file, summary)
    write_frame(seed_file, seed_metrics)
    write_json(
        metadata_file,
        {
            "run_id": run_id,
            "evidence_level": "C",
            "seeds_per_dgp": config.evaluation.seeds,
            "requested_seed_runs": config.evaluation.seeds * len(config.evaluation.dgps),
            "failed_seed_runs": sum(c["status"] == "failed" for c in checkpoints),
            "bootstrap_draws_per_estimator": config.evaluation.bootstrap_draws,
            "reporting_min_draws": config.evaluation.reporting_min_draws,
            "checkpoints": checkpoints,
            "thresholds_frozen_before_test": {
                "theta_rmse": config.evaluation.theta_rmse_target,
                "scenario_probability_rmse": config.evaluation.probability_rmse_target,
            },
            "limits": "Controlled DGP only; small runs do not establish stable coverage",
        },
    )
    return {
        "summary": metrics_file,
        "seed_metrics": seed_file,
        "metadata": metadata_file,
        "checkpoint_files": [p for p in output.glob("*-*.json")],
        "rows": len(summary),
    }
