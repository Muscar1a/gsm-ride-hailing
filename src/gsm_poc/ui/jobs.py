"""One bounded worker process per dashboard; reuse the existing pipeline."""

from __future__ import annotations

import dataclasses
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gsm_poc.core.artifacts import (
    completed_run,
    read_json,
    safe_id,
    sha256_file,
    utc_now,
    write_json,
)
from gsm_poc.core.config import Config
from gsm_poc.pipeline.pipeline import Pipeline


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    action: Literal["train", "prepare_demand", "simulate"]
    source_run_id: str | None = None
    estimator: Literal["naive_ols", "adjusted_ols", "dml"] = "adjusted_ols"
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    bootstrap_draws: int = Field(default=10, ge=0, le=39)
    delta_x: float = Field(default=0, ge=-0.9, le=1)
    delta_y: float = Field(default=0, ge=-0.9, le=1)
    upload_id: str | None = None


def prepare_job(workspace: Path, request: JobRequest) -> dict:
    if request.action == "train":
        config = Config.load(workspace / "configs/week4.toml")
        config = dataclasses.replace(
            config,
            model=dataclasses.replace(
                config.model,
                estimators=(request.estimator,),
                scenario_estimator=request.estimator,
                n_trees=min(config.model.n_trees, 20),
            ),
            evaluation=dataclasses.replace(
                config.evaluation, bootstrap_draws=request.bootstrap_draws
            ),
        )
    else:
        if not request.source_run_id:
            raise ValueError("Select a completed source run")
        manifest = completed_run(workspace, request.source_run_id)
        stage = "prepare_demand" if request.action == "simulate" else "fit"
        stages = manifest.get("stages", {})
        if stages.get(stage, {}).get("status") != "succeeded" and not (
            stage == "fit" and stages.get("freeze_choice", {}).get("status") == "succeeded"
        ):
            raise ValueError(f"Source run requires a completed {stage} stage")
        source_config = manifest.get("choice_source", {}).get("source_config", manifest["config"])
        config = Config.from_dict(source_config, workspace)
    config = dataclasses.replace(
        config, simulation=dataclasses.replace(config.simulation, seed=request.seed)
    )
    upload = None
    if request.upload_id:
        if request.action != "simulate":
            raise ValueError("Request CSV uploads can only be used for simulation")
        directory = workspace / ".cache/web/uploads" / safe_id(request.upload_id)
        upload = read_json(directory / "metadata.json")
        if upload["kind"] != "requests" or sha256_file(directory / "data.csv") != upload["sha256"]:
            raise ValueError("Upload is not a verified request CSV")
    return {"request": request.model_dump(), "config": config.as_dict(), "upload": upload}


def execute_job(workspace: Path, job_id: str) -> None:
    payload = read_json(workspace / ".cache/web/jobs" / safe_id(job_id) / "request.json")
    request = JobRequest.model_validate(payload["request"])
    config = Config.from_dict(payload["config"], workspace)
    pipeline = Pipeline(config, job_id)
    try:
        if request.action == "train":
            pipeline.run_all(include_evaluation=False)
        elif request.action == "prepare_demand":
            from gsm_poc.causal.scenario import ScenarioRequest

            assert request.source_run_id is not None
            pipeline.prepare_demand(
                request.source_run_id,
                workspace / "configs/week3_snapshot.json",
                ScenarioRequest(
                    delta_price_x=request.delta_x,
                    delta_price_y=request.delta_y,
                    interval_level=config.evaluation.interval_level,
                ),
            )
            pipeline.run.complete()
        else:
            assert request.source_run_id is not None
            requests_path = None
            if request.upload_id:
                requests_path = (
                    workspace / ".cache/web/uploads" / safe_id(request.upload_id) / "data.csv"
                )
                if sha256_file(requests_path) != payload["upload"]["sha256"]:
                    raise ValueError("Uploaded requests changed after the job was submitted")
            pipeline.simulate_marketplace(
                request.source_run_id,
                workspace / "configs/week3_poc.json",
                requests_path,
                compensation_path=workspace / "configs/week3_compensation.json",
            )
            pipeline.run.complete()
    except Exception as exc:
        if pipeline.run.manifest["status"] != "failed":
            pipeline.run.fail_stage("web_action", exc)
        raise


class JobManager:
    def __init__(self, workspace: Path, timeout_seconds: int = 600) -> None:
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.process: subprocess.Popen | None = None
        self.stop_requested = False
        self.job_id: str | None = None

    def start(self, payload: dict) -> dict:
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("A job is already running. Wait for it or cancel it first.")
            job_id = f"web-{uuid.uuid4().hex}"
            self.job_id = job_id
            directory = self.workspace / ".cache/web/jobs" / job_id
            write_json(directory / "request.json", payload)
            record = {
                "job_id": job_id,
                "run_id": job_id,
                "action": payload["request"]["action"],
                "status": "running",
                "created_at": utc_now(),
                "timeout_seconds": self.timeout_seconds,
            }
            write_json(directory / "status.json", record)
            self.stop_requested = False
            self.thread = threading.Thread(target=self.run_worker, args=(record,), daemon=True)
            self.thread.start()
            return record

    def run_worker(self, record: dict) -> None:
        directory = self.workspace / ".cache/web/jobs" / record["job_id"]
        try:
            with (directory / "output.log").open("wb") as output:
                with self.lock:
                    if self.stop_requested:
                        raise RuntimeError("Job cancelled before launch")
                    self.process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "gsm_poc.ui.worker",
                            str(self.workspace),
                            record["job_id"],
                        ],
                        cwd=self.workspace,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                    )
                try:
                    exit_code = self.process.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=10)
                    raise TimeoutError(f"Job exceeded {self.timeout_seconds} seconds") from None
            if self.stop_requested:
                raise RuntimeError("Job cancelled")
            if exit_code:
                raise RuntimeError(f"Worker exited with code {exit_code}. See the job log.")
            completed_run(self.workspace, record["run_id"])
            record["status"] = "succeeded"
        except Exception as exc:
            record.update(status="failed", error=str(exc))
            manifest_path = self.workspace / "runs" / record["run_id"] / "manifest.json"
            if manifest_path.exists():
                manifest = read_json(manifest_path)
                if manifest["status"] not in ("failed", "succeeded"):
                    manifest.update(status="failed", web_worker_error=str(exc))
                    write_json(manifest_path, manifest)
        finally:
            record["ended_at"] = utc_now()
            write_json(directory / "status.json", record)
            with self.lock:
                self.process = None

    def read(self, job_id: str) -> dict:
        directory = self.workspace / ".cache/web/jobs" / safe_id(job_id)
        record = read_json(directory / "status.json")
        log = directory / "output.log"
        if log.exists():
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 16_384))
                record["log"] = stream.read().decode("utf-8", errors="replace")
        manifest_path = self.workspace / "runs" / job_id / "manifest.json"
        if manifest_path.exists():
            record["stages"] = read_json(manifest_path)["stages"]
        return record

    def close(self) -> None:
        with self.lock:
            self.stop_requested = True
            if self.process and self.process.poll() is None:
                self.process.terminate()
        if self.thread:
            self.thread.join(timeout=15)
