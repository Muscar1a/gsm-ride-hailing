from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gsm_poc.core.artifacts import Run, write_frame, write_json
from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.ui.app import create_app
from gsm_poc.ui.results import load_simulation


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
    client = TestClient(create_app(run.config.workspace))
    response = client.get(f"/api/runs/{run.run_id}")
    assert response.status_code == 200
    data = response.json()
    result = data["simulation"]["result"]
    assert result["summary"]["completed_trips"] == 2
    assert result["summary"]["mean_wait_seconds"] == 120.5
    assert result["earnings"]["summary"]["total_driver_pay"] == 22.0
    assert result["calibration_status"] == "not_calibrated"
    assert result["interval_status"] == "interval_unavailable"
    assert data["simulation"]["spec"]["compensation"]["contract"]["driver_fare_share"] == 1
    table = client.get(
        f"/api/runs/{run.run_id}/table", params={"artifact": f"runs/{run.run_id}/driver_income.csv"}
    ).json()
    assert [row["total_driver_pay"] for row in table["rows"]] == [22.0, 0.0]
    for name in (
        "requests.csv",
        "simulation_result.json",
        "simulation_spec.json",
        "end_snapshot.json",
    ):
        response = client.get(
            f"/api/runs/{run.run_id}/download", params={"artifact": f"runs/{run.run_id}/{name}"}
        )
        assert response.status_code == 200
        assert response.content == (run.path / name).read_bytes()


def test_simulation_checksum_failure_is_visible_and_withholds_metrics(simulation_run, monkeypatch):
    run, _ = simulation_run
    (run.path / "requests.csv").write_text("tampered", encoding="utf-8")
    client = TestClient(create_app(run.config.workspace))
    response = client.get(f"/api/runs/{run.run_id}")
    assert response.status_code == 409
    assert "checksum mismatch" in response.json()["detail"]
    assert "simulation" not in response.json()
    assert (
        client.get(
            f"/api/runs/{run.run_id}/download",
            params={"artifact": f"runs/{run.run_id}/requests.csv"},
        ).status_code
        == 409
    )


def test_incomplete_simulation_is_not_selectable(simulation_run, monkeypatch):
    run, _ = simulation_run
    run.manifest["status"] = "running"
    run.save()
    client = TestClient(create_app(run.config.workspace))
    assert client.get("/api/runs").json()["runs"] == []
    assert client.get(f"/api/runs/{run.run_id}").status_code == 409
    with pytest.raises(ValueError, match="not complete"):
        load_simulation(run.config.workspace, run.run_id)


def test_missing_wait_is_unavailable_not_zero(simulation_run, monkeypatch):
    run, result = simulation_run
    result["summary"]["mean_wait_seconds"] = None
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    response = TestClient(create_app(run.config.workspace)).get(f"/api/runs/{run.run_id}")
    assert response.status_code == 200
    assert response.json()["simulation"]["result"]["summary"]["mean_wait_seconds"] is None


def test_malformed_completed_result_is_reported(simulation_run, monkeypatch):
    run, result = simulation_run
    result["summary"].pop("completed_trips")
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    response = TestClient(create_app(run.config.workspace)).get(f"/api/runs/{run.run_id}")
    assert response.status_code == 409
    assert "completed_trips" in response.json()["detail"]


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
    client = TestClient(create_app(run.config.workspace))
    result = client.get(f"/api/runs/{run.run_id}").json()["simulation"]["result"]
    assert result["scope"]["online_drivers"] == 2
    assert result["offers"]["acceptance_rate"] == 0.5
    assert result["offers"]["withdrawn"] == result["offers"]["pending_end"] == 1
    assert result["offers"]["acceptance_denominator"] == 4
    assert result["summary"]["online_hours"] == 4.0
    table = client.get(
        f"/api/runs/{run.run_id}/table", params={"artifact": f"runs/{run.run_id}/driver_offers.csv"}
    ).json()
    assert table["rows"][-1]["state"] == "offered"


def test_no_resolved_offer_is_unavailable_not_zero(simulation_run, monkeypatch):
    run, result = fixed_online_run(simulation_run)
    result["offers"].update(
        offered=1,
        accepted=0,
        rejected=0,
        timed_out=0,
        withdrawn=0,
        pending_start=0,
        pending_end=1,
        acceptance_rate=None,
        acceptance_denominator=0,
        acceptance_status="unavailable_no_responses",
    )
    write_json(run.path / "simulation_result.json", result)
    run.register([run.path / "simulation_result.json"])
    response = TestClient(create_app(run.config.workspace)).get(f"/api/runs/{run.run_id}")
    assert response.status_code == 200
    assert response.json()["simulation"]["result"]["offers"]["acceptance_rate"] is None


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
    client = TestClient(create_app(config.workspace))
    records = client.get("/api/runs").json()["runs"]
    models = [row["run_id"] for row in records if "fit" in row["stages"]]
    simulations = [row["run_id"] for row in records if "simulate_marketplace" in row["stages"]]
    assert models == ["choice-ui"]
    assert simulations == [run.run_id]


def test_explicit_simulation_opens_without_reading_corrupt_choice(simulation_run, monkeypatch):
    run, _ = fixed_online_run(simulation_run)
    choice = Pipeline(run.config, "corrupt-choice")
    with choice.run.stage("fit", {"fixture": True}):
        path = choice.run.path / "fixture.json"
        write_json(path, {"model": "fixture"})
        choice.run.outputs("fit", [path])
    choice.run.complete()
    path.write_text("corrupt", encoding="utf-8")
    client = TestClient(create_app(run.config.workspace, run.run_id))
    assert client.get("/api/runs").json()["initial_run_id"] == run.run_id
    assert client.get(f"/api/runs/{run.run_id}").status_code == 200
