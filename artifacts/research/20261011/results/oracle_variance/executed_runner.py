"""Evaluator-only exact conditional OLS variance; never an inference input."""

from __future__ import annotations

import argparse
import dataclasses
import os
from pathlib import Path

if __name__ == "__main__":
    for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[thread_variable] = "1"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gsm_poc.causal.features import (  # noqa: E402
    OUTCOME_COLUMNS,
    TREATMENT_COLUMNS,
    Encoder,
    date_splits,
    require_observed,
)
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
from gsm_poc.core.validators import require_probabilities  # noqa: E402
from gsm_poc.simulation.dgp import TRUE_THETA, generate  # noqa: E402
from scripts.compare_week2_variance import verify_hashes  # noqa: E402
from scripts.diagnose_week2_score_inference import derived_outputs  # noqa: E402


def ols_reference(
    train: pd.DataFrame, contexts: pd.DataFrame, encoder: Encoder, oracle: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Observed point, exact conditional mean and covariance on a fixed design."""
    require_observed(train)
    if train.empty or contexts.empty or (contexts.n_sessions <= 0).any():
        raise ValueError("Positive nonempty training and evaluation contexts required")
    if not np.isfinite(contexts.n_sessions).all():
        raise ValueError("Invalid context weights")
    if oracle.block_id.duplicated().any() or train.block_id.duplicated().any():
        raise ValueError("Duplicate oracle or training block keys")
    joined = train[["block_id"]].merge(oracle, on="block_id", how="left", validate="one_to_one")
    probabilities = joined[["p_x", "p_y", "p_none"]].to_numpy(float)
    require_probabilities(probabilities)
    weights = train.n_sessions.to_numpy(float)
    treatment = train[list(TREATMENT_COLUMNS)].to_numpy(float)
    design = np.column_stack([treatment, np.ones(len(train)), encoder.transform(train)])
    evaluation = np.column_stack([np.ones(len(contexts)), encoder.transform(contexts)])
    mean_controls = np.average(evaluation, axis=0, weights=contexts.n_sessions)
    targets = np.zeros((3, design.shape[1]))
    targets[0, 0], targets[1, 1], targets[2, 2:] = 1, 1, mean_controls
    inverse = np.linalg.pinv(design.T @ (weights[:, None] * design), hermitian=True)
    if not np.allclose(targets @ inverse @ design.T @ (weights[:, None] * design), targets):
        raise ValueError("Target is not estimable in this design")
    loadings = (weights[:, None] * design) @ inverse @ targets.T
    mapping = np.zeros((len(train), 6, 2))
    mapping[:, [0, 1, 4], 0] = loadings
    mapping[:, [2, 3, 5], 1] = loadings
    xy = probabilities[:, :2]
    count_covariance = -xy[:, :, None] * xy[:, None, :]
    count_covariance[:, 0, 0] += xy[:, 0]
    count_covariance[:, 1, 1] += xy[:, 1]
    count_covariance /= weights[:, None, None]
    covariance = np.einsum("nai,nij,nbj->ab", mapping, count_covariance, mapping)
    observed = np.einsum("nai,ni->a", mapping, train[list(OUTCOME_COLUMNS)].to_numpy(float))
    expected = np.einsum("nai,ni->a", mapping, xy)
    return observed, expected, covariance


def freeze_plan(source_root: Path, plan_path: Path) -> dict:
    if plan_path.exists():
        raise FileExistsError("Oracle diagnostic plan already exists")
    source_root = source_root.resolve()
    checksums = read_json(source_root / "evidence_checksums.json")
    verify_hashes(source_root, checksums)
    source = read_json(source_root / "development_plan.json")
    context_root = Path(source["source_diagnostic_root"]) / "source_context"
    verify_hashes(context_root, source["context_sha256"])
    plan = {
        "created_at_utc": utc_now(),
        "purpose": "Posthoc evaluator diagnosis, existing OLS seeds; not new calibration",
        "source_root": str(source_root),
        "source_artifacts": {
            **checksums,
            "evidence_checksums.json": sha256_file(source_root / "evidence_checksums.json"),
        },
        "context_root": str(context_root),
        "context_sha256": source["context_sha256"],
        "config": source["source_config"],
        "context_version": source["context_version"],
        "environment": environment(Path.cwd()),
        "script_sha256": sha256_file(Path(__file__)),
        "dgps": ["RCT_SYN", "NULL_EFFECT"],
        "seeds": list(range(44001, 44101)),
        "maximum_generated_datasets": 200,
        "estimator_fits": 0,
        "oracle_role": "evaluation only; conditional on frozen contexts and assigned prices",
        "formula": "sum M_i [diag(p_i)-p_i p_i'] M_i' / n_i; joint theta/p0 loadings",
    }
    plan["plan_hash"] = fingerprint(plan)
    write_json(plan_path, plan)
    return plan


def run_diagnostic(plan_path: Path, output_root: Path) -> dict:
    plan = read_json(plan_path)
    if output_root.exists():
        raise FileExistsError("Oracle diagnostic output already exists")
    if fingerprint({k: v for k, v in plan.items() if k != "plan_hash"}) != plan["plan_hash"]:
        raise ValueError("Invalid plan fingerprint")
    if (
        plan["seeds"] != list(range(44001, 44101))
        or plan["dgps"] != ["RCT_SYN", "NULL_EFFECT"]
        or plan["maximum_generated_datasets"] != 200
        or plan["estimator_fits"] != 0
        or plan["environment"] != environment(Path.cwd())
        or plan["script_sha256"] != sha256_file(Path(__file__))
    ):
        raise ValueError("Frozen diagnostic design or environment changed")
    source_root, context_root = Path(plan["source_root"]), Path(plan["context_root"])
    verify_hashes(source_root, plan["source_artifacts"])
    verify_hashes(context_root, plan["context_sha256"])
    context = pd.read_parquet(context_root / "context_templates.parquet")
    metadata = read_json(context_root / "context_templates.json")
    config = Config.from_dict(plan["config"], Path.cwd())
    if (
        metadata["fit_start"] != config.source.start
        or metadata["fit_end_exclusive"] != config.source.train_end
    ):
        raise ValueError("Context fit period differs from configuration")
    encoder = Encoder(config.source.zones)
    output_root.mkdir(parents=True)
    write_json(output_root / "protocol.json", plan)
    (output_root / "executed_runner.py").write_bytes(Path(__file__).read_bytes())
    rows, jobs = [], []
    for dgp in plan["dgps"]:
        for seed in plan["seeds"]:
            selected = dataclasses.replace(
                config, simulation=dataclasses.replace(config.simulation, dgp=dgp, seed=seed)
            )
            data = generate(selected, context, plan["context_version"])
            splits = date_splits(data.blocks, selected)
            point, expected, reference = ols_reference(
                splits["train"], splits["test"], encoder, data.oracle
            )
            job = read_json(source_root / "ols" / f"{dgp}-{seed}-adjusted_ols-5fold.json")
            if job["status"] != "succeeded" or job["dataset_id"] != data.dataset_id:
                raise ValueError("Regenerated dataset identity differs from saved fit")
            if not np.allclose(point, job["point"], atol=1e-10, rtol=1e-9):
                raise ValueError("Exact linear estimator differs from saved production point")
            evaluation_oracle = splits["test"][["block_id", "n_sessions"]].merge(
                data.oracle, on="block_id", validate="one_to_one"
            )
            truth = np.r_[
                np.zeros(4) if dgp == "NULL_EFFECT" else TRUE_THETA.ravel(),
                np.average(
                    evaluation_oracle[["b_x", "b_y"]], axis=0, weights=evaluation_oracle.n_sessions
                ),
            ]
            if not np.allclose(expected, truth, atol=1e-10, rtol=0):
                raise ValueError("Conditional estimator mean differs from target truth")
            jobs.append(
                {
                    "dgp_id": dgp,
                    "seed": seed,
                    "dataset_id": data.dataset_id,
                    "conditional_covariance": reference.tolist(),
                    "maximum_point_difference": float(np.max(np.abs(point - job["point"]))),
                    "maximum_conditional_bias": float(np.max(np.abs(expected - truth))),
                }
            )
            for output in derived_outputs(truth, config.model.elasticity_min_probability):
                gradient = output["gradient"]
                reference_variance = float(gradient @ reference @ gradient)
                theta_gradient, baseline_gradient = gradient.copy(), gradient.copy()
                theta_gradient[4:], baseline_gradient[:4] = 0, 0
                for method, values in job["covariance"].items():
                    estimated = np.asarray(values)
                    rows.append(
                        {
                            "dgp_id": dgp,
                            "seed": seed,
                            "interval_method": method,
                            "family": output["family"],
                            "output_id": output["output_id"],
                            "reference_variance": reference_variance,
                            "estimated_variance": float(gradient @ estimated @ gradient),
                            "theta_variance": float(theta_gradient @ reference @ theta_gradient),
                            "baseline_variance": float(
                                baseline_gradient @ reference @ baseline_gradient
                            ),
                            "twice_cross_covariance": float(
                                2 * theta_gradient @ reference @ baseline_gradient
                            ),
                        }
                    )
        print(f"oracle variance: {dgp} 100/100, no model refits", flush=True)
    metrics = pd.DataFrame(rows)
    summary = metrics.groupby(
        ["dgp_id", "interval_method", "family", "output_id"], as_index=False
    ).agg(
        seeds=("seed", "size"),
        mean_reference_variance=("reference_variance", "mean"),
        mean_estimated_variance=("estimated_variance", "mean"),
        mean_theta_variance=("theta_variance", "mean"),
        mean_baseline_variance=("baseline_variance", "mean"),
        mean_twice_cross_covariance=("twice_cross_covariance", "mean"),
    )
    summary["estimated_to_reference_rms_se"] = np.sqrt(
        summary.mean_estimated_variance / summary.mean_reference_variance
    )
    write_frame(output_root / "seed_variances.parquet", metrics)
    write_frame(output_root / "summary.csv", summary)
    write_json(output_root / "jobs.json", jobs)
    verify_hashes(source_root, plan["source_artifacts"])
    artifacts = {
        str(p.relative_to(output_root)): sha256_file(p)
        for p in output_root.rglob("*")
        if p.is_file()
    }
    status = {
        "status": "completed",
        "plan_hash": plan["plan_hash"],
        "regenerated_datasets": len(jobs),
        "model_fits": 0,
        "maximum_point_difference": max(j["maximum_point_difference"] for j in jobs),
        "maximum_conditional_bias": max(j["maximum_conditional_bias"] for j in jobs),
        "artifacts": artifacts,
    }
    write_json(output_root / "status.json", status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze-source", type=Path)
    action.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    if args.freeze_source is not None:
        freeze_plan(args.freeze_source, args.plan)
    else:
        run_diagnostic(args.plan, args.output_root)


if __name__ == "__main__":
    main()
