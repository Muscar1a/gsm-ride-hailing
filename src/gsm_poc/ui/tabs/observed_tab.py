"""TLC observed market tab for the Streamlit dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from gsm_poc.core.artifacts import read_json

ZONE_NAMES = {
    161: "Midtown Center",
    162: "Midtown East",
    163: "Midtown North",
    164: "Midtown South",
    170: "Murray Hill",
}


def observed_tab(workspace: Path, manifest: dict[str, Any], artifact_loader: Any) -> None:
    st.subheader("Completed trips")
    st.caption("TLC observed · NYC, January 2024 · money in USD · local New York time")
    build = manifest.get("observed_build")
    if build is None:
        st.info("This run uses synthetic contexts. Run the TLC profile to view observed trips.")
        return
    mart = artifact_loader(workspace, manifest, build["mart"].replace("\\", "/"))
    dates = pd.to_datetime(mart.slot_start_local)
    controls = st.columns([2, 2, 1])
    with controls[0]:
        selected_dates = st.date_input(
            "Dates",
            (dates.min().date(), dates.max().date()),
            min_value=dates.min().date(),
            max_value=dates.max().date(),
        )
    with controls[1]:
        zones = st.multiselect(
            "Pickup zones",
            sorted(mart.zone_id.unique()),
            default=sorted(mart.zone_id.unique()),
            format_func=lambda z: ZONE_NAMES.get(z, str(z)),
        )
    with controls[2]:
        platforms = st.multiselect(
            "Platforms", sorted(mart.platform.unique()), default=sorted(mart.platform.unique())
        )
    if len(selected_dates) != 2:
        st.info("Select both the start and end date.")
        return
    selected = mart[
        (dates.dt.date >= selected_dates[0])
        & (dates.dt.date <= selected_dates[1])
        & mart.zone_id.isin(zones)
        & mart.platform.isin(platforms)
    ].copy()
    if selected.empty:
        st.info("Choose at least one pickup zone and platform.")
        return
    count = int(selected.completed_trip_count.sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed trips", f"{count:,}")
    c2.metric("Valid duration", f"{int(selected.n_valid_duration.sum()):,}")
    c3.metric("Valid wait metric", f"{int(selected.n_valid_wait.sum()):,}")
    missing = 100 * (1 - selected.n_valid_wait.sum() / count) if count else None
    c4.metric("Wait invalid or missing", f"{missing:.1f}%" if missing is not None else "—")
    selected["slot_start_local"] = pd.to_datetime(selected.slot_start_local)
    series = selected.groupby(
        ["slot_start_local", "platform"], as_index=False
    ).completed_trip_count.sum()
    chart = (
        alt.Chart(series, mark="line")
        .encode(
            x=alt.X("slot_start_local:T", title="Pickup time (New York)"),
            y=alt.Y("completed_trip_count:Q", title="Completed trips"),
            color=alt.Color("platform:N", title="Platform"),
            tooltip=["slot_start_local:T", "platform:N", "completed_trip_count:Q"],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Quantiles are shown per zone, time block and platform. Cells with fewer than the "
        "configured valid trips have no published quantile."
    )
    st.dataframe(
        selected[
            [
                "zone_id",
                "slot_start_local",
                "platform",
                "completed_trip_count",
                "trip_seconds_p50",
                "trip_km_p50",
                "base_fare_usd_p50",
                "request_to_pickup_p50",
                "n_valid_duration",
                "n_valid_distance",
                "n_valid_fare_transaction",
                "n_valid_wait",
            ]
        ],
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Export observed CSV", selected.to_csv(index=False), "tlc_observed_market.csv", "text/csv"
    )
    with st.expander("Data quality and scope"):
        quality = read_json(workspace / build["quality"])
        st.json(quality)
