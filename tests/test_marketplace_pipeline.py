from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from gsm_poc.cli import main
from gsm_poc.core.artifacts import (
    completed_run,
    fingerprint,
    read_json,
    sha256_file,
    write_frame,
    write_json,
)
from gsm_poc.pipeline.marketplace import evaluate_marketplace_run
from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.simulation.demand import validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def demand_sources(config):
    snapshot = validate_snapshot(read_json(ROOT / "configs/week3_snapshot.json"), config)
    sources = {}
    for label, delta in (("baseline", 0.0), ("target", 0.1)):
        pipeline = Pipeline(config, f"evaluation-{label}")
        policy = {
            "baseline_multiplier_x": 1.0,
            "baseline_multiplier_y": 1.0,
            "delta_price_x": delta,
            "delta_price_y": 0.0,
        }
        spec = {
            "schema_version": 1,
            "model_version": "fixture-choice",
            "source_version": "fixture-source",
            "snapshot_version": snapshot["snapshot_version"],
            "policy": policy,
            "policy_version": fingerprint(policy),
            "units": {"request_rate": "requests/hour"},
        }
        version = fingerprint(spec)
        rows = []
        for zone in snapshot["zone_ids"]:
            for service, rate in (("X", 2.0 * (1 - delta)), ("Y", 1.0)):
                rows.append(
                    {
                        "zone_id": zone,
                        "service_id": service,
                        "block_start": pd.Timestamp(snapshot["horizon_start"]),
                        "block_end": pd.Timestamp(snapshot["horizon_end"]),
                        "block_hours": 2.0,
                        "request_rate": rate,
                        "expected_bookings": rate * 2,
                        "source_block_id": f"block-{zone}",
                        "status": "ok",
                        "support_status": "ok",
                        "demand_plan_version": version,
                        "snapshot_id": snapshot["snapshot_id"],
                        "model_version": spec["model_version"],
                        "source_version": spec["source_version"],
                        "policy_version": spec["policy_version"],
                        "source_kind": "synthetic",
                        "evidence_level": "C",
                        "demand_mode": snapshot["demand_mode"],
                        "exposure_mode": snapshot["exposure_mode"],
                    }
                )
        result = {
            "schema_version": 1,
            "status": "ok",
            "usable_for_simulation": True,
            "demand_plan_version": version,
            "source_kind": "synthetic",
            "summary": {"expected_bookings": sum(row["expected_bookings"] for row in rows)},
        }
        with pipeline.run.stage("prepare_demand", {"fixture": True}):
            paths = []
            path = pipeline.run.path / "demand_plan.parquet"
            write_frame(path, pd.DataFrame(rows))
            paths.append(path)
            for name, value in (
                ("demand_result.json", result),
                ("demand_spec.json", spec),
                ("baseline_snapshot.json", snapshot),
            ):
                path = pipeline.run.path / name
                write_json(path, value)
                paths.append(path)
            pipeline.run.manifest["demand_source"] = {"source_config": config.as_dict()}
            pipeline.run.outputs("prepare_demand", paths)
        pipeline.run.complete()
        sources[label] = pipeline
    return sources


def test_cli_evaluation_freezes_inputs_and_reuses_only_verified_outputs(
    config, demand_sources, monkeypatch, capsys
):
    protocol = read_json(ROOT / "configs/week3_poc_pilot.json") | {"n_seeds": 1}
    protocol_path = config.workspace / "pilot.json"
    write_json(protocol_path, protocol)
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: config)
    monkeypatch.setattr("joblib.load", lambda *_: pytest.fail("No choice refit/bootstrap read"))
    hashes = {
        name: sha256_file(source.run.manifest_path) for name, source in demand_sources.items()
    }
    args = [
        "evaluate-marketplace",
        "--baseline-demand-run-id",
        demand_sources["baseline"].run.run_id,
        "--target-demand-run-id",
        demand_sources["target"].run.run_id,
        "--rules",
        str(ROOT / "configs/week3_poc.json"),
        "--compensation",
        str(ROOT / "configs/week3_compensation.json"),
        "--protocol",
        str(protocol_path),
        "--run-id",
        "marketplace-evaluation",
    ]
    assert main(args) == 0
    manifest = completed_run(config.workspace, "marketplace-evaluation")
    output = config.workspace / "runs/marketplace-evaluation"
    result = read_json(output / "marketplace_evaluation.json")
    assert result["status"] == "development_only"
    assert result["execution_status"] == "completed"
    assert result["environment"] == manifest["environment"]
    for label, source in demand_sources.items():
        assert sha256_file(source.run.manifest_path) == hashes[label]
        assert (output / f"evaluation_inputs/{label}/demand_plan.parquet").read_bytes() == (
            source.run.path / "demand_plan.parquet"
        ).read_bytes()
    assert (output / "source_snapshot/src/gsm_poc/simulation/evaluation.py").is_file()
    assert (output / "marketplace_seed_records.csv").is_file()
    capsys.readouterr()
    assert main(args) == 0
    assert "reuse verified artifacts" in capsys.readouterr().out
    (output / "marketplace_seed_records.csv").write_text("corrupt", encoding="utf-8")
    assert main(args) == 0
    assert not pd.read_csv(output / "marketplace_seed_records.csv").empty


