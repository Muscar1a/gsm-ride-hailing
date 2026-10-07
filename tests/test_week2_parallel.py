from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from gsm_poc.artifacts import fingerprint, read_json, sha256_file, utc_now, write_json

script_root = Path(__file__).resolve().parents[1] / "scripts"


def import_script(name):
    spec = importlib.util.spec_from_file_location(name, script_root / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parallel = import_script("run_week2_parallel")
serial = import_script("run_week2_coverage")
benchmark = import_script("benchmark_week2_cpu")
checkpoint_io = import_script("week2_checkpoint_io")


@pytest.fixture(autouse=True)
def stable_memory_counter(monkeypatch):
    monkeypatch.setattr(parallel, "available_ram_gib", lambda: 32.0)


def fake_runner(tmp_path, jobs, completed):
    spec = {"batch_size": 5, "native_threads": {"OMP_NUM_THREADS": "1"}, "version": 1}
    root = tmp_path / "week2_reporting"
    write_json(root / "frozen_spec.json", spec)

    def aggregate(snapshot, frozen_spec, all_jobs):
        return {
            "status": "complete" if len(completed) == len(all_jobs) else "partial",
            "completed_batches": [job["run_id"] for job in all_jobs if job["run_id"] in completed],
            "completed_seeds": {"RCT_SYN": len(completed)},
        }

    return SimpleNamespace(
        REPORT_DIRECTORY="week2_reporting",
        read_json=read_json,
        write_json=write_json,
        fingerprint=fingerprint,
        sha256_file=sha256_file,
        utc_now=utc_now,
        evaluation_spec=lambda *args: spec,
        batch_jobs=lambda *args: jobs,
        aggregate_batches=aggregate,
    )


def jobs_fixture():
    return [
        {"dgp": "RCT_SYN", "seed": 20001 + index, "seeds": 1, "run_id": f"job-{index}"}
        for index in range(4)
    ]


def test_parallel_command_preserves_original_evaluation_flags(tmp_path, monkeypatch):
    captured = {}

    def capture(command, **kwargs):
        captured.update(command=command, **kwargs)

    monkeypatch.setattr(serial.subprocess, "run", capture)
    job = serial.batch_jobs(5)[0]
    serial.run_batch(tmp_path, "fixed-build", job, 10800)
    command = parallel.batch_command("fixed-build", job)
    assert command[0] == captured["command"][0]
    assert Path(command[1]) == parallel.checkpoint_io_path()
    assert command[2:] == captured["command"][3:]
    assert captured["cwd"] == tmp_path
    assert captured["env"]["PYTHONPATH"] == str(tmp_path / "src")
    assert all(
        captured["env"][name] == "1"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    )


def test_parallel_resume_skips_completed_batches_and_bounds_concurrency(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    completed = {"job-0"}
    runner = fake_runner(tmp_path, jobs, completed)
    spec_path = tmp_path / "week2_reporting/frozen_spec.json"
    original_spec = spec_path.read_bytes()
    gate = threading.Barrier(2)
    lock = threading.Lock()
    calls = []
    active = 0
    peak = 0

    def execute(snapshot, build_id, job, timeout_seconds):
        nonlocal active, peak
        with lock:
            calls.append(job["run_id"])
            active += 1
            peak = max(peak, active)
        if job["run_id"] in ("job-1", "job-2"):
            gate.wait(timeout=3)
        with lock:
            completed.add(job["run_id"])
            active -= 1
        return 0.1

    monkeypatch.setattr(parallel, "execute_batch", execute)
    result = parallel.run_parallel_protocol(tmp_path, "build", 2, 10, runner)
    assert peak == 2
    assert set(calls) == {"job-1", "job-2", "job-3"}
    assert result["process_status"] == "finished"
    assert result["status"] == "complete"
    assert spec_path.read_bytes() == original_spec
    assert read_json(tmp_path / "week2_reporting/execution.json")["model_change"] is False


def test_parallel_failure_records_error_and_does_not_launch_pending_batches(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    runner = fake_runner(tmp_path, jobs, set())
    calls = []

    def fail(snapshot, build_id, job, timeout_seconds):
        calls.append(job["run_id"])
        raise subprocess.CalledProcessError(1, "fixture")

    monkeypatch.setattr(parallel, "execute_batch", fail)
    with pytest.raises(subprocess.CalledProcessError):
        parallel.run_parallel_protocol(tmp_path, "build", 1, 10, runner)
    assert calls == ["job-0"]
    state = read_json(tmp_path / "week2_reporting/status.json")
    assert state["process_status"] == "failed"
    assert state["error_type"] == "CalledProcessError"
    assert state["queued_batches"] == 3
    assert state["failed_batches"][0]["job"]["run_id"] == "job-0"


def test_parallel_foreign_protocol_is_rejected_before_launch(tmp_path, monkeypatch):
    runner = fake_runner(tmp_path, jobs_fixture(), set())
    runner.evaluation_spec = lambda *args: {"batch_size": 5, "version": 2}
    monkeypatch.setattr(parallel, "execute_batch", lambda *args: pytest.fail("Foreign spec ran"))
    with pytest.raises(ValueError, match="Frozen protocol"):
        parallel.run_parallel_protocol(tmp_path, "build", 2, 10, runner)
    assert not (tmp_path / "week2_reporting/execution.json").exists()


def test_checkpoint_progress_counts_finished_failures_and_verifies_original_bytes(tmp_path):
    jobs = jobs_fixture()[:2]
    runner = fake_runner(tmp_path, jobs, set())
    paths = []
    for index, job in enumerate(jobs):
        path = tmp_path / "runs" / job["run_id"] / "evaluation" / f"RCT_SYN-{job['seed']}.json"
        path.parent.mkdir(parents=True)
        metrics = path.with_suffix(".parquet")
        metrics.write_bytes(b"preserved checkpoint fixture")
        write_json(
            path,
            {
                "seed": job["seed"],
                "dgp_id": "RCT_SYN",
                "bootstrap_draws": 199,
                "status": "succeeded" if index == 0 else "failed",
                "metrics_sha256": sha256_file(metrics),
            },
        )
        paths.append(metrics)
    before = paths[0].read_bytes()
    progress = parallel.checkpoint_progress(tmp_path, jobs, runner)
    assert progress["completed_checkpoint_seeds"] == 2
    assert progress["failed_checkpoint_seeds"] == 1
    assert paths[0].read_bytes() == before
    paths[0].write_bytes(b"corrupted fixture")
    with pytest.raises(ValueError, match="checksum"):
        parallel.checkpoint_progress(tmp_path, jobs, runner)


def test_parallel_rejects_corrupt_checkpoint_before_any_child(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    runner = fake_runner(tmp_path, jobs, set())
    path = tmp_path / "runs/job-0/evaluation/RCT_SYN-20001.json"
    write_json(
        path,
        {
            "status": "succeeded",
            "seed": 20001,
            "dgp_id": "RCT_SYN",
            "bootstrap_draws": 199,
            "metrics_sha256": "missing",
        },
    )
    monkeypatch.setattr(
        parallel, "execute_batch", lambda *args: pytest.fail("Corrupt checkpoint ran")
    )
    with pytest.raises(ValueError, match="checksum"):
        parallel.run_parallel_protocol(tmp_path, "build", 2, 10, runner)
    assert not (tmp_path / "week2_reporting/execution.json").exists()


@pytest.mark.parametrize("value", ["", "0", "21", "1,1", "1,nope"])
def test_benchmark_rejects_unbounded_or_duplicate_worker_counts(value):
    with pytest.raises(ValueError):
        benchmark.worker_counts(value)


def test_low_memory_defers_new_batches_and_resumes_when_memory_returns(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    completed = set()
    runner = fake_runner(tmp_path, jobs, completed)
    memory = {"available": 5.5}
    monkeypatch.setattr(parallel, "available_ram_gib", lambda: memory["available"])
    monkeypatch.setattr(parallel.time, "sleep", lambda _: memory.update(available=32.0))

    def execute(snapshot, build_id, job, timeout_seconds):
        assert memory["available"] == 32.0
        completed.add(job["run_id"])
        return 0.1

    monkeypatch.setattr(parallel, "execute_batch", execute)
    state = parallel.run_parallel_protocol(tmp_path, "build", 1, 10, runner, ram_reserve_gib=5.0)
    assert state["status"] == "complete"
    assert state["minimum_available_ram_gib"] == 5.5
    assert state["waiting_for_memory"] is False


def test_low_memory_wait_is_bounded_and_does_not_launch_jobs(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    runner = fake_runner(tmp_path, jobs, set())
    clock = [0.0]
    monkeypatch.setattr(parallel, "available_ram_gib", lambda: 4.5)
    monkeypatch.setattr(parallel.time, "perf_counter", lambda: clock[0])

    def advance_clock(seconds):
        clock[0] += seconds

    monkeypatch.setattr(parallel.time, "sleep", advance_clock)
    monkeypatch.setattr(parallel, "execute_batch", lambda *args: pytest.fail("Low RAM ran a job"))
    with pytest.raises(MemoryError, match="RAM remained below"):
        parallel.run_parallel_protocol(tmp_path, "build", 1, 10, runner, ram_reserve_gib=5.0)
    state = read_json(tmp_path / "week2_reporting/status.json")
    assert state["process_status"] == "failed"
    assert state["completed_seeds"]["RCT_SYN"] == 0


def test_startup_reservations_prevent_many_children_from_overcommitting_ram(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    completed = set()
    runner = fake_runner(tmp_path, jobs, completed)
    monkeypatch.setattr(parallel, "available_ram_gib", lambda: 6.5)
    original_wait = parallel.wait
    outstanding_counts = []

    def observe_wait(futures, **kwargs):
        outstanding_counts.append(len(futures))
        return original_wait(futures, **kwargs)

    def execute(snapshot, build_id, job, timeout_seconds):
        completed.add(job["run_id"])
        return 0.1

    monkeypatch.setattr(parallel, "wait", observe_wait)
    monkeypatch.setattr(parallel, "execute_batch", execute)
    result = parallel.run_parallel_protocol(tmp_path, "build", 4, 10, runner, ram_reserve_gib=5.0)
    assert result["status"] == "complete"
    assert outstanding_counts == [1, 1, 1, 1]


def test_fifty_worker_pool_resumes_only_unfinished_batches(tmp_path, monkeypatch):
    jobs = jobs_fixture()
    completed = {"job-0"}
    runner = fake_runner(tmp_path, jobs, completed)
    calls = []

    def execute(snapshot, build_id, job, timeout_seconds):
        calls.append(job["run_id"])
        completed.add(job["run_id"])
        return 0.1

    monkeypatch.setattr(parallel, "execute_batch", execute)
    state = parallel.run_parallel_protocol(tmp_path, "build", 50, 21600, runner)
    assert set(calls) == {"job-1", "job-2", "job-3"}
    assert state["status"] == "complete"
    assert state["workers"] == 50
    execution = read_json(tmp_path / "week2_reporting/execution.json")
    assert execution["workers"] == 50
    assert execution["ram_reserve_gib"] == 5.0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing regression")
def test_atomic_replace_retries_until_windows_reader_releases_checkpoint(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    write_json(path, {"status": "running"})
    delays = []
    with path.open("r", encoding="utf-8") as reader:

        def release_reader(delay):
            assert read_json(path) == {"status": "running"}
            delays.append(delay)
            reader.close()

        monkeypatch.setattr(checkpoint_io.time, "sleep", release_reader)
        with checkpoint_io.atomic_path_with_retry(path) as temporary:
            temporary.write_text('{"status": "succeeded"}', encoding="utf-8")
    assert delays == [0.02]
    assert read_json(path) == {"status": "succeeded"}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing regression")
def test_persistent_windows_lock_is_bounded_and_preserves_previous_checkpoint(
    tmp_path, monkeypatch
):
    path = tmp_path / "checkpoint.json"
    write_json(path, {"status": "running"})
    original = path.read_bytes()
    delays = []
    monkeypatch.setattr(checkpoint_io.time, "sleep", delays.append)
    with path.open("r", encoding="utf-8"):
        with pytest.raises(PermissionError):
            with checkpoint_io.atomic_path_with_retry(path) as temporary:
                temporary.write_text('{"status": "succeeded"}', encoding="utf-8")
    assert tuple(delays) == checkpoint_io.REPLACE_RETRY_DELAYS
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_other_write_errors_are_not_retried_or_hidden(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    write_json(path, {"status": "running"})
    original = path.read_bytes()

    def fail_replace(*args):
        raise OSError("disk is full")

    monkeypatch.setattr(checkpoint_io.os, "replace", fail_replace)
    monkeypatch.setattr(
        checkpoint_io.time, "sleep", lambda _: pytest.fail("Unrelated error retried")
    )
    with pytest.raises(OSError, match="disk is full"):
        with checkpoint_io.atomic_path_with_retry(path) as temporary:
            temporary.write_text('{"status": "succeeded"}', encoding="utf-8")
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_io_adapter_preserves_checkpoint_serialization_and_frozen_source(tmp_path, monkeypatch):
    from gsm_poc import artifacts

    value = {"status": "succeeded", "label": "Bun — nghiệm thu", "theta": [0.1, -0.2]}
    before = tmp_path / "original.json"
    after = tmp_path / "adapted.json"
    write_json(before, value)
    source_path = Path(artifacts.__file__)
    original_source = source_path.read_bytes()
    monkeypatch.setattr(artifacts, "atomic_path", artifacts.atomic_path)
    checkpoint_io.install_checkpoint_io()
    write_json(after, value)
    assert after.read_bytes() == before.read_bytes()
    assert source_path.read_bytes() == original_source
