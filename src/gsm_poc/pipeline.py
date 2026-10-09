"""Batch stage orchestration. The UI only reads finished artifacts."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from gsm_poc.artifacts import (
    Run,
    atomic_path,
    completed_run,
    fingerprint,
    read_json,
    safe_id,
    sha256_file,
    write_frame,
    write_json,
    write_model,
)
from gsm_poc.build_context import build_context
from gsm_poc.build_marts import build_marts
from gsm_poc.build_silver import build_silver
from gsm_poc.config import Config
from gsm_poc.demand import DemandPlan, prepare_demand_plan
from gsm_poc.estimate import FitResult, fit_all
from gsm_poc.evaluate import effect_rows, monte_carlo, saved_method_evaluation
from gsm_poc.features import date_splits, require_observed
from gsm_poc.generate import generate, save_generated
from gsm_poc.ingest import ingest
from gsm_poc.marketplace_simulator import simulate_marketplace
from gsm_poc.scenario import ScenarioRequest, scenario
from gsm_poc.uncertainty import BootstrapResult, bootstrap


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
            rawDatasetId = dataset_id or self.run.manifest.get("dataset_id", "")
            if not rawDatasetId:
                raise ValueError(
                    "Dataset ID is required to fit models; pass --dataset-id or run generate"
                )
            validatedDatasetId = safe_id(rawDatasetId)
            root = self.config.workspace / "data/synthetic" / validatedDatasetId
            observed = root / "observed/choice_block.parquet"
            metadataPath = root / "manifest.json"
            if not observed.is_file():
                raise FileNotFoundError(f"Observed choice block not found: {observed}")
            if not metadataPath.is_file():
                raise FileNotFoundError(f"Dataset manifest not found: {metadataPath}")
            return {
                "dataset_id": validatedDatasetId,
                "observed_sha256": sha256_file(observed),
                "metadata_sha256": sha256_file(metadataPath),
            }

        with self.run.stage("fit", fit_inputs) as execute:
            if execute:
                rawDatasetId = dataset_id or self.run.manifest.get("dataset_id", "")
                validatedDatasetId = safe_id(rawDatasetId)
                root = self.config.workspace / "data/synthetic" / validatedDatasetId
                observed = root / "observed/choice_block.parquet"
                metadataPath = root / "manifest.json"
                blocks = pd.read_parquet(observed)
                metadata = read_json(metadataPath)
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
                            validatedDatasetId,
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
                    dataset_id=validatedDatasetId,
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
            metadataPath = root / "manifest.json"
            if not oracle.is_file():
                raise FileNotFoundError(f"Oracle block not found: {oracle}")
            if not observed.is_file():
                raise FileNotFoundError(f"Observed choice block not found: {observed}")
            if not metadataPath.is_file():
                raise FileNotFoundError(f"Dataset manifest not found: {metadataPath}")
            inputs = {
                "dataset_id": dataset_id,
                "oracle_sha256": sha256_file(oracle),
                "observed_sha256": sha256_file(observed),
                "metadata_sha256": sha256_file(metadataPath),
                "scenario": self.config.scenario.__dict__,
                "models": {},
            }
            for name in self.config.model.estimators:
                directory = self.run.path / "models" / name
                diagnosticsPath = directory / "diagnostics.json"
                if not diagnosticsPath.is_file():
                    raise FileNotFoundError(f"Estimator diagnostics not found: {diagnosticsPath}")
                modelInputs = {"diagnostics_sha256": sha256_file(diagnosticsPath)}
                if read_json(diagnosticsPath)["status"] != "not_identified":
                    modelBundle = directory / "model_bundle.joblib"
                    bootstrapBundles = directory / "bootstrap_bundles.joblib"
                    if not modelBundle.is_file():
                        raise FileNotFoundError(f"Model bundle not found: {modelBundle}")
                    if not bootstrapBundles.is_file():
                        raise FileNotFoundError(f"Bootstrap bundles not found: {bootstrapBundles}")
                    modelInputs.update(
                        model_sha256=sha256_file(modelBundle),
                        bootstrap_sha256=sha256_file(bootstrapBundles),
                    )
                inputs["models"][name] = modelInputs
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

    def scenario(
        self,
        request: ScenarioRequest | None = None,
        model_run_id: str | None = None,
        zone: int | None = None,
        **kwargs: Any,
    ) -> dict:
        if "modelRunId" in kwargs and model_run_id is None:
            model_run_id = kwargs["modelRunId"]

        selectedRun = model_run_id or self.run.run_id
        directory = self.config.workspace / "runs" / safe_id(selectedRun)
        targetContextSet = (
            f"zone_{zone}" if zone is not None else self.config.scenario.target_context_set
        )
        if request is None:
            resolvedRequest = ScenarioRequest(
                delta_price_x=self.config.scenario.delta_price_x,
                delta_price_y=self.config.scenario.delta_price_y,
                n_sessions=self.config.scenario.n_sessions,
                interval_level=self.config.evaluation.interval_level,
                target_context_set=targetContextSet,
            )
        elif zone is not None and request.target_context_set == "all":
            resolvedRequest = dataclasses.replace(request, target_context_set=targetContextSet)
        else:
            resolvedRequest = request

        def scenario_inputs():
            if model_run_id:
                completed_run(self.config.workspace, selectedRun)
            name = self.config.model.scenario_estimator
            diagnosticsPath = directory / "models" / name / "diagnostics.json"
            if not diagnosticsPath.is_file():
                raise FileNotFoundError(f"Estimator diagnostics not found: {diagnosticsPath}")
            diagnostics = read_json(diagnosticsPath)
            modelPath = directory / "models" / name / "model_bundle.joblib"
            bootstrapPath = modelPath.with_name("bootstrap_bundles.joblib")
            modelSha256 = None
            bootstrapSha256 = None
            if diagnostics["status"] != "not_identified":
                if not modelPath.is_file():
                    raise FileNotFoundError(f"Model bundle not found: {modelPath}")
                if not bootstrapPath.is_file():
                    raise FileNotFoundError(f"Bootstrap bundles not found: {bootstrapPath}")
                modelSha256 = sha256_file(modelPath)
                bootstrapSha256 = sha256_file(bootstrapPath)
            contextsPath = directory / "scenario_contexts.parquet"
            if not contextsPath.is_file():
                raise FileNotFoundError(f"Scenario contexts not found: {contextsPath}")
            return {
                "model_run_id": selectedRun,
                "request": dataclasses.asdict(resolvedRequest),
                "zone": zone,
                "diagnostics_sha256": sha256_file(diagnosticsPath),
                "model_sha256": modelSha256,
                "bootstrap_sha256": bootstrapSha256,
                "contexts_sha256": sha256_file(contextsPath),
            }

        with self.run.stage("scenario", scenario_inputs) as execute:
            path = self.run.path / "scenario_result.json"
            if execute:
                name = self.config.model.scenario_estimator
                diagnostics = read_json(directory / "models" / name / "diagnostics.json")
                model_path = directory / "models" / name / "model_bundle.joblib"
                bundle = (
                    joblib.load(model_path) if diagnostics["status"] != "not_identified" else None
                )
                draws = (
                    joblib.load(model_path.with_name("bootstrap_bundles.joblib"))
                    if bundle
                    else None
                )
                contexts = pd.read_parquet(directory / "scenario_contexts.parquet")
                if zone is not None:
                    contexts = contexts[contexts.zone_id == zone]
                result = scenario(
                    bundle, contexts, resolvedRequest, self.config, selectedRun, draws
                )
                write_json(path, result)
                self.run.outputs("scenario", [path], output_status=result["status"])
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
            if source_manifest.get("stages", {}).get("fit", {}).get("status") != "succeeded":
                raise ValueError("Demand requires a completed choice fit")
            source_config = Config.from_dict(source_manifest["config"], self.config.workspace)
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
                paths = []
                for name, expected in source_artifacts.items():
                    destination = frozen / name
                    with atomic_path(destination) as temporary:
                        shutil.copyfile(source / name, temporary)
                        if sha256_file(temporary) != expected:
                            raise ValueError(
                                f"Source changed while freezing demand artifact: {name}"
                            )
                    paths.append(destination)
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
    ) -> dict:
        """Freeze a verified demand run before one bounded fixed-supply trajectory."""
        if demand_run_id == self.run.run_id:
            raise ValueError("simulate-marketplace requires a separate output run")
        if carry_in_run_id == self.run.run_id:
            raise ValueError("Carry-in and simulation output must use separate runs")
        source_manifest: dict = {}
        source_artifacts: dict[str, str] = {}
        rules: dict = {}
        requests_checksum: str | None = None
        carry_manifest: dict = {}
        carry_checksum: str | None = None

        def simulation_inputs():
            nonlocal source_manifest, source_artifacts, rules, requests_checksum
            nonlocal carry_manifest, carry_checksum
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
                paths = []
                for name, expected in source_artifacts.items():
                    destination = frozen / name
                    with atomic_path(destination) as temporary:
                        shutil.copyfile(source / name, temporary)
                        if sha256_file(temporary) != expected:
                            raise ValueError(
                                f"Source changed while freezing simulation input: {name}"
                            )
                    paths.append(destination)
                source_path = frozen / "source_manifest.json"
                rules_copy = frozen / "rules.json"
                write_json(source_path, source_manifest)
                write_json(rules_copy, rules)
                paths.extend([source_path, rules_copy])
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
                )
                for name, frame in (
                    ("requests", simulation.requests),
                    ("request_events", simulation.request_events),
                    ("vehicle_intervals", simulation.vehicle_intervals),
                ):
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
