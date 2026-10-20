"""Batch stage orchestration. The UI only reads finished artifacts."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from gsm_poc.causal.analytic import model_identity, validate_covariance
from gsm_poc.causal.estimate import FitResult, fit_all, fit_estimator
from gsm_poc.causal.evaluate import effect_rows, monte_carlo, saved_method_evaluation
from gsm_poc.causal.features import date_splits, require_observed
from gsm_poc.causal.forecast_contract import (
    format_scenario_metrics_csv,
    select_scenario_contexts,
)
from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.causal.uncertainty import BootstrapResult, bootstrap
from gsm_poc.core.artifacts import (
    Run,
    atomic_path,
    completed_run,
    fingerprint,
    freeze_artifacts,
    read_json,
    safe_id,
    sha256_file,
    write_frame,
    write_json,
    write_model,
)
from gsm_poc.core.config import Config
from gsm_poc.data.context import build_context
from gsm_poc.data.ingest import ingest
from gsm_poc.data.marts import build_marts
from gsm_poc.data.silver import build_silver
from gsm_poc.simulation.compensation import validate_compensation
from gsm_poc.simulation.demand import DemandPlan, prepare_demand_plan
from gsm_poc.simulation.dgp import generate, save_generated
from gsm_poc.simulation.marketplace import simulate_marketplace


class Pipeline:
    def __init__(self, config: Config, run_id: str | None = None, **kwargs: Any) -> None:
        if "runId" in kwargs and run_id is None:
            run_id = kwargs["runId"]
        self.config, self.run = config, Run(config, run_id)

    def ingest(self) -> dict:
        manifest_file = self.config.workspace / "data/bronze/source_manifest.json"
        inputs = {"trip_url": self.config.source.trip_url, "zone_url": self.config.source.zone_url}
        with self.run.stage("ingest", inputs) as execute:
            if execute:
                source = ingest(self.config)
                self.run.manifest["source_manifest"] = source
                self.run.outputs("ingest", [manifest_file], input_rows=source["schema"]["rows"])
            else:
                # Always validate cached source bytes, not just the JSON manifest.
                source = ingest(self.config)
        return source

    def build(self) -> dict:
        source = self.ingest()
        with self.run.stage("build", source) as execute:
            if execute:
                silver = build_silver(self.config, source)
                marts = build_marts(self.config, silver["silver"], silver["build_id"])
                contexts = build_context(self.config, silver["silver"], silver["build_id"])
                paths = [
                    silver["silver"],
                    silver["quality"],
                    silver["quarantine"],
                    marts["mart"],
                    marts["mart_metadata"],
                    contexts["contexts"],
                    contexts["context_metadata"],
                ]
                record = {
                    "build_id": silver["build_id"],
                    "context_version": contexts["context_version"],
                    "silver": str(silver["silver"].relative_to(self.config.workspace)),
                    "quality": str(silver["quality"].relative_to(self.config.workspace)),
                    "mart": str(marts["mart"].relative_to(self.config.workspace)),
                    "contexts": str(contexts["contexts"].relative_to(self.config.workspace)),
                    "context_metadata": str(
                        contexts["context_metadata"].relative_to(self.config.workspace)
                    ),
                }
                self.run.manifest["observed_build"] = record
                self.run.outputs(
                    "build",
                    paths,
                    input_rows=source["schema"]["rows"],
                    silver_rows=silver["row_count"],
                    mart_rows=marts["row_count"],
                    reconciled_completed_trips=marts["completed_trip_count"],
                )
        return self.run.manifest["observed_build"]

    def context(
        self, build_id: str | None = None, **kwargs: Any
    ) -> tuple[pd.DataFrame | None, str]:
        if "buildId" in kwargs and build_id is None:
            build_id = kwargs["buildId"]
        if self.config.project.context_mode == "synthetic":
            return None, "synthetic-v1"
        record = self.run.manifest.get("observed_build")
        if record is not None and (build_id is None or record["build_id"] == build_id):
            path = self.config.workspace / record["contexts"]
            metadata = read_json(self.config.workspace / record["context_metadata"])
        elif build_id is not None:
            path = (
                self.config.workspace
                / "data/gold"
                / safe_id(build_id)
                / "context_templates.parquet"
            )
            metadata = read_json(path.with_suffix(".json"))
        else:
            raise ValueError("TLC context is missing; run build or pass --build-id")
        if (
            metadata["fit_end_exclusive"] != self.config.source.train_end
            or metadata["fit_start"] != self.config.source.start
        ):
            raise ValueError("Context was fitted on different train dates")
        frame = pd.read_parquet(path)
        version = fingerprint({"metadata": metadata, "parquet_sha256": sha256_file(path)})
        return frame, version

    def generate(self, build_id: str | None = None, **kwargs: Any) -> str:
        if "buildId" in kwargs and build_id is None:
            build_id = kwargs["buildId"]

        contexts = None
        context_version = None

        def generate_inputs():
            nonlocal contexts, context_version
            contexts, context_version = self.context(build_id)
            return {"context_version": context_version}

        with self.run.stage("generate", generate_inputs) as execute:
            if execute:
                if context_version is None:
                    raise RuntimeError("Generate stage inputs did not resolve the context version")
                data = generate(self.config, contexts, context_version)
                paths = save_generated(self.config, data)
                self.run.manifest["dataset_id"] = data.dataset_id
                self.run.manifest["context_version"] = context_version
                self.run.outputs(
                    "generate",
                    paths,
                    output_blocks=len(data.blocks),
                    output_sessions=len(data.sessions),
                )
        return self.run.manifest["dataset_id"]

    def fit(self, dataset_id: str | None = None, **kwargs: Any) -> None:
        if "datasetId" in kwargs and dataset_id is None:
            dataset_id = kwargs["datasetId"]

        def fit_inputs():
            raw_dataset_id = dataset_id or self.run.manifest.get("dataset_id", "")
            if not raw_dataset_id:
                raise ValueError(
                    "Dataset ID is required to fit models; pass --dataset-id or run generate"
                )
            validated_dataset_id = safe_id(raw_dataset_id)
            root = self.config.workspace / "data/synthetic" / validated_dataset_id
            observed = root / "observed/choice_block.parquet"
            metadata_path = root / "manifest.json"
            if not observed.is_file():
                raise FileNotFoundError(f"Observed choice block not found: {observed}")
            if not metadata_path.is_file():
                raise FileNotFoundError(f"Dataset manifest not found: {metadata_path}")
            return {
                "dataset_id": validated_dataset_id,
                "observed_sha256": sha256_file(observed),
                "metadata_sha256": sha256_file(metadata_path),
            }

        with self.run.stage("fit", fit_inputs) as execute:
            if execute:
                raw_dataset_id = dataset_id or self.run.manifest.get("dataset_id", "")
                validated_dataset_id = safe_id(raw_dataset_id)
                root = self.config.workspace / "data/synthetic" / validated_dataset_id
                observed = root / "observed/choice_block.parquet"
                metadata_path = root / "manifest.json"
                blocks = pd.read_parquet(observed)
                metadata = read_json(metadata_path)
                if metadata["source_kind"] != self.run.manifest["source_kind"]:
                    raise ValueError("Dataset source kind differs from run configuration")
                if metadata["dgp_id"] != self.config.simulation.dgp:
                    raise ValueError("Dataset DGP differs from run configuration")
                if metadata["seed"] != self.config.simulation.seed:
                    raise ValueError("Dataset seed differs from configuration; pass --seed")
                require_observed(blocks)
                splits = date_splits(blocks, self.config)
                results, split_record = fit_all(blocks, self.config)
                paths, effects, draws_all = [], [], {}
                for name, result in results.items():
                    diagnostics = self.run.path / "models" / name / "diagnostics.json"
                    if result.bundle is not None:
                        print(
                            f"fit: {name}, {self.config.evaluation.bootstrap_draws} day draws",
                            flush=True,
                        )
                        draws = bootstrap(splits["train"], self.config, name)
                        draws_all[name] = draws
                        model_path = diagnostics.parent / "model_bundle.joblib"
                        draws_path = diagnostics.parent / "bootstrap_bundles.joblib"
                        records_path = diagnostics.parent / "bootstrap_draws.parquet"
                        write_model(model_path, result.bundle)
                        write_model(draws_path, draws)
                        records = pd.DataFrame(draws.records)
                        if records.empty:
                            records = pd.DataFrame(
                                columns=pd.Index(["draw_id", "estimator", "status"])
                            )
                        write_frame(records_path, records)
                        paths.extend([model_path, draws_path, records_path])
                    else:
                        draws = None
                    write_json(diagnostics, result.diagnostics)
                    paths.append(diagnostics)
                    effects.extend(
                        effect_rows(
                            result,
                            draws,
                            splits["test"],
                            self.config,
                            self.run.run_id,
                            validated_dataset_id,
                        )
                    )
                effects_path = self.run.path / "effects.csv"
                context_path = self.run.path / "scenario_contexts.parquet"
                split_path = self.run.path / "splits.json"
                write_frame(effects_path, pd.DataFrame(effects))
                write_frame(
                    context_path,
                    splits["test"].drop(
                        columns=[
                            "q_x",
                            "q_y",
                            "q_none",
                            "n_x",
                            "n_y",
                            "n_none",
                            "assignment_probability",
                        ]
                    ),
                )
                write_json(split_path, split_record)
                paths.extend([effects_path, context_path, split_path])
                self.run.manifest.update(
                    dataset_id=validated_dataset_id,
                    model_results={
                        name: result.diagnostics["status"] for name, result in results.items()
                    },
                )
                self.run.outputs(
                    "fit",
                    paths,
                    input_blocks=len(blocks),
                    train_blocks=len(splits["train"]),
                    test_blocks=len(splits["test"]),
                )

    def method_evaluation(self) -> None:
        def evaluation_inputs():
            dataset_id = self.run.manifest.get("dataset_id")
            if not dataset_id:
                raise ValueError(
                    "Run manifest has no dataset_id; fit must run before method_evaluation"
                )
            root = self.config.workspace / "data/synthetic" / dataset_id
            oracle = root / "oracle/oracle_block.parquet"
            observed = root / "observed/choice_block.parquet"
            metadata_path = root / "manifest.json"
            if not oracle.is_file():
                raise FileNotFoundError(f"Oracle block not found: {oracle}")
            if not observed.is_file():
                raise FileNotFoundError(f"Observed choice block not found: {observed}")
            if not metadata_path.is_file():
                raise FileNotFoundError(f"Dataset manifest not found: {metadata_path}")
            inputs = {
                "dataset_id": dataset_id,
                "oracle_sha256": sha256_file(oracle),
                "observed_sha256": sha256_file(observed),
                "metadata_sha256": sha256_file(metadata_path),
                "scenario": self.config.scenario.__dict__,
                "models": {},
            }
            for name in self.config.model.estimators:
                directory = self.run.path / "models" / name
                diagnostics_path = directory / "diagnostics.json"
                if not diagnostics_path.is_file():
                    raise FileNotFoundError(f"Estimator diagnostics not found: {diagnostics_path}")
                model_inputs = {"diagnostics_sha256": sha256_file(diagnostics_path)}
                if read_json(diagnostics_path)["status"] != "not_identified":
                    model_bundle = directory / "model_bundle.joblib"
                    bootstrap_bundles = directory / "bootstrap_bundles.joblib"
                    if not model_bundle.is_file():
                        raise FileNotFoundError(f"Model bundle not found: {model_bundle}")
                    if not bootstrap_bundles.is_file():
                        raise FileNotFoundError(f"Bootstrap bundles not found: {bootstrap_bundles}")
                    model_inputs.update(
                        model_sha256=sha256_file(model_bundle),
                        bootstrap_sha256=sha256_file(bootstrap_bundles),
                    )
                inputs["models"][name] = model_inputs
            return inputs

        with self.run.stage("method_evaluation", evaluation_inputs) as execute:
            if execute:
                results, draws = self.load_models()
                dataset_id = self.run.manifest["dataset_id"]
                metrics = saved_method_evaluation(
                    self.config, dataset_id, results, draws, self.run.run_id
                )
                path = self.run.path / "method_metrics.csv"
                write_frame(path, metrics)
                self.run.outputs("method_evaluation", [path], output_rows=len(metrics))

    def load_models(self) -> tuple[dict[str, FitResult], dict[str, BootstrapResult]]:
        results, draws = {}, {}
        for name in self.config.model.estimators:
            directory = self.run.path / "models" / name
            diagnostic = read_json(directory / "diagnostics.json")
            bundle = (
                joblib.load(directory / "model_bundle.joblib")
                if diagnostic["status"] != "not_identified"
                else None
            )
            results[name] = FitResult(bundle, diagnostic)
            if bundle is not None:
                draws[name] = joblib.load(directory / "bootstrap_bundles.joblib")
        return results, draws

    def freeze_choice(self, model_run_id: str) -> dict:
        """Freeze the complete choice results independently of operational inputs."""
        if model_run_id == self.run.run_id:
            raise ValueError("freeze-choice requires a separate output run")
        if set(self.run.manifest.get("stages", {})) - {"freeze_choice"}:
            raise ValueError("freeze-choice cannot overwrite an unrelated run; use a new run ID")
        if (
            self.run.manifest.get("choice_source", {}).get("model_run_id", model_run_id)
            != model_run_id
        ):
            raise ValueError("freeze-choice requires a new run ID for a different source")
        source_manifest: dict = {}
        source_artifacts: dict[str, str] = {}
        source_manifest_sha256 = ""

        def choice_inputs():
            nonlocal source_manifest, source_artifacts, source_manifest_sha256
            source_manifest = completed_run(self.config.workspace, model_run_id)
            for stage in ("fit", "method_evaluation", "scenario"):
                if source_manifest.get("stages", {}).get(stage, {}).get("status") != "succeeded":
                    raise ValueError(f"Choice handoff requires a completed {stage} stage")
            source_config = Config.from_dict(source_manifest["config"], self.config.workspace)
            directory = self.config.workspace / "runs" / safe_id(model_run_id)
            names = [
                "effects.csv",
                "splits.json",
                "scenario_result.json",
                "scenario_contexts.parquet",
                "method_metrics.csv",
            ]
            for name in source_config.model.estimators:
                prefix = f"models/{name}"
                diagnostics = read_json(directory / prefix / "diagnostics.json")
                if diagnostics["status"] != source_manifest.get("model_results", {}).get(name):
                    raise ValueError("Choice model status differs from estimator diagnostics")
                names.append(f"{prefix}/diagnostics.json")
                if diagnostics["status"] != "not_identified":
                    names.extend(
                        [
                            f"{prefix}/model_bundle.joblib",
                            f"{prefix}/bootstrap_bundles.joblib",
                            f"{prefix}/bootstrap_draws.parquet",
                        ]
                    )
            source_artifacts = {}
            for name in names:
                relative = f"runs/{model_run_id}/{name}"
                if relative not in source_manifest["artifacts"]:
                    raise ValueError(f"Required choice artifact is not registered: {relative}")
                source_artifacts[name] = source_manifest["artifacts"][relative]
            source_manifest_sha256 = sha256_file(directory / "manifest.json")
            return {
                "model_run_id": model_run_id,
                "source_manifest_sha256": source_manifest_sha256,
                "source_artifacts": source_artifacts,
            }

        with self.run.stage("freeze_choice", choice_inputs) as execute:
            result_path = self.run.path / "choice_handoff.json"
            if execute:
                source = self.config.workspace / "runs" / model_run_id
                paths = freeze_artifacts(source, self.run.path, source_artifacts)
                manifest_path = self.run.path / "source_manifest.json"
                with atomic_path(manifest_path) as temporary:
                    shutil.copyfile(source / "manifest.json", temporary)
                    if sha256_file(temporary) != source_manifest_sha256:
                        raise ValueError("Source manifest changed while freezing choice artifacts")
                paths.append(manifest_path)
                source_config = Config.from_dict(source_manifest["config"], self.config.workspace)
                name = source_config.model.scenario_estimator
                prefix = self.run.path / "models" / name
                diagnostics = read_json(prefix / "diagnostics.json")
                bundle = (
                    joblib.load(prefix / "model_bundle.joblib")
                    if diagnostics["status"] != "not_identified"
                    else None
                )
                if bundle is not None and (
                    bundle.estimator != name
                    or bundle.source_kind != source_manifest["source_kind"]
                    or bundle.dataset_id != source_manifest["dataset_id"]
                    or bundle.dgp_id != source_config.simulation.dgp
                    or bundle.seed != source_config.simulation.seed
                ):
                    raise ValueError("Choice bundle provenance differs from the source manifest")
                draws = joblib.load(prefix / "bootstrap_bundles.joblib") if bundle else None
                historical = read_json(self.run.path / "scenario_result.json")
                contexts = pd.read_parquet(self.run.path / "scenario_contexts.parquet")
                request = ScenarioRequest(**historical["request"])
                scoped_contexts, scope_info = select_scenario_contexts(
                    contexts,
                    target_context_set=request.target_context_set,
                    zone=historical.get("scope", {}).get("selected_zone"),
                    horizon_start=request.horizon_start,
                    horizon_end=request.horizon_end,
                    timezone=getattr(source_config.source, "assumed_timezone", "America/New_York"),
                    slot_minutes=source_config.simulation.slot_minutes,
                )
                expected_blocks = historical.get("scope", {}).get(
                    "context_blocks", historical.get("context_blocks", len(scoped_contexts))
                )
                if expected_blocks != len(scoped_contexts):
                    raise ValueError(
                        "Saved scenario scope cannot be reproduced from frozen contexts"
                    )
                current = scenario(
                    bundle,
                    scoped_contexts,
                    request,
                    source_config,
                    model_run_id,
                    draws,
                    inference_method="bootstrap",
                )
                current_path = self.run.path / "current_scenario_result.json"
                write_json(current_path, current)
                paths.append(current_path)
                comparison_fields = [
                    key
                    for key in (
                        "theta",
                        "elasticity_at_baseline",
                        "probabilities",
                        "interval",
                        "theta_interval",
                        "elasticity_interval",
                        "before_expected_bookings",
                        "after_expected_bookings",
                        "delta_expected_bookings",
                        "context_blocks",
                        "context_weight_sessions",
                        "bootstrap",
                    )
                    if key in historical
                ]
                result = {
                    "schema_version": 1,
                    "source_model_run_id": model_run_id,
                    "dataset_id": source_manifest["dataset_id"],
                    "source_kind": source_manifest["source_kind"],
                    "evidence_level": source_manifest["evidence_level"],
                    "source_config": source_manifest["config"],
                    "source_environment": source_manifest["environment"],
                    "packaging_environment": self.run.manifest["environment"],
                    "source_manifest_sha256": source_manifest_sha256,
                    "artifacts": source_artifacts,
                    "model_results": source_manifest["model_results"],
                    "scope": current["scope"],
                    "units": current["units"],
                    "current_status": current["status"],
                    "current_support_status": current.get("support_status", "not_evaluated"),
                    "current_reasons": current["reasons"],
                    "reproduction_mode": "saved_model_replay; no refit",
                    "replay_verification": {
                        "compared_fields": comparison_fields,
                        "matching_values": (
                            all(historical[key] == current.get(key) for key in comparison_fields)
                            if comparison_fields
                            else None
                        ),
                        "historical_status": historical["status"],
                        "current_status": current["status"],
                        "status_matches": historical["status"] == current["status"],
                    },
                    "interval_qualification": {
                        "interval_kind": "day-bootstrap percentile; individual intervals",
                        "interval_scope": "individual",
                        "interval_validation_scope": "technical_checks_only",
                        "interval_calibration_status": "not_validated_by_packaging",
                    },
                    "review_status": "pending_reviewer_acceptance",
                }
                write_json(result_path, result)
                paths.append(result_path)
                self.run.manifest.update(
                    dataset_id=result["dataset_id"],
                    source_kind=result["source_kind"],
                    evidence_level=result["evidence_level"],
                    model_results=result["model_results"],
                    choice_source={
                        "model_run_id": model_run_id,
                        "source_config": result["source_config"],
                        "source_environment": result["source_environment"],
                        "source_manifest_sha256": source_manifest_sha256,
                    },
                )
                self.run.outputs("freeze_choice", paths, copied_artifacts=len(source_artifacts))
            return read_json(result_path)

    def prepare_inference(self, model_run_id: str) -> dict:
        """Copy a frozen baseline, adding compact covariance without changing its bytes."""
        if model_run_id == self.run.run_id or self.run.manifest.get("stages"):
            raise ValueError("prepare-inference requires a new, separate output run")
        source = completed_run(self.config.workspace, model_run_id)
        if source.get("stages", {}).get("freeze_choice", {}).get("status") != "succeeded":
            raise ValueError("prepare-inference requires a completed freeze-choice baseline")
        directory = self.config.workspace / "runs" / safe_id(model_run_id)
        source_config = Config.from_dict(
            source["choice_source"]["source_config"], self.config.workspace
        )
        original = read_json(directory / "source_manifest.json")
        dataset_id = safe_id(source["dataset_id"])
        dataset = self.config.workspace / "data/synthetic" / dataset_id
        fit_inputs = {
            "dataset_id": dataset_id,
            "observed_sha256": sha256_file(dataset / "observed/choice_block.parquet"),
            "metadata_sha256": sha256_file(dataset / "manifest.json"),
        }
        expected = fingerprint(
            {
                "inputs": fit_inputs,
                "config": original["config_hash"],
                "code": original["environment"]["source_code_sha256"],
            }
        )
        input_verification = "fit_observed_and_metadata_hash"
        if expected != original["stages"]["fit"]["input_hash"]:
            # Early manifests hashed observed bytes at fit; generation registered metadata.
            legacy_inputs = {key: fit_inputs[key] for key in ("dataset_id", "observed_sha256")}
            legacy_hash = fingerprint(
                {
                    "inputs": legacy_inputs,
                    "config": original["config_hash"],
                    "code": original["environment"]["source_code_sha256"],
                }
            )
            metadata_relative = f"data/synthetic/{dataset_id}/manifest.json"
            if (
                legacy_hash != original["stages"]["fit"]["input_hash"]
                or original["artifacts"].get(metadata_relative) != fit_inputs["metadata_sha256"]
            ):
                raise ValueError("Observed dataset or metadata differs from the frozen fit inputs")
            input_verification = "legacy_fit_observed_hash_and_registered_metadata_hash"
        names = {
            relative.removeprefix(f"runs/{model_run_id}/"): checksum
            for relative, checksum in source["artifacts"].items()
        }
        with self.run.stage(
            "freeze_choice", {"baseline_run_id": model_run_id, "artifacts": names}
        ) as execute:
            if execute:
                paths = freeze_artifacts(directory, self.run.path, names)
                self.run.manifest.update(
                    {
                        key: source[key]
                        for key in (
                            "dataset_id",
                            "source_kind",
                            "evidence_level",
                            "model_results",
                            "choice_source",
                        )
                    }
                )
                self.run.outputs("freeze_choice", paths, copied_artifacts=len(names))
        with self.run.stage("prepare_inference", fit_inputs) as execute:
            result_path = self.run.path / "inference_preparation.json"
            if execute:
                blocks = pd.read_parquet(dataset / "observed/choice_block.parquet")
                require_observed(blocks)
                train = date_splits(blocks, source_config)["train"]
                paths, methods = [], {}
                for name, status in source["model_results"].items():
                    if status == "not_identified" or name not in ("adjusted_ols", "dml"):
                        continue
                    prefix = self.run.path / "models" / name
                    bundle = joblib.load(prefix / "model_bundle.joblib")
                    record = getattr(bundle, "analytic_inference", None)
                    if record is None:
                        fitted = fit_estimator(train, source_config, name)
                        new = fitted.bundle
                        if (
                            new is None
                            or new.active_treatments != bundle.active_treatments
                            or not np.allclose(new.theta, bundle.theta, atol=1e-10, rtol=1e-9)
                            or not np.allclose(
                                new.base_rate_model.coef_,
                                bundle.base_rate_model.coef_,
                                atol=1e-10,
                                rtol=1e-9,
                            )
                            or not np.allclose(
                                new.base_rate_model.intercept_,
                                bundle.base_rate_model.intercept_,
                                atol=1e-10,
                                rtol=1e-9,
                            )
                        ):
                            raise ValueError(
                                f"{name}: refitted point differs from the frozen baseline"
                            )
                        record = new.analytic_inference
                        if record is None:
                            raise ValueError(
                                f"{name}: {fitted.diagnostics.get('analytic_unavailable_reason')}"
                            )
                        record = {**record, "model_identity": model_identity(bundle)}
                    validate_covariance(bundle, record)
                    path = prefix / "analytic_inference.json"
                    write_json(path, record)
                    paths.append(path)
                    methods[name] = record["method"]
                result = {
                    "baseline_run_id": model_run_id,
                    "dataset_id": dataset_id,
                    "fit_inputs": fit_inputs,
                    "input_verification": input_verification,
                    "methods": methods,
                    "baseline_bytes_preserved": True,
                    "point_reconstruction_verified": True,
                    "review_status": "technical_exception_accepted",
                    "reviewer": "Bun",
                    "review_date": "2026-10-11",
                    "interval_calibration_status": "not_certified_at_nominal_95",
                }
                write_json(result_path, result)
                paths.append(result_path)
                self.run.outputs("prepare_inference", paths, estimators=len(methods))
            return read_json(result_path)

    def scenario(
        self,
        request: ScenarioRequest | None = None,
        model_run_id: str | None = None,
        zone: int | None = None,
        inference_method: str = "bootstrap",
        **kwargs: Any,
    ) -> dict:
        if inference_method not in ("analytic", "bootstrap"):
            raise ValueError("inference_method must be analytic or bootstrap")
        if "modelRunId" in kwargs and model_run_id is None:
            model_run_id = kwargs["modelRunId"]

        selected_run = model_run_id or self.run.run_id
        directory = self.config.workspace / "runs" / safe_id(selected_run)
        source_config = self.config
        target_context_set = (
            f"zone_{zone}" if zone is not None else self.config.scenario.target_context_set
        )
        if request is None:
            resolved_request = ScenarioRequest(
                delta_price_x=self.config.scenario.delta_price_x,
                delta_price_y=self.config.scenario.delta_price_y,
                n_sessions=self.config.scenario.n_sessions,
                interval_level=self.config.evaluation.interval_level,
                target_context_set=target_context_set,
            )
        elif zone is not None and request.target_context_set == "all":
            resolved_request = dataclasses.replace(request, target_context_set=target_context_set)
        else:
            resolved_request = request

        def scenario_inputs():
            nonlocal source_config
            source_manifest = self.run.manifest
            if model_run_id:
                source_manifest = completed_run(self.config.workspace, selected_run)
                source_config = Config.from_dict(
                    source_manifest.get("choice_source", {}).get(
                        "source_config", source_manifest["config"]
                    ),
                    self.config.workspace,
                )
                if self.config.model.scenario_estimator not in source_manifest.get(
                    "model_results", {}
                ):
                    raise ValueError("Selected estimator is not present in the frozen model run")
            name = self.config.model.scenario_estimator
            diagnostics_path = directory / "models" / name / "diagnostics.json"
            if not diagnostics_path.is_file():
                raise FileNotFoundError(f"Estimator diagnostics not found: {diagnostics_path}")
            diagnostics = read_json(diagnostics_path)
            model_path = directory / "models" / name / "model_bundle.joblib"
            bootstrap_path = model_path.with_name("bootstrap_bundles.joblib")
            model_sha256 = None
            bootstrap_sha256 = None
            if diagnostics["status"] != "not_identified":
                if not model_path.is_file():
                    raise FileNotFoundError(f"Model bundle not found: {model_path}")
                if inference_method == "bootstrap" and not bootstrap_path.is_file():
                    raise FileNotFoundError(f"Bootstrap bundles not found: {bootstrap_path}")
                model_sha256 = sha256_file(model_path)
                if inference_method == "bootstrap":
                    bootstrap_sha256 = sha256_file(bootstrap_path)
            analytic_path = model_path.with_name("analytic_inference.json")
            if inference_method == "analytic" and analytic_path.is_file():
                relative = str(analytic_path.relative_to(self.config.workspace)).replace("\\", "/")
                if source_manifest["artifacts"].get(relative) != sha256_file(analytic_path):
                    raise ValueError("Analytic covariance is unregistered or its checksum differs")
            contexts_path = directory / "scenario_contexts.parquet"
            if not contexts_path.is_file():
                raise FileNotFoundError(f"Scenario contexts not found: {contexts_path}")
            return {
                "schema_version": 2,
                "contract_version": "forecast_contract_v2",
                "model_run_id": selected_run,
                "request": dataclasses.asdict(resolved_request),
                "zone": zone,
                "diagnostics_sha256": sha256_file(diagnostics_path),
                "model_sha256": model_sha256,
                "bootstrap_sha256": bootstrap_sha256,
                "contexts_sha256": sha256_file(contexts_path),
                "source_config": source_config.as_dict(),
                "inference_method": inference_method,
                "analytic_sha256": sha256_file(analytic_path)
                if inference_method == "analytic" and analytic_path.is_file()
                else None,
            }

        with self.run.stage("scenario", scenario_inputs) as execute:
            path = self.run.path / "scenario_result.json"
            metrics_csv_path = self.run.path / "scenario_metrics.csv"
            if execute:
                name = self.config.model.scenario_estimator
                diagnostics = read_json(directory / "models" / name / "diagnostics.json")
                model_path = directory / "models" / name / "model_bundle.joblib"
                bundle = (
                    joblib.load(model_path) if diagnostics["status"] != "not_identified" else None
                )
                draws = (
                    joblib.load(model_path.with_name("bootstrap_bundles.joblib"))
                    if bundle and inference_method == "bootstrap"
                    else None
                )
                analytic_path = model_path.with_name("analytic_inference.json")
                if bundle and inference_method == "analytic" and analytic_path.is_file():
                    bundle.analytic_inference = read_json(analytic_path)
                contexts = pd.read_parquet(directory / "scenario_contexts.parquet")
                if zone is not None:
                    contexts = contexts[contexts.zone_id == zone]
                provenance_payload = {
                    "model_run_id": selected_run,
                    "source_context_sha256": sha256_file(directory / "scenario_contexts.parquet"),
                    "source_config_hash": fingerprint(source_config.as_dict()),
                    "code_version": self.run.manifest.get("code_version", "unavailable"),
                }
                result = scenario(
                    bundle,
                    contexts,
                    resolved_request,
                    source_config,
                    selected_run,
                    draws,
                    inference_method=inference_method,
                    provenance=provenance_payload,
                )
                write_json(path, result)
                outputs = [path]
                if "metrics" in result:
                    metrics_csv_content = format_scenario_metrics_csv(result)
                    metrics_csv_path.write_text(metrics_csv_content, encoding="utf-8")
                    outputs.append(metrics_csv_path)
                self.run.outputs("scenario", outputs, output_status=result["status"])
            else:
                result = read_json(path)
        return result

    def prepare_demand(
        self,
        model_run_id: str,
        snapshot_path: Path,
        request: ScenarioRequest | None = None,
        estimator: str | None = None,
    ) -> dict:
        """Freeze a verified local choice handoff and prepare simulator inputs."""
        if model_run_id == self.run.run_id:
            raise ValueError("prepare-demand requires a new run separate from the frozen model run")
        source_manifest: dict = {}
        snapshot: dict = {}
        source_artifacts: dict[str, str] = {}
        source_config = None
        selected_estimator = ""

        def demand_inputs():
            nonlocal source_manifest, snapshot, source_config, selected_estimator, source_artifacts
            source_manifest = completed_run(self.config.workspace, model_run_id)
            if not any(
                source_manifest.get("stages", {}).get(stage, {}).get("status") == "succeeded"
                for stage in ("fit", "freeze_choice")
            ):
                raise ValueError("Demand requires a completed choice fit")
            source_config = Config.from_dict(
                source_manifest.get("choice_source", {}).get(
                    "source_config", source_manifest["config"]
                ),
                self.config.workspace,
            )
            selected_estimator = estimator or source_config.model.scenario_estimator
            if selected_estimator not in source_manifest.get("model_results", {}):
                raise ValueError("Selected estimator is not present in the frozen model run")
            directory = self.config.workspace / "runs" / safe_id(model_run_id)
            prefix = f"models/{selected_estimator}"
            names = [
                "effects.csv",
                "splits.json",
                "scenario_result.json",
                "scenario_contexts.parquet",
                f"{prefix}/diagnostics.json",
            ]
            diagnostics = read_json(directory / names[-1])
            if diagnostics["status"] != source_manifest["model_results"][selected_estimator]:
                raise ValueError("Frozen model status differs from estimator diagnostics")
            if diagnostics["status"] != "not_identified":
                names.extend(
                    [f"{prefix}/model_bundle.joblib", f"{prefix}/bootstrap_bundles.joblib"]
                )
                if (
                    f"runs/{model_run_id}/{prefix}/analytic_inference.json"
                    in source_manifest["artifacts"]
                ):
                    names.append(f"{prefix}/analytic_inference.json")
            source_artifacts = {}
            for name in names:
                relative = f"runs/{model_run_id}/{name}"
                if relative not in source_manifest["artifacts"]:
                    raise ValueError(f"Required demand artifact is not registered: {relative}")
                source_artifacts[name] = source_manifest["artifacts"][relative]
            snapshot = read_json(snapshot_path)
            return {
                "model_run_id": model_run_id,
                "estimator": selected_estimator,
                "source_manifest_sha256": sha256_file(directory / "manifest.json"),
                "source_artifacts": source_artifacts,
                "snapshot": snapshot,
                "request": dataclasses.asdict(request) if request is not None else None,
            }

        with self.run.stage("prepare_demand", demand_inputs) as execute:
            result_path = self.run.path / "demand_result.json"
            if execute:
                assert source_config is not None
                source = self.config.workspace / "runs" / model_run_id
                frozen = self.run.path / "demand_bundle"
                paths = freeze_artifacts(source, frozen, source_artifacts)
                manifest_path = frozen / "source_manifest.json"
                write_json(manifest_path, source_manifest)
                paths.append(manifest_path)
                prefix = frozen / "models" / selected_estimator
                diagnostic = read_json(prefix / "diagnostics.json")
                bundle = (
                    joblib.load(prefix / "model_bundle.joblib")
                    if diagnostic["status"] != "not_identified"
                    else None
                )
                if bundle is not None and (
                    bundle.estimator != selected_estimator
                    or bundle.source_kind != source_manifest["source_kind"]
                    or bundle.dataset_id != source_manifest["dataset_id"]
                    or bundle.dgp_id != source_config.simulation.dgp
                    or bundle.seed != source_config.simulation.seed
                ):
                    raise ValueError("Choice bundle provenance differs from the source manifest")
                analytic_path = prefix / "analytic_inference.json"
                if bundle is not None and analytic_path.is_file():
                    bundle.analytic_inference = read_json(analytic_path)
                resolved_request = request or ScenarioRequest(
                    delta_price_x=source_config.scenario.delta_price_x,
                    delta_price_y=source_config.scenario.delta_price_y,
                    interval_level=source_config.evaluation.interval_level,
                )
                plan = prepare_demand_plan(
                    bundle,
                    pd.read_parquet(frozen / "scenario_contexts.parquet"),
                    snapshot,
                    resolved_request,
                    source_config,
                    model_run_id,
                    source_artifacts.get(f"models/{selected_estimator}/model_bundle.joblib"),
                    fingerprint({"manifest": source_manifest, "artifacts": source_artifacts}),
                )
                for name in ("demand_plan.parquet", "demand_plan.csv"):
                    path = self.run.path / name
                    write_frame(path, plan.frame)
                    paths.append(path)
                for name, value in (
                    ("baseline_snapshot.json", plan.snapshot),
                    ("demand_spec.json", plan.spec),
                    ("demand_result.json", plan.result),
                ):
                    path = self.run.path / name
                    write_json(path, value)
                    paths.append(path)
                self.run.manifest["demand_source"] = {
                    "model_run_id": model_run_id,
                    "estimator": selected_estimator,
                    "source_config": source_config.as_dict(),
                    "source_environment": source_manifest["environment"],
                }
                self.run.outputs(
                    "prepare_demand",
                    paths,
                    output_rows=len(plan.frame),
                    output_status=plan.result["status"],
                    usable_for_simulation=plan.result["usable_for_simulation"],
                )
            return read_json(result_path)

    def simulate_marketplace(
        self,
        demand_run_id: str,
        rules_path: Path,
        requests_path: Path | None = None,
        *,
        window_start: str | None = None,
        window_end: str | None = None,
        carry_in_run_id: str | None = None,
        compensation_path: Path | None = None,
    ) -> dict:
        """Freeze a verified demand run before one bounded fixed-supply trajectory."""
        if demand_run_id == self.run.run_id:
            raise ValueError("simulate-marketplace requires a separate output run")
        if carry_in_run_id == self.run.run_id:
            raise ValueError("Carry-in and simulation output must use separate runs")
        simulation_artifact = f"runs/{self.run.run_id}/simulation_result.json"
        if simulation_artifact in self.run.manifest["artifacts"]:
            earnings_artifact = f"runs/{self.run.run_id}/earnings_result.json"
            had_compensation = earnings_artifact in self.run.manifest["artifacts"]
            if had_compensation != (compensation_path is not None):
                raise ValueError("Use a new run ID when adding or removing compensation")
            old_version = read_json(self.run.path / "simulation_spec.json")["schema_version"]
            new_version = read_json(rules_path).get("schema_version")
            if (old_version == 3) != (new_version == 3):
                raise ValueError("Use a new run ID when changing the dispatch mode")
        source_manifest: dict = {}
        source_artifacts: dict[str, str] = {}
        rules: dict = {}
        requests_checksum: str | None = None
        carry_manifest: dict = {}
        carry_checksum: str | None = None
        compensation: dict | None = None

        def simulation_inputs():
            nonlocal source_manifest, source_artifacts, rules, requests_checksum
            nonlocal carry_manifest, carry_checksum
            nonlocal compensation
            source_manifest = completed_run(self.config.workspace, demand_run_id)
            if (
                source_manifest.get("stages", {}).get("prepare_demand", {}).get("status")
                != "succeeded"
            ):
                raise ValueError("Simulation requires a completed prepare-demand run")
            source = self.config.workspace / "runs" / safe_id(demand_run_id)
            names = [
                "demand_plan.parquet",
                "demand_result.json",
                "demand_spec.json",
                "baseline_snapshot.json",
            ]
            source_artifacts = {}
            for name in names:
                relative = f"runs/{demand_run_id}/{name}"
                if relative not in source_manifest["artifacts"]:
                    raise ValueError(f"Required simulation input is not registered: {relative}")
                source_artifacts[name] = source_manifest["artifacts"][relative]
            if read_json(source / "demand_result.json").get("usable_for_simulation") is not True:
                raise ValueError("Demand usable_for_simulation gate is false or unavailable")
            rules = read_json(rules_path)
            compensation = (
                validate_compensation(read_json(compensation_path))
                if compensation_path is not None
                else None
            )
            requests_checksum = sha256_file(requests_path) if requests_path else None
            if carry_in_run_id is not None:
                carry_manifest = completed_run(self.config.workspace, carry_in_run_id)
                if (
                    carry_manifest.get("stages", {}).get("simulate_marketplace", {}).get("status")
                    != "succeeded"
                ):
                    raise ValueError("Carry-in requires a completed simulate-marketplace run")
                relative = f"runs/{carry_in_run_id}/end_snapshot.json"
                if relative not in carry_manifest["artifacts"]:
                    raise ValueError("Carry-in checkpoint is not registered")
                carry_checksum = carry_manifest["artifacts"][relative]
            return {
                "demand_run_id": demand_run_id,
                "source_manifest_sha256": sha256_file(source / "manifest.json"),
                "source_artifacts": source_artifacts,
                "rules": rules,
                "seed": self.config.simulation.seed,
                "prescribed_requests_sha256": requests_checksum,
                "compensation": compensation,
                "window_start": window_start,
                "window_end": window_end,
                "carry_in_run_id": carry_in_run_id,
                "carry_checkpoint_sha256": carry_checksum,
                "carry_manifest_sha256": sha256_file(
                    self.config.workspace / "runs" / safe_id(carry_in_run_id) / "manifest.json"
                )
                if carry_in_run_id is not None
                else None,
            }

        with self.run.stage("simulate_marketplace", simulation_inputs) as execute:
            result_path = self.run.path / "simulation_result.json"
            if execute:
                source = self.config.workspace / "runs" / demand_run_id
                frozen = self.run.path / "simulation_inputs"
                paths = freeze_artifacts(source, frozen, source_artifacts)
                source_path = frozen / "source_manifest.json"
                rules_copy = frozen / "rules.json"
                write_json(source_path, source_manifest)
                write_json(rules_copy, rules)
                paths.extend([source_path, rules_copy])
                if compensation is not None:
                    compensation_copy = frozen / "compensation.json"
                    write_json(compensation_copy, compensation)
                    paths.append(compensation_copy)
                carry_in = None
                if carry_in_run_id is not None:
                    destination = frozen / "carry_in.json"
                    with atomic_path(destination) as temporary:
                        shutil.copyfile(
                            self.config.workspace
                            / "runs"
                            / safe_id(carry_in_run_id)
                            / "end_snapshot.json",
                            temporary,
                        )
                        if sha256_file(temporary) != carry_checksum:
                            raise ValueError("Carry-in changed while freezing")
                    carry_in = read_json(destination)
                    carry_manifest_path = frozen / "carry_manifest.json"
                    write_json(carry_manifest_path, carry_manifest)
                    paths.extend([destination, carry_manifest_path])
                prescribed = None
                if requests_path is not None:
                    # Read and freeze the same bytes; CSV is the explicit fixture exchange format.
                    if requests_path.suffix.lower() != ".csv":
                        raise ValueError("Prescribed requests must use CSV")
                    destination = frozen / "prescribed_requests.csv"
                    with atomic_path(destination) as temporary:
                        shutil.copyfile(requests_path, temporary)
                        if sha256_file(temporary) != requests_checksum:
                            raise ValueError("Prescribed requests changed while freezing")
                    paths.append(destination)
                    prescribed = pd.read_csv(
                        destination, dtype={"request_id": str, "service_id": str}
                    )
                source_config = Config.from_dict(
                    source_manifest["demand_source"]["source_config"], self.config.workspace
                )
                simulation = simulate_marketplace(
                    DemandPlan(
                        pd.read_parquet(frozen / "demand_plan.parquet"),
                        read_json(frozen / "demand_result.json"),
                        read_json(frozen / "baseline_snapshot.json"),
                        read_json(frozen / "demand_spec.json"),
                    ),
                    rules,
                    source_config,
                    self.config.simulation.seed,
                    prescribed,
                    window_start=window_start,
                    window_end=window_end,
                    carry_in=carry_in,
                    compensation=compensation,
                )
                frames = dict(
                    requests=simulation.requests,
                    request_events=simulation.request_events,
                    vehicle_intervals=simulation.vehicle_intervals,
                )
                frames.update(simulation.financial_tables or {})
                if simulation.driver_offers is not None:
                    frames["driver_offers"] = simulation.driver_offers
                if simulation.offer_events is not None:
                    frames["offer_events"] = simulation.offer_events
                for name, frame in frames.items():
                    for extension in ("parquet", "csv"):
                        path = self.run.path / f"{name}.{extension}"
                        write_frame(path, frame)
                        paths.append(path)
                for name, value in (
                    ("simulation_result.json", simulation.result),
                    ("simulation_spec.json", simulation.spec),
                    ("end_snapshot.json", simulation.end_snapshot),
                ):
                    path = self.run.path / name
                    write_json(path, value)
                    paths.append(path)
                if simulation.financial_tables is not None:
                    earnings_path = self.run.path / "earnings_result.json"
                    write_json(earnings_path, simulation.result["earnings"])
                    paths.append(earnings_path)
                self.run.manifest["simulation_source"] = {
                    "demand_run_id": demand_run_id,
                    "source_environment": source_manifest["environment"],
                    "source_kind": simulation.result["source_kind"],
                    "demand_source_kind": simulation.result["demand_source_kind"],
                    "carry_in_run_id": carry_in_run_id,
                    "carry_checkpoint_version": carry_in.get("checkpoint_version")
                    if carry_in
                    else None,
                }
                self.run.manifest["source_kind"] = "synthetic"
                self.run.outputs(
                    "simulate_marketplace",
                    paths,
                    output_requests=len(simulation.requests),
                    completed_trips=simulation.result["summary"]["completed_trips"],
                    output_status=simulation.result["status"],
                )
            return read_json(result_path)

    def evaluate(self, build_id: str | None = None, **kwargs: Any) -> None:
        if "buildId" in kwargs and build_id is None:
            build_id = kwargs["buildId"]

        context = None
        context_version = None

        def evaluate_inputs():
            nonlocal context, context_version
            context, context_version = self.context(build_id)
            return {"context_version": context_version}

        with self.run.stage("evaluate", evaluate_inputs) as execute:
            if execute:
                if context_version is None:
                    raise RuntimeError("Evaluate stage inputs did not resolve the context version")
                result = monte_carlo(
                    self.config,
                    context,
                    context_version,
                    self.run.path / "evaluation",
                    self.run.run_id,
                )
                paths = [
                    result["summary"],
                    result["seed_metrics"],
                    result["metadata"],
                    *result["checkpoint_files"],
                ]
                self.run.outputs("evaluate", paths, output_rows=result["rows"])

    def run_all(self, include_evaluation: bool = True, **kwargs: Any) -> str:
        if "includeEvaluation" in kwargs:
            include_evaluation = kwargs["includeEvaluation"]
        if self.config.project.context_mode == "tlc":
            self.build()
        self.generate()
        self.fit()
        self.method_evaluation()
        self.scenario()
        if include_evaluation:
            self.evaluate()
        self.run.complete()
        return self.run.run_id
