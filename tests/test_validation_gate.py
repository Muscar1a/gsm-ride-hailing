import dataclasses

import numpy as np
import pytest

from gsm_poc.artifacts import completed_run, read_json, write_frame
from gsm_poc.estimate import fit_estimator
from gsm_poc.features import TREATMENT_COLUMNS, date_splits
from gsm_poc.generate import TRUE_THETA, save_generated
from gsm_poc.pipeline import Pipeline
from gsm_poc.validate import valid_probabilities


@pytest.fixture
def invalid_validation(config, generated):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    blocks = generated.blocks.copy()
    train = blocks.day_id < config.source.train_end
    validation = (blocks.day_id >= config.source.train_end) & (
        blocks.day_id < config.source.validation_end
    )
    # Observations remain valid, but the fitted response extrapolates outside the
    # probability simplex on validation contexts while test contexts remain valid.
    blocks.loc[train, "distance_scaled"] *= 0.1
    blocks.loc[validation, "distance_scaled"] = 1.0
    blocks.loc[~(train | validation), "distance_scaled"] = 0.0
    effects = blocks.loc[train, list(TREATMENT_COLUMNS)].to_numpy() @ TRUE_THETA.T
    qx = 0.3 + 0.8 * blocks.loc[train, "distance_scaled"] + effects[:, 0]
    qy = 0.25 + effects[:, 1]
    n_train = int(1e8)
    nx = np.round(qx * n_train).astype(int)
    ny = np.round(qy * n_train).astype(int)
    nnone = n_train - nx - ny
    blocks.loc[train, "n_sessions"] = n_train
    blocks.loc[train, "n_x"] = nx
    blocks.loc[train, "n_y"] = ny
    blocks.loc[train, "n_none"] = nnone
    blocks.loc[train, "q_x"] = nx / n_train
    blocks.loc[train, "q_y"] = ny / n_train
    blocks.loc[train, "q_none"] = nnone / n_train
    return config, generated, blocks


def test_pipeline_records_validation_failure_without_publishing_model(invalid_validation):
    config, data, blocks = invalid_validation
    splits = date_splits(blocks, config)
    bundle = fit_estimator(splits["train"], config, "adjusted_ols").bundle
    assert bundle is not None
    assert valid_probabilities(blocks[["q_x", "q_y", "q_none"]].to_numpy())
    assert valid_probabilities(bundle.probabilities(splits["test"], np.zeros(2)))
    assert not valid_probabilities(
        bundle.probabilities(
            splits["validation"], splits["validation"][list(TREATMENT_COLUMNS)].to_numpy()
        )
    )
    save_generated(config, data)
    observed = (
        config.workspace / "data/synthetic" / data.dataset_id / "observed/choice_block.parquet"
    )
    write_frame(observed, blocks)
    pipeline = Pipeline(config, "invalid-validation")
    with pytest.raises(ValueError, match="adjusted_ols.*validation"):
        pipeline.fit(data.dataset_id)
    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["stages"]["fit"]["status"] == "failed"
    assert "validation" in manifest["stages"]["fit"]["error"].lower()
    assert not (pipeline.run.path / "models/adjusted_ols/model_bundle.joblib").exists()
    with pytest.raises(ValueError, match="not complete"):
        completed_run(config.workspace, pipeline.run.run_id)


def test_pipeline_rejects_count_mismatch_without_publishing_model(config, generated):
    config = dataclasses.replace(
        config,
        model=dataclasses.replace(
            config.model, estimators=("adjusted_ols",), scenario_estimator="adjusted_ols"
        ),
    )
    data = generated
    save_generated(config, data)
    observed = (
        config.workspace / "data/synthetic" / data.dataset_id / "observed/choice_block.parquet"
    )
    blocks = data.blocks.copy()
    # Corrupt one block so that n_x + n_y + n_none != n_sessions
    blocks.loc[0, "n_x"] += 5
    write_frame(observed, blocks)

    pipeline = Pipeline(config, "invalid-counts")
    with pytest.raises(ValueError, match="Choice counts do not conserve sessions"):
        pipeline.fit(data.dataset_id)

    manifest = read_json(pipeline.run.manifest_path)
    assert manifest["status"] == "failed"
    assert manifest["stages"]["fit"]["status"] == "failed"
    assert "conserve sessions" in manifest["stages"]["fit"]["error"]
    assert not (pipeline.run.path / "models/adjusted_ols/model_bundle.joblib").exists()
    with pytest.raises(ValueError, match="not complete"):
        completed_run(config.workspace, pipeline.run.run_id)
