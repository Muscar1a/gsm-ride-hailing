"""Development pricing policies chosen on validation, scored by independent test truth."""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t

from gsm_poc.artifacts import Run, fingerprint, read_json, write_frame, write_json, write_model
from gsm_poc.config import Config
from gsm_poc.estimate import ModelBundle, fit_estimator
from gsm_poc.features import date_splits, require_observed
from gsm_poc.generate import PRICE_LEVELS, TRUE_THETA, Generated, generate
from gsm_poc.validate import valid_probabilities

POLICIES = ("unchanged", "simple_rule", "naive_ols", "adjusted_ols", "dml", "oracle_reference")
ACTIONS = tuple(itertools.product(PRICE_LEVELS.tolist(), repeat=2))
UNCHANGED = (1.0, 1.0)
SIMPLE_RULE = (0.9, 1.0)
SUPPORTED_DGPS = ("RCT_SYN", "OBSERVED_CONFOUNDING")


def protocol_spec(config: Config) -> dict:
    if config.project.context_mode != "synthetic":
        raise ValueError("Policy development benchmark requires explicit synthetic context")
    if set(config.evaluation.dgps) - set(SUPPORTED_DGPS):
        raise ValueError("Policy development DGPs must be RCT_SYN or OBSERVED_CONFOUNDING")
    if tuple(config.model.estimators) != POLICIES[2:5]:
        raise ValueError("Policy benchmark requires naive_ols, adjusted_ols and dml in that order")
    if config.evaluation.bootstrap_draws != 0:
        raise ValueError("Policy development uses seed variability, not day-bootstrap draws")
    return {
        "version": 1,
        "profile": "development; independent synthetic seeds; evidence C",
        "seeds": list(
            range(config.simulation.seed, config.simulation.seed + config.evaluation.seeds)
        ),
        "dgps": list(config.evaluation.dgps),
        "actions": ACTIONS,
        "policy_class": "one constant joint action for every context",
        "tie_break": "unchanged first, then lexicographic grid order; tolerance 1e-10",
        "simple_rule": SIMPLE_RULE,
        "owned_services": ["X", "Y"],
        "baseline_fares": {"X": 1.0, "Y": 1.0},
        "value_unit": "normalized simulated gross booking value / 1000 quote sessions",
        "selection": "train-only fit; predicted validation value; freeze before test scoring",
        "evaluation": "held-out test oracle conditional means; no learned-model self-scoring",
        "oracle_reference": "best constant action on test in the same train-supported grid",
        "support": "each zone/weekend/peak stratum needs min_price_cell_count train blocks",
        "min_price_cell_count": config.model.min_price_cell_count,
        "fallback": "unchanged nonintervention; learning failure and reason retained",
        "test_rejection": "record failure without reselection or test-dependent fallback",
        "uncertainty": "95% unadjusted Student-t intervals for means across independent seeds",
        "assumptions": "fixed quote population; bookings complete and pay; no capacity/costs",
        "limitations": "development only; not realized revenue, profit, GSM impact or calibration",
    }


def gross_value(
    probabilities: np.ndarray, action: tuple[float, float], weights: np.ndarray
) -> float:
    if probabilities.shape != (len(weights), 3) or not valid_probabilities(probabilities):
        raise ValueError("Invalid policy probabilities; clipping is forbidden")
    if not len(weights) or not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Policy session weights must be positive and finite")
    return float(1000 * np.average(probabilities[:, :2] @ np.asarray(action), weights=weights))


def supported_actions(train: pd.DataFrame, contexts: pd.DataFrame, config: Config) -> list:
    if train.empty or contexts.empty:
        raise ValueError("Policy support requires nonempty train and target contexts")
    group_columns = ["zone_id", "is_weekend", "is_peak"]
    groups = contexts[group_columns].drop_duplicates()
    accepted = []
    for action in ACTIONS:
        selected = train[
            np.isclose(train.multiplier_x, action[0]) & np.isclose(train.multiplier_y, action[1])
        ]
        counts = selected.groupby(group_columns).size().rename("blocks").reset_index()
        joined = groups.merge(counts, on=group_columns, how="left", validate="one_to_one")
        if joined.blocks.fillna(0).ge(config.model.min_price_cell_count).all():
            accepted.append(action)
    return accepted


def best_action(values: dict[tuple[float, float], float]) -> tuple[float, float]:
    if not values or not np.isfinite(list(values.values())).all():
        raise ValueError("Cannot select from empty or nonfinite action values")
    maximum = max(values.values())
    order = [UNCHANGED, *[action for action in ACTIONS if action != UNCHANGED]]
    return next(
        action for action in order if action in values and values[action] >= maximum - 1e-10
    )


