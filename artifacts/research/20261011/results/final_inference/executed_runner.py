"""One frozen independent assessment of joint block inference; no automatic promotion."""

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
from scipy.stats import binomtest  # noqa: E402

from gsm_poc.causal.estimate import fit_all  # noqa: E402
from gsm_poc.causal.features import date_splits  # noqa: E402
from gsm_poc.causal.scenario import joint_support  # noqa: E402
from gsm_poc.core.artifacts import (  # noqa: E402
    environment,
    fingerprint,
    read_json,
    sha256_file,
    utc_now,
    write_frame,
    write_json,
)
from gsm_poc.core.config import Config  # noqa: E402
from gsm_poc.core.validators import valid_probabilities  # noqa: E402
from gsm_poc.simulation.dgp import TRUE_THETA, generate  # noqa: E402
from scripts.compare_week2_variance import verify_hashes  # noqa: E402
from scripts.diagnose_week2_score_inference import (  # noqa: E402
    SCENARIOS,
    derived_outputs,
    interval_rows,
    score_covariances,
    score_influence,
    summarize_scores,
)
from scripts.review_week2_statistics import holm_adjust  # noqa: E402

METHODS = {"adjusted_ols": "block_hc3_t", "dml": "block_score_normal"}


def freeze_plan(source_root: Path, plan_path: Path) -> dict:
    if plan_path.exists():
        raise FileExistsError("Final assessment plan already exists")
    source_root = source_root.resolve()
    checksums = read_json(source_root / "evidence_checksums.json")
    verify_hashes(source_root, checksums)
    source = read_json(source_root / "development_plan.json")
    context_root = Path(source["source_diagnostic_root"]) / "source_context"
    verify_hashes(context_root, source["context_sha256"])
    used = pd.read_csv(source_root / "seed_metrics.csv")[["seed"]]
    if used.seed.between(45001, 45100).any():
        raise ValueError("Final seeds already used in development")
    plan = {
        "created_at_utc": utc_now(),
        "purpose": "One independent frozen statistical assessment, evidence C",
        "source_root": str(source_root),
        "source_artifacts": {
            **checksums,
            "evidence_checksums.json": sha256_file(source_root / "evidence_checksums.json"),
        },
        "context_root": str(context_root),
        "context_sha256": source["context_sha256"],
        "context_version": source["context_version"],
        "config": source["source_config"],
        "environment": environment(Path.cwd()),
        "script_sha256": sha256_file(Path(__file__)),
        "helper_sha256": {
            name: sha256_file(Path(__file__).with_name(name))
            for name in (
                "diagnose_week2_score_inference.py",
                "compare_week2_variance.py",
                "review_week2_statistics.py",
            )
        },
        "dgps": ["RCT_SYN", "NULL_EFFECT"],
        "seeds": list(range(45001, 45101)),
        "methods": METHODS,
        "maximum_point_fits": 400,
        "bootstrap_or_jackknife_fits": 0,
        "native_threads": 1,
        "maximum_concurrent_processes": 2,
        "retry_failed_jobs": 0,
        "criterion": (
            "All attempted denominators retained; exact one-sided binomial undercoverage/NULL "
            "overrejection tests; one Holm family alpha=.05 across both estimators/DGPs and "
            "distinct outputs. No rejection is not proof of nominal coverage."
        ),
        "deduplication": (
            "Keep before_probability only for x_plus10; the other two scenarios repeat the "
            "same baseline. Retain every original metric row in evidence."
        ),
        "scope": (
            "Full fixed calendar, 1440 test blocks; unchanged support gate; statistical "
            "diagnostics can remain unsupported for policy."
        ),
        "decision": (
            "No automatic production promotion, exception, seed expansion or interval scaling; "
            "report failed/inconclusive checks."
        ),
    }
    plan["plan_hash"] = fingerprint(plan)
    write_json(plan_path, plan)
    return plan


