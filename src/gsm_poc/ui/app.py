"""Streamlit artifact reader: no training or raw-source downloads in user actions."""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st

from gsm_poc.causal.estimate import ModelBundle
from gsm_poc.causal.uncertainty import BootstrapResult
from gsm_poc.core.artifacts import completed_run, read_json
from gsm_poc.core.config import Config
from gsm_poc.ui.tabs import method_tab, observed_tab, scenario_tab


@st.cache_data
def read_table(path: str, checksum: str) -> pd.DataFrame:
    assert checksum
    return pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)


@st.cache_resource
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


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--run-id")
    args, _ = parser.parse_known_args()
    workspace = args.workspace.resolve()
    st.set_page_config(page_title="GSM Causal Marketplace", layout="wide")
    token_path = workspace / "tokens.css"
    if token_path.exists():
        css = (
            token_path.read_text(encoding="utf-8")
            + "\n"
            + Path(__file__).with_name("ui.css").read_text(encoding="utf-8")
        )
        st.html(f"<style>{css}</style>")
    st.title("GSM Causal Marketplace")
    st.caption("First two weeks · controlled PoC")
    available = []
    run_configs = {}
    for path in sorted((workspace / "runs").glob("*/manifest.json"), reverse=True):
        try:
            record = read_json(path)
        except (ValueError, OSError):
            continue
        if record.get("status") == "succeeded" and any(
            record.get("stages", {}).get(stage, {}).get("status") == "succeeded"
            for stage in ("fit", "freeze_choice")
        ):
            available.append(record["run_id"])
            run_configs[record["run_id"]] = record.get("choice_source", {}).get(
                "source_config", record["config"]
            )
    if not available:
        st.info(
            "No completed model run yet. Run the offline demo command in the README, "
            "then refresh this page."
        )
        return
    with st.sidebar:
        st.subheader("Completed run")
        initial = args.run_id or st.query_params.get("run")
        initial = initial if initial in available else available[0]
        initial_simulation = run_configs[initial]["simulation"]
        dgps = sorted({config["simulation"]["dgp"] for config in run_configs.values()})
        selected_dgp = st.selectbox("DGP", dgps, index=dgps.index(initial_simulation["dgp"]))
        matching = [
            run for run in available if run_configs[run]["simulation"]["dgp"] == selected_dgp
        ]
        seeds = sorted({run_configs[run]["simulation"]["seed"] for run in matching})
        seed_index = (
            seeds.index(initial_simulation["seed"]) if initial_simulation["seed"] in seeds else 0
        )
        selected_seed = st.selectbox("Seed", seeds, index=seed_index)
        matching = [
            run for run in matching if run_configs[run]["simulation"]["seed"] == selected_seed
        ]
        selected_run_id = st.selectbox(
            "Run ID",
            matching,
            index=matching.index(initial) if initial in matching else 0,
            help="Frozen audit directory in workspace/runs",
        )
        st.query_params["run"] = selected_run_id
        manifest = checked_manifest(workspace, selected_run_id)
        choice_source = manifest.get("choice_source", {})
        frozen_config = choice_source.get("source_config", manifest["config"])
        source_environment = choice_source.get("source_environment", manifest["environment"])
        config = Config.from_dict(frozen_config, workspace)
        st.caption(f"Run {manifest['run_id']} · created {manifest['created_at']}")
        st.caption(f"Code hash {source_environment['source_code_sha256'][:12]}")
        with st.expander("Frozen configuration"):
            st.json(frozen_config)
        with st.expander("Stages"):
            st.json(manifest["stages"])
        with st.expander("Model environment and versions"):
            st.json(source_environment)
        if choice_source:
            st.caption(f"Source model run {choice_source['model_run_id']}")
            with st.expander("Packaging environment and versions"):
                st.json(manifest["environment"])
    tabs = st.tabs(["Observed", "Method evaluation", "Price scenario"])
    with tabs[0]:
        observed_tab(workspace, manifest, artifact)
    with tabs[1]:
        method_tab(workspace, manifest, artifact)
    with tabs[2]:
        scenario_tab(workspace, manifest, config, artifact, load_model)


if __name__ == "__main__":
    main()
