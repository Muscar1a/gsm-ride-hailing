import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsm_poc.core.artifacts import completed_run
from gsm_poc.ui.app import create_app
from gsm_poc.ui.jobs import JobManager

ROOT = Path(__file__).parents[1]


def test_web_jobs_train_prepare_and_simulate_in_real_worker(tmp_path):
    directory = tmp_path / "configs"
    directory.mkdir()
    for name in ("week3_snapshot.json", "week3_poc.json", "week3_compensation.json"):
        shutil.copyfile(ROOT / "configs" / name, directory / name)
    (directory / "week4.toml").write_text(
        "[source]\nzones = [161, 162]\n[simulation]\nslot_minutes = 120\n"
        "[model]\nmin_price_cell_count = 1\nn_trees = 5\n",
        encoding="utf-8",
    )
    with TestClient(create_app(tmp_path)) as client:

        def finish_job(request):
            response = client.post("/api/jobs", json=request)
            assert response.status_code == 202, response.text
            record = response.json()
            client.app.state.jobs.thread.join(timeout=60)
            assert not client.app.state.jobs.thread.is_alive()
            result = client.get(f"/api/jobs/{record['job_id']}").json()
            assert result["status"] == "succeeded", result
            assert completed_run(tmp_path, record["run_id"])["status"] == "succeeded"
            return record["run_id"]

        model_id = finish_job({"action": "train", "bootstrap_draws": 0})
        response = client.post("/api/scenario", json={"run_id": model_id, "delta_x": 0})
        assert response.status_code == 200
        assert response.json()["delta_expected_bookings"] == 0
        demand_id = finish_job({"action": "prepare_demand", "source_run_id": model_id})
        csv = (
            "request_id,created_at,origin_zone_id,destination_zone_id,service_id\n"
            "web-r1,2024-01-26T13:00:00+00:00,161,162,X\n"
        )
        upload = client.post("/api/uploads?kind=requests", content=csv)
        assert upload.status_code == 201
        simulation_id = finish_job(
            {
                "action": "simulate",
                "source_run_id": demand_id,
                "upload_id": upload.json()["upload_id"],
            }
        )
        result = client.get(f"/api/runs/{simulation_id}").json()["simulation"]["result"]
        assert result["summary"]["created_requests"] == 1
        assert result["scope"]["online_drivers"] == 2
        assert result["calibration_status"] == "not_calibrated"
        rejected = client.post("/api/jobs", json={"action": "simulate", "source_run_id": model_id})
        assert rejected.status_code == 409


def test_worker_is_bounded_and_failures_do_not_look_successful(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class StalledProcess:
        def __init__(self, command, **kwargs):
            assert command[1:3] == ["-m", "gsm_poc.ui.worker"]
            self.killed = False

        def wait(self, timeout):
            if self.killed:
                return -1
            entered.set()
            assert release.wait(timeout=5)
            raise subprocess.TimeoutExpired("worker", timeout)

        def kill(self):
            self.killed = True

    monkeypatch.setattr("gsm_poc.ui.jobs.subprocess.Popen", StalledProcess)
    manager = JobManager(tmp_path, timeout_seconds=1)
    record = manager.start({"request": {"action": "train"}})
    assert entered.wait(timeout=5)
    with pytest.raises(RuntimeError, match="already running"):
        manager.start({"request": {"action": "train"}})
    release.set()
    manager.thread.join(timeout=5)
    result = manager.read(record["job_id"])
    assert result["status"] == "failed"
    assert "exceeded 1 seconds" in result["error"]
    assert not (tmp_path / "runs" / record["run_id"] / "manifest.json").exists()
