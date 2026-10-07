"""Resume unchanged Week 2 batches with bounded parallel CPU child processes."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import math
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any


def checkpoint_io_path() -> Path:
    return Path(__file__).with_name("week2_checkpoint_io.py")


def available_ram_gib() -> float:
    """Read available physical memory; unavailable counters are errors."""
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in (
                    "total_physical",
                    "available_physical",
                    "total_page",
                    "available_page",
                    "total_virtual",
                    "available_virtual",
                    "available_extended",
                )
            ]

        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise OSError("Windows available-memory counter failed")
        return memory.available_physical / 2**30
    memory_info = Path("/proc/meminfo")
    if memory_info.is_file():
        for line in memory_info.read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2**20
    raise OSError("Available-memory counter is unsupported on this platform")


def load_runner(snapshot: Path):
    sys.path.insert(0, str(snapshot / "src"))
    path = Path(__file__).with_name("run_week2_coverage.py")
    module_spec = importlib.util.spec_from_file_location("week2_serial_runner", path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError("Original frozen-protocol runner is unavailable")
    runner = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(runner)
    adapter_spec = importlib.util.spec_from_file_location(
        "week2_checkpoint_io", checkpoint_io_path()
    )
    if adapter_spec is None or adapter_spec.loader is None:
        raise ValueError("Checkpoint I/O adapter is unavailable")
    adapter = importlib.util.module_from_spec(adapter_spec)
    adapter_spec.loader.exec_module(adapter)
    adapter.install_checkpoint_io()
    return runner


def batch_command(build_id: str, job: dict) -> list[str]:
    return [
        sys.executable,
        str(checkpoint_io_path()),
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


def terminate_child(process: subprocess.Popen) -> None:
    """Terminate only this coordinator's child tree, including Windows venv launchers."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0 and process.poll() is None:
            raise RuntimeError(f"Failed to stop owned batch child: {result.stderr.strip()}")
    else:
        process.kill()
    process.wait(timeout=15)


def execute_batch(snapshot: Path, build_id: str, job: dict, timeout_seconds: int) -> float:
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(snapshot / "src")
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        child_env[variable] = "1"
    log_path = snapshot / "week2_reporting/logs" / f"{job['run_id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            batch_command(build_id, job),
            cwd=snapshot,
            env=child_env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            terminate_child(process)
            raise
        if return_code:
            raise subprocess.CalledProcessError(return_code, process.args)
    return time.perf_counter() - started


def checkpoint_progress(snapshot: Path, jobs: list[dict], runner: Any) -> dict:
    completed, failures, running = 0, 0, []
    for job in jobs:
        root = snapshot / "runs" / job["run_id"] / "evaluation"
        for seed in range(job["seed"], job["seed"] + job["seeds"]):
            path = root / f"{job['dgp']}-{seed}.json"
            if not path.exists():
                continue
            checkpoint = runner.read_json(path)
            if checkpoint.get("status") == "running":
                running.append({"dgp": job["dgp"], "seed": seed, "run_id": job["run_id"]})
                continue
            metrics = path.with_suffix(".parquet")
            if checkpoint.get("status") not in ("succeeded", "failed"):
                raise ValueError(f"Unknown checkpoint status: {path}")
            if (
                checkpoint.get("seed") != seed
                or checkpoint.get("dgp_id") != job["dgp"]
                or checkpoint.get("bootstrap_draws") != 199
                or not metrics.is_file()
                or runner.sha256_file(metrics) != checkpoint.get("metrics_sha256")
            ):
                raise ValueError(f"Invalid checkpoint identity/checksum: {path}")
            completed += 1
            failures += checkpoint["status"] == "failed"
    return {
        "completed_checkpoint_seeds": completed,
        "failed_checkpoint_seeds": failures,
        "running_seeds": running,
    }


