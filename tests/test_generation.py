import dataclasses

import numpy as np
import pandas as pd
import pytest

from gsm_poc.build_context import build_context
from gsm_poc.build_silver import build_silver
from gsm_poc.config import DGPS
from gsm_poc.features import Encoder, date_splits, day_folds, require_observed
from gsm_poc.generate import generate
from gsm_poc.uncertainty import bootstrap_sample
from gsm_poc.validate import valid_probabilities


@pytest.mark.parametrize("dgp", DGPS)
def test_all_dgps_conserve_sessions_and_have_valid_truth(config, dgp):
    config = dataclasses.replace(config, simulation=dataclasses.replace(config.simulation, dgp=dgp))
    data = generate(config)
    assert data.sessions.session_id.nunique() == len(data.sessions)
    assert (data.sessions[["y_x", "y_y", "y_none"]].sum(axis=1) == 1).all()
    assert (data.blocks[["n_x", "n_y", "n_none"]].sum(axis=1) == data.blocks.n_sessions).all()
    reconstructed = data.sessions.groupby("block_id")[["y_x", "y_y", "y_none"]].sum()
    expected = data.blocks.set_index("block_id")[["n_x", "n_y", "n_none"]]
    np.testing.assert_array_equal(reconstructed.loc[expected.index].to_numpy(), expected.to_numpy())
    assert valid_probabilities(data.oracle[["p_x", "p_y", "p_none"]].to_numpy())
    assert "u" not in data.blocks
    assert "p_x" not in data.policy
    assert data.metadata["evidence_level"] == "C"
    if dgp == "COLLINEAR_PRICE":
        np.testing.assert_array_equal(data.blocks.multiplier_x, data.blocks.multiplier_y)


def test_rng_reproduction_and_stream_separation(config):
    first, second = generate(config), generate(config)
    pd.testing.assert_frame_equal(first.blocks, second.blocks)
    pd.testing.assert_frame_equal(first.sessions, second.sessions)
    larger = dataclasses.replace(
        config, simulation=dataclasses.replace(config.simulation, sessions_per_block=100)
    )
    third = generate(larger)
    np.testing.assert_array_equal(first.policy.multiplier_x, third.policy.multiplier_x)
    np.testing.assert_array_equal(first.policy.distance_scaled, third.policy.distance_scaled)
    assert first.dataset_id != third.dataset_id


def test_day_splits_and_duplicate_bootstrap_day_groups(config, generated):
    splits = date_splits(generated.blocks, config)
    assert splits["train"].day_id.nunique() == 20
    assert splits["validation"].day_id.nunique() == 5
    assert splits["test"].day_id.nunique() == 6
    sampled = bootstrap_sample(splits["train"], np.random.default_rng(1))
    assert sampled.original_day_id.nunique() < 20
    for train, validation in day_folds(sampled, config.model.folds):
        assert not set(sampled.original_day_id.iloc[train]) & set(
            sampled.original_day_id.iloc[validation]
        )


def test_oracle_contamination_rejected_and_ids_never_encoded(config, generated):
    with pytest.raises(ValueError, match="Oracle"):
        require_observed(generated.blocks.assign(u=0))
    encoder = Encoder(config.source.zones)
    original = encoder.transform(generated.blocks)
    altered = generated.blocks.assign(assignment_probability=999, block_id="adversarial", seed=999)
    np.testing.assert_array_equal(original, encoder.transform(altered))


def test_tlc_mode_never_fabricates_missing_context(config):
    config = dataclasses.replace(
        config, project=dataclasses.replace(config.project, context_mode="tlc")
    )
    with pytest.raises(ValueError, match="requires train-fitted context"):
        generate(config)


@pytest.mark.parametrize("dgp", DGPS)
def test_dgps_accept_parquet_contexts_from_tlc_build(tlc_fixture, dgp):
    config, source = tlc_fixture
    config = dataclasses.replace(
        config,
        project=dataclasses.replace(config.project, context_mode="tlc"),
        simulation=dataclasses.replace(config.simulation, dgp=dgp),
    )
    silver = build_silver(config, source)
    output = build_context(config, silver["silver"], silver["build_id"])
    contexts = pd.read_parquet(output["contexts"])
    assert contexts.is_weekend.dtype == bool
    data = generate(config, contexts, output["context_version"])
    assert data.metadata["source_kind"] == "semi_synthetic"
    assert valid_probabilities(data.oracle[["p_x", "p_y", "p_none"]].to_numpy(float))
    assert (data.blocks[["n_x", "n_y", "n_none"]].sum(axis=1) == data.blocks.n_sessions).all()
