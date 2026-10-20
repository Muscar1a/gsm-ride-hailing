"""Artifact-backed browser dashboard and bounded Python actions."""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import os
import secrets
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import joblib
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from gsm_poc.causal.estimate import ModelBundle
from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.causal.uncertainty import BootstrapResult
from gsm_poc.core.artifacts import (
    completed_run,
    fingerprint,
    read_json,
    safe_id,
    sha256_file,
    write_json,
)
from gsm_poc.core.config import Config
from gsm_poc.ui.jobs import JobManager, JobRequest, prepare_job
from gsm_poc.ui.results import load_simulation


def read_table(path: str, checksum: str) -> pd.DataFrame:
    assert checksum
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)


def read_bundle(path: str, checksum: str):
    assert checksum
    return joblib.load(path)


def checked_manifest(workspace: Path, run_id: str) -> dict:
    return completed_run(workspace, run_id, verify=True)


def artifact(workspace: Path, manifest: dict, relative: str) -> pd.DataFrame:
    checksum = manifest["artifacts"][relative]
    return read_table(str(workspace / relative), checksum)


def load_model(
    workspace: Path, manifest: dict, estimator: str, inference_method: str = "analytic"
) -> tuple[ModelBundle | None, BootstrapResult | None]:
    if inference_method not in ("analytic", "bootstrap"):
        raise ValueError("inference_method must be analytic or bootstrap")
    prefix = f"runs/{manifest['run_id']}/models/{estimator}"
    diagnostic = read_json(workspace / f"{prefix}/diagnostics.json")
    if diagnostic["status"] == "not_identified":
        return None, None
    bundle = read_bundle(
        str(workspace / f"{prefix}/model_bundle.joblib"),
        manifest["artifacts"][f"{prefix}/model_bundle.joblib"],
    )
    draws = None
    if inference_method == "bootstrap":
        draws = read_bundle(
            str(workspace / f"{prefix}/bootstrap_bundles.joblib"),
            manifest["artifacts"][f"{prefix}/bootstrap_bundles.joblib"],
        )
    elif f"{prefix}/analytic_inference.json" in manifest["artifacts"]:
        bundle = dataclasses.replace(
            bundle, analytic_inference=read_json(workspace / f"{prefix}/analytic_inference.json")
        )
    return bundle, draws


class PriceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    run_id: str
    estimator: Literal["naive_ols", "adjusted_ols", "dml", "contrast_ols"] = "adjusted_ols"
    inference_method: Literal["analytic", "bootstrap"] = "analytic"
    baseline_x: float = Field(default=1.0, gt=0, le=2)
    baseline_y: float = Field(default=1.0, gt=0, le=2)
    delta_x: float = Field(default=0.1, ge=-0.9, le=1)
    delta_y: float = Field(default=0, ge=-0.9, le=1)
    n_sessions: int = Field(default=10000, ge=1, le=10000000)
    zone: int | None = None
    horizon_start: str | None = None
    horizon_end: str | None = None


def registered_path(workspace: Path, manifest: dict, relative: str) -> Path:
    if relative not in manifest["artifacts"]:
        raise ValueError("Artifact is not registered in this run")
    path = (workspace / relative).resolve()
    if not path.is_relative_to(workspace) or not path.is_file():
        raise ValueError("Artifact is outside the workspace or missing")
    if sha256_file(path) != manifest["artifacts"][relative]:
        raise ValueError("Artifact checksum mismatch")
    return path


def list_runs(workspace: Path) -> list[dict]:
    records = []
    for path in (workspace / "runs").glob("*/manifest.json"):
        try:
            manifest = read_json(path)
            if manifest["status"] != "succeeded":
                continue
            safe_id(manifest["run_id"])
            if manifest["run_id"] != path.parent.name:
                continue
            config = manifest.get("choice_source", {}).get("source_config", manifest["config"])
            records.append(
                {
                    "run_id": manifest["run_id"],
                    "created_at": manifest["created_at"],
                    "stages": [
                        name
                        for name, value in manifest["stages"].items()
                        if value["status"] == "succeeded"
                    ],
                    "dgp": config["simulation"]["dgp"],
                    "seed": config["simulation"]["seed"],
                }
            )
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return sorted(records, key=lambda value: value["created_at"], reverse=True)