@pytest.mark.parametrize("failure", ["checksum", "support", "unregistered", "same_run"])
def test_evaluation_rejects_ineligible_source_and_preserves_failure(
    config, demand_sources, failure
):
    baseline = demand_sources["baseline"]
    if failure == "checksum":
        (baseline.run.path / "demand_plan.parquet").write_bytes(b"corrupt")
    elif failure == "support":
        result_path = baseline.run.path / "demand_result.json"
        write_json(result_path, read_json(result_path) | {"usable_for_simulation": False})
        baseline.run.register([result_path])
    elif failure == "unregistered":
        baseline.run.manifest["artifacts"].pop(f"runs/{baseline.run.run_id}/demand_plan.parquet")
        baseline.run.save()
    output = baseline if failure == "same_run" else Pipeline(config, f"bad-{failure}")
    with pytest.raises(ValueError):
        evaluate_marketplace_run(
            output.run,
            baseline.run.run_id,
            demand_sources["target"].run.run_id,
            ROOT / "configs/week3_poc.json",
            ROOT / "configs/week3_compensation.json",
            ROOT / "configs/week3_poc_pilot.json",
        )
    if failure != "same_run":
        assert (
            read_json(output.run.manifest_path)["stages"]["evaluate_marketplace"]["status"]
            == "failed"
        )


def test_cli_v3_exports_offers_and_frozen_pending_continuation(
    config, demand_sources, monkeypatch, capsys
):
    rules = read_json(ROOT / "configs/week3_poc.json") | {"acceptance_probability": 1.0}
    rules_path = config.workspace / "offers.json"
    write_json(rules_path, rules)
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: config)
    common = [
        "simulate-marketplace",
        "--demand-run-id",
        demand_sources["baseline"].run.run_id,
        "--rules",
        str(rules_path),
        "--compensation",
        str(ROOT / "configs/week3_compensation.json"),
    ]
    first = common + [
        "--requests",
        str(ROOT / "configs/week3_requests.csv"),
        "--window-end",
        "2024-01-26T08:00:02-05:00",
        "--run-id",
        "offers-first",
    ]
    assert main(first) == 0
    parent = config.workspace / "runs/offers-first"
    original = sha256_file(parent / "end_snapshot.json")
    assert len(pd.read_parquet(parent / "driver_offers.parquet")) == 2
    assert set(pd.read_parquet(parent / "driver_offers.parquet").state) == {"offered"}
    second = common + [
        "--window-start",
        "2024-01-26T08:00:02-05:00",
        "--carry-in-run-id",
        "offers-first",
        "--run-id",
        "offers-second",
    ]
    assert main(second) == 0
    output = config.workspace / "runs/offers-second"
    assert (output / "simulation_inputs/carry_in.json").read_bytes() == (
        parent / "end_snapshot.json"
    ).read_bytes()
    assert sha256_file(parent / "end_snapshot.json") == original
    manifest = completed_run(config.workspace, "offers-second")
    for name in ("driver_offers", "offer_events", "earnings_ledger"):
        assert f"runs/offers-second/{name}.parquet" in manifest["artifacts"]
    assert read_json(output / "simulation_result.json")["offers"]["accepted"] == 2
    assert pd.read_csv(output / "earnings_ledger.csv").driver_pay.sum() == 2.0
    capsys.readouterr()
    assert main(second) == 0
    assert "reuse verified artifacts" in capsys.readouterr().out


def test_legacy_rules_window_reuses_its_normalized_checkpoint(config, demand_sources, capsys):
    rules = read_json(ROOT / "configs/week3_simulation.json")
    rules["schema_version"] = 1
    rules.pop("max_wait_seconds")
    rules.pop("cancel_policy")
    path = config.workspace / "legacy-rules.json"
    write_json(path, rules)
    pipeline = Pipeline(config, "legacy-window")
    args = (demand_sources["baseline"].run.run_id, path, ROOT / "configs/week3_requests.csv")
    first = pipeline.simulate_marketplace(*args, window_end="2024-01-26T08:04:00-05:00")
    pipeline.run.complete()
    assert first["schema_version"] == 2
    capsys.readouterr()
    second = Pipeline(config, "legacy-window").simulate_marketplace(
        *args, window_end="2024-01-26T08:04:00-05:00"
    )
    assert first == second
    assert "reuse verified artifacts" in capsys.readouterr().out
