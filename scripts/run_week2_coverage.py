"""Run the frozen 500-seed reporting protocol in resumable batches of at most five.

The child imports exclusively from the frozen snapshot. Live development can
continue without changing evaluation code, config, lock, or context bytes.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from gsm_poc.artifacts import (
    completed_run,
    environment,
    fingerprint,
    read_json,
    sha256_file,
    utc_now,
    write_frame,
    write_json,
)
from gsm_poc.config import Config

PRIORITY_DGPS = (
    "RCT_SYN",
    "OBSERVED_CONFOUNDING",
    "NULL_EFFECT",
    "HIDDEN_CONFOUNDING",
    "COLLINEAR_PRICE",
)
REPORTING_SEEDS = tuple(range(20001, 20101))
REPORT_DIRECTORY = "week2_reporting"


def freeze_snapshot(workspace: Path, snapshot: Path, build_id: str) -> None:
    if snapshot.exists():
        if not (snapshot / "src/gsm_poc/cli.py").is_file():
            raise ValueError("Existing snapshot is incomplete; use a new directory")
        return
    snapshot.mkdir(parents=True)
    shutil.copytree(
        workspace / "src", snapshot / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    (snapshot / "configs").mkdir()
    for name in ("uv.lock", "pyproject.toml"):
        shutil.copy2(workspace / name, snapshot / name)
    shutil.copy2(workspace / "configs/default.toml", snapshot / "configs/default.toml")
    gold = snapshot / "data/gold" / build_id
    gold.mkdir(parents=True)
    for name in ("context_templates.parquet", "context_templates.json"):
        shutil.copy2(workspace / "data/gold" / build_id / name, gold / name)


def evaluation_spec(snapshot: Path, build_id: str, batch_size: int) -> dict:
    config = Config.load(snapshot / "configs/default.toml")
    if (
        config.evaluation.seeds != 100
        or config.evaluation.bootstrap_draws != 199
        or set(config.evaluation.dgps) != set(PRIORITY_DGPS)
    ):
        raise ValueError("Frozen reporting config must declare 100 seeds, 199 draws and five DGPs")
    gold = snapshot / "data/gold" / build_id
    return {
        "version": 1,
        "snapshot": str(snapshot),
        "build_id": build_id,
        "environment": environment(snapshot),
        "config": config.as_dict(),
        "context_sha256": sha256_file(gold / "context_templates.parquet"),
        "context_metadata_sha256": sha256_file(gold / "context_templates.json"),
        "reporting_seeds": list(REPORTING_SEEDS),
        "dgps": list(PRIORITY_DGPS),
        "probe_seed": 19001,
        "batch_size": batch_size,
        "runner_sha256": sha256_file(Path(__file__)),
        "native_threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        "coverage_target": "nominal 0.95; exact binomial confidence interval reported",
        "null_target": "nominal 0.05; exact binomial confidence interval reported",
        "technical_targets": {"rct_theta_rmse": 0.10, "rct_scenario_probability_rmse": 0.02},
        "stress_cases": "hidden confounding is not identified causally; collinear effects reject",
    }


def batch_jobs(batch_size: int) -> list[dict]:
    if type(batch_size) is not int or not 1 <= batch_size <= 5:
        raise ValueError("Batch size must be between one and five")
    jobs = []
    for dgp in PRIORITY_DGPS:
        for offset in range(0, len(REPORTING_SEEDS), batch_size):
            seeds = REPORTING_SEEDS[offset : offset + batch_size]
            jobs.append(
                {
                    "dgp": dgp,
                    "seed": seeds[0],
                    "seeds": len(seeds),
                    "run_id": f"week2-{dgp.lower()}-{seeds[0]}-{seeds[-1]}",
                }
            )
    return jobs


@contextlib.contextmanager
def runner_lock(root: Path):
    """OS-released lock prevents two resumes from executing the same seeds."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / "runner.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def run_batch(snapshot: Path, build_id: str, job: dict, timeout_seconds: int) -> None:
    command = [
        sys.executable,
        "-m",
        "gsm_poc",
        "evaluate",
        "--config",
        "configs/default.toml",
        "--build-id",
        build_id,
        "--seed",
        str(job["seed"]),
        "--seeds",
        str(job["seeds"]),
        "--bootstrap-draws",
        "199",
        "--dgps",
        job["dgp"],
        "--run-id",
        job["run_id"],
    ]
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(snapshot / "src")
    # Bound native library fan-out; fitted model parameters remain unchanged.
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        child_env[variable] = "1"
    logs = snapshot / REPORT_DIRECTORY / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / f"{job['run_id']}.log").open("a", encoding="utf-8") as log:
        subprocess.run(
            command,
            cwd=snapshot,
            env=child_env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=True,
        )


def compatible_config(raw: dict) -> dict:
    config = copy.deepcopy(raw)
    config["simulation"].pop("seed", None)
    config["evaluation"].pop("seeds", None)
    config["evaluation"].pop("dgps", None)
    return config