def verify_plan(plan: dict) -> None:
    if fingerprint({k: v for k, v in plan.items() if k != "plan_hash"}) != plan["plan_hash"]:
        raise ValueError("Invalid frozen plan fingerprint")
    if (
        plan["seeds"] != list(range(45001, 45101))
        or plan["dgps"] != ["RCT_SYN", "NULL_EFFECT"]
        or plan["methods"] != METHODS
        or plan["maximum_point_fits"] != 400
        or plan["bootstrap_or_jackknife_fits"] != 0
    ):
        raise ValueError("Final assessment design changed")
    if (
        environment(Path.cwd()) != plan["environment"]
        or sha256_file(Path(__file__)) != plan["script_sha256"]
    ):
        raise ValueError("Final code or environment changed")
    for name, checksum in plan["helper_sha256"].items():
        if sha256_file(Path(__file__).with_name(name)) != checksum:
            raise ValueError("Final inference or verification helper changed")


def assessment_tests(summary: pd.DataFrame) -> pd.DataFrame:
    selected = summary.loc[
        ~(
            summary.output_id.str.contains("before_probability")
            & ~summary.output_id.str.startswith("x_plus10:")
        )
    ]
    tests = []
    for row in selected.to_dict("records"):
        for label, target, alternative in (
            ("covered", 0.95, "less"),
            ("false_positive", 0.05, "greater"),
        ):
            count, denominator = row[f"{label}_count"], row[f"{label}_denominator"]
            if denominator:
                tests.append(
                    {
                        **{key: row[key] for key in ("dgp_id", "estimator", "family", "output_id")},
                        "check": label,
                        "count": count,
                        "denominator": denominator,
                        "p_value": binomtest(
                            count, denominator, target, alternative=alternative
                        ).pvalue,
                    }
                )
    frame = pd.DataFrame(tests)
    if frame.empty:
        raise ValueError("No assessable final intervals")
    frame["holm_p_value"] = holm_adjust(frame.p_value.to_numpy())
    frame["rejected"] = frame.holm_p_value < 0.05
    return frame


