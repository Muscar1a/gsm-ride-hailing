from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gsm_poc.causal.experiments import plan_experiment, reconcile_experiment
from gsm_poc.causal.scenario import ScenarioRequest
from gsm_poc.cli import main
from gsm_poc.core.artifacts import completed_run, read_json, sha256_file, write_json
from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.pipeline.policy import (
    compare_policies_run,
    evaluate_policies_run,
    export_handoff_run,
    plan_experiment_run,
    reconcile_experiment_run,
)
from gsm_poc.simulation.policies import (
    UNITS,
    decide_policies,
    evaluate_frozen_decision,
    summarize_policies,
    validate_policy_spec,
)
from gsm_poc.ui.app import create_app

ROOT = Path(__file__).parents[1]


@pytest.fixture
def policy_spec():
    spec = read_json(ROOT / "configs/week4_policies.json")
    return spec | {
        "candidates": spec["candidates"][:2],
        "n_seeds": 2,
        "bootstrap_draws": 0,
        "sensitivities": [],
    }


@pytest.fixture
def policy_source(config):
    config = dataclasses.replace(
        config,
        simulation=dataclasses.replace(config.simulation, slot_minutes=30),
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    source = Pipeline(config, "week45-choice")
    source.generate()
    source.fit()
    source.method_evaluation()
    source.scenario()
    source.run.complete()
    demand = Pipeline(config, "week45-demand")
    result = demand.prepare_demand(
        source.run.run_id, ROOT / "configs/week3_snapshot.json", ScenarioRequest(delta_price_x=0.0)
    )
    assert result["usable_for_simulation"]
    demand.run.complete()
    return source, demand


@pytest.mark.parametrize(
    "change",
    [
        {"n_seeds": True},
        {"max_seconds": float("nan")},
        {"bootstrap_draws": -1},
        {"unknown": 1},
        {"source_kind": "gsm"},
        {"criterion": {"metric": "profit", "direction": "maximize", "minimum_gain": 0}},
        {
            "costs": {
                "currency": "VND",
                "per_completed_trip": 0,
                "per_online_hour": 0,
                "per_horizon": 0,
            }
        },
    ],
)
def test_policy_contract_rejects_invalid_inputs(policy_spec, change):
    with pytest.raises(ValueError):
        validate_policy_spec(policy_spec | change)


def model_records(spec):
    rows = []
    for kind, count in (("point", 1), ("bootstrap", spec["bootstrap_draws"])):
        for draw_id in range(count):
            for policy_id, value in (("baseline", 10.0), ("x-plus5", 15.0 + draw_id / 10)):
                for seed in range(2):
                    rows.append(
                        {
                            "kind": kind,
                            "draw_id": draw_id,
                            "policy_id": policy_id,
                            "sensitivity_id": "declared_rules",
                            "seed": seed,
                            "status": "succeeded",
                            "completed_trips": value,
                            "mean_wait_seconds": 100.0,
                            "pay_per_presence_hour": 2.0,
                        }
                    )
    return pd.DataFrame(rows)


def test_model_intervals_propagate_fit_variation_and_do_not_hide_failed_draws(policy_spec):
    spec = policy_spec | {"bootstrap_draws": 20}
    records = model_records(spec)
    summary = summarize_policies(records, spec)
    row = next(
        r for r in summary if r["policy_id"] == "x-plus5" and r["metric"] == "completed_trips"
    )
    assert row["mc_delta_lower"] == row["mc_delta_upper"] == 5.0
    assert row["model_delta_upper"] > row["model_delta_lower"] >= 5.0
    assert row["valid_model_draws"] == 20
    records.loc[
        records.kind.eq("bootstrap") & records.draw_id.eq(0) & records.policy_id.eq("x-plus5"),
        "status",
    ] = "failed"
    row = next(
        r
        for r in summarize_policies(records, spec)
        if r["policy_id"] == "x-plus5" and r["metric"] == "completed_trips"
    )
    assert row["valid_model_draws"] == 19
    assert row["model_delta_lower"] is None
    assert row["interval_status"] == "unavailable"


def test_bootstrap_missing_costs_remain_unavailable_without_failing(policy_spec):
    spec = policy_spec | {"bootstrap_draws": 20}
    records = model_records(spec)
    records["conditional_surplus"] = None
    summary = summarize_policies(records, spec)
    monetary = [r for r in summary if r["metric"] == "conditional_surplus"]
    assert all(r["valid_model_draws"] == 0 for r in monetary)
    assert all(r["target_mean"] is None and r["model_delta_lower"] is None for r in monetary)


def test_guardrail_violation_blocks_better_objective(policy_spec):
    spec = policy_spec | {"bootstrap_draws": 20}
    records = model_records(spec)
    records.loc[records.policy_id.eq("x-plus5"), "mean_wait_seconds"] = 400.0
    decisions = decide_policies(summarize_policies(records, spec), spec)
    target = next(r for r in decisions["decisions"] if r["policy_id"] == "x-plus5")
    assert target["status"] == "not_recommended"
    assert any("Guardrail" in reason for reason in target["reasons"])


def test_independent_reference_reports_regret_without_changing_the_selected_policy(policy_spec):
    summary = summarize_policies(model_records(policy_spec), policy_spec)
    result = evaluate_frozen_decision(summary, policy_spec, "baseline")
    assert result["reference_best_policy_id"] == "x-plus5"
    assert result["frozen_policy_id"] == "baseline"
    assert result["regret"] == 5.0
    assert result["reselection"] is False
    target_wait = next(
        r for r in summary if r["policy_id"] == "x-plus5" and r["metric"] == "mean_wait_seconds"
    )
    target_wait["target_mean"] = 400.0
    result = evaluate_frozen_decision(summary, policy_spec, "x-plus5")
    assert result["frozen_policy_guardrails_passed"] is False
    assert result["reference_best_policy_id"] == "baseline"
    assert result["regret"] is None


def test_end_to_end_policy_evaluation_experiment_and_verified_handoff(
    policy_source,
    policy_spec,
    monkeypatch,
    capsys,
):
    source, demand = policy_source
    config = source.config
    before = sha256_file(source.run.manifest_path), sha256_file(demand.run.manifest_path)
    spec_path = config.workspace / "policy.json"
    write_json(spec_path, policy_spec)
    monkeypatch.setattr("gsm_poc.cli.Config.load", lambda _: config)
    args = [
        "compare-policies",
        "--demand-run-id",
        demand.run.run_id,
        "--rules",
        str(ROOT / "configs/week3_poc.json"),
        "--compensation",
        str(ROOT / "configs/week3_compensation.json"),
        "--spec",
        str(spec_path),
        "--run-id",
        "week45-comparison",
    ]
    assert main(args) == 0
    output = config.workspace / "runs/week45-comparison"
    comparison = read_json(output / "policy_comparison.json")
    assert comparison["failed_trajectories"] == 0
    assert comparison["economics"]["status"] == "not_evaluated_missing_costs"
    baseline = [r for r in comparison["summary"] if r["policy_id"] == "baseline"]
    assert all(r["delta_mean"] == 0 for r in baseline if r["delta_mean"] is not None)
    capsys.readouterr()
    assert main(args) == 0
    assert "reuse verified artifacts" in capsys.readouterr().out
    assert before == (sha256_file(source.run.manifest_path), sha256_file(demand.run.manifest_path))

    evaluation_spec = policy_spec | {"seed_start": 110001}
    evaluation_path = config.workspace / "assessment.json"
    write_json(evaluation_path, evaluation_spec)
    evaluation = Pipeline(config, "week45-assessment")
    result = evaluate_policies_run(
        evaluation.run, "week45-comparison", source.run.run_id, evaluation_path
    )
    assert result["failed_trajectories"] == 0
    assert result["reselection"] is False
    assert result["frozen_selection"] == comparison["selected_policy_id"]
    evaluation.run.complete()

    experiment_spec = read_json(ROOT / "configs/week5_experiment.json")
    experiment_path = config.workspace / "experiment.json"
    write_json(experiment_path, experiment_spec)
    experiment = Pipeline(config, "week45-experiment")
    plan = plan_experiment_run(experiment.run, "week45-comparison", experiment_path)
    assert plan["power"]["status"] == "unavailable_missing_variance"
    experiment.run.complete()
    schedule = pd.read_csv(experiment.run.path / "experiment_schedule.csv")
    observations = outcome_fixture(plan, schedule)
    observation_path = config.workspace / "observations.csv"
    observations.to_csv(observation_path, index=False)
    reconciliation = Pipeline(config, "week45-reconciliation")
    reconciled = reconcile_experiment_run(
        reconciliation.run, experiment.run.run_id, observation_path
    )
    assert reconciled["aa_zero_in_interval"] is True
    assert reconciled["observed_effect"] == 0
    reconciliation.run.complete()

    handoff = Pipeline(config, "week45-handoff")
    result = export_handoff_run(handoff.run, [evaluation.run.run_id, reconciliation.run.run_id])
    handoff.run.complete()
    completed_run(config.workspace, handoff.run.run_id)
    with zipfile.ZipFile(handoff.run.path / "handoff.zip") as archive:
        inventory = json.loads(archive.read("handoff_inventory.json"))
        assert "src/gsm_poc/ui/static/index.html" in inventory["files"]
        assert "src/gsm_poc/ui/static/dashboard.js" in inventory["files"]
        assert f"runs/{source.run.run_id}/manifest.json" in inventory["files"]
        assert any(name.endswith("observed/choice_block.parquet") for name in inventory["files"])
        for name, expected in inventory["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
    assert result["archive_sha256"] == sha256_file(handoff.run.path / "handoff.zip")
    client = TestClient(create_app(config.workspace, "week45-comparison"))
    response = client.get("/api/runs/week45-comparison")
    assert response.status_code == 200
    table = client.get(
        "/api/runs/week45-comparison/table",
        params={"artifact": "runs/week45-comparison/policy_summary.csv"},
    )
    assert table.status_code == 200
    assert table.json()["total_rows"] > 0


def outcome_fixture(plan, schedule, difference=0.0):
    return pd.DataFrame(
        {
            "block_id": schedule.block_id,
            "applied_policy_id": schedule.policy_id,
            "metric": plan["spec"]["metric"],
            "unit": UNITS[plan["spec"]["metric"]],
            "value": np.where(schedule.arm.eq("treatment"), 10.0 + difference, 10.0),
            "source_kind": "synthetic",
        }
    )


@pytest.fixture
def frozen_forecast(policy_spec):
    spec = policy_spec | {"bootstrap_draws": 20}
    summary = summarize_policies(model_records(spec), spec)
    return {
        "summary": summary,
        **decide_policies(summary, spec),
        "failed_trajectories": 0,
        "spec_version": "frozen",
        "scope": {"horizon_minutes": 120, "zone_ids": [161, 162], "roster_size": 2},
    }


def test_switchback_power_balance_and_frozen_prediction(frozen_forecast):
    spec = read_json(ROOT / "configs/week5_experiment.json") | {
        "mode": "AB",
        "paired_difference_sd": 2.0,
        "minimum_effect": 1.0,
    }
    plan, schedule = plan_experiment(spec, frozen_forecast)
    assert plan["power"]["required_independent_pairs"] == 32
    assert plan["power"]["sufficient_under_assumptions"] is False
    assert schedule.groupby("pair_id").arm.nunique().eq(2).all()
    assert len(schedule) == 20
    assert plan_experiment(spec, frozen_forecast)[1].equals(schedule)
    prediction = copy.deepcopy(plan["prediction"])
    result = reconcile_experiment(plan, schedule, outcome_fixture(plan, schedule, 2.0))
    assert result["observed_effect"] == 2.0
    assert result["frozen_prediction"] == prediction
    assert plan["prediction"] == prediction
    assert result["forecast_error"] == 2.0 - prediction["delta"]


@pytest.mark.parametrize("fault", ["duplicate", "exposure", "unknown", "unit", "nan", "real"])
def test_reconciliation_rejects_invalid_outcomes(frozen_forecast, fault):
    plan, schedule = plan_experiment(
        read_json(ROOT / "configs/week5_experiment.json"), frozen_forecast
    )
    observations = outcome_fixture(plan, schedule)
    if fault == "duplicate":
        observations = pd.concat([observations, observations.iloc[:1]])
    elif fault == "exposure":
        observations.loc[0, "applied_policy_id"] = "other-policy"
    elif fault == "unknown":
        observations.loc[0, "block_id"] = "unknown"
    elif fault == "unit":
        observations.loc[0, "unit"] = "VND"
    elif fault == "nan":
        observations.loc[0, "value"] = np.nan
    else:
        observations["source_kind"] = "gsm"
    with pytest.raises(ValueError):
        reconcile_experiment(plan, schedule, observations)


def test_missing_pairs_and_scope_mismatch_stay_unavailable(frozen_forecast):
    spec = read_json(ROOT / "configs/week5_experiment.json") | {"mode": "AB", "block_minutes": 60}
    plan, schedule = plan_experiment(spec, frozen_forecast)
    assert plan["prediction"]["status"] == "scope_mismatch"
    result = reconcile_experiment(plan, schedule, outcome_fixture(plan, schedule).iloc[1:])
    assert result["missing_blocks"] == 1
    assert result["interval"] is None
    assert result["forecast_error"] is None


def test_handoff_refuses_missing_sources_and_byte_budget(policy_source):
    source, demand = policy_source
    output = Pipeline(source.config, "small-handoff")
    with pytest.raises(ValueError, match="budget"):
        export_handoff_run(output.run, [demand.run.run_id], max_bytes=1)
    assert read_json(output.run.manifest_path)["stages"]["export_handoff"]["status"] == "failed"
    assert not (output.run.path / "handoff.zip").exists()


def test_unsupported_policy_retains_failure_diagnostics(policy_source, policy_spec):
    source, demand = policy_source
    policy_spec["candidates"][1]["delta_x"] = 0.2
    path = source.config.workspace / "unsupported.json"
    write_json(path, policy_spec)
    output = Pipeline(source.config, "unsupported-policy")
    with pytest.raises(RuntimeError, match="trajectories failed"):
        compare_policies_run(
            output.run,
            demand.run.run_id,
            ROOT / "configs/week3_poc.json",
            ROOT / "configs/week3_compensation.json",
            path,
        )
    result = read_json(output.run.path / "policy_comparison.json")
    assert result["failed_trajectories"] == policy_spec["n_seeds"]
    assert result["status"] == "completed_with_failures"


@pytest.mark.parametrize("scenario", ["costs", "budget", "insufficient_draws", "source_tamper"])
def test_finance_and_execution_limits_preserve_their_meaning(policy_source, policy_spec, scenario):
    source, demand = policy_source
    if scenario == "costs":
        policy_spec["costs"].update(per_completed_trip=2.0, per_online_hour=3.0, per_horizon=5.0)
    elif scenario == "budget":
        policy_spec["max_seconds"] = 1e-12
    elif scenario == "insufficient_draws":
        policy_spec["bootstrap_draws"] = 20
    else:
        (demand.run.path / "demand_bundle/scenario_contexts.parquet").write_bytes(b"corrupt")
    path = source.config.workspace / "limit-spec.json"
    write_json(path, policy_spec)
    output = Pipeline(source.config, f"week45-{scenario}")
    if scenario != "costs":
        with pytest.raises((ValueError, RuntimeError)):
            compare_policies_run(
                output.run,
                demand.run.run_id,
                ROOT / "configs/week3_poc.json",
                ROOT / "configs/week3_compensation.json",
                path,
            )
        manifest = read_json(output.run.manifest_path)
        assert manifest["stages"]["compare_policies"]["status"] == "failed"
        if scenario == "budget":
            result = read_json(output.run.path / "policy_comparison.json")
            assert result["failed_trajectories"] == result["attempted_trajectories"]
        return
    result = compare_policies_run(
        output.run,
        demand.run.run_id,
        ROOT / "configs/week3_poc.json",
        ROOT / "configs/week3_compensation.json",
        path,
    )
    assert result["economics"]["status"] == "conditional_only"
    assert result["economics"]["profit_status"] == "not_evaluated"
    records = pd.read_csv(output.run.path / "policy_records.csv")
    expected = -2 * records.completed_trips - 3 * records.online_hours - 5
    np.testing.assert_allclose(records.conditional_surplus, expected)
    assert (records.conditional_surplus < 0).all()


def test_independent_evaluation_refuses_development_seed_reuse(policy_source, policy_spec):
    source, demand = policy_source
    path = source.config.workspace / "comparison-spec.json"
    write_json(path, policy_spec)
    comparison = Pipeline(source.config, "week45-frozen")
    compare_policies_run(
        comparison.run,
        demand.run.run_id,
        ROOT / "configs/week3_poc.json",
        ROOT / "configs/week3_compensation.json",
        path,
    )
    comparison.run.complete()
    output = Pipeline(source.config, "week45-overlapping-evaluation")
    with pytest.raises(ValueError, match="overlap"):
        evaluate_policies_run(output.run, comparison.run.run_id, source.run.run_id, path)


def test_bootstrap_pipeline_runs_with_unavailable_economic_intervals(policy_source, policy_spec):
    source, demand = policy_source
    policy_spec["bootstrap_draws"] = 3
    path = source.config.workspace / "bootstrap-policy.json"
    write_json(path, policy_spec)
    output = Pipeline(source.config, "week45-bootstrap")
    result = compare_policies_run(
        output.run,
        demand.run.run_id,
        ROOT / "configs/week3_poc.json",
        ROOT / "configs/week3_compensation.json",
        path,
    )
    assert result["failed_trajectories"] == 0
    assert result["attempted_trajectories"] == 16
    assert result["economics"]["status"] == "not_evaluated_missing_costs"
