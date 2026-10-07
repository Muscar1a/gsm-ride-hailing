"""Compare a frozen CPU probe with explicit cuML nuisance forests.

Development only: separate single-output GPU forests change the nuisance learner.
No outputs from this script belong to the frozen 500-job coverage protocol.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Match the reporting process's native thread limits, before numerical imports.
for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import numpy as np  # noqa: E402
from sklearn.base import BaseEstimator, RegressorMixin  # noqa: E402
from sklearn.ensemble import RandomForestRegressor as CpuForest  # noqa: E402


def snapshot_source_hash(snapshot: Path) -> str:
    """Match the frozen Windows manifest without changing its source or paths."""
    source_checksums = {
        path.relative_to(snapshot).as_posix().replace("/", "\\"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in (snapshot / "src/gsm_poc").rglob("*.py")
    }
    encoded = json.dumps(source_checksums, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class ProbeForest(RegressorMixin, BaseEstimator):
    """Cloneable single-output forest adapter, with explicit GPU execution."""

    fit_counts = {"cpu": 0, "gpu": 0, "uniform_weight_omissions": 0}

    def __init__(
        self,
        n_estimators: int = 50,
        max_depth: int = 6,
        min_samples_leaf: int = 20,
        random_state: int = 19001,
        n_jobs: int = 1,
        backend: str = "gpu",
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.n_jobs = n_jobs
        self.backend = backend

    def fit(
        self, x_data: np.ndarray, y_data: np.ndarray, sample_weight: np.ndarray | None = None
    ) -> ProbeForest:
        if self.backend not in ("cpu", "gpu"):
            raise ValueError("Probe forest backend must be cpu or gpu")
        x_data = np.asarray(x_data, dtype=np.float32)
        y_data = np.asarray(y_data, dtype=np.float32)
        if x_data.ndim != 2 or y_data.ndim not in (1, 2) or len(x_data) != len(y_data):
            raise ValueError("Invalid nuisance training matrix/target shapes")
        if not np.isfinite(x_data).all() or not np.isfinite(y_data).all():
            raise ValueError("Nuisance training inputs must be finite")
        self.single_output_ = y_data.ndim == 1
        targets = y_data[:, None] if self.single_output_ else y_data
        self.n_features_in_ = x_data.shape[1]
        weights = None if sample_weight is None else np.asarray(sample_weight, dtype=np.float32)
        if weights is not None and (
            weights.shape != (len(x_data),)
            or not np.isfinite(weights).all()
            or (weights <= 0).any()
        ):
            raise ValueError("Invalid sample weights")
        self.models_: list[Any] = []
        if self.backend == "gpu":
            import cupy as cp
            from cuml.ensemble import RandomForestRegressor as GpuForest

            device_features = cp.asarray(x_data)
        for output_index in range(targets.shape[1]):
            parameters = {
                "n_estimators": self.n_estimators,
                "max_depth": self.max_depth,
                "min_samples_leaf": self.min_samples_leaf,
                "random_state": self.random_state + output_index,
            }
            if self.backend == "cpu":
                model = CpuForest(**parameters, n_jobs=self.n_jobs)
                model.fit(x_data, targets[:, output_index], sample_weight=weights)
            else:
                model = GpuForest(**parameters, n_streams=1, n_bins=128, output_type="numpy")
                fit_parameters = inspect.signature(model.fit).parameters
                if "sample_weight" in fit_parameters:
                    model.fit(
                        device_features,
                        cp.asarray(targets[:, output_index]),
                        sample_weight=None if weights is None else cp.asarray(weights),
                    )
                else:
                    # Positive constant weights do not change a forest's optimization.
                    # Nonuniform weights must never be silently discarded.
                    if weights is not None and not np.equal(weights, weights[0]).all():
                        raise ValueError(
                            "Installed cuML forest does not support nonuniform weights"
                        )
                    if weights is not None:
                        self.fit_counts["uniform_weight_omissions"] += 1
                    model.fit(device_features, cp.asarray(targets[:, output_index]))
                cp.cuda.Stream.null.synchronize()
                if not type(model).__module__.startswith("cuml."):
                    raise RuntimeError("GPU nuisance model unexpectedly used a CPU implementation")
            self.fit_counts[self.backend] += 1
            self.models_.append(model)
        return self

    def predict(self, x_data: np.ndarray) -> np.ndarray:
        x_data = np.asarray(x_data, dtype=np.float32)
        if x_data.ndim != 2 or x_data.shape[1] != self.n_features_in_:
            raise ValueError("Invalid nuisance prediction feature shape")
        if self.backend == "gpu":
            import cupy as cp

            features = cp.asarray(x_data)
            values = [np.asarray(model.predict(features)) for model in self.models_]
            cp.cuda.Stream.null.synchronize()
        else:
            values = [model.predict(x_data) for model in self.models_]
        prediction = np.column_stack(values).astype(float)
        return prediction[:, 0] if self.single_output_ else prediction


def sample_gpu(stop_event: threading.Event, samples: list[dict]) -> None:
    executable = shutil.which("nvidia-smi")
    if executable is None and Path("/usr/lib/wsl/lib/nvidia-smi").is_file():
        executable = "/usr/lib/wsl/lib/nvidia-smi"
    if executable is None:
        return
    while not stop_event.is_set():
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=memory.used,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            values = result.stdout.strip().splitlines()[0].split(",")
            samples.append(
                {
                    "elapsed_seconds": time.perf_counter(),
                    "memory_mib": float(values[0]),
                    "utilization_percent": float(values[1]),
                    "temperature_celsius": float(values[2]),
                }
            )
        except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
            samples.append({"telemetry_error": str(exc)})
        stop_event.wait(0.5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("cpu", "gpu", "matching_cpu"), required=True)
    parser.add_argument("--draws", type=int, choices=(2, 10, 199), required=True)
    args = parser.parse_args(argv)
    snapshot = args.snapshot.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Probe output already exists; use a new directory")
    if output.is_relative_to(snapshot):
        raise ValueError("Probe outputs must remain outside the frozen coverage snapshot")
    output.mkdir(parents=True)
    sys.path.insert(0, str(snapshot / "src"))
    import pandas as pd

    import gsm_poc
    import gsm_poc.estimate as estimation
    import gsm_poc.uncertainty as uncertainty
    from gsm_poc.artifacts import (
        code_hash,
        fingerprint,
        read_json,
        sha256_file,
        utc_now,
        write_json,
    )
    from gsm_poc.config import Config
    from gsm_poc.evaluate import method_metrics
    from gsm_poc.features import date_splits
    from gsm_poc.generate import generate

    if not Path(gsm_poc.__file__).resolve().is_relative_to(snapshot):
        raise ValueError("Evaluation imports must come exclusively from the frozen snapshot")
    spec = read_json(snapshot / "week2_reporting/frozen_spec.json")
    original_source_hash = snapshot_source_hash(snapshot)
    if original_source_hash != spec["environment"]["source_code_sha256"]:
        raise ValueError("Frozen evaluation code changed")
    config = Config.load(snapshot / "configs/default.toml")
    if fingerprint(config.as_dict()) != fingerprint(spec["config"]):
        raise ValueError("Frozen evaluation configuration changed")
    config = dataclasses.replace(
        config,
        simulation=dataclasses.replace(config.simulation, seed=19001, dgp="RCT_SYN"),
        evaluation=dataclasses.replace(config.evaluation, bootstrap_draws=args.draws),
    )
    gold = snapshot / "data/gold" / spec["build_id"]
    context_path = gold / "context_templates.parquet"
    metadata_path = gold / "context_templates.json"
    if (
        sha256_file(context_path) != spec["context_sha256"]
        or sha256_file(metadata_path) != spec["context_metadata_sha256"]
    ):
        raise ValueError("Frozen TLC context changed")
    context = pd.read_parquet(context_path)
    context_version = fingerprint(
        {"metadata": read_json(metadata_path), "parquet_sha256": sha256_file(context_path)}
    )
    versions = {}
    for package_name in (
        "numpy",
        "pandas",
        "scipy",
        "scikit-learn",
        "econml",
        "joblib",
        "cuml-cu12",
        "cupy-cuda12x",
        "nvidia-cuda-runtime-cu12",
        "nvidia-cuda-nvrtc-cu12",
    ):
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = "unavailable"
    report = {
        "status": "running",
        "started_at": utc_now(),
        "seed": 19001,
        "backend": args.backend,
        "bootstrap_draws": args.draws,
        "config": config.as_dict(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": versions,
        "frozen_source_sha256": original_source_hash,
        "native_source_sha256": code_hash(snapshot),
        "probe_script_sha256": sha256_file(Path(__file__)),
        "context_sha256": spec["context_sha256"],
        "evidence_level": "C",
        "included_in_reporting": False,
        "method_change": "none"
        if args.backend == "cpu"
        else "Separate single-output nuisance forests; float32 inputs"
        + ("; cuML quantile splits" if args.backend == "gpu" else "; sklearn exact splits"),
        "estimators": {},
    }
    write_json(output / "report.json", report)
    stop_event = threading.Event()
    telemetry: list[dict] = []
    monitor = threading.Thread(target=sample_gpu, args=(stop_event, telemetry), daemon=True)
    monitor.start()
    started = time.perf_counter()
    try:
        if args.backend == "gpu":
            import cupy as cp

            cp.cuda.Device(0).use()
            gpu_properties = cp.cuda.runtime.getDeviceProperties(0)
            report["gpu"] = {
                "name": gpu_properties["name"].decode(),
                "total_memory_bytes": gpu_properties["totalGlobalMem"],
                "driver_version": cp.cuda.runtime.driverGetVersion(),
                "runtime_version": cp.cuda.runtime.runtimeGetVersion(),
            }
        if args.backend != "cpu":
            forest_backend = "gpu" if args.backend == "gpu" else "cpu"
            estimation.RandomForestRegressor = functools.partial(
                ProbeForest, backend=forest_backend
            )
        data = generate(config, context, context_version)
        splits = date_splits(data.blocks, config)
        report["blocks"] = {name: len(frame) for name, frame in splits.items()}
        report["train_weight_values"] = sorted(splits["train"].n_sessions.unique().tolist())
        metrics = []
        original_fit = uncertainty.fit_estimator
        draw_counts = dict.fromkeys(config.model.estimators, 0)

        def progress_fit(train, fit_config, estimator, seed=None):
            fit_result = original_fit(train, fit_config, estimator, seed=seed)
            draw_counts[estimator] += 1
            if draw_counts[estimator] % 25 == 0:
                print(f"{args.backend}: {estimator}, draw {draw_counts[estimator]}", flush=True)
            return fit_result

        uncertainty.fit_estimator = progress_fit
        for estimator in config.model.estimators:
            print(f"{args.backend}: {estimator}, {args.draws} bootstrap draws", flush=True)
            method_config = dataclasses.replace(
                config,
                model=dataclasses.replace(
                    config.model, estimators=(estimator,), scenario_estimator=estimator
                ),
            )
            method_started = time.perf_counter()
            results, _ = estimation.fit_all(data.blocks, method_config)
            result = results[estimator]
            if result.bundle is None:
                raise ValueError(f"Probe estimator is not identified: {estimator}")
            draws = uncertainty.bootstrap(splits["train"], method_config, estimator)
            report["estimators"][estimator] = {
                "duration_seconds": time.perf_counter() - method_started,
                "requested_draws": args.draws,
                "successful_draws": draws.successful_draws,
                "interval_status": draws.interval_status,
                "theta": result.bundle.theta.tolist(),
                "diagnostics": result.diagnostics,
            }
            metrics.extend(method_metrics(result, draws, data, method_config, "gpu-probe-19001"))
            write_json(output / "report.json", report)
            if draws.successful_draws != args.draws:
                raise ValueError(f"Probe bootstrap failures for {estimator}")
        metric_frame = pd.DataFrame(metrics)
        metric_frame["probe_backend"] = args.backend
        metric_frame.to_csv(output / "metrics.csv", index=False)
        if args.backend == "gpu" and ProbeForest.fit_counts["gpu"] == 0:
            raise RuntimeError("No GPU forest fit was executed")
        if snapshot_source_hash(snapshot) != original_source_hash:
            raise ValueError("Frozen source changed during the probe")
        report.update(status="succeeded", metrics_sha256=sha256_file(output / "metrics.csv"))
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        stop_event.set()
        monitor.join(timeout=6)
        report.update(
            finished_at=utc_now(),
            duration_seconds=time.perf_counter() - started,
            forest_fit_counts=ProbeForest.fit_counts.copy(),
        )
        valid_samples = [sample for sample in telemetry if "memory_mib" in sample]
        report["telemetry"] = {
            "samples": len(valid_samples),
            "peak_global_vram_mib": max(
                (sample["memory_mib"] for sample in valid_samples), default=None
            ),
            "peak_gpu_utilization_percent": max(
                (sample["utilization_percent"] for sample in valid_samples), default=None
            ),
        }
        write_json(output / "telemetry.json", telemetry)
        write_json(output / "report.json", report)
        print(f"Probe {report['status']}: {report['duration_seconds']:.2f}s; {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
