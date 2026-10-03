"""Controlled choice DGPs. Only this module creates the hidden oracle."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd

from gsm_poc.artifacts import fingerprint, sha256_file, write_frame, write_json
from gsm_poc.config import Config
from gsm_poc.validate import require_probabilities

PRICE_LEVELS = np.array([0.9, 1.0, 1.1])
TRUE_THETA = np.array([[-0.60, 0.15], [0.12, -0.50]])


@dataclasses.dataclass
class Generated:
    dataset_id: str
    policy: pd.DataFrame
    sessions: pd.DataFrame
    blocks: pd.DataFrame
    oracle: pd.DataFrame
    metadata: dict


def generate(
    config: Config, contexts: pd.DataFrame | None = None, context_version: str = "synthetic-v1"
) -> Generated:
    if config.project.context_mode == "tlc" and contexts is None:
        raise ValueError("TLC mode requires train-fitted context; no synthetic substitution")
    source_kind = "semi_synthetic" if contexts is not None else "synthetic"
    rng_context, rng_policy, rng_choice = [
        np.random.default_rng(s) for s in np.random.SeedSequence(config.simulation.seed).spawn(3)
    ]
    slots = pd.date_range(
        config.source.start,
        config.source.end,
        freq=f"{config.simulation.slot_minutes}min",
        inclusive="left",
    )
    blocks = pd.MultiIndex.from_product(
        [config.source.zones, slots], names=["zone_id", "slot_start_local"]
    ).to_frame(index=False)
    blocks["day_id"] = blocks.slot_start_local.dt.strftime("%Y-%m-%d")
    blocks["original_day_id"] = blocks.day_id
    blocks["hour"] = blocks.slot_start_local.dt.hour + blocks.slot_start_local.dt.minute / 60
    blocks["weekday"] = blocks.slot_start_local.dt.weekday
    blocks["is_weekend"] = (blocks.weekday >= 5).astype(int)
    blocks["is_peak"] = (
        ((blocks.hour >= 7) & (blocks.hour < 10)) | ((blocks.hour >= 16) & (blocks.hour < 20))
    ).astype(int)
    blocks["hour_sin"] = np.sin(2 * np.pi * blocks.hour / 24)
    blocks["hour_cos"] = np.cos(2 * np.pi * blocks.hour / 24)
    if contexts is None:
        blocks["distance_scaled"] = rng_context.uniform(0, 1, len(blocks))
        blocks["context_id"] = "synthetic-context"
        blocks["fallback_level"] = -1
    else:
        if contexts.duplicated(["zone_id", "hour", "is_weekend"]).any():
            raise ValueError("Context templates have duplicate keys")
        blocks["template_hour"] = blocks.slot_start_local.dt.hour
        selected = contexts[
            ["zone_id", "hour", "is_weekend", "distance_scaled", "context_id", "fallback_level"]
        ].rename(columns={"hour": "template_hour"})
        # DuckDB context keys are booleans; match the simulation's integer key
        # so pandas does not promote numeric calculations to object arrays.
        selected["is_weekend"] = selected.is_weekend.astype(int)
        blocks = blocks.merge(
            selected,
            on=["zone_id", "template_hour", "is_weekend"],
            how="left",
            validate="many_to_one",
        )
        if blocks.distance_scaled.isna().any():
            raise ValueError("Context templates do not cover every simulation context")
        blocks = blocks.drop(columns="template_hour")
    if not blocks.distance_scaled.between(0, 1).all():
        raise ValueError("Context distance is outside frozen [0,1] scale")
    dataset_id = (
        "ds-"
        + fingerprint(
            {
                "simulation": config.as_dict()["simulation"],
                "scope": config.as_dict()["source"],
                "context_version": context_version,
                "source_kind": source_kind,
                "generator_code_sha256": sha256_file(Path(__file__)),
            }
        )[:20]
    )
    blocks["dataset_id"] = dataset_id
    blocks["block_id"] = np.arange(len(blocks)).astype(str)
    blocks["source_kind"] = source_kind
    blocks["dgp_id"] = config.simulation.dgp
    blocks["seed"] = config.simulation.seed
    peak, weekend, distance = (
        blocks[c].to_numpy(dtype=float) for c in ("is_peak", "is_weekend", "distance_scaled")
    )
    sx = np.clip(2 * peak - 1 + 0.5 * weekend - 0.5 * distance, -1, 1)
    sy = np.clip(1.5 * peak - 0.75 + 0.5 * blocks.hour_sin.to_numpy(), -1, 1)
    hidden = np.zeros(len(blocks))
    if config.simulation.dgp == "HIDDEN_CONFOUNDING":
        hidden = rng_policy.uniform(-1, 1, len(blocks))
        sx, sy = np.clip(sx + 0.5 * hidden, -1, 1), np.clip(sy + 0.5 * hidden, -1, 1)
    if config.simulation.dgp in ("OBSERVED_CONFOUNDING", "HIDDEN_CONFOUNDING"):
        px = np.exp(0.8 * sx[:, None] * np.array([-1, 0, 1]))
        py = np.exp(0.8 * sy[:, None] * np.array([-1, 0, 1]))
        px, py = px / px.sum(axis=1, keepdims=True), py / py.sum(axis=1, keepdims=True)
    else:
        px = py = np.full((len(blocks), 3), 1 / 3)
    ix = (rng_policy.random(len(blocks))[:, None] > np.cumsum(px, axis=1)).sum(axis=1)
    iy = (rng_policy.random(len(blocks))[:, None] > np.cumsum(py, axis=1)).sum(axis=1)
    if config.simulation.dgp == "COLLINEAR_PRICE":
        iy = ix.copy()
    blocks["multiplier_x"], blocks["multiplier_y"] = PRICE_LEVELS[ix], PRICE_LEVELS[iy]
    blocks["log_multiplier_x"] = np.log(blocks.multiplier_x)
    blocks["log_multiplier_y"] = np.log(blocks.multiplier_y)
    rows = np.arange(len(blocks))
    blocks["assignment_probability"] = px[rows, ix] * py[rows, iy]
    if config.simulation.dgp == "COLLINEAR_PRICE":
        blocks["assignment_probability"] = 1 / 3
    baseline = np.column_stack(
        [
            0.30 + 0.05 * peak - 0.04 * distance + 0.02 * weekend + 0.02 * blocks.hour_sin,
            0.25 + 0.04 * peak - 0.03 * distance + 0.01 * weekend + 0.02 * blocks.hour_cos,
        ]
    )
    if config.simulation.dgp == "HIDDEN_CONFOUNDING":
        baseline += hidden[:, None] * np.array([0.025, 0.020])
    theta = np.zeros((2, 2)) if config.simulation.dgp == "NULL_EFFECT" else TRUE_THETA.copy()
    treatment = blocks[["log_multiplier_x", "log_multiplier_y"]].to_numpy()
    probs_xy = baseline + treatment @ theta.T
    probs = np.column_stack([probs_xy, 1 - probs_xy.sum(axis=1)])
    require_probabilities(probs)
    counts = np.array(
        [rng_choice.multinomial(config.simulation.sessions_per_block, p) for p in probs]
    )
    policy = blocks.copy()
    n = config.simulation.sessions_per_block
    # Each block's counts become exactly n mutually exclusive session labels.
    choice = np.concatenate([np.repeat(np.array(["X", "Y", "NONE"]), row) for row in counts])
    sessions = pd.DataFrame(
        {
            "dataset_id": dataset_id,
            "block_id": np.repeat(blocks.block_id.to_numpy(), n),
            "session_id": np.arange(len(blocks) * n).astype(str),
            "synthetic_customer_id": np.arange(len(blocks) * n).astype(str),
            "choice": choice,
            "y_x": (choice == "X").astype("int8"),
            "y_y": (choice == "Y").astype("int8"),
            "y_none": (choice == "NONE").astype("int8"),
            "source_kind": source_kind,
        }
    )
    blocks["n_sessions"] = n
    for j, label in enumerate(("x", "y", "none")):
        blocks[f"n_{label}"] = counts[:, j]
        blocks[f"q_{label}"] = counts[:, j] / n
    if not (blocks[["n_x", "n_y", "n_none"]].sum(axis=1) == n).all():
        raise ValueError("Choice counts do not conserve sessions")
    if not (sessions[["y_x", "y_y", "y_none"]].sum(axis=1) == 1).all():
        raise ValueError("Sessions are not mutually exclusive")
    oracle = blocks[["dataset_id", "block_id"]].copy()
    for j, label in enumerate(("x", "y", "none")):
        oracle[f"p_{label}"] = probs[:, j]
    oracle["b_x"], oracle["b_y"], oracle["u"] = baseline[:, 0], baseline[:, 1], hidden
    metadata = {
        "dataset_id": dataset_id,
        "source_kind": source_kind,
        "evidence_level": "C",
        "dgp_id": config.simulation.dgp,
        "seed": config.simulation.seed,
        "context_version": context_version,
        "blocks": len(blocks),
        "sessions": len(sessions),
        "rng": "numpy.SeedSequence: independent context, assignment, choice streams",
        "price_levels": PRICE_LEVELS.tolist(),
        "train_end_exclusive": config.source.train_end,
        "validation_end_exclusive": config.source.validation_end,
        "end_exclusive": config.source.end,
        "choice_unit": "quote sessions held fixed; not completed trips",
    }
    return Generated(dataset_id, policy, sessions, blocks, oracle, metadata)


def save_generated(config: Config, data: Generated) -> list[Path]:
    root = config.workspace / "data/synthetic" / data.dataset_id
    observed, oracle = root / "observed", root / "oracle"
    paths = [
        observed / "synthetic_policy_block.parquet",
        observed / "synthetic_quote_session.parquet",
        observed / "choice_block.parquet",
        oracle / "oracle_block.parquet",
        oracle / "parameters.json",
        root / "manifest.json",
    ]
    for path, frame in zip(
        paths[:4], (data.policy, data.sessions, data.blocks, data.oracle), strict=True
    ):
        write_frame(path, frame)
    theta = np.zeros((2, 2)) if data.metadata["dgp_id"] == "NULL_EFFECT" else TRUE_THETA
    write_json(
        paths[4],
        {
            "theta": theta.tolist(),
            "outcome_order": ["X", "Y"],
            "treatment_order": ["X", "Y"],
            **data.metadata,
        },
    )
    write_json(paths[5], data.metadata)
    return paths