def select_policy(bundle: ModelBundle, validation: pd.DataFrame, actions: list) -> dict:
    require_observed(validation)
    if bundle.active_treatments != (0, 1):
        raise ValueError("Policy grid requires both price effects to be identified")
    values = {}
    rejected = []
    for action in actions:
        probabilities = bundle.probabilities(validation, np.log(action))
        if valid_probabilities(probabilities):
            values[action] = gross_value(
                probabilities, action, validation.n_sessions.to_numpy(float)
            )
        else:
            rejected.append(action)
    return {
        "action": best_action(values) if values else UNCHANGED,
        "selection_status": "ok" if values else "no_valid_candidate",
        "fallback": not bool(values),
        "validation_value": max(values.values()) if values else None,
        "rejected_probability_candidates": len(rejected),
        "candidate_scores": [
            {"action": action, "predicted_validation_value": value}
            for action, value in values.items()
        ],
    }


def oracle_probabilities(data: Generated, test: pd.DataFrame, action: tuple) -> np.ndarray:
    truth = test[["dataset_id", "block_id"]].merge(
        data.oracle, on=["dataset_id", "block_id"], how="left", validate="one_to_one"
    )
    if len(truth) != len(test) or truth[["b_x", "b_y"]].isna().any().any():
        raise ValueError("Oracle keys do not cover every held-out test context")
    xy = truth[["b_x", "b_y"]].to_numpy(float) + np.log(action) @ TRUE_THETA.T
    probabilities = np.column_stack([xy, 1 - xy.sum(axis=1)])
    if not valid_probabilities(probabilities):
        raise ValueError("Invalid oracle counterfactual probabilities")
    return probabilities


