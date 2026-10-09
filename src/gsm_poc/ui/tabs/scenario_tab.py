"""Price scenario tab for the Streamlit dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.core.config import Config

ZONE_NAMES = {
    161: "Midtown Center",
    162: "Midtown East",
    163: "Midtown North",
    164: "Midtown South",
    170: "Murray Hill",
}
STATUS_LABELS = {
    "ok": "Supported",
    "limited": "Limited support",
    "insufficient_support": "Limited context support",
    "out_of_support": "Out of support",
    "not_identified": "Not identified",
    "interval_unstable": "Not ready for reporting",
}


def scenario_tab(
    workspace: Path,
    manifest: dict[str, Any],
    config: Config,
    artifact_loader: Any,
    model_loader: Any,
) -> None:
    st.subheader("Price scenario")
    st.caption("Evidence C · hypothetical services X and Y · quote session population held fixed")
    choices = config.model.estimators
    if "model_results" not in manifest:
        st.info("Fit a model before comparing price scenarios.")
        return
    context = artifact_loader(
        workspace, manifest, f"runs/{manifest['run_id']}/scenario_contexts.parquet"
    )
    controls = st.columns([2, 2, 1])
    with controls[0]:
        estimator = st.selectbox(
            "Scenario estimator", choices, index=choices.index(config.model.scenario_estimator)
        )
    with controls[1]:
        zone = st.selectbox(
            "Context zone",
            ["All zones", *sorted(context.zone_id.unique())],
            format_func=lambda z: ZONE_NAMES.get(z, str(z)),
        )
    with controls[2]:
        sessions = st.number_input(
            "Quote sessions",
            min_value=1,
            max_value=10_000_000,
            value=config.scenario.n_sessions,
            step=1000,
        )
    if zone != "All zones":
        context = context[context.zone_id == zone]
    sliders = st.columns(2)
    with sliders[0]:
        delta_x = st.slider("Price X change (%)", -10, 10, 10, step=1)
    with sliders[1]:
        delta_y = st.slider("Price Y change (%)", -10, 10, 0, step=1)
    inspect_outside = st.checkbox("Inspect unsupported price")
    if inspect_outside:
        delta_x = st.number_input(
            "Price X change to inspect (%)", min_value=-90.0, max_value=100.0, value=20.0, step=1.0
        )
    bundle, draws = model_loader(workspace, manifest, estimator)
    target_context_set = "all" if zone == "All zones" else f"zone_{zone}"
    request = ScenarioRequest(
        "interactive-price-scenario",
        delta_price_x=delta_x / 100,
        delta_price_y=delta_y / 100,
        n_sessions=int(sessions),
        interval_level=config.evaluation.interval_level,
        target_context_set=target_context_set,
    )
    result = scenario(bundle, context, request, config, manifest["run_id"], draws)
    if result["status"] in ("out_of_support", "not_identified", "invalid_probability"):
        st.warning(" · ".join(result["reasons"]))
    else:
        if result["status"] != "ok":
            st.warning(" · ".join(result["reasons"]) or "Selected context has limited support.")
        rows = [
            {
                "Service": service,
                "Before (%)": value["before_probability"] * 100,
                "After (%)": value["after_probability"] * 100,
                "Change (pp)": value["delta_percentage_points"],
                "Expected choices before": value["before_expected_choices"],
                "Expected choices after": value["after_expected_choices"],
            }
            for service, value in result["probabilities"].items()
        ]
        table = pd.DataFrame(rows)
        left, right = st.columns([2, 1])
        with left:
            long = table.melt(
                id_vars=["Service"],
                value_vars=["Before (%)", "After (%)"],
                var_name="Policy",
                value_name="Probability (%)",
            )
            chart = (
                alt.Chart(long, mark="bar")
                .encode(
                    x=alt.X("Service:N", title=None),
                    y=alt.Y("Probability (%):Q", scale=alt.Scale(domain=[0, 100])),
                    color=alt.Color("Policy:N", title=None),
                    xOffset="Policy:N",
                    tooltip=[
                        "Service:N",
                        "Policy:N",
                        alt.Tooltip("Probability (%):Q", format=".2f"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(chart, width="stretch")
        with right:
            st.metric(
                "Expected bookings",
                f"{result['after_expected_bookings']:,.0f}",
                f"{result['delta_expected_bookings']:+,.0f}",
                delta_color="off",
            )
            st.caption(
                f"Based on {sessions:,} assumed quote sessions. These are simulated "
                "booking choices; completed trips require a supply model."
            )
            scope_label = "All zones" if zone == "All zones" else ZONE_NAMES.get(zone, str(zone))
            st.write(f"Scope: **{scope_label}**")
            st.write(f"Support: **{STATUS_LABELS[result['support_status']]}**")
            st.write(f"Interval: **{STATUS_LABELS[result['bootstrap']['interval_status']]}**")
        st.dataframe(table, hide_index=True, width="stretch")
        if result["interval"] is not None:
            st.subheader("Uncertainty")
            st.dataframe(pd.DataFrame(result["interval"]).T, width="stretch")
        with st.expander("Effect matrix and interpretation"):
            st.dataframe(
                pd.DataFrame(
                    result["theta"],
                    index=pd.Index(["Choice X", "Choice Y"]),
                    columns=pd.Index(["Price X", "Price Y"]),
                ),
                width="stretch",
            )
            st.write(
                "The matrix is shared across the cluster. Changes in choice probabilities "
                "are net changes; they do not identify which customers switched service."
            )
    st.download_button(
        "Export scenario JSON",
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
        "scenario_result.json",
        "application/json",
    )
