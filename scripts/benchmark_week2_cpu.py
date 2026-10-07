"""Measure CPU job throughput with the frozen Week 2 evaluator; probe seed only."""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def worker_counts(value: str) -> list[int]:
    counts = [int(part) for part in value.split(",")]
    if (
        not counts
        or len(set(counts)) != len(counts)
        or any(not 1 <= count <= 20 for count in counts)
    ):
        raise ValueError("Use distinct worker counts between one and twenty")
    return counts


def run_worker(snapshot: Path, output: Path, draws: int) -> None:
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"
    sys.path.insert(0, str(snapshot / "src"))
    import pandas as pd

    import gsm_poc
    from gsm_poc.artifacts import environment, fingerprint, read_json, sha256_file
    from gsm_poc.config import Config
    from gsm_poc.evaluate import monte_carlo

    if output.exists() or output.is_relative_to(snapshot):
        raise ValueError("Probe outputs must be new directories outside the frozen snapshot")
    if not Path(gsm_poc.__file__).resolve().is_relative_to(snapshot):
        raise ValueError("Probe must import the frozen evaluation package")
    spec = read_json(snapshot / "week2_reporting/frozen_spec.json")
    if environment(snapshot) != spec["environment"]:
        raise ValueError("Frozen code/environment changed")
    config = Config.load(snapshot / "configs/default.toml")
    if fingerprint(config.as_dict()) != fingerprint(spec["config"]):
        raise ValueError("Frozen configuration changed")
    gold = snapshot / "data/gold" / spec["build_id"]
    context_path = gold / "context_templates.parquet"
    metadata_path = gold / "context_templates.json"
    if (
        sha256_file(context_path) != spec["context_sha256"]
        or sha256_file(metadata_path) != spec["context_metadata_sha256"]
    ):
        raise ValueError("Frozen context changed")
    config = dataclasses.replace(
        config,
        simulation=dataclasses.replace(config.simulation, seed=19001, dgp="RCT_SYN"),
        evaluation=dataclasses.replace(
            config.evaluation, seeds=1, dgps=("RCT_SYN",), bootstrap_draws=draws
        ),
    )
    output.mkdir(parents=True)
    context_version = fingerprint(
        {"metadata": read_json(metadata_path), "parquet_sha256": sha256_file(context_path)}
    )
    started = time.perf_counter()
    artifacts = monte_carlo(
        config, pd.read_parquet(context_path), context_version, output / "evaluation", output.name
    )
    checkpoint = read_json(output / "evaluation/RCT_SYN-19001.json")
    frame = pd.read_parquet(artifacts["seed_metrics"])
    if checkpoint["status"] != "succeeded" or len(frame) != 12:
        raise ValueError("Probe evaluator failed or omitted metric cells")
    if not frame.successful_draws.eq(draws).all():
        raise ValueError("Probe bootstrap draws failed")
    if environment(snapshot) != spec["environment"]:
        raise ValueError("Frozen code/environment changed during the probe")
    write_report(
        output / "report.json",
        {
            "status": "succeeded",
            "seed": 19001,
            "draws": draws,
            "duration_seconds": time.perf_counter() - started,
            "environment": spec["environment"],
            "config": config.as_dict(),
            "context_sha256": spec["context_sha256"],
            "metrics_sha256": sha256_file(artifacts["seed_metrics"]),
            "probe_script_sha256": sha256_file(Path(__file__)),
            "included_in_reporting": False,
        },
    )


def run_probe(snapshot: Path, output: Path, draws: int, timeout_seconds: int) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--snapshot",
        str(snapshot),
        "--output",
        str(output),
        "--draws",
        str(draws),
    ]
    started = time.perf_counter()
    with output.with_suffix(".log").open("x", encoding="utf-8") as log:
        subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout_seconds
        )
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    report["wall_seconds"] = time.perf_counter() - started
    report["output"] = str(output)
    return report