def run_assessment(plan_path: Path, output_root: Path, dgp: str) -> dict:
    plan = read_json(plan_path)
    verify_plan(plan)
    if dgp not in plan["dgps"]:
        raise ValueError("Unknown frozen assessment DGP")
    if output_root.exists():
        raise FileExistsError("Final assessment output already exists")
    verify_hashes(Path(plan["source_root"]), plan["source_artifacts"])
    verify_hashes(Path(plan["context_root"]), plan["context_sha256"])
    context = pd.read_parquet(Path(plan["context_root"]) / "context_templates.parquet")
    config = Config.from_dict(plan["config"], Path.cwd())
    output_root.mkdir(parents=True)
    write_json(output_root / "protocol.json", plan)
    (output_root / "executed_runner.py").write_bytes(Path(__file__).read_bytes())
    started, metrics = time.perf_counter(), []
    progress = {
        "status": "running",
        "dgp_id": dgp,
        "plan_hash": plan["plan_hash"],
        "attempted_fits": 0,
        "failed_fits_or_inference": 0,
        "expected_fits": 200,
        "bootstrap_or_jackknife_fits": 0,
    }
    write_json(output_root / "status.json", progress)
    for seed in plan["seeds"]:
        verify_plan(plan)
        selected = dataclasses.replace(
            config, simulation=dataclasses.replace(config.simulation, dgp=dgp, seed=seed)
        )
        data = generate(selected, context, plan["context_version"])
        splits = date_splits(data.blocks, selected)
        evaluation = splits["test"]
        for estimator, method in METHODS.items():
            point = None
            rows: list[dict]
            job = {
                "dgp_id": dgp,
                "seed": seed,
                "estimator": estimator,
                "dataset_id": data.dataset_id,
                "status": "failed",
                "point_successful": False,
            }
            fit_config = dataclasses.replace(
                selected,
                model=dataclasses.replace(
                    selected.model, estimators=(estimator,), scenario_estimator=estimator
                ),
            )
            progress["attempted_fits"] += 1
            try:
                results, _ = fit_all(data.blocks, fit_config, capture_residuals=True)
                result = results[estimator]
                point, scores, leverage, rank = score_influence(result, splits["train"], evaluation)
                bundle = result.bundle
                assert bundle is not None
                job["point_successful"] = True
                covariance = score_covariances(
                    scores, splits["train"].original_day_id.to_numpy(), leverage, rank, estimator
                )[method]
                rows = interval_rows(point, {method: covariance}, fit_config)
                support = {}
                for scenario_id, changes in SCENARIOS.items():
                    statuses = [
                        joint_support(bundle, evaluation, multipliers, fit_config)[0]
                        for multipliers in (np.ones(2), 1 + np.asarray(changes))
                    ]
                    support[scenario_id] = next(
                        (status for status in statuses if status != "ok"), "ok"
                    )
                    if not valid_probabilities(bundle.probabilities(evaluation, np.log1p(changes))):
                        raise ValueError("Invalid scenario probabilities")
                job.update(
                    status="succeeded",
                    point=point.tolist(),
                    covariance=covariance[0].tolist(),
                    diagnostics=result.diagnostics,
                    scenario_support=support,
                )
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                progress["failed_fits_or_inference"] += 1
                job.update(error_type=type(exc).__name__, error=str(exc))
                support = dict.fromkeys(SCENARIOS, "unavailable")
                rows = [
                    {
                        "family": row["family"],
                        "output_id": row["output_id"],
                        "point": row["point"] if point is not None else None,
                        "interval_method": method,
                        "standard_error": None,
                        "lower": None,
                        "upper": None,
                        "interval_available": False,
                        "unavailable_reason": str(exc),
                    }
                    for row in derived_outputs(
                        point if point is not None else np.r_[np.zeros(4), 0.3, 0.25],
                        config.model.elasticity_min_probability,
                    )
                ]
            # Evaluator truth is accessed only after observed points and intervals are fixed.
            oracle = evaluation[["block_id", "n_sessions"]].merge(
                data.oracle[["block_id", "b_x", "b_y"]], on="block_id", validate="one_to_one"
            )
            if len(oracle) != len(evaluation):
                raise ValueError("Oracle evaluation context cardinality changed")
            truth = np.r_[
                np.zeros(4) if dgp == "NULL_EFFECT" else TRUE_THETA.ravel(),
                np.average(oracle[["b_x", "b_y"]], axis=0, weights=oracle.n_sessions),
            ]
            targets = {
                (row["family"], row["output_id"]): row["point"]
                for row in derived_outputs(truth, config.model.elasticity_min_probability)
            }
            for row in rows:
                target = targets[row["family"], row["output_id"]]
                row.update(
                    dgp_id=dgp,
                    seed=seed,
                    estimator=estimator,
                    dataset_id=data.dataset_id,
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
                    evidence_level="C",
                    development_only=False,
                    interval_calibration_status="independent_assessment_not_certification",
                )
            metrics.extend(rows)
            write_json(output_root / f"{dgp}-{seed}-{estimator}.json", job)
        write_json(output_root / "status.json", progress)
        if seed % 10 == 0:
            print(
                f"final {dgp}: {seed - 45000}/100 seeds; "
                f"{progress['failed_fits_or_inference']} failures",
                flush=True,
            )
    frame = pd.DataFrame(metrics)
    summary = summarize_scores(frame, dict.fromkeys(METHODS, 100))
    summary["development_only"] = False
    summary["interval_calibration_status"] = "independent_assessment_not_certification"
    write_frame(output_root / "seed_metrics.parquet", frame)
    write_frame(output_root / "summary.csv", summary)
    verify_plan(plan)
    artifacts = {
        str(p.relative_to(output_root)): sha256_file(p)
        for p in output_root.rglob("*")
        if p.is_file() and p.name != "status.json"
    }
    progress.update(
        status="completed", duration_seconds=time.perf_counter() - started, artifacts=artifacts
    )
    write_json(output_root / "status.json", progress)
    return progress


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze-source", type=Path)
    action.add_argument("--output-root", type=Path)
    parser.add_argument("--dgp", choices=["RCT_SYN", "NULL_EFFECT"])
    args = parser.parse_args()
    if args.freeze_source is not None:
        freeze_plan(args.freeze_source, args.plan)
    elif args.dgp is None:
        parser.error("--dgp is required for execution")
    else:
        run_assessment(args.plan, args.output_root, args.dgp)


if __name__ == "__main__":
    main()
