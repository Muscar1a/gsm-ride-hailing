"""Streamlit artifact reader: no training or raw-source downloads in user actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import altair as alt
import joblib
import pandas as pd
import streamlit as st

from gsm_poc.artifacts import completed_run, read_json, safe_id, sha256_file
from gsm_poc.config import Config
from gsm_poc.scenario import ScenarioRequest, scenario

ZONE_NAMES = {
    161: "Midtown Center",
    162: "Midtown East",
    163: "Midtown North",
    164: "Midtown South",
    170: "Murray Hill",
}
STATUS_LABELS = {
    "ok": "Supported",
    "insufficient_support": "Limited context support",
    "interval_unstable": "Not ready for reporting",
}


@st.cache_data(show_spinner=False)
def read_table(path: str, checksum: str) -> pd.DataFrame:
    if sha256_file(Path(path)) != checksum:
        raise ValueError("Table checksum mismatch")
    return pd.read_csv(path) if Path(path).suffix == ".csv" else pd.read_parquet(path)


@st.cache_resource(show_spinner=False)
def read_bundle(path: str, checksum: str):
    if sha256_file(Path(path)) != checksum:
        raise ValueError("Model checksum mismatch")
    return joblib.load(path)


@st.cache_data(show_spinner=False)
def checked_manifest(
    workspace: str, run_id: str, manifest_hash: str, artifact_stats: tuple
) -> dict:
    return completed_run(Path(workspace), run_id)


def artifact(workspace: Path, manifest: dict, relative: str) -> pd.DataFrame:
    path = workspace / relative
    checksum = manifest["artifacts"][relative.replace("\\", "/")]
    return read_table(str(path), checksum)


def load_model(workspace: Path, manifest: dict, estimator: str):
    prefix = f"runs/{manifest['run_id']}/models/{estimator}"
    diagnostic = read_json(workspace / prefix / "diagnostics.json")
    if diagnostic["status"] == "not_identified":
        return None, None
    loaded = []
    for name in ("model_bundle.joblib", "bootstrap_bundles.joblib"):
        relative = f"{prefix}/{name}"
        loaded.append(read_bundle(str(workspace / relative), manifest["artifacts"][relative]))
    return tuple(loaded)


def observed_tab(workspace: Path, manifest: dict) -> None:
    st.subheader("Completed trips")
    st.caption("TLC observed · NYC, January 2024 · money in USD · local New York time")
    build = manifest.get("observed_build")
    if build is None:
        st.info("This run uses synthetic contexts. Run the TLC profile to view observed trips.")
        return
    mart = artifact(workspace, manifest, build["mart"].replace("\\", "/"))
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
        alt.Chart(series)
        .mark_line()
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


def method_tab(workspace: Path, manifest: dict) -> None:
    st.subheader("Recovering known effects")
    st.caption(
        "Controlled simulation · evidence C · each matrix row is an outcome; "
        "each column is the service whose price changes"
    )
    relative = f"runs/{manifest['run_id']}/method_metrics.csv"
    if relative not in manifest["artifacts"]:
        st.info("This run has no method evaluation. Fit a generated dataset first.")
        return
    metrics = artifact(workspace, manifest, relative)
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
            alt.Chart(values)
            .mark_bar()
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
        summary = artifact(workspace, manifest, evaluation_relative)
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


def scenario_tab(workspace: Path, manifest: dict, config: Config) -> None:
    st.subheader("Price scenario")
    st.caption("Evidence C · hypothetical services X and Y · quote session population held fixed")
    choices = config.model.estimators
    if "model_results" not in manifest:
        st.info("Fit a model before comparing price scenarios.")
        return
    context = artifact(workspace, manifest, f"runs/{manifest['run_id']}/scenario_contexts.parquet")
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
    bundle, draws = load_model(workspace, manifest, estimator)
    request = ScenarioRequest(
        "interactive-price-scenario",
        delta_price_x=delta_x / 100,
        delta_price_y=delta_y / 100,
        n_sessions=int(sessions),
        interval_level=config.evaluation.interval_level,
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
                alt.Chart(long)
                .mark_bar()
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
            st.write(f"Support: **{STATUS_LABELS[result['support_status']]}**")
            st.write(f"Interval: **{STATUS_LABELS[result['bootstrap']['interval_status']]}**")
        st.dataframe(table, hide_index=True, width="stretch")
        if result["interval"] is not None:
            st.subheader("Uncertainty")
            st.dataframe(pd.DataFrame(result["interval"]).T, width="stretch")
        with st.expander("Effect matrix and interpretation"):
            st.dataframe(
                pd.DataFrame(
                    result["theta"], index=["Choice X", "Choice Y"], columns=["Price X", "Price Y"]
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
    run_records = {}
    for path in sorted((workspace / "runs").glob("*/manifest.json"), reverse=True):
        try:
            record = read_json(path)
        except (ValueError, OSError):
            continue
        if record.get("status") == "succeeded" and "fit" in record.get("stages", {}):
            available.append(record["run_id"])
            run_records[record["run_id"]] = record
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
        initial_simulation = run_records[initial]["config"]["simulation"]
        dgps = sorted({record["config"]["simulation"]["dgp"] for record in run_records.values()})
        selected_dgp = st.selectbox("DGP", dgps, index=dgps.index(initial_simulation["dgp"]))
        matching = [
            run
            for run in available
            if run_records[run]["config"]["simulation"]["dgp"] == selected_dgp
        ]
        seeds = sorted({run_records[run]["config"]["simulation"]["seed"] for run in matching})
        seed_index = (
            seeds.index(initial_simulation["seed"]) if initial_simulation["seed"] in seeds else 0
        )
        selected_seed = st.selectbox("Seed", seeds, index=seed_index)
        matching = [
            run
            for run in matching
            if run_records[run]["config"]["simulation"]["seed"] == selected_seed
        ]
        index = matching.index(initial) if initial in matching else 0
        selected = st.selectbox("Run", matching, index=index)
    selected = safe_id(selected)
    manifest_path = workspace / "runs" / selected / "manifest.json"
    preliminary = read_json(manifest_path)
    stats = tuple(
        (relative, (workspace / relative).stat().st_mtime_ns, (workspace / relative).stat().st_size)
        for relative in preliminary["artifacts"]
        if (workspace / relative).is_file()
    )
    try:
        with st.spinner("Loading completed artifacts…"):
            manifest = checked_manifest(str(workspace), selected, sha256_file(manifest_path), stats)
    except (ValueError, OSError) as exc:
        st.error(f"Cannot load this run: {exc}")
        return
    config = Config.from_dict(manifest["config"], workspace)
    with st.sidebar:
        st.write(f"**{config.simulation.dgp}** · seed {config.simulation.seed}")
        st.caption(f"Simulated behavior · {manifest['source_kind']} · evidence C")
        st.caption(
            "Hypothetical X/Y choices. Results require GSM data and an identification "
            "design before being used for GSM pricing."
        )
        effects_relative = f"runs/{selected}/effects.csv"
        st.download_button(
            "Export effects CSV",
            (workspace / effects_relative).read_bytes(),
            "effects.csv",
            "text/csv",
        )
        summary = {
            "run_id": selected,
            "source_kind": manifest["source_kind"],
            "evidence_level": "C",
            "config": manifest["config"],
            "environment": manifest["environment"],
            "stages": manifest["stages"],
        }
        st.download_button(
            "Export run summary",
            json.dumps(summary, indent=2),
            "run_summary.json",
            "application/json",
        )
    tabs = st.tabs(["Operations", "Method checks", "Price scenarios"])
    with tabs[0]:
        observed_tab(workspace, manifest)
    with tabs[1]:
        method_tab(workspace, manifest)
    with tabs[2]:
        scenario_tab(workspace, manifest, config)
    st.divider()
    st.caption(
        "GSM PoC · January 2024 context · supply response and marketplace matching begin "
        "in the next phase"
    )


if __name__ == "__main__":
    main()
