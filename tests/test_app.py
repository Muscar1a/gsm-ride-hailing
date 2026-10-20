import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.ui.app import create_app


@pytest.fixture
def model_run(config):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    pipeline = Pipeline(config, "app-test")
    pipeline.run_all(include_evaluation=False)
    return pipeline


def test_dashboard_changes_scenario_and_withholds_unsupported_price(model_run):
    client = TestClient(create_app(model_run.config.workspace))
    request = {"run_id": model_run.run.run_id}
    result = client.post("/api/scenario", json=request).json()
    assert "88–89%" in result["coverage_warning"]
    assert result["inference_method"] == "analytic"
    assert result["after_expected_bookings"] > 0
    result = client.post("/api/scenario", json=request | {"inference_method": "bootstrap"}).json()
    assert "day-bootstrap" in result["interval_kind"]
    result = client.post("/api/scenario", json=request | {"delta_x": 0}).json()
    assert result["delta_expected_bookings"] == 0
    result = client.post("/api/scenario", json=request | {"delta_x": 0.2}).json()
    assert result["status"] == "out_of_support"
    assert "after_expected_bookings" not in result
    assert any("outside the designed" in reason for reason in result["reasons"])


def test_dashboard_saves_selected_zone_scope_in_export(model_run):
    client = TestClient(create_app(model_run.config.workspace))
    response = client.post("/api/scenario", json={"run_id": model_run.run.run_id, "zone": 161})
    assert response.status_code == 200
    assert response.json()["target_context_set"] == "zone_161"
    assert (
        client.post("/api/scenario", json={"run_id": model_run.run.run_id, "zone": 999}).status_code
        == 409
    )


def test_dashboard_uses_source_config_for_frozen_choice_package(model_run):
    source_config = model_run.config
    config = dataclasses.replace(
        source_config,
        simulation=dataclasses.replace(source_config.simulation, dgp="COLLINEAR_PRICE", seed=99),
        model=dataclasses.replace(source_config.model, min_price_cell_count=100_000),
        evaluation=dataclasses.replace(source_config.evaluation, interval_level=0.80),
        scenario=dataclasses.replace(source_config.scenario, n_sessions=1234),
    )
    package = Pipeline(config, "app-choice-package")
    package.freeze_choice(model_run.run.run_id)
    package.run.complete()
    client = TestClient(create_app(config.workspace))
    records = client.get("/api/runs").json()["runs"]
    assert {record["dgp"] for record in records} == {"RCT_SYN"}
    assert {record["seed"] for record in records} == {source_config.simulation.seed}
    result = client.post("/api/scenario", json={"run_id": package.run.run_id}).json()
    original = client.post("/api/scenario", json={"run_id": model_run.run.run_id}).json()
    assert result["interval_level"] == source_config.evaluation.interval_level
    assert result["support_status"] == original["support_status"]
    assert result["probabilities"] == original["probabilities"]
    data = client.get(f"/api/runs/{package.run.run_id}").json()
    assert data["manifest"]["choice_source"]["source_config"] == json.loads(
        json.dumps(source_config.as_dict())
    )


def test_web_auth_origin_validation_and_static_assets(tmp_path):
    client = TestClient(create_app(tmp_path, token="test-secret"))
    assert client.get("/").status_code == 200
    assert client.get("/assets/dashboard.js").status_code == 200
    assert "streamlit" not in client.get("/").text.lower()
    assert client.get("/api/runs").status_code == 401
    headers = {"Authorization": "Bearer test-secret"}
    assert client.get("/api/runs", headers=headers).status_code == 200
    assert (
        client.post(
            "/api/jobs",
            json={"action": "train"},
            headers=headers | {"Origin": "https://other.example"},
        ).status_code
        == 403
    )
    assert client.get("/api/runs", headers=headers | {"Host": "evil.example"}).status_code == 400
    assert (
        client.post(
            "/api/scenario", json={"run_id": "../outside", "delta_x": 100}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/scenario",
            content='{"run_id":"x","delta_x":NaN}',
            headers=headers | {"Content-Type": "application/json"},
        ).status_code
        == 422
    )


def test_csv_upload_preserves_source_and_reports_missingness(tmp_path):
    client = TestClient(create_app(tmp_path))
    source = b"zone_id,trips\n161,3\n162,\n"
    response = client.post("/api/uploads", content=source)
    assert response.status_code == 201
    result = response.json()
    assert result["total_rows"] == 2
    assert result["missing_values"]["trips"] == 1
    assert result["rows"][1]["trips"] is None
    assert result["source_kind"] == "user_uploaded_unvalidated"
    assert (
        tmp_path / ".cache/web/uploads" / result["upload_id"] / "data.csv"
    ).read_bytes() == source
    assert client.post("/api/uploads", content=b"a,a\n1,2\n").status_code == 409
    assert client.post("/api/uploads", content=b"a\ninf\n").status_code == 409
    assert client.post("/api/uploads?kind=requests", content=source).status_code == 409
    assert client.post("/api/uploads", content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413


def test_table_pagination_filters_and_download_are_verified(model_run):
    client = TestClient(create_app(model_run.config.workspace))
    run_id = model_run.run.run_id
    params = {
        "artifact": f"runs/{run_id}/method_metrics.csv",
        "limit": 2,
        "offset": 1,
        "estimator": "adjusted_ols",
    }
    response = client.get(f"/api/runs/{run_id}/table", params=params)
    assert response.status_code == 200
    assert len(response.json()["rows"]) == 2
    assert response.json()["total_rows"] == 4
    filtered = client.get(
        f"/api/runs/{run_id}/table",
        params=params | {"download": True},
    )
    assert filtered.status_code == 200
    assert len(filtered.text.splitlines()) == 5
    assert "adjusted_ols" in filtered.text
    assert (
        client.get(
            f"/api/runs/{run_id}/download", params={"artifact": "../pyproject.toml"}
        ).status_code
        == 409
    )
    params = {"artifact": f"runs/{run_id}/models/adjusted_ols/model_bundle.joblib"}
    assert client.get(f"/api/runs/{run_id}/download", params=params).status_code == 409
    manifest = model_run.run.manifest
    path = model_run.run.path / "method_metrics.csv"
    expected = path.read_bytes()
    params = {"artifact": f"runs/{run_id}/method_metrics.csv"}
    assert client.get(f"/api/runs/{run_id}/download", params=params).content == expected
    path.write_text("corrupt", encoding="utf-8")
    assert client.get(f"/api/runs/{run_id}/table", params=params).status_code == 409
    assert json.loads(model_run.run.manifest_path.read_text())["artifacts"] == manifest["artifacts"]
