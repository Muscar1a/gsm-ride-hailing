"""Atomic artifacts and auditable stage lifecycle; no success-shaped error defaults."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from gsm_poc.config import Config


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, (Path, dt.date, dt.datetime)):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=_json_default, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


@contextlib.contextmanager
def atomic_path(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        yield temporary
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    with atomic_path(path) as temporary:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, default=_json_default, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    with atomic_path(path) as temporary:
        if path.suffix == ".csv":
            frame.to_csv(temporary, index=False)
        else:
            frame.to_parquet(temporary, index=False)


def write_model(path: Path, model: Any) -> None:
    with atomic_path(path) as temporary:
        joblib.dump(model, temporary, compress=3)


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Artifact IDs must use letters, digits, underscores or hyphens")
    return value


def code_hash(workspace: Path) -> str:
    paths = sorted((workspace / "src/gsm_poc").rglob("*.py"))
    return fingerprint({str(p.relative_to(workspace)): sha256_file(p) for p in paths})


def environment(workspace: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        revision = None
    packages = {}
    for name in (
        "gsm-poc",
        "numpy",
        "pandas",
        "duckdb",
        "pyarrow",
        "scikit-learn",
        "econml",
        "streamlit",
        "scipy",
        "joblib",
        "simpy",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "unavailable"
    lock = workspace / "uv.lock"
    return {
        "python": platform.python_version(),
        "packages": packages,
        "git_revision": revision,
        "source_code_sha256": code_hash(workspace),
        "lock_sha256": sha256_file(lock) if lock.exists() else None,
    }


class Run:
    def __init__(self, config: Config, run_id: str | None = None) -> None:
        self.config = config
        self.run_id = (
            safe_id(run_id)
            if run_id
            else (dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
        )
        self.path = config.workspace / "runs" / self.run_id
        self.manifest_path = self.path / "manifest.json"
        effective_hash = fingerprint(config.as_dict())
        runtime = environment(config.workspace)
        self.manifest: dict[str, Any]
        if self.manifest_path.exists():
            self.manifest = read_json(self.manifest_path)
            if self.manifest["config_hash"] != effective_hash:
                raise ValueError("Existing run has a different effective configuration")
            if self.manifest["environment"] != runtime:
                raise ValueError("Code or environment changed; start a new run ID")
        else:
            self.manifest = {
                "run_id": self.run_id,
                "created_at": utc_now(),
                "status": "pending",
                "config": config.as_dict(),
                "config_hash": effective_hash,
                "environment": runtime,
                "stages": {},
                "artifacts": {},
                "source_kind": "synthetic"
                if config.project.context_mode == "synthetic"
                else "semi_synthetic",
                "evidence_level": "C",
            }
            self.save()

    def save(self) -> None:
        write_json(self.manifest_path, self.manifest)

    def register(self, paths: list[Path]) -> None:
        for path in paths:
            relative = path.resolve().relative_to(self.config.workspace.resolve())
            self.manifest["artifacts"][str(relative).replace("\\", "/")] = sha256_file(path)
        self.save()

    def fail_stage(
        self,
        stage_name: str,
        error: Exception | str,
        error_type: str | None = None,
        started_at: str | None = None,
        duration_seconds: float = 0.0,
    ) -> None:
        self.manifest["status"] = "failed"
        resolved_started_at = (
            started_at or self.manifest["stages"].get(stage_name, {}).get("started_at") or utc_now()
        )
        self.manifest["stages"][stage_name] = {
            "status": "failed",
            "started_at": resolved_started_at,
            "ended_at": utc_now(),
            "duration_seconds": duration_seconds,
            "error_type": error_type
            or (type(error).__name__ if isinstance(error, Exception) else "ValueError"),
            "error": str(error),
        }
        self.save()

    @contextlib.contextmanager
    def stage(self, stage_name: str, stage_inputs: Any):
        started = time.perf_counter()
        started_at = utc_now()
        try:
            resolved_inputs = stage_inputs() if callable(stage_inputs) else stage_inputs
        except Exception as exc:
            self.fail_stage(
                stage_name,
                exc,
                started_at=started_at,
                duration_seconds=time.perf_counter() - started,
            )
            raise

        digest = fingerprint(
            {
                "inputs": resolved_inputs,
                "config": self.manifest["config_hash"],
                "code": self.manifest["environment"]["source_code_sha256"],
            }
        )
        previous = self.manifest["stages"].get(stage_name, {})
        reusable = previous.get("status") == "succeeded" and previous.get("input_hash") == digest
        if reusable:
            for relative, expected in previous.get("outputs", {}).items():
                path = self.config.workspace / relative
                if not path.is_file() or sha256_file(path) != expected:
                    reusable = False
                    break
        if reusable:
            print(f"{stage_name}: reuse verified artifacts", flush=True)
            yield False
            return
        self.manifest["status"] = "running"
        self.manifest["stages"][stage_name] = {
            "status": "running",
            "started_at": started_at,
            "input_hash": digest,
        }
        self.save()
        print(f"{stage_name}: running", flush=True)
        try:
            yield True
        except Exception as exc:
            self.manifest["stages"][stage_name].update(
                status="failed",
                error_type=type(exc).__name__,
                error=str(exc),
                duration_seconds=time.perf_counter() - started,
                ended_at=utc_now(),
            )
            self.manifest["status"] = "failed"
            self.save()
            raise
        else:
            stage_record = self.manifest["stages"][stage_name]
            stage_record.update(
                status="succeeded",
                duration_seconds=time.perf_counter() - started,
                ended_at=utc_now(),
            )
            self.save()
            print(f"{stage_name}: succeeded ({stage_record['duration_seconds']:.2f}s)", flush=True)

    def outputs(self, stage: str, paths: list[Path], **counts: Any) -> None:
        self.register(paths)
        self.manifest["stages"][stage]["outputs"] = {
            str(p.relative_to(self.config.workspace)).replace("\\", "/"): sha256_file(p)
            for p in paths
        }
        self.manifest["stages"][stage].update(counts)
        self.save()

    def complete(self) -> None:
        if any(s["status"] != "succeeded" for s in self.manifest["stages"].values()):
            raise ValueError("Cannot complete a run with unfinished stages")
        self.manifest.update(status="succeeded", completed_at=utc_now())
        self.save()


def completed_run(workspace: Path, run_id: str, verify: bool = True) -> dict[str, Any]:
    manifest = read_json(workspace / "runs" / safe_id(run_id) / "manifest.json")
    if manifest["status"] != "succeeded":
        raise ValueError("Run is not complete; the dashboard cannot read partial artifacts")
    if verify:
        for relative, expected in manifest["artifacts"].items():
            path = (workspace / relative).resolve()
            if not path.is_relative_to(workspace.resolve()):
                raise ValueError("Manifest artifact escapes workspace")
            if not path.is_file() or sha256_file(path) != expected:
                raise ValueError(f"Artifact checksum mismatch: {relative}")
    return manifest