def create_app(workspace: Path, run_id: str | None = None, token: str | None = None) -> FastAPI:
    workspace = workspace.resolve()
    jobs = JobManager(workspace)
    forecast_slot = threading.Lock()
    static = Path(__file__).with_name("static")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        jobs.close()

    app = FastAPI(
        title="GSM Causal Marketplace",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.jobs = jobs
    # shortcut: one server worker per workspace, use a durable queue for multiple workers.
    hosts = os.environ.get("GSM_WEB_HOSTS", "localhost,127.0.0.1,[::1],testserver").split(",")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def protect_api(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if token and not secrets.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {token}"
            ):
                return JSONResponse(
                    {"detail": "Enter the dashboard access token."}, status_code=401
                )
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.url.netloc:
                return JSONResponse(
                    {"detail": "Cross-origin requests are disabled."}, status_code=403
                )
            request.state.workspace = workspace
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    async def artifact_error(request: Request, exc: Exception):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    for exception_type in (ValueError, KeyError, TypeError, OSError):
        app.add_exception_handler(exception_type, artifact_error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        errors = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.get("/api/runs")
    def get_runs():
        return {"runs": list_runs(workspace), "initial_run_id": run_id}

    @app.get("/api/runs/{selected}")
    def get_run(selected: str):
        manifest = checked_manifest(workspace, selected)
        result = {"manifest": manifest, "files": [], "results": {}}
        for relative in manifest["artifacts"]:
            path = Path(relative)
            if path.suffix in (".csv", ".parquet", ".json", ".zip"):
                result["files"].append(relative)
            if path.parent.as_posix() == f"runs/{selected}" and path.name.endswith("_result.json"):
                result["results"][path.name] = read_json(workspace / relative)
        if manifest.get("stages", {}).get("simulate_marketplace", {}).get("status") == "succeeded":
            _, simulation, spec, checkpoint = load_simulation(workspace, selected)
            result["simulation"] = {"result": simulation, "spec": spec, "checkpoint": checkpoint}
        if manifest.get("model_results"):
            context_path = registered_path(
                workspace, manifest, f"runs/{selected}/scenario_contexts.parquet"
            )
            result["zones"] = sorted(pd.read_parquet(context_path).zone_id.unique().tolist())
        return result

    @app.get("/api/runs/{selected}/table")
    def get_table(
        selected: str,
        artifact: str,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        zone: int | None = None,
        platform: str | None = None,
        estimator: str | None = None,
        start: str | None = None,
        end: str | None = None,
        download: bool = False,
    ):
        manifest = checked_manifest(workspace, selected)
        path = registered_path(workspace, manifest, artifact)
        if path.suffix not in (".csv", ".parquet"):
            raise ValueError("Select a CSV or Parquet table")
        frame = read_table(str(path), manifest["artifacts"][artifact])
        for column, value in (("zone_id", zone), ("platform", platform), ("estimator", estimator)):
            if value is not None:
                if column not in frame:
                    raise ValueError(f"This table has no {column} column")
                frame = frame[frame[column] == value]
        if start or end:
            if "slot_start_local" not in frame:
                raise ValueError("Date filters require slot_start_local")
            dates = pd.to_datetime(frame.slot_start_local).dt.date
            if start:
                frame = frame[dates >= pd.Timestamp(start).date()]
                dates = dates.loc[frame.index]
            if end:
                frame = frame[dates <= pd.Timestamp(end).date()]
        summary = {}
        for column in ("completed_trip_count", "n_valid_duration", "n_valid_wait"):
            if column in frame:
                summary[column] = float(frame[column].sum())
        if download:
            return Response(
                frame.to_csv(index=False),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="filtered.csv"'},
            )
        page = frame.iloc[offset : offset + limit]
        return {
            "columns": list(frame.columns),
            "rows": json.loads(page.to_json(orient="records", date_format="iso")),
            "total_rows": len(frame),
            "offset": offset,
            "summary": summary,
        }

    @app.get("/api/runs/{selected}/download")
    def download(selected: str, artifact: str):
        manifest = checked_manifest(workspace, selected)
        path = registered_path(workspace, manifest, artifact)
        if path.suffix not in (".csv", ".parquet", ".json", ".zip"):
            raise ValueError(
                "Only registered data, results and delivery archives can be downloaded"
            )
        return FileResponse(path, filename=path.name)

    @app.post("/api/scenario")
    def predict_price(request: PriceRequest):
        if not forecast_slot.acquire(blocking=False):
            raise HTTPException(429, "A forecast is already running. Try again after it completes.")
        try:
            manifest = checked_manifest(workspace, request.run_id)
            if request.estimator not in manifest.get("model_results", {}):
                raise ValueError("Select an estimator present in this model run")
            config = Config.from_dict(
                manifest.get("choice_source", {}).get("source_config", manifest["config"]),
                workspace,
            )
            relative = f"runs/{request.run_id}/scenario_contexts.parquet"
            context = artifact(workspace, manifest, relative)
            if request.zone is not None:
                context = context[context.zone_id == request.zone]
                if context.empty:
                    raise ValueError("Selected zone has no scenario contexts")
            bundle, draws = load_model(
                workspace, manifest, request.estimator, request.inference_method
            )
            provenance_payload = {
                "model_run_id": request.run_id,
                "source_context_sha256": manifest["artifacts"].get(relative, "unavailable"),
                "source_config_hash": fingerprint(config.as_dict()),
                "code_version": manifest.get("code_version", "unavailable"),
            }
            return scenario(
                bundle,
                context,
                ScenarioRequest(
                    "interactive-price-scenario",
                    baseline_multiplier_x=request.baseline_x,
                    baseline_multiplier_y=request.baseline_y,
                    delta_price_x=request.delta_x,
                    delta_price_y=request.delta_y,
                    n_sessions=request.n_sessions,
                    interval_level=config.evaluation.interval_level,
                    target_context_set="all" if request.zone is None else f"zone_{request.zone}",
                    horizon_start=request.horizon_start,
                    horizon_end=request.horizon_end,
                ),
                config,
                request.run_id,
                draws,
                inference_method=request.inference_method,
                provenance=provenance_payload,
            )
        finally:
            forecast_slot.release()

    @app.post("/api/jobs", status_code=202)
    def start_job(request: JobRequest):
        payload = prepare_job(workspace, request)
        try:
            return jobs.start(payload)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return jobs.read(job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        record = jobs.read(job_id)
        if record["status"] == "running":
            if jobs.job_id != job_id:
                raise HTTPException(409, "This job belongs to an earlier server process")
            jobs.close()
        return jobs.read(job_id)

    @app.post("/api/uploads", status_code=201)
    async def upload_csv(request: Request, kind: Literal["table", "requests"] = "table"):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 5 * 1024 * 1024:
                raise HTTPException(413, "CSV exceeds the 5 MiB upload limit")
        import csv

        import numpy as np

        text = data.decode("utf-8-sig")
        columns = next(csv.reader(io.StringIO(text)), [])
        if not columns or len(columns) != len(set(columns)) or any(not value for value in columns):
            raise ValueError("CSV requires unique, nonempty column names")
        frame = pd.read_csv(io.StringIO(text), dtype={"request_id": str})
        if frame.empty or len(frame) > 100000 or len(frame.columns) > 100:
            raise ValueError("CSV must contain 1–100,000 rows and at most 100 columns")
        if np.isinf(frame.select_dtypes(include="number").to_numpy()).any():
            raise ValueError("CSV contains infinite numeric values")
        if kind == "requests":
            fields = {
                "request_id",
                "created_at",
                "origin_zone_id",
                "destination_zone_id",
                "service_id",
            }
            if set(frame) - fields - {"cancel_at"} or fields - set(frame):
                raise ValueError("Request CSV does not match the explicit simulation contract")
            if frame[list(fields)].isna().any().any() or frame.request_id.duplicated().any():
                raise ValueError("Request CSV has missing required values or duplicate request IDs")
            if len(frame) > 10000 or not frame.service_id.isin(["X", "Y"]).all():
                raise ValueError("Request CSV requires X/Y services and at most 10,000 rows")
        upload_id = uuid.uuid4().hex
        directory = workspace / ".cache/web/uploads" / upload_id
        directory.mkdir(parents=True)
        path = directory / "data.csv"
        path.write_bytes(data)
        metadata = {
            "upload_id": upload_id,
            "kind": kind,
            "source_kind": "user_uploaded_unvalidated",
            "sha256": sha256_file(path),
            "total_rows": len(frame),
            "columns": list(frame.columns),
            "missing_values": {name: int(value) for name, value in frame.isna().sum().items()},
        }
        write_json(directory / "metadata.json", metadata)
        preview = frame.iloc[:100]
        return metadata | {"rows": json.loads(preview.to_json(orient="records", date_format="iso"))}

    @app.get("/assets/tokens.css")
    def tokens():
        path = workspace / "tokens.css"
        return FileResponse(
            path if path.is_file() else static / "tokens.css", media_type="text/css"
        )

    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="GSM browser dashboard with Python computation")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--run-id")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    token = os.environ.get("GSM_WEB_TOKEN")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not token:
        parser.error("Set GSM_WEB_TOKEN before exposing the dashboard outside localhost")
    uvicorn.run(create_app(args.workspace, args.run_id, token), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
