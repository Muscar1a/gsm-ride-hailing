"""Separate, person-held-out Swissmetro choice benchmark; no GSM coefficient transfer."""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

from gsm_poc.artifacts import Run, sha256_file, utc_now, write_frame, write_json
from gsm_poc.config import Config

SOURCE_URL = "https://transp-or.epfl.ch/data/swissmetro.dat"
DICTIONARY_URL = "https://transp-or.epfl.ch/biogeme-2.5/swissmetro.pdf"
PREPARATION_URL = "https://biogeme.epfl.ch/sphinx/_modules/biogeme/data/swissmetro.html"
REQUIRED_COLUMNS = (
    "ID",
    "SP",
    "CHOICE",
    "GA",
    "TRAIN_AV",
    "SM_AV",
    "CAR_AV",
    "TRAIN_TT",
    "SM_TT",
    "CAR_TT",
    "TRAIN_CO",
    "SM_CO",
    "CAR_CO",
)
PARAMETER_NAMES = ("asc_train", "asc_car", "time_per_100_minutes", "cost_per_100_chf")


def prepare_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    missing = sorted(set(REQUIRED_COLUMNS) - set(raw.columns))
    if missing:
        raise ValueError(f"Swissmetro missing columns: {missing}")
    if raw.empty:
        raise ValueError("Swissmetro source is empty")
    frame = raw.copy()
    for column in REQUIRED_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    values = frame[list(REQUIRED_COLUMNS)].to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("Swissmetro required fields must be finite and nonmissing")
    for column in ("SP", "GA", "TRAIN_AV", "SM_AV", "CAR_AV"):
        if not frame[column].isin((0, 1)).all():
            raise ValueError(f"Swissmetro {column} must be binary")
    if not frame.CHOICE.isin((0, 1, 2, 3)).all():
        raise ValueError("Swissmetro CHOICE must be 0, 1, 2, or 3")
    if not ((frame.ID > 0) & (frame.ID == np.floor(frame.ID))).all():
        raise ValueError("Swissmetro ID must be a positive integer")
    for column in ("TRAIN_TT", "SM_TT", "CAR_TT", "TRAIN_CO", "SM_CO", "CAR_CO"):
        if (frame[column] < 0).any():
            raise ValueError(f"Swissmetro {column} must be nonnegative")
    # Preserve repeated survey tasks, including exact duplicate attributes.
    frame["source_row"] = np.arange(len(frame))
    retained = (frame.SP == 1) & (frame.CHOICE != 0)
    quality = {
        "input_rows": len(frame),
        "input_people": int(frame.ID.nunique()),
        "unknown_choice_rows": int((frame.CHOICE == 0).sum()),
        "non_sp_rows": int((frame.SP != 1).sum()),
        "excluded_rows_union": int((~retained).sum()),
        "duplicate_attribute_rows": int(raw.duplicated(keep=False).sum()),
        "deduplication": "none; repeated stated-choice tasks are retained",
        "purpose_filter": "none; all stated-preference trip purposes",
    }
    frame = frame.loc[retained].copy().reset_index(drop=True)
    if frame.empty:
        raise ValueError("No known stated-preference choices remain")
    frame["person_id"] = frame.ID.astype(np.int64)
    frame["choice_index"] = frame.CHOICE.astype(np.int64) - 1
    availability = frame[["TRAIN_AV", "SM_AV", "CAR_AV"]].to_numpy(bool)
    if not availability.any(axis=1).all():
        raise ValueError("Swissmetro task has no available alternative")
    if not availability[np.arange(len(frame)), frame.choice_index].all():
        raise ValueError("Swissmetro chosen alternative is unavailable")
    quality.update(retained_rows=len(frame), retained_people=int(frame.person_id.nunique()))
    return frame, quality


def split_people(frame: pd.DataFrame, seed: int) -> dict[str, pd.DataFrame]:
    if type(seed) is not int or seed < 0:
        raise ValueError("Split seed must be a nonnegative integer")
    people = np.sort(frame.person_id.unique())
    if len(people) < 7:
        raise ValueError("Person-level train/validation/test split requires at least seven people")
    shuffled = np.random.default_rng(seed).permutation(people)
    train_end, validation_end = int(len(people) * 0.70), int(len(people) * 0.85)
    groups = {
        "train": shuffled[:train_end],
        "validation": shuffled[train_end:validation_end],
        "test": shuffled[validation_end:],
    }
    return {name: frame.loc[frame.person_id.isin(ids)].copy() for name, ids in groups.items()}