def sample_resources(stop_event: threading.Event, samples: list[dict]) -> None:
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

    kernel = ctypes.windll.kernel32
    previous = None
    while not stop_event.is_set():
        idle, kernel_time, user_time = (ctypes.c_ulonglong() for _ in range(3))
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if kernel.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel_time), ctypes.byref(user_time)
        ) and kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
            total = kernel_time.value + user_time.value
            sample = {
                "time": time.time(),
                "available_ram_gib": memory.available_physical / 2**30,
                "used_ram_gib": (memory.total_physical - memory.available_physical) / 2**30,
            }
            if previous is not None and total > previous[1]:
                sample["cpu_percent"] = 100 * (
                    1 - (idle.value - previous[0]) / (total - previous[1])
                )
            samples.append(sample)
            previous = idle.value, total
        stop_event.wait(1)


def run_benchmark(snapshot: Path, output: Path, counts: list[int], draws: int, waves: int) -> dict:
    if os.name != "nt":
        raise ValueError("CPU scaling uses the frozen Windows reporting environment")
    if output.exists() or output.is_relative_to(snapshot):
        raise ValueError("Benchmark output must be new and outside the snapshot")
    if not 1 <= waves <= 2:
        raise ValueError("Use one or two bounded waves")
    output.mkdir(parents=True)
    report = {
        "status": "running",
        "seed": 19001,
        "draws": draws,
        "waves": waves,
        "included_in_reporting": False,
        "configurations": [],
    }
    reference = None
    import pandas as pd

    try:
        for count in counts:
            samples: list[dict] = []
            stop_event = threading.Event()
            monitor = threading.Thread(
                target=sample_resources, args=(stop_event, samples), daemon=True
            )
            monitor.start()
            started = time.perf_counter()
            runs = []
            print(
                f"CPU benchmark: {count} workers, {count * waves} probe jobs, {draws} draws",
                flush=True,
            )
            try:
                with ThreadPoolExecutor(max_workers=count) as executor:
                    futures = [
                        executor.submit(
                            run_probe, snapshot, output / f"w{count}-job{index:02d}", draws, 1800
                        )
                        for index in range(count * waves)
                    ]
                    for future in as_completed(futures):
                        result = future.result()
                        metrics_path = Path(result["output"]) / "evaluation/seed_metrics.parquet"
                        if (
                            hashlib.sha256(metrics_path.read_bytes()).hexdigest()
                            != result["metrics_sha256"]
                        ):
                            raise ValueError("Probe metrics checksum changed")
                        frame = pd.read_parquet(metrics_path).drop(columns="run_id")
                        frame = frame.sort_values(
                            ["estimator", "outcome", "treatment"]
                        ).reset_index(drop=True)
                        if reference is None:
                            reference = frame
                        else:
                            pd.testing.assert_frame_equal(
                                reference,
                                frame,
                                check_dtype=False,
                                check_exact=False,
                                rtol=0,
                                atol=1e-12,
                            )
                        runs.append(result)
            finally:
                stop_event.set()
                monitor.join(timeout=2)
            elapsed = time.perf_counter() - started
            configuration = {
                "workers": count,
                "jobs": len(runs),
                "wall_seconds": elapsed,
                "jobs_per_hour": len(runs) * 3600 / elapsed,
                "min_available_ram_gib": min(
                    (item["available_ram_gib"] for item in samples), default=None
                ),
                "peak_cpu_percent": max(
                    (item.get("cpu_percent", 0) for item in samples), default=None
                ),
                "runs": runs,
            }
            report["configurations"].append(configuration)
            write_report(output / f"resources-w{count}.json", {"samples": samples})
            write_report(output / "benchmark.json", report)
            print(
                f"CPU benchmark: {count} workers -> "
                f"{configuration['jobs_per_hour']:.2f} probe jobs/hour",
                flush=True,
            )
        best = max(report["configurations"], key=lambda item: item["jobs_per_hour"])
        report.update(
            status="succeeded",
            selected_workers=best["workers"],
            selection=(
                "maximum measured probe throughput; requires 199-draw confirmation"
                if draws == 10
                else "passed full 199-draw concurrency confirmation for requested worker counts"
            ),
        )
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_report(output / "benchmark.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draws", type=int, choices=(10, 199), default=10)
    parser.add_argument("--workers", default="1,2,4,6,8")
    parser.add_argument("--waves", type=int, default=2)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        run_worker(args.snapshot.resolve(), args.output.resolve(), args.draws)
    else:
        run_benchmark(
            args.snapshot.resolve(),
            args.output.resolve(),
            worker_counts(args.workers),
            args.draws,
            args.waves,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
