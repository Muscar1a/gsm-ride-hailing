"""Method evaluation tab for the Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import altair as alt
import streamlit as st

from gsm_poc.core.artifacts import read_json


def method_tab(workspace: Path, manifest: dict[str, Any], artifact_loader: Any) -> None:
    st.subheader("Recovering known effects")
    st.caption(
        "Controlled simulation · evidence C · each matrix row is an outcome; "
        "each column is the service whose price changes"
    )
    relative = f"runs/{manifest['run_id']}/method_metrics.csv"
    if relative not in manifest["artifacts"]:
        st.info("This run has no method evaluation. Fit a generated dataset first.")
        return
    metrics = artifact_loader(workspace, manifest, relative)
    estimator = st.selectbox("Estimator", list(metrics.estimator.unique()), key="method_estimator")
    selected = metrics[metrics.estimator == estimator].copy()
    status = manifest["model_results"][estimator]
    if status == "not_identified":
        st.warning(
            "Prices move together in this run. Their separate responses cannot be identified."
        )
    else:
        values = selected.melt(
            id_vars=["outcome", "treatment"],
            value_vars=["true_theta", "theta"],
            var_name="coefficient",
            value_name="value",
        )
        values["effect"] = values.outcome + " ← price " + values.treatment
        chart = (
            alt.Chart(values, mark="bar")
            .encode(
                y=alt.Y("effect:N", title=None),
                x=alt.X("value:Q", title="Probability / log price"),
                color=alt.Color("coefficient:N", title=None),
                yOffset="coefficient:N",
                tooltip=["effect:N", "coefficient:N", alt.Tooltip("value:Q", format=".4f")],
            )
            .properties(height=250)
        )
        st.altair_chart(chart, width="stretch")
    columns = [
        "outcome",
        "treatment",
        "true_theta",
        "theta",
        "error",
        "theta_lower",
        "theta_upper",
        "interval_status",
        "status",
    ]
    st.dataframe(selected[columns], hide_index=True, width="stretch")
    st.caption(
        "Intervals from a small development run are experimental. A single run does not "
        "measure coverage; the repeated-seed table does."
    )
    evaluation_relative = f"runs/{manifest['run_id']}/evaluation/evaluation_metrics.csv"
    if evaluation_relative in manifest["artifacts"]:
        summary = artifact_loader(workspace, manifest, evaluation_relative)
        st.subheader("Repeated seeds")
        st.caption(
            f"{manifest['config']['evaluation']['seeds']} seeds per DGP · "
            f"{manifest['config']['evaluation']['bootstrap_draws']} day draws per estimator. "
            "Coverage includes exact binomial intervals and its valid-run denominator."
        )
        st.dataframe(summary, hide_index=True, width="stretch")
        st.download_button(
            "Export evaluation CSV",
            summary.to_csv(index=False),
            "evaluation_metrics.csv",
            "text/csv",
        )
    else:
        st.info("Repeated-seed evaluation has not been run for this model run.")
    with st.expander("Assumptions and identification"):
        st.write(
            "The model adjusts observed context. It cannot correct hidden confounding. "
            "The hidden-confounder DGP demonstrates that limitation. Effects apply to a "
            "fixed population of quote viewers, and are common across the selected cluster."
        )
        st.json(read_json(workspace / "runs" / manifest["run_id"] / "splits.json"))
