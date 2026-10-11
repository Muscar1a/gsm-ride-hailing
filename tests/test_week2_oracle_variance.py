import numpy as np
import pytest

from gsm_poc.causal.estimate import fit_estimator
from gsm_poc.causal.features import Encoder, date_splits
from gsm_poc.simulation.dgp import TRUE_THETA
from scripts.diagnose_week2_oracle_variance import ols_reference


def test_exact_conditional_mean_and_saved_point(config, generated):
    splits = date_splits(generated.blocks, config)
    train, contexts = splits["train"], splits["test"]
    point, expected, covariance = ols_reference(
        train, contexts, Encoder(config.source.zones), generated.oracle
    )
    bundle = fit_estimator(train, config, "adjusted_ols").bundle
    assert bundle is not None
    actual = np.r_[
        bundle.theta.ravel(),
        np.average(bundle.baseline(contexts), axis=0, weights=contexts.n_sessions),
    ]
    np.testing.assert_allclose(point, actual, atol=1e-10, rtol=0)
    np.testing.assert_allclose(expected[:4], TRUE_THETA.ravel(), atol=1e-10, rtol=0)
    oracle = contexts[["block_id", "n_sessions"]].merge(
        generated.oracle, on="block_id", validate="one_to_one"
    )
    np.testing.assert_allclose(
        expected[4:],
        np.average(oracle[["b_x", "b_y"]], axis=0, weights=oracle.n_sessions),
        atol=1e-10,
    )
    np.testing.assert_allclose(covariance, covariance.T, atol=1e-15)
    assert np.linalg.eigvalsh(covariance).min() > 0
    assert covariance[4, 5] < 0  # Mutually exclusive multinomial choices share negative covariance.


def test_doubling_sessions_halves_reference_variance(config, generated):
    splits = date_splits(generated.blocks, config)
    train, contexts = splits["train"], splits["test"]
    encoder = Encoder(config.source.zones)
    point, expected, covariance = ols_reference(train, contexts, encoder, generated.oracle)
    doubled = train.copy()
    doubled[["n_sessions", "n_x", "n_y", "n_none"]] *= 2
    new_point, new_expected, new_covariance = ols_reference(
        doubled, contexts, encoder, generated.oracle
    )
    np.testing.assert_allclose(new_point, point, atol=1e-12)
    np.testing.assert_allclose(new_expected, expected, atol=1e-12)
    np.testing.assert_allclose(new_covariance, covariance / 2, atol=1e-14)


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "probability"])
def test_invalid_oracle_rejected(config, generated, invalid):
    splits = date_splits(generated.blocks, config)
    oracle = generated.oracle.copy()
    if invalid == "missing":
        oracle = oracle.iloc[1:]
    elif invalid == "duplicate":
        oracle.loc[1, "block_id"] = oracle.loc[0, "block_id"]
    else:
        oracle.loc[0, "p_x"] = -1
    with pytest.raises(ValueError):
        ols_reference(splits["train"], splits["test"], Encoder(config.source.zones), oracle)
