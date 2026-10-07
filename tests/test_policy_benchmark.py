from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from gsm_poc import policy_benchmark as policy
from gsm_poc.artifacts import read_json
from gsm_poc.estimate import ModelBundle, fit_estimator
from gsm_poc.features import date_splits
from gsm_poc.generate import TRUE_THETA


@pytest.fixture
def policy_config(config):
    return dataclasses.replace(
        config,
        evaluation=dataclasses.replace(
            config.evaluation, seeds=1, bootstrap_draws=0, dgps=("RCT_SYN",)
        ),
    )


def test_value_uses_log_prices_and_session_weights():
    probabilities = np.array([[0.2, 0.3, 0.5], [0.4, 0.2, 0.4]])
    assert policy.gross_value(probabilities, (0.9, 1.1), np.array([1, 3])) == pytest.approx(562.5)
    with pytest.raises(ValueError, match="probabilities"):
        policy.gross_value(np.array([[1.1, -0.1, 0]]), (1, 1), np.ones(1))
    with pytest.raises(ValueError, match="weights"):
        policy.gross_value(probabilities, (1, 1), np.array([0, 1]))
    assert policy.best_action({(0.9, 0.9): 1, (1.0, 1.0): 1}) == (1.0, 1.0)


def test_selection_has_no_oracle_and_ignores_holdout_outcomes(policy_config, exact_blocks):
    splits = date_splits(exact_blocks, policy_config)
    bundle = fit_estimator(splits["train"], policy_config, "adjusted_ols").bundle
    assert bundle is not None
    before = policy.select_policy(bundle, splits["validation"], list(policy.ACTIONS))
    modified = splits["validation"].copy()
    modified["n_x"], modified["n_y"], modified["n_none"] = 0, 0, modified.n_sessions
    modified["q_x"], modified["q_y"], modified["q_none"] = 0.0, 0.0, 1.0
    after = policy.select_policy(bundle, modified, list(policy.ACTIONS))
    assert before == after
    modified["b_x"] = 0.3
    with pytest.raises(ValueError, match="Oracle"):
        policy.select_policy(bundle, modified, list(policy.ACTIONS))


def test_oracle_scoring_joins_keys_and_preserves_negative_uplift(policy_config, generated):
    test = date_splits(generated.blocks, policy_config)["test"]
    generated.oracle = generated.oracle.sample(frac=1, random_state=8)
    baseline = policy.oracle_probabilities(generated, test, (1.0, 1.0))
    changed = policy.oracle_probabilities(generated, test, (1.1, 1.1))
    np.testing.assert_allclose(
        changed[:, :2] - baseline[:, :2],
        np.broadcast_to(np.log([1.1, 1.1]) @ TRUE_THETA.T, (len(test), 2)),
    )
    weights = test.n_sessions.to_numpy(float)
    assert policy.gross_value(changed, (1.1, 1.1), weights) < policy.gross_value(
        baseline, (1, 1), weights
    )
    missing_block = test.block_id.iloc[0]
    generated.oracle = generated.oracle.loc[generated.oracle.block_id.ne(missing_block)]
    with pytest.raises(ValueError, match="keys"):
        policy.oracle_probabilities(generated, test, (1, 1))


def test_support_requires_every_context_stratum(policy_config, generated):
    train = date_splits(generated.blocks, policy_config)["train"]
    contexts = train.copy()
    supported = policy.supported_actions(train, contexts, policy_config)
    assert supported
    action = supported[0]
    group = contexts[["zone_id", "is_weekend", "is_peak"]].iloc[0]
    removed = (
        train.zone_id.eq(group.zone_id)
        & train.is_weekend.eq(group.is_weekend)
        & train.is_peak.eq(group.is_peak)
        & np.isclose(train.multiplier_x, action[0])
        & np.isclose(train.multiplier_y, action[1])
    )
    assert action not in policy.supported_actions(train.loc[~removed], contexts, policy_config)


def test_test_outcomes_and_oracle_cannot_change_frozen_policy(
    policy_config, generated, tmp_path, monkeypatch
):
    monkeypatch.setattr(policy, "generate", lambda config: generated)
    policy.evaluate_seed(policy_config, tmp_path / "before")
    test_mask = generated.blocks.day_id.ge(policy_config.source.validation_end)
    generated.blocks.loc[test_mask, ["n_x", "n_y", "q_x", "q_y"]] = 0
    generated.blocks.loc[test_mask, "n_none"] = generated.blocks.loc[test_mask, "n_sessions"]
    generated.blocks.loc[test_mask, "q_none"] = 1.0
    generated.oracle[["b_x", "b_y"]] = 0.4, 0.3
    policy.evaluate_seed(policy_config, tmp_path / "after")
    before = read_json(tmp_path / "before/selected_policies.json")
    after = read_json(tmp_path / "after/selected_policies.json")
    for record in (before, after):
        for selection in record["selections"].values():
            selection.pop("fit_select_seconds", None)
    assert before == after