def aggregate_batches(snapshot: Path, spec: dict, jobs: list[dict]) -> dict:
    frames, completed_batches = [], []
    for job in jobs:
        path = snapshot / "runs" / job["run_id"] / "manifest.json"
        if not path.is_file() or read_json(path).get("status") != "succeeded":
            continue
        manifest = completed_run(snapshot, job["run_id"])
        if manifest["environment"] != spec["environment"]:
            raise ValueError("Cannot aggregate a different code/environment revision")
        if fingerprint(compatible_config(manifest["config"])) != fingerprint(
            compatible_config(spec["config"])
        ):
            raise ValueError("Cannot aggregate different estimator/data configurations")
        frame = pd.read_parquet(path.parent / "evaluation/seed_metrics.parquet")
        expected_seeds = set(range(job["seed"], job["seed"] + job["seeds"]))
        if set(frame.seed) != expected_seeds or set(frame.dgp_id) != {job["dgp"]}:
            raise ValueError("Batch contains unexpected reporting seeds or DGP")
        frames.append(frame)
        completed_batches.append(job["run_id"])
    counts = dict.fromkeys(PRIORITY_DGPS, 0)
    outputs = {}
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        keys = ["dgp_id", "seed", "estimator", "outcome", "treatment"]
        if combined.duplicated(keys).any():
            raise ValueError("Duplicate reporting metric cells; refusing to pool batches")
        expected_cells = len(spec["config"]["model"]["estimators"]) * 4
        if not combined.groupby(["dgp_id", "seed"]).size().eq(expected_cells).all():
            raise ValueError("Reporting seed has missing estimator/effect cells")
        # Read the evaluator from the snapshot too; never pool with live changed code.
        module_spec = importlib.util.spec_from_file_location(
            "gsm_poc._reporting_evaluate", snapshot / "src/gsm_poc/evaluate.py"
        )
        if module_spec is None or module_spec.loader is None:
            raise ValueError("Frozen evaluator could not be loaded")
        evaluator = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(evaluator)
        summary = evaluator.aggregate_metrics(combined, 100)
        root = snapshot / REPORT_DIRECTORY
        write_frame(root / "seed_metrics.parquet", combined)
        write_frame(root / "evaluation_metrics.csv", summary)
        outputs = {
            name: sha256_file(root / name)
            for name in ("seed_metrics.parquet", "evaluation_metrics.csv")
        }
        counts.update({dgp: int(group.seed.nunique()) for dgp, group in combined.groupby("dgp_id")})
    complete = all(count == 100 for count in counts.values())
    return {
        "status": "complete" if complete else "partial",
        "updated_at": utc_now(),
        "completed_seeds": counts,
        "expected_seeds_per_dgp": 100,
        "completed_batches": completed_batches,
        "total_batches": len(jobs),
        "artifact_checksums": outputs,
        "evidence_level": "C",
        "statistical_acceptance": "requires review of coverage/null/failures and technical targets",
    }


def run_protocol(snapshot: Path, build_id: str, batch_size: int, timeout_seconds: int) -> dict:
    spec = evaluation_spec(snapshot, build_id, batch_size)
    root = snapshot / REPORT_DIRECTORY
    root.mkdir(parents=True, exist_ok=True)
    spec_path = root / "frozen_spec.json"
    if spec_path.exists() and fingerprint(read_json(spec_path)) != fingerprint(spec):
        raise ValueError("Frozen protocol changed; use a new snapshot")
    write_json(spec_path, spec)
    jobs = batch_jobs(batch_size)
    status_path = root / "status.json"
    state = aggregate_batches(snapshot, spec, jobs)
    state.update(process_id=os.getpid(), process_status="running", spec_hash=fingerprint(spec))
    write_json(status_path, state)
    try:
        for index, job in enumerate(jobs):
            manifest_path = snapshot / "runs" / job["run_id"] / "manifest.json"
            if manifest_path.exists() and read_json(manifest_path).get("status") == "succeeded":
                completed_run(snapshot, job["run_id"])
                continue
            # Recheck immutability before every child process, including context bytes.
            if evaluation_spec(snapshot, build_id, batch_size) != spec:
                raise ValueError("Snapshot/config/environment changed during evaluation")
            state.update(active_batch=job, batch_index=index + 1)
            write_json(status_path, state)
            print(f"Batch {index + 1}/{len(jobs)}: {job['run_id']}", flush=True)
            started = time.perf_counter()
            run_batch(snapshot, build_id, job, timeout_seconds)
            state = aggregate_batches(snapshot, spec, jobs)
            state.update(
                process_id=os.getpid(),
                process_status="running",
                spec_hash=fingerprint(spec),
                last_batch_seconds=time.perf_counter() - started,
            )
            write_json(status_path, state)
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        state.update(
            process_status="failed",
            error_type=type(exc).__name__,
            error=str(exc),
            updated_at=utc_now(),
        )
        write_json(status_path, state)
        raise
    state.update(process_status="finished", updated_at=utc_now())
    write_json(status_path, state)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--batch-timeout-seconds", type=int, default=10800)
    args = parser.parse_args(argv)
    try:
        batch_jobs(args.batch_size)
        if args.batch_timeout_seconds <= 0:
            raise ValueError("Batch timeout must be positive")
        snapshot = args.snapshot.resolve()
        freeze_snapshot(args.workspace.resolve(), snapshot, args.build_id)
        with runner_lock(snapshot / REPORT_DIRECTORY):
            run_protocol(snapshot, args.build_id, args.batch_size, args.batch_timeout_seconds)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"week2-coverage: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
