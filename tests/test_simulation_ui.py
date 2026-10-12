from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from gsm_poc.core.artifacts import Run, write_frame, write_json
from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.ui.tabs.simulation_tab import load_simulation

APP_PATH = Path(__file__).parents[1] / "src/gsm_poc/ui/app.py"


@pytest.fixture
def simulation_run(config):
    run = Run(config, "simulation-ui")
    result = {
        "schema_version": 2,
        "status": "ok",
        "source_kind": "synthetic",
        "evidence_level": "C",
        "calibration_status": "not_calibrated",
        "interval_status": "interval_unavailable",
        "scope": {
            "horizon_start": "2024-01-26T13:00:00+00:00",
            "horizon_end": "2024-01-26T15:00:00+00:00",
            "vehicles": 2,
        },
        "summary": {
            "created_requests": 5,
            "completed_trips": 2,
            "open_requests_end": 1,
            "mean_wait_seconds": 120.5,
            "wait_observed_requests": 2,
            "wait_censored_requests": 1,
            "idle_hours": 2.5,
            "canceled_requests": 1,
            "expired_requests": 1,
        },
        "wait_population": "pickups in this window, using original creation times",
        "earnings": {
            "summary": {
                "total_driver_pay": 22.0,
                "settled_completed_trips": 2,
                "pay_per_presence_hour": 5.5,
            },
            "currency": "SYNTHETIC_UNIT",
            "income_denominator": "all roster drivers, including zero-trip idle time",
        },
    }
    spec = {"compensation": {"contract": {"driver_fare_share": 1.0}}}
    with run.stage("simulate_marketplace", {}):
        paths = []
        for name, value in (
            ("simulation_result.json", result),
            ("simulation_spec.json", spec),
            ("end_snapshot.json", {"vehicles": [], "open_requests": []}),
        ):
            path = run.path / name
            write_json(path, value)
            paths.append(path)
        for name in ("requests", "driver_income"):
            path = run.path / f"{name}.csv"
            frame = (
                pd.DataFrame({"request_id": ["r1"], "state": ["completed"]})
                if name == "requests"
                else pd.DataFrame({"driver_id": ["d1", "d2"], "total_driver_pay": [22.0, 0.0]})
            )
            write_frame(path, frame)
            paths.append(path)
        run.outputs("simulate_marketplace", paths)
    run.complete()
    return run, result


def fixed_online_run(simulation_run):
    run, result = simulation_run
    result["schema_version"] = 3
    result["scope"].update(online_drivers=2, online_population_rule="fixed_roster")
    result["summary"].update(online_hours=4.0, online_drivers=2)
    result["offers"] = {
        "offered": 6,
        "accepted": 2,
        "rejected": 1,
        "timed_out": 1,
        "withdrawn": 1,
        "pending_start": 0,
        "pending_end": 1,
        "acceptance_rate": 0.5,
        "acceptance_denominator": 4,
        "acceptance_status": "ok",
        "acceptance_population": "resolved responses in this window, including carry-in offers",
        "accounting": (
            "pending_start + offered = accepted + rejected + timed_out + withdrawn + pending_end"
        ),
    }
    frame = pd.DataFrame(
        {
            "offer_id": [f"offer-{i}" for i in range(6)],
            "state": ["accepted", "accepted", "rejected", "timed_out", "withdrawn", "offered"],
        }
    )
    paths = []
    for extension in ("parquet", "csv"):
        path = run.path / f"driver_offers.{extension}"
        write_frame(path, frame)
        paths.append(path)
    write_json(run.path / "simulation_result.json", result)
    run.register(paths + [run.path / "simulation_result.json"])
    return run, result


def test_simulation_only_dashboard_displays_frozen_results_and_exports(simulation_run, monkeypatch):
    run, _ = simulation_run
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Completed trips"] == "2"
    assert metrics["Mean pickup wait (seconds)"] == "120.5"
    assert metrics["Gross driver pay"] == "22.00"
    assert any("not_calibrated" in item.value for item in app.caption)
    assert any("confidence intervals are unavailable" in item.value for item in app.warning)
    assert any("100% of displayed fare" in item.value for item in app.caption)
    assert any("Legacy fixed-supply" in item.value for item in app.caption)
    assert not any(item.label == "Inference method" for item in app.selectbox)
    assert len(app.get("download_button")) == 4
    next(item for item in app.selectbox if item.label == "Simulation data").select(
        "driver_income"
    ).run()
    assert not app.exception
    assert app.dataframe[0].value.total_driver_pay.tolist() == [22.0, 0.0]


def test_simulation_checksum_failure_is_visible_and_withholds_metrics(simulation_run, monkeypatch):
    run, _ = simulation_run
    (run.path / "requests.csv").write_text("tampered", encoding="utf-8")
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert any("checksum mismatch" in item.value for item in app.error)
    assert not app.metric
    assert not app.get("download_button")


