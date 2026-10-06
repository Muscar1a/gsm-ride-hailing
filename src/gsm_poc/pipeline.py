"""Batch stage orchestration. The UI only reads finished artifacts."""

from __future__ import annotations

import joblib
import pandas as pd

from gsm_poc.artifacts import (
    Run,
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
from gsm_poc.estimate import FitResult, fit_all
from gsm_poc.evaluate import effect_rows, monte_carlo, saved_method_evaluation
from gsm_poc.features import date_splits
from gsm_poc.generate import generate, save_generated
from gsm_poc.ingest import ingest
from gsm_poc.scenario import ScenarioRequest, scenario
from gsm_poc.uncertainty import BootstrapResult, bootstrap


class Pipeline:
    def __init__(self, config: Config, run_id: str | None = None) -> None:
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

    def context(self, build_id: str | None = None) -> tuple[pd.DataFrame | None, str]:
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

    def generate(self, build_id: str | None = None) -> str:
        contexts, version = self.context(build_id)
        with self.run.stage("generate", {"context_version": version}) as execute:
            if execute:
                data = generate(self.config, contexts, version)
                paths = save_generated(self.config, data)
                self.run.manifest["dataset_id"] = data.dataset_id
                self.run.manifest["context_version"] = version
                self.run.outputs(
                    "generate",
                    paths,
                    output_blocks=len(data.blocks),
                    output_sessions=len(data.sessions),
                )
        return self.run.manifest["dataset_id"]

    def fit(self, dataset_id: str | None = None) -> None:
        dataset_id = safe_id(dataset_id or self.run.manifest.get("dataset_id", ""))
        root = self.config.workspace / "data/synthetic" / dataset_id
        observed = root / "observed/choice_block.parquet"
        metadata_path = root / "manifest.json"
        inputs = {
            "dataset_id": dataset_id,
            "observed_sha256": sha256_file(observed),
            "metadata_sha256": sha256_file(metadata_path),
        }
        with self.run.stage("fit", inputs) as execute:
            if execute:
                blocks = pd.read_parquet(observed)
                metadata = read_json(metadata_path)
                if metadata["source_kind"] != self.run.manifest["source_kind"]:
                    raise ValueError("Dataset source kind differs from run configuration")
                if metadata["dgp_id"] != self.config.simulation.dgp:
                    raise ValueError("Dataset DGP differs from run configuration")
                if metadata["seed"] != self.config.simulation.seed:
                    raise ValueError("Dataset seed differs from configuration; pass --seed")
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
                            records = pd.DataFrame(columns=["draw_id", "estimator", "status"])
                        write_frame(records_path, records)
                        paths.extend([model_path, draws_path, records_path])
                    else:
                        draws = None
                    write_json(diagnostics, result.diagnostics)
                    paths.append(diagnostics)
                    effects.extend(
                        effect_rows(
                            result, draws, splits["test"], self.config, self.run.run_id, dataset_id
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
                    dataset_id=dataset_id,
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
        dataset_id = self.run.manifest["dataset_id"]
        root = self.config.workspace / "data/synthetic" / dataset_id
        oracle = root / "oracle/oracle_block.parquet"
        inputs = {
            "dataset_id": dataset_id,
            "oracle_sha256": sha256_file(oracle),
            "observed_sha256": sha256_file(root / "observed/choice_block.parquet"),
            "metadata_sha256": sha256_file(root / "manifest.json"),
            "models": {},
        }
        for name in self.config.model.estimators:
            directory = self.run.path / "models" / name
            diagnostics_path = directory / "diagnostics.json"
            model_inputs = {"diagnostics_sha256": sha256_file(diagnostics_path)}
            if read_json(diagnostics_path)["status"] != "not_identified":
                model_inputs.update(
                    model_sha256=sha256_file(directory / "model_bundle.joblib"),
                    bootstrap_sha256=sha256_file(directory / "bootstrap_bundles.joblib"),
                )
            inputs["models"][name] = model_inputs
        with self.run.stage("method_evaluation", inputs) as execute:
            if execute:
                results, draws = self.load_models()
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
    ) -> dict:
        selected_run = model_run_id or self.run.run_id
        directory = self.config.workspace / "runs" / safe_id(selected_run)
        if model_run_id:
            completed_run(self.config.workspace, selected_run)
        request = request or ScenarioRequest(
            delta_price_x=self.config.scenario.delta_price_x,
            delta_price_y=self.config.scenario.delta_price_y,
            n_sessions=self.config.scenario.n_sessions,
            interval_level=self.config.evaluation.interval_level,
        )
        name = self.config.model.scenario_estimator
        diagnostics = read_json(directory / "models" / name / "diagnostics.json")
        model_path = directory / "models" / name / "model_bundle.joblib"
        bundle = joblib.load(model_path) if diagnostics["status"] != "not_identified" else None
        draws = joblib.load(model_path.with_name("bootstrap_bundles.joblib")) if bundle else None
        contexts = pd.read_parquet(directory / "scenario_contexts.parquet")
        if zone is not None:
            contexts = contexts[contexts.zone_id == zone]
        inputs = {
            "model_run_id": selected_run,
            "request": request.__dict__,
            "zone": zone,
            "diagnostics_sha256": sha256_file(directory / "models" / name / "diagnostics.json"),
            "model_sha256": sha256_file(model_path) if bundle else None,
            "bootstrap_sha256": (
                sha256_file(model_path.with_name("bootstrap_bundles.joblib")) if bundle else None
            ),
            "contexts_sha256": sha256_file(directory / "scenario_contexts.parquet"),
        }
        with self.run.stage("scenario", inputs) as execute:
            path = self.run.path / "scenario_result.json"
            if execute:
                result = scenario(bundle, contexts, request, self.config, selected_run, draws)
                write_json(path, result)
                self.run.outputs("scenario", [path], output_status=result["status"])
            else:
                result = read_json(path)
        return result

    def evaluate(self, build_id: str | None = None) -> None:
        context, version = self.context(build_id)
        with self.run.stage("evaluate", {"context_version": version}) as execute:
            if execute:
                result = monte_carlo(
                    self.config, context, version, self.run.path / "evaluation", self.run.run_id
                )
                paths = [
                    result["summary"],
                    result["seed_metrics"],
                    result["metadata"],
                    *result["checkpoint_files"],
                ]
                self.run.outputs("evaluate", paths, output_rows=result["rows"])

    def run_all(self, include_evaluation: bool = True) -> str:
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