def test_decisions_frozen_before_oracle_and_estimator_failure_retained(
    policy_config, tmp_path, monkeypatch
):
    original_fit = policy.fit_estimator
    original_oracle = policy.oracle_probabilities
    root = tmp_path / "seed"

    def fail_one_fit(train, config, estimator):
        if estimator == "naive_ols":
            raise RuntimeError("controlled fit failure")
        return original_fit(train, config, estimator)

    def inspect_frozen_decisions(data, test, action):
        frozen = read_json(root / "selected_policies.json")
        assert set(frozen["selections"]) == set(policy.POLICIES[:-1])
        assert "oracle_reference" not in frozen["selections"]
        return original_oracle(data, test, action)

    monkeypatch.setattr(policy, "fit_estimator", fail_one_fit)
    monkeypatch.setattr(policy, "oracle_probabilities", inspect_frozen_decisions)
    rows, _ = policy.evaluate_seed(policy_config, root)
    results = pd.DataFrame(rows).set_index("policy")
    assert results.loc["naive_ols", "fallback"]
    assert results.loc["naive_ols", "selection_status"] == "learning_failed"
    assert results.loc["naive_ols", "error"] == "controlled fit failure"
    assert (
        results.loc["naive_ols", "gross_value_per_1000"]
        == results.loc["unchanged", "gross_value_per_1000"]
    )
    assert results.loc["adjusted_ols", "selection_status"] != "learning_failed"
    assert results.regret_per_1000.dropna().ge(-1e-10).all()


def test_failed_seed_denominators_and_empty_uncertainty():
    results = pd.DataFrame(
        policy.failed_seed_rows("RCT_SYN", 32001, ValueError("generator failure"))
    )
    summary, paired = policy.summarize_results(results, 20)
    assert summary.expected_seeds.eq(20).all()
    assert summary.attempted_seeds.eq(1).all()
    assert summary.valid_value_seeds.eq(0).all()
    assert summary.failed_value_seeds.eq(1).all()
    assert paired.n.eq(0).all()
    assert paired["mean"].isna().all()
    assert policy.mean_interval(np.zeros(20)) == {"mean": 0, "lower": 0, "upper": 0, "n": 20}


def test_test_probability_rejection_never_reselects(policy_config, tmp_path, monkeypatch):
    original_probabilities = ModelBundle.probabilities

    def invalid_on_test(self, context, treatment):
        if context.day_id.ge(policy_config.source.validation_end).all():
            return np.broadcast_to(np.array([-0.1, 0.3, 0.8]), (len(context), 3))
        return original_probabilities(self, context, treatment)

    monkeypatch.setattr(ModelBundle, "probabilities", invalid_on_test)
    rows, _ = policy.evaluate_seed(policy_config, tmp_path)
    results = pd.DataFrame(rows).set_index("policy")
    frozen = read_json(tmp_path / "selected_policies.json")["selections"]
    for estimator in policy.POLICIES[2:5]:
        row = results.loc[estimator]
        assert row.selection_status == "ok"
        assert row.status == "test_invalid_probability"
        assert not row.fallback
        assert pd.isna(row.gross_value_per_1000)
        assert [row.multiplier_x, row.multiplier_y] == frozen[estimator]["action"]


def test_run_reuses_checked_outputs_and_rejects_changed_protocol(policy_config, monkeypatch):
    run = policy.run_benchmark(policy_config, "policy-test")

    def unexpected_generate(config):
        pytest.fail("Verified completed run must reuse outputs")

    monkeypatch.setattr(policy, "generate", unexpected_generate)
    assert policy.run_benchmark(policy_config, "policy-test").run_id == run.run_id
    changed = dataclasses.replace(
        policy_config, simulation=dataclasses.replace(policy_config.simulation, seed=43)
    )
    with pytest.raises(ValueError, match="different effective configuration"):
        policy.run_benchmark(changed, "policy-test")


def test_shared_seed_failure_records_every_policy(policy_config, monkeypatch):
    def fail_generate(config):
        raise ValueError("shared generation failed")

    monkeypatch.setattr(policy, "generate", fail_generate)
    run = policy.run_benchmark(policy_config, "policy-failed-seed")
    results = pd.read_csv(run.path / "policy/seed_results.csv")
    assert len(results) == 6
    assert results.status.eq("failed").all()
    assert results.error.eq("shared generation failed").all()
    assert results.gross_value_per_1000.isna().all()