def evaluate_seed(config: Config, output: Path) -> tuple[list[dict], list[Path]]:
    started = time.perf_counter()
    data = generate(config)
    splits = date_splits(data.blocks, config)
    train, validation, test = (splits[name] for name in ("train", "validation", "test"))
    actions = supported_actions(train, validation, config)
    selections: dict[str, dict] = {
        "unchanged": {"action": UNCHANGED, "selection_status": "prespecified", "fallback": False},
        "simple_rule": {
            "action": SIMPLE_RULE if SIMPLE_RULE in actions else UNCHANGED,
            "selection_status": "prespecified" if SIMPLE_RULE in actions else "unsupported_rule",
            "fallback": SIMPLE_RULE not in actions,
        },
    }
    bundles = {}
    paths = []
    for estimator in config.model.estimators:
        fit_started = time.perf_counter()
        try:
            fit = fit_estimator(train, config, estimator)
            if fit.bundle is None:
                raise ValueError(f"{fit.diagnostics['status']}: {fit.diagnostics.get('reason')}")
            bundles[estimator] = fit.bundle
            selections[estimator] = select_policy(fit.bundle, validation, actions)
            model_path = output / estimator / "model_bundle.joblib"
            write_model(model_path, fit.bundle)
            paths.append(model_path)
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
            selections[estimator] = {
                "action": UNCHANGED,
                "selection_status": "learning_failed",
                "fallback": True,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        selections[estimator]["fit_select_seconds"] = time.perf_counter() - fit_started
    # Persist all learned decisions before the evaluator reads any test truth.
    frozen_path = output / "selected_policies.json"
    write_json(
        frozen_path,
        {
            "dataset_id": data.dataset_id,
            "seed": config.simulation.seed,
            "dgp_id": config.simulation.dgp,
            "selections": selections,
            "supported_validation_actions": actions,
            "split_days": {name: sorted(part.day_id.unique()) for name, part in splits.items()},
        },
    )
    paths.append(frozen_path)
    test_actions = supported_actions(train, test, config)
    # Unchanged remains the explicit nonintervention reference even without model support.
    reference_actions = [UNCHANGED, *[action for action in test_actions if action != UNCHANGED]]
    weights = test.n_sessions.to_numpy(float)
    truth_probabilities = {
        action: oracle_probabilities(data, test, action) for action in reference_actions
    }
    oracle_values = {
        action: gross_value(probabilities, action, weights)
        for action, probabilities in truth_probabilities.items()
    }
    oracle_action = best_action(oracle_values)
    selections["oracle_reference"] = {
        "action": oracle_action,
        "selection_status": "evaluator_only",
        "fallback": False,
    }
    baseline_value = oracle_values[UNCHANGED]
    baseline_conversion = np.average(
        truth_probabilities[UNCHANGED][:, :2].sum(axis=1), weights=weights
    )
    rows = []
    for policy, selection in selections.items():
        action = tuple(selection["action"])
        row = {
            "dgp_id": config.simulation.dgp,
            "seed": config.simulation.seed,
            "dataset_id": data.dataset_id,
            "policy": policy,
            "multiplier_x": action[0],
            "multiplier_y": action[1],
            "selection_status": selection["selection_status"],
            "fallback": selection["fallback"],
            "rejected_support_candidates": len(ACTIONS) - len(actions),
            "rejected_probability_candidates": selection.get("rejected_probability_candidates", 0),
            "fit_select_seconds": selection.get("fit_select_seconds", 0.0),
            "error_type": selection.get("error_type"),
            "error": selection.get("error"),
            "test_blocks": len(test),
            "test_quote_sessions": int(weights.sum()),
            "source_kind": "synthetic",
            "evidence_level": "C",
            "status": "fallback" if selection["fallback"] else "ok",
            "gross_value_per_1000": None,
            "uplift_per_1000": None,
            "relative_uplift": None,
            "regret_per_1000": None,
            "conversion": None,
            "choice_change_per_1000": None,
        }
        if action not in oracle_values:
            row.update(
                status="test_unsupported", error="Frozen action lacks held-out context support"
            )
        elif (
            policy in bundles
            and not selection["fallback"]
            and not valid_probabilities(bundles[policy].probabilities(test, np.log(action)))
        ):
            row.update(status="test_invalid_probability", error="Frozen policy fails test simplex")
        else:
            value = oracle_values[action]
            conversion = float(
                np.average(truth_probabilities[action][:, :2].sum(axis=1), weights=weights)
            )
            row.update(
                gross_value_per_1000=value,
                uplift_per_1000=value - baseline_value,
                relative_uplift=(value - baseline_value) / baseline_value
                if baseline_value
                else None,
                regret_per_1000=oracle_values[oracle_action] - value,
                conversion=conversion,
                choice_change_per_1000=1000 * (conversion - baseline_conversion),
            )
        rows.append(row)
    duration = time.perf_counter() - started
    for row in rows:
        row["seed_seconds"] = duration
    return rows, paths


def mean_interval(values: np.ndarray) -> dict:
    values = values[np.isfinite(values)]
    count = len(values)
    if not count:
        return {"mean": None, "lower": None, "upper": None, "n": 0}
    mean = float(values.mean())
    half_width = (
        float(t.ppf(0.975, count - 1) * values.std(ddof=1) / np.sqrt(count)) if count > 1 else None
    )
    return {
        "mean": mean,
        "lower": mean - half_width if half_width is not None else None,
        "upper": mean + half_width if half_width is not None else None,
        "n": count,
    }


def failed_seed_rows(dgp: str, seed: int, error: Exception) -> list[dict]:
    return [
        {
            "dgp_id": dgp,
            "seed": seed,
            "policy": policy,
            "selection_status": "seed_failed",
            "status": "failed",
            "fallback": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "source_kind": "synthetic",
            "evidence_level": "C",
            "rejected_support_candidates": None,
            "rejected_probability_candidates": None,
            "fit_select_seconds": None,
            **dict.fromkeys(
                (
                    "gross_value_per_1000",
                    "uplift_per_1000",
                    "relative_uplift",
                    "regret_per_1000",
                    "conversion",
                    "choice_change_per_1000",
                )
            ),
        }
        for policy in POLICIES
    ]


def summarize_results(
    results: pd.DataFrame, expected_seeds: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if results.duplicated(["dgp_id", "seed", "policy"]).any():
        raise ValueError("Duplicate policy/seed results")
    rows, paired = [], []
    for group_key, group in results.groupby(["dgp_id", "policy"]):
        if not isinstance(group_key, tuple) or len(group_key) != 2:
            raise ValueError("Expected a DGP/policy metric group key")
        dgp, policy = group_key
        row = {
            "dgp_id": dgp,
            "policy": policy,
            "expected_seeds": expected_seeds,
            "attempted_seeds": len(group),
            "valid_value_seeds": int(group.gross_value_per_1000.notna().sum()),
            "failed_value_seeds": int(group.gross_value_per_1000.isna().sum()),
            "fallback_seeds": int(group.fallback.fillna(False).sum()),
            "learning_failed_seeds": int(group.selection_status.eq("learning_failed").sum()),
            "mean_rejected_support_candidates": float(group.rejected_support_candidates.mean()),
            "mean_rejected_probability_candidates": float(
                group.rejected_probability_candidates.mean()
            ),
            "mean_fit_select_seconds": float(group.fit_select_seconds.mean()),
        }
        for metric in (
            "gross_value_per_1000",
            "uplift_per_1000",
            "relative_uplift",
            "regret_per_1000",
            "conversion",
            "choice_change_per_1000",
        ):
            interval = mean_interval(group[metric].to_numpy(float))
            row.update({f"{metric}_{key}": value for key, value in interval.items()})
        rows.append(row)
        for comparator in POLICIES[:4]:
            if comparator == policy:
                continue
            other = results[(results.dgp_id == dgp) & (results.policy == comparator)]
            joined = group[["seed", "gross_value_per_1000"]].merge(
                other[["seed", "gross_value_per_1000"]],
                on="seed",
                suffixes=("", "_reference"),
                validate="one_to_one",
            )
            difference = (
                joined.gross_value_per_1000 - joined.gross_value_per_1000_reference
            ).to_numpy(float)
            paired.append(
                {
                    "dgp_id": dgp,
                    "policy": policy,
                    "comparator": comparator,
                    "expected_pairs": expected_seeds,
                    **mean_interval(difference),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(paired)


def run_benchmark(config: Config, run_id: str | None = None) -> Run:
    spec = protocol_spec(config)
    run = Run(config, run_id)
    root = run.path / "policy"
    with run.stage("policy_benchmark", spec) as execute:
        if execute:
            spec_path = root / "frozen_spec.json"
            if spec_path.exists() and fingerprint(read_json(spec_path)) != fingerprint(spec):
                raise ValueError("Existing policy protocol differs; use a new run ID")
            write_json(spec_path, spec)
            paths = [spec_path]
            rows = []
            started = time.perf_counter()
            for dgp in spec["dgps"]:
                for seed in spec["seeds"]:
                    print(f"policy: {dgp}, seed {seed}", flush=True)
                    seed_config = dataclasses.replace(
                        config,
                        simulation=dataclasses.replace(config.simulation, dgp=dgp, seed=seed),
                    )
                    seed_root = root / f"{dgp}-{seed}"
                    try:
                        seed_rows, seed_paths = evaluate_seed(seed_config, seed_root)
                    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                        seed_rows, seed_paths = failed_seed_rows(dgp, seed, exc), []
                    checkpoint = seed_root / "seed_results.json"
                    write_json(checkpoint, seed_rows)
                    rows.extend(seed_rows)
                    paths.extend([*seed_paths, checkpoint])
            results = pd.DataFrame(rows)
            summary, paired = summarize_results(results, config.evaluation.seeds)
            outputs = [
                root / "seed_results.csv",
                root / "summary.csv",
                root / "paired_differences.csv",
                root / "report.json",
            ]
            for path, frame in zip(outputs[:3], (results, summary, paired), strict=True):
                write_frame(path, frame)
            write_json(
                outputs[3],
                {
                    "protocol": spec,
                    "run_id": run.run_id,
                    "seed_jobs": len(spec["dgps"]) * len(spec["seeds"]),
                    "policy_rows": len(results),
                    "failed_value_rows": int(results.gross_value_per_1000.isna().sum()),
                    "fallback_rows": int(results.fallback.sum()),
                    "learning_failed_rows": int(
                        results.selection_status.eq("learning_failed").sum()
                    ),
                    "failed_seed_jobs": int(
                        results.loc[results.status.eq("failed"), ["dgp_id", "seed"]]
                        .drop_duplicates()
                        .shape[0]
                    ),
                    "evaluation_status": (
                        "complete_with_failures"
                        if results.gross_value_per_1000.isna().any()
                        else "complete_with_fallbacks"
                        if results.fallback.any()
                        else "complete"
                    ),
                    "duration_seconds": time.perf_counter() - started,
                    "statistical_acceptance": (
                        "development evidence only; reporting coverage is a separate gate"
                    ),
                },
            )
            paths.extend(outputs)
            run.outputs("policy_benchmark", paths, policy_rows=len(results))
    run.complete()
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/policy_development.toml"))
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        run = run_benchmark(Config.load(args.config), args.run_id)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"policy-benchmark: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Run: {run.run_id}\nArtifacts: {run.path / 'policy'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