def run_parallel_protocol(
    snapshot: Path,
    build_id: str,
    workers: int,
    timeout_seconds: int,
    runner: Any,
    ram_reserve_gib: float = 5.0,
) -> dict:
    if type(workers) is not int or not 1 <= workers <= 50:
        raise ValueError("Workers must be between one and fifty")
    if timeout_seconds <= 0:
        raise ValueError("Batch timeout must be positive")
    if not math.isfinite(ram_reserve_gib) or ram_reserve_gib <= 0:
        raise ValueError("RAM reserve must be finite and positive")
    root = snapshot / runner.REPORT_DIRECTORY
    spec_path = root / "frozen_spec.json"
    if not spec_path.exists():
        raise ValueError("Parallel execution requires the existing frozen protocol")
    frozen_spec = runner.read_json(spec_path)
    batch_size = frozen_spec["batch_size"]
    spec = runner.evaluation_spec(snapshot, build_id, batch_size)
    if runner.fingerprint(frozen_spec) != runner.fingerprint(spec):
        raise ValueError("Frozen protocol/environment changed; refusing to resume")
    jobs = runner.batch_jobs(batch_size)
    state = runner.aggregate_batches(snapshot, spec, jobs)
    checkpoint_progress(snapshot, jobs, runner)
    pending = [job for job in jobs if job["run_id"] not in state["completed_batches"]]
    failed_batches = []
    active = {}
    stopped = False
    first_error = None
    memory_wait_started = None
    waiting_for_memory = False
    current_available_ram = None
    minimum_available_ram = None
    dispatch_headroom_gib = 1.0
    startup_reservation_seconds = 10
    startup_reservations = {}
    execution = {
        "backend": "cpu_parallel",
        "workers": workers,
        "started_at": runner.utc_now(),
        "spec_hash": runner.fingerprint(spec),
        "coordinator_sha256": runner.sha256_file(Path(__file__)),
        "initial_completed_seeds": state["completed_seeds"],
        "batch_size": batch_size,
        "batch_timeout_seconds": timeout_seconds,
        "native_threads": spec["native_threads"],
        "model_change": False,
        "checkpoint_io_adapter_sha256": runner.sha256_file(checkpoint_io_path()),
        "checkpoint_replace_attempts": 8,
        "ram_reserve_gib": ram_reserve_gib,
        "dispatch_headroom_gib": dispatch_headroom_gib,
        "startup_reservation_seconds": startup_reservation_seconds,
        "memory_wait_timeout_seconds": min(timeout_seconds, 600),
    }
    runner.write_json(root / "execution.json", execution)

    def record_memory() -> float:
        nonlocal current_available_ram, minimum_available_ram
        current_available_ram = available_ram_gib()
        minimum_available_ram = (
            current_available_ram
            if minimum_available_ram is None
            else min(minimum_available_ram, current_available_ram)
        )
        return current_available_ram

    def save_state() -> None:
        record_memory()
        active_jobs = list(active.values())
        state.update(
            process_id=os.getpid(),
            process_status="running",
            execution_backend="cpu_parallel",
            workers=workers,
            spec_hash=runner.fingerprint(spec),
            updated_at=runner.utc_now(),
            active_batches=active_jobs,
            active_batch=active_jobs[0] if active_jobs else None,
            queued_batches=len(pending),
            failed_batches=failed_batches,
            ram_reserve_gib=ram_reserve_gib,
            available_ram_gib=current_available_ram,
            minimum_available_ram_gib=minimum_available_ram,
            waiting_for_memory=waiting_for_memory,
            **checkpoint_progress(snapshot, jobs, runner),
        )
        runner.write_json(root / "status.json", state)

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while pending or active:
                waiting_for_memory = False
                while pending and len(active) < workers and not stopped:
                    now = time.perf_counter()
                    reserved_startups = sum(
                        now - started < startup_reservation_seconds
                        for started in startup_reservations.values()
                    )
                    # Child imports allocate memory after Popen returns; reserve that delay.
                    dispatch_memory = record_memory() - reserved_startups * dispatch_headroom_gib
                    if dispatch_memory < ram_reserve_gib + dispatch_headroom_gib:
                        waiting_for_memory = True
                        if memory_wait_started is None:
                            memory_wait_started = time.perf_counter()
                        break
                    memory_wait_started = None
                    if runner.fingerprint(
                        runner.evaluation_spec(snapshot, build_id, batch_size)
                    ) != runner.fingerprint(spec):
                        stopped = True
                        first_error = ValueError(
                            "Snapshot/config/environment changed during execution"
                        )
                        break
                    job = pending.pop(0)
                    future = executor.submit(
                        execute_batch, snapshot, build_id, job, timeout_seconds
                    )
                    active[future] = job
                    startup_reservations[future] = time.perf_counter()
                    print(f"Start CPU batch: {job['run_id']}", flush=True)
                save_state()
                if not active:
                    if pending and waiting_for_memory and not stopped:
                        assert memory_wait_started is not None
                        elapsed_wait = time.perf_counter() - memory_wait_started
                        if elapsed_wait >= min(timeout_seconds, 600):
                            raise MemoryError(
                                f"RAM remained below dispatch threshold for {elapsed_wait:.1f}s; "
                                f"available={current_available_ram:.2f} GiB, "
                                f"reserve={ram_reserve_gib:.2f} GiB"
                            )
                        time.sleep(min(10, min(timeout_seconds, 600) - elapsed_wait))
                        continue
                    break
                done, _ = wait(active, timeout=10, return_when=FIRST_COMPLETED)
                for future in done:
                    job = active.pop(future)
                    startup_reservations.pop(future)
                    try:
                        elapsed = future.result()
                    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError) as exc:
                        first_error = first_error or exc
                        stopped = True
                        failed_batches.append(
                            {"job": job, "error_type": type(exc).__name__, "error": str(exc)}
                        )
                        print(f"Failed batch: {job['run_id']}: {exc}", flush=True)
                    else:
                        state["last_batch_seconds"] = elapsed
                        print(f"Completed CPU batch: {job['run_id']} ({elapsed:.1f}s)", flush=True)
                if done:
                    state = runner.aggregate_batches(snapshot, spec, jobs)
            save_state()
        if first_error is not None:
            raise first_error
        state = runner.aggregate_batches(snapshot, spec, jobs)
        if state["status"] != "complete":
            raise ValueError("All scheduled batches finished but reporting seeds are incomplete")
    except Exception as exc:
        state.update(process_status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    else:
        state.update(process_status="finished")
    finally:
        exception_in_flight = sys.exc_info()[0] is not None
        checkpoint_error = None
        try:
            final_progress = checkpoint_progress(snapshot, jobs, runner)
        except (ValueError, OSError) as exc:
            checkpoint_error = exc
            final_progress = {}
            state.update(
                process_status="failed",
                checkpoint_validation_error=str(exc),
                error_type=type(exc).__name__,
                error=str(exc),
            )
        state.update(
            process_id=os.getpid(),
            workers=workers,
            execution_backend="cpu_parallel",
            spec_hash=runner.fingerprint(spec),
            updated_at=runner.utc_now(),
            failed_batches=failed_batches,
            active_batches=[],
            active_batch=None,
            ram_reserve_gib=ram_reserve_gib,
            available_ram_gib=current_available_ram,
            minimum_available_ram_gib=minimum_available_ram,
            waiting_for_memory=False,
            **final_progress,
        )
        runner.write_json(root / "status.json", state)
        execution.update(
            finished_at=runner.utc_now(),
            process_status=state["process_status"],
            minimum_available_ram_gib=minimum_available_ram,
        )
        runner.write_json(root / "execution.json", execution)
        if checkpoint_error is not None and not exception_in_flight:
            raise checkpoint_error
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--batch-timeout-seconds", type=int, default=10800)
    parser.add_argument("--ram-reserve-gib", type=float, default=5.0)
    args = parser.parse_args(argv)
    snapshot = args.snapshot.resolve()
    try:
        runner = load_runner(snapshot)
        with runner.runner_lock(snapshot / runner.REPORT_DIRECTORY):
            run_parallel_protocol(
                snapshot,
                args.build_id,
                args.workers,
                args.batch_timeout_seconds,
                runner,
                args.ram_reserve_gib,
            )
    except (ValueError, OSError, RuntimeError, MemoryError, subprocess.SubprocessError) as exc:
        print(f"week2-parallel: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