def model_arrays(
    frame: pd.DataFrame, attributes: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = np.zeros((len(frame), 3, 4 if attributes else 2))
    features[:, 0, 0] = 1  # Swissmetro is the reference alternative.
    features[:, 2, 1] = 1
    if attributes:
        features[:, :, 2] = frame[["TRAIN_TT", "SM_TT", "CAR_TT"]].to_numpy(float) / 100
        costs = frame[["TRAIN_CO", "SM_CO", "CAR_CO"]].to_numpy(float).copy()
        # EPFL convention: incremental rail/SM fare is zero for annual GA holders.
        costs[:, :2] *= (frame.GA.to_numpy() == 0)[:, None]
        features[:, :, 3] = costs / 100
    availability = frame[["TRAIN_AV", "SM_AV", "CAR_AV"]].to_numpy(bool)
    return features, availability, frame.choice_index.to_numpy(int)


def log_probabilities(
    coefficients: np.ndarray, features: np.ndarray, availability: np.ndarray
) -> np.ndarray:
    utilities = np.einsum("nak,k->na", features, coefficients)
    utilities = np.where(availability, utilities, -np.inf)
    return utilities - logsumexp(utilities, axis=1, keepdims=True)


def likelihood_gradient(
    coefficients: np.ndarray, features: np.ndarray, availability: np.ndarray, choices: np.ndarray
) -> tuple[float, np.ndarray]:
    log_probs = log_probabilities(coefficients, features, availability)
    probabilities = np.exp(log_probs)
    selected = features[np.arange(len(choices)), choices]
    gradient = (np.einsum("na,nak->nk", probabilities, features) - selected).mean(axis=0)
    return -float(log_probs[np.arange(len(choices)), choices].mean()), gradient


def fit_model(train: pd.DataFrame, attributes: bool) -> dict:
    features, availability, choices = model_arrays(train, attributes)
    if set(choices) != {0, 1, 2}:
        raise ValueError("Training requires observed choices for all three alternatives")
    started = time.perf_counter()
    result = minimize(
        likelihood_gradient,
        np.zeros(features.shape[2]),
        args=(features, availability, choices),
        jac=True,
        method="BFGS",
        options={"maxiter": 500, "gtol": 1e-7},
    )
    diagnostics = {
        "optimizer_success": bool(result.success),
        "message": str(result.message),
        "iterations": int(result.nit),
        "gradient_max_abs": float(np.abs(result.jac).max()),
        "duration_seconds": time.perf_counter() - started,
    }
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(f"Swissmetro optimizer did not converge: {diagnostics}")
    probabilities = np.exp(log_probabilities(result.x, features, availability))
    expected = np.einsum("na,nak->nk", probabilities, features)
    centered = features - expected[:, None, :]
    information = np.einsum("na,nak,nal->kl", probabilities, centered, centered)
    rank = int(np.linalg.matrix_rank(information))
    if rank != features.shape[2]:
        raise ValueError(f"Swissmetro model not identified: information rank {rank}")
    return {
        "coefficients": dict(
            zip(PARAMETER_NAMES[: features.shape[2]], result.x.tolist(), strict=True)
        ),
        "attributes": attributes,
        "diagnostics": {**diagnostics, "information_rank": rank},
    }


def score_model(
    model: dict, frame: pd.DataFrame, split: str, name: str
) -> tuple[dict, pd.DataFrame]:
    features, availability, choices = model_arrays(frame, model["attributes"])
    coefficients = np.array(list(model["coefficients"].values()))
    log_probs = log_probabilities(coefficients, features, availability)
    probabilities = np.exp(log_probs)
    if not np.isfinite(probabilities).all() or not np.allclose(probabilities.sum(axis=1), 1):
        raise ValueError("Invalid Swissmetro probabilities")
    if (probabilities[~availability] != 0).any():
        raise ValueError("Unavailable Swissmetro alternatives received probability")
    loss = -log_probs[np.arange(len(frame)), choices]
    predictions = frame[["source_row", "person_id", "CHOICE"]].copy()
    predictions["split"], predictions["model"] = split, name
    predictions[["p_train", "p_swissmetro", "p_car"]] = probabilities
    predictions["log_loss"] = loss
    metrics = {
        "model": name,
        "split": split,
        "rows": len(frame),
        "people": int(frame.person_id.nunique()),
        "log_loss": float(loss.mean()),
        "person_mean_log_loss": float(predictions.groupby("person_id").log_loss.mean().mean()),
        "accuracy": float((probabilities.argmax(axis=1) == choices).mean()),
        "unavailable_probability_violations": 0,
        "source_kind": "public_stated_preference",
        "evidence_level": "C",
        "status": "ok",
    }
    return metrics, predictions


def run_benchmark(
    workspace: Path,
    data_path: Path,
    seed: int,
    run_id: str | None = None,
    source_kind: str = "public_stated_preference",
) -> Run:
    if source_kind not in {"public_stated_preference", "synthetic_fixture"}:
        raise ValueError("Invalid choice-benchmark source label")
    # Freeze the prespecified model/split before opening the final test data.
    config = Config(workspace=workspace.resolve())
    config = dataclasses.replace(
        config, simulation=dataclasses.replace(config.simulation, seed=seed)
    )
    run = Run(config, run_id)
    inputs = {
        "source_sha256": sha256_file(data_path),
        "split_seed": seed,
        "model_spec": "two ASCs; generic time/cost; SM reference; availability masked",
        "split_fractions": [0.70, 0.15, 0.15],
        "version": 1,
        "source_kind": source_kind,
    }
    with run.stage("swissmetro", inputs) as execute:
        if execute:
            frame, quality = prepare_data(pd.read_csv(data_path, sep="\t"))
            splits = split_people(frame, seed)
            split_record = {
                name: {"people": sorted(part.person_id.unique().tolist()), "rows": len(part)}
                for name, part in splits.items()
            }
            models = {
                "intercept_only": fit_model(splits["train"], False),
                "multinomial_logit": fit_model(splits["train"], True),
            }
            metrics, predictions = [], []
            for name, model in models.items():
                for split, part in splits.items():
                    row, predicted = score_model(model, part, split, name)
                    row["source_kind"] = source_kind
                    metrics.append(row)
                    predictions.append(predicted)
            table = pd.DataFrame(metrics)
            test_scores = table[table.split == "test"].set_index("model").log_loss
            report = {
                "status": "ok",
                "source_kind": source_kind,
                "evidence_level": "C",
                "quality": quality,
                "models": models,
                "split_seed": seed,
                "test_log_loss_improvement": float(
                    test_scores.intercept_only - test_scores.multinomial_logit
                ),
                "test_selection": "none; both prespecified models reported",
                "units": {"time": "minutes / 100", "cost": "CHF / 100"},
                "ga_rule": "TRAIN_CO and SM_CO multiplied by (GA == 0)",
                "limitations": [
                    "Hypothetical stated choices, not observed GSM bookings",
                    "No GSM elasticity, calibration, causal or ROI claim",
                    "No coefficient transfer to TLC or GSM",
                    "Dataset-specific reuse license is not stated on the source page",
                ],
            }
            source = {
                "source_url": SOURCE_URL if source_kind == "public_stated_preference" else None,
                "dictionary_url": DICTIONARY_URL,
                "preparation_url": PREPARATION_URL,
                "path": str(data_path.resolve()),
                "sha256": inputs["source_sha256"],
                "bytes": data_path.stat().st_size,
                "license_status": "dataset_specific_license_not_stated",
                "verified_at": utc_now(),
                "permitted_use_evidence": (
                    "EPFL publicly distributes the file for choice-model examples"
                    if source_kind == "public_stated_preference"
                    else "Generated synthetic test fixture"
                ),
                "redistribution": "raw source kept ignored; no redistribution grant inferred",
            }
            directory = run.path / "swissmetro"
            paths = [
                directory / "source_manifest.json",
                directory / "splits.json",
                directory / "report.json",
                directory / "metrics.csv",
                directory / "predictions.parquet",
            ]
            write_json(paths[0], source)
            write_json(paths[1], split_record)
            write_json(paths[2], report)
            write_frame(paths[3], table)
            write_frame(paths[4], pd.concat(predictions, ignore_index=True))
            run.manifest.update(source_kind=source_kind, evidence_level="C")
            run.outputs(
                "swissmetro",
                paths,
                input_rows=quality["input_rows"],
                retained_rows=len(frame),
                output_rows=len(table),
            )
    run.complete()
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/raw/swissmetro/swissmetro.dat"))
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--seed", type=int, default=31001)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        run = run_benchmark(args.workspace, args.data, args.seed, args.run_id)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"swissmetro: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Run: {run.run_id}\nArtifacts: {run.path / 'swissmetro'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