def test_incomplete_simulation_is_not_selectable(simulation_run, monkeypatch):
    run, _ = simulation_run
    run.manifest["status"] = "running"
    run.save()
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert not app.selectbox
    assert not app.metric
    with pytest.raises(ValueError, match="not complete"):
        load_simulation(run.config.workspace, run.run_id)


def test_missing_wait_is_unavailable_not_zero(simulation_run, monkeypatch):
    run, result = simulation_run
    result["summary"]["mean_wait_seconds"] = None
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    metric = next(item for item in app.metric if item.label == "Mean pickup wait (seconds)")
    assert metric.value == "—"


def test_malformed_completed_result_is_reported(simulation_run, monkeypatch):
    run, result = simulation_run
    result["summary"].pop("completed_trips")
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert any("completed_trips" in item.value for item in app.error)
    assert not app.metric


def test_missing_registration_is_rejected(simulation_run):
    run, _ = simulation_run
    del run.manifest["artifacts"][f"runs/{run.run_id}/simulation_spec.json"]
    run.save()
    with pytest.raises(ValueError, match="not registered"):
        load_simulation(run.config.workspace, run.run_id)


def test_claimed_calibration_is_rejected(simulation_run):
    run, result = simulation_run
    result["calibration_status"] = "calibrated"
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    with pytest.raises(ValueError, match="calibration_status"):
        load_simulation(run.config.workspace, run.run_id)


def test_unregistered_driver_offers_are_rejected_for_v3(simulation_run):
    run, _ = fixed_online_run(simulation_run)
    del run.manifest["artifacts"][f"runs/{run.run_id}/driver_offers.parquet"]
    run.save()
    with pytest.raises(ValueError, match="driver-offer artifact"):
        load_simulation(run.config.workspace, run.run_id)


def test_fixed_online_dashboard_uses_declared_offer_denominator(simulation_run, monkeypatch):
    run, _ = fixed_online_run(simulation_run)
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Online drivers"] == "2"
    assert metrics["Offer acceptance"] == "50.0%"
    assert metrics["Withdrawn offers"] == metrics["Pending offers at end"] == "1"
    assert any("Acceptance denominator: 4" in item.value for item in app.caption)
    assert any("withdrawals and pending offers are excluded" in item.value for item in app.caption)
    assert any("4.00 online hours" in item.value for item in app.caption)
    data = next(item for item in app.selectbox if item.label == "Simulation data")
    data.select("driver_offers").run()
    assert not app.exception
    assert app.dataframe[0].value.state.tolist()[-1] == "offered"


def test_no_resolved_offer_is_unavailable_not_zero(simulation_run, monkeypatch):
    run, result = fixed_online_run(simulation_run)
    result["offers"].update(
        offered=1,
        accepted=0,
        rejected=0,
        timed_out=0,
        withdrawn=0,
        acceptance_rate=None,
        acceptance_denominator=0,
        acceptance_status="unavailable_no_responses",
    )
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    monkeypatch.chdir(run.config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert next(item for item in app.metric if item.label == "Offer acceptance").value == "—"
    assert any("Acceptance denominator: 0" in item.value for item in app.caption)


def test_inconsistent_offer_denominator_is_rejected(simulation_run):
    run, result = fixed_online_run(simulation_run)
    result["offers"]["acceptance_denominator"] = 6
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    with pytest.raises(ValueError, match="denominator"):
        load_simulation(run.config.workspace, run.run_id)


def test_simulation_does_not_enter_choice_selector(simulation_run, monkeypatch):
    run, _ = fixed_online_run(simulation_run)
    config = dataclasses.replace(
        run.config,
        model=dataclasses.replace(
            run.config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    Pipeline(config, "choice-ui").run_all(include_evaluation=False)
    monkeypatch.chdir(config.workspace)
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 4
    assert next(item for item in app.selectbox if item.label == "Run ID").options == ["choice-ui"]
    assert next(item for item in app.selectbox if item.label == "Simulation run ID").options == [
        run.run_id
    ]
    assert (
        next(item for item in app.selectbox if item.label == "Inference method").value == "analytic"
    )


def test_explicit_simulation_opens_without_reading_corrupt_choice(simulation_run, monkeypatch):
    import sys

    run, _ = fixed_online_run(simulation_run)
    choice = Pipeline(run.config, "corrupt-choice")
    with choice.run.stage("fit", {"fixture": True}):
        path = choice.run.path / "fixture.json"
        write_json(path, {"model": "fixture"})
        choice.run.outputs("fit", [path])
    choice.run.complete()
    path.write_text("corrupt", encoding="utf-8")
    monkeypatch.chdir(run.config.workspace)
    monkeypatch.setattr(sys, "argv", ["app.py", "--run-id", run.run_id])
    app = AppTest.from_file(str(APP_PATH)).run(timeout=30)
    assert not app.exception
    assert not app.error
    assert next(item for item in app.selectbox if item.label == "Simulation run ID").value == (
        run.run_id
    )
    assert not any(item.label in ("DGP", "Run ID") for item in app.selectbox)
