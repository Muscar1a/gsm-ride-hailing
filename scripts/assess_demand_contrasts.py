"""Frozen, observed-only demand contrast assessment with separate evaluator truth."""

from __future__ import annotations

import argparse
import dataclasses
import importlib.metadata
import json
import platform
import subprocess
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from gsm_poc.causal.estimate import fit_estimator
from gsm_poc.causal.features import date_splits
from gsm_poc.causal.identification import RANK_ATOL, SPAN_ATOL
from gsm_poc.causal.scenario import ScenarioRequest, scenario
from gsm_poc.core.artifacts import sha256_file, write_json
from gsm_poc.core.config import Config
from gsm_poc.simulation.dgp import TRUE_THETA, generate

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "configs/demand_contrast_protocol.json"
PROFILE = ROOT / "configs/demand_contrast.toml"


def source_hashes() -> dict[str, str]:
    paths = sorted((ROOT / "src/gsm_poc").rglob("*.py")) + [
        Path(__file__).resolve(),
        PROTOCOL,
        PROFILE,
        ROOT / "uv.lock",
        ROOT / "pyproject.toml",
        ROOT / "tests/test_demand_contrast.py",
    ]
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}


def environment() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "pandas", "scipy", "scikit-learn", "econml")
        },
    }


def observed_case(
    config: Config, regime: str, effect: str, seed: int
) -> tuple[pd.DataFrame, np.ndarray]:
    # The generator/evaluator constructs truth; estimator input contains observed counts only.
    skeleton_config = dataclasses.replace(
        config,
        simulation=dataclasses.replace(
            config.simulation, seed=seed, dgp="RCT_SYN", sessions_per_block=1
        ),
    )
    generated = generate(skeleton_config)
    blocks = generated.blocks.copy()
    if regime == "collinear":
        blocks["log_multiplier_y"] = blocks.log_multiplier_x
        blocks["multiplier_y"] = blocks.multiplier_x
    elif regime in ("single_price", "no_variation"):
        blocks["log_multiplier_y"], blocks["multiplier_y"] = 0.0, 1.0
        if regime == "no_variation":
            blocks["log_multiplier_x"], blocks["multiplier_x"] = 0.0, 1.0
    theta = np.zeros((2, 2)) if effect == "NULL_EFFECT" else TRUE_THETA
    logs = blocks[["log_multiplier_x", "log_multiplier_y"]].to_numpy()
    base = generated.oracle[["b_x", "b_y"]].to_numpy()
    xy = base + logs @ theta.T
    probabilities = np.column_stack([xy, 1 - xy.sum(axis=1)])
    count = config.simulation.sessions_per_block
    rng = np.random.default_rng(np.random.SeedSequence([seed, 64321]))
    counts = np.array([rng.multinomial(count, point) for point in probabilities])
    blocks["dataset_id"] = f"demand-contrast-v1-{seed}-{regime}-{effect}"
    blocks["dgp_id"], blocks["seed"] = effect, seed
    blocks["assignment_probability"] = {
        "independent": 1 / 9,
        "collinear": 1 / 3,
        "single_price": 1 / 3,
        "no_variation": 1,
    }[regime]
    blocks["n_sessions"] = count
    for index, label in enumerate(("x", "y", "none")):
        blocks[f"n_{label}"] = counts[:, index]
        blocks[f"q_{label}"] = counts[:, index] / count
    return blocks, theta


def summarize(records: pd.DataFrame, protocol: dict) -> dict:
    rows = []
    for keys, group in records.groupby(["regime", "effect", "estimator", "outcome"], sort=True):
        valid = group[group.estimate.notna()]
        intervals = valid[valid.lower.notna()]
        errors = valid.estimate - valid.truth
        covered = int(
            ((intervals.lower <= intervals.truth) & (intervals.upper >= intervals.truth)).sum()
        )
        test = (
            binomtest(covered, len(intervals), p=0.95, alternative="less")
            if len(intervals)
            else None
        )
        interval = binomtest(covered, len(intervals)).proportion_ci() if len(intervals) else None
        rows.append(
            dict(zip(("regime", "effect", "estimator", "outcome"), keys, strict=True))
            | {
                "attempted": len(group),
                "valid": len(valid),
                "intervals": len(intervals),
                "bias": float(errors.mean()) if len(valid) else None,
                "rmse": float(np.sqrt(np.mean(errors**2))) if len(valid) else None,
                "sign_errors": int(
                    ((np.sign(valid.estimate) != np.sign(valid.truth)) & (valid.truth != 0)).sum()
                ),
                "coverage": covered / len(intervals) if len(intervals) else None,
                "coverage_exact_95": [float(interval.low), float(interval.high)]
                if interval
                else None,
                "mean_width": float((intervals.upper - intervals.lower).mean())
                if len(intervals)
                else None,
                "null_exclusions": int(((intervals.lower > 0) | (intervals.upper < 0)).sum())
                if keys[1] == "NULL_EFFECT"
                else None,
                "undercoverage_p": float(test.pvalue) if test else None,
            }
        )
    family = [
        row
        for row in rows
        if row["estimator"] == "contrast_ols" and row["regime"] != "no_variation"
    ]
    ordered = sorted(
        family, key=lambda row: row["undercoverage_p"] if row["undercoverage_p"] is not None else -1
    )
    previous = 0.0
    for index, row in enumerate(ordered):
        adjusted = min(1.0, max(previous, (len(family) - index) * (row["undercoverage_p"] or 0)))
        row["undercoverage_holm_p"] = adjusted
        previous = adjusted
    gates = protocol["gates"]
    quality = all(
        row["valid"] == row["attempted"]
        and row["intervals"] == row["attempted"]
        and row["rmse"] <= gates["max_effect_probability_rmse"]
        and abs(row["bias"]) <= gates["max_effect_probability_abs_bias"]
        for row in family
    )
    coverage = len(family) == 18 and all(
        row.get("undercoverage_holm_p", 0) >= gates["family_undercoverage_alpha"] for row in family
    )
    negatives = records[(records.estimator == "contrast_ols") & (records.regime == "no_variation")]
    rejection = bool(
        len(negatives)
        and negatives.estimate.isna().all()
        and (negatives.status == "not_identified").all()
    )
    paired = []
    candidate = records[records.estimator == "contrast_ols"]
    for comparator in ("unchanged", "adjusted_ols", "dml"):
        joined = candidate.merge(
            records[records.estimator == comparator],
            on=["seed", "regime", "effect", "outcome"],
            suffixes=("_new", "_reference"),
            validate="one_to_one",
        )
        for regime, group in joined.groupby("regime"):
            common = group.dropna(subset=["estimate_new", "estimate_reference"])
            paired.append(
                {
                    "reference": comparator,
                    "regime": regime,
                    "attempted": len(group),
                    "common_valid": len(common),
                    "new_rmse": float(
                        np.sqrt(np.mean((common.estimate_new - common.truth_new) ** 2))
                    )
                    if len(common)
                    else None,
                    "reference_rmse": float(
                        np.sqrt(np.mean((common.estimate_reference - common.truth_reference) ** 2))
                    )
                    if len(common)
                    else None,
                }
            )
    return {
        "families": rows,
        "paired_comparisons": paired,
        "gates": {
            "recovery_and_availability": quality,
            "no_holm_undercoverage_rejection": coverage,
            "no_variation_rejection": rejection,
        },
        "scope": protocol["scope"],
    }


def run_phase(phase: str, output: Path) -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    config = Config.load(PROFILE)
    config = dataclasses.replace(
        config,
        source=dataclasses.replace(config.source, zones=tuple(protocol["simulation"]["zones"])),
    )
    assert RANK_ATOL == protocol["numerics"]["covariance_rank_atol"]
    assert SPAN_ATOL == protocol["numerics"]["span_atol"]
    assert (
        config.model.min_price_cell_count
        == protocol["support"]["min_training_blocks_per_context_point"]
    )
    assert config.model.max_condition_number == protocol["numerics"]["max_condition_number"]
    output.mkdir(parents=True, exist_ok=True)
    freeze_path = output / "freeze.json"
    if phase == "freeze":
        if freeze_path.exists():
            raise ValueError("Freeze already exists; do not overwrite an assessment identity")
        if not (output / "development/summary.json").exists():
            raise ValueError("Development results are required before freeze")
        hashes = source_hashes()
        development = json.loads((output / "development/summary.json").read_text(encoding="utf-8"))
        if development["source_hashes"] != hashes:
            raise ValueError("Sources changed since development; rerun development in a new output")
        with zipfile.ZipFile(
            output / "frozen_source.zip", "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for relative in hashes:
                archive.write(ROOT / relative, relative)
        write_json(
            freeze_path,
            {
                "protocol_id": protocol["protocol_id"],
                "source_hashes": hashes,
                "environment": environment(),
                "revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "working_tree": subprocess.check_output(
                    ["git", "status", "--short"], cwd=ROOT, text=True
                ),
                "development_summary_sha256": sha256_file(output / "development/summary.json"),
                "source_archive_sha256": sha256_file(output / "frozen_source.zip"),
            },
        )
        print(f"Frozen {len(hashes)} source/configuration files", flush=True)
        return
    if phase == "assessment":
        frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
        if frozen["source_hashes"] != source_hashes() or frozen["environment"] != environment():
            raise ValueError("Source/configuration/environment changed after freeze")
        seeds = list(
            range(
                protocol["assessment_seeds"]["start"],
                protocol["assessment_seeds"]["stop_exclusive"],
            )
        )
    else:
        if freeze_path.exists():
            raise ValueError("Cannot tune development after freezing this assessment")
        seeds = protocol["development_seeds"]
    if (
        len(seeds) * len(protocol["regimes"]) * len(protocol["effects"])
        > protocol["limits"]["max_data_sets"]
    ):
        raise ValueError("Dataset budget exceeded")
    destination = output / phase
    destination.mkdir(exist_ok=False)
    started = time.perf_counter()
    records, rejection_checks = [], []
    for seed in seeds:
        for regime in protocol["regimes"]:
            for effect in protocol["effects"]:
                if time.perf_counter() - started > protocol["limits"]["wall_seconds"]:
                    raise TimeoutError("Frozen assessment time budget exhausted")
                observed, theta = observed_case(config, regime, effect, seed)
                data_path = (
                    ROOT
                    / ".cache/demand_contrast"
                    / output.name
                    / phase
                    / f"{seed}-{regime}-{effect}.parquet"
                )
                data_path.parent.mkdir(parents=True, exist_ok=True)
                observed.to_parquet(data_path, index=False)
                split = date_splits(observed, config)
                contexts = split["test"].query(
                    "zone_id == 161 and is_weekend == 0 and is_peak == 0"
                )
                joint = regime in ("independent", "collinear")
                request = ScenarioRequest(delta_price_y=0.1 if joint else 0, n_sessions=1000)
                truth = theta @ np.log([1.1, 1.1 if joint else 1])
                for estimator in protocol["estimators"]:
                    result = {"status": "comparison_only", "reasons": []}
                    prediction, lower, upper = [None] * 3, [None] * 3, [None] * 3
                    if estimator == "unchanged":
                        prediction = [0.0] * 3
                    else:
                        try:
                            fit = fit_estimator(split["train"], config, estimator, seed=seed)
                            result = scenario(
                                fit.bundle, contexts, request, config, f"{seed}-{regime}-{effect}"
                            )
                            if (
                                result["status"] in ("ok", "interval_unstable")
                                and result.get("support_status") == "ok"
                            ):
                                prediction = [
                                    result["probabilities"][label]["delta_percentage_points"] / 100
                                    for label in ("X", "Y")
                                ] + [result["delta_expected_bookings"] / request.n_sessions]
                                intervals = result.get("interval") or {}
                                for index, key in enumerate(
                                    (
                                        "X_delta_percentage_points",
                                        "Y_delta_percentage_points",
                                        "delta_expected_bookings",
                                    )
                                ):
                                    if key in intervals:
                                        divisor = 100 if index < 2 else request.n_sessions
                                        lower[index], upper[index] = (
                                            intervals[key]["lower"] / divisor,
                                            intervals[key]["upper"] / divisor,
                                        )
                            if estimator == "contrast_ols" and regime == "collinear":
                                rejected = scenario(
                                    fit.bundle,
                                    contexts,
                                    ScenarioRequest(),
                                    config,
                                    "unidentified-x-only",
                                )
                                rejection_checks.append(
                                    rejected["status"] == "not_identified"
                                    and "probabilities" not in rejected
                                )
                        except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                            result = {"status": "failed", "reasons": [str(exc)]}
                            prediction, lower, upper = [None] * 3, [None] * 3, [None] * 3
                            if estimator == "contrast_ols" and regime == "collinear":
                                rejection_checks.append(False)
                    for index, label in enumerate(("X", "Y", "TOTAL")):
                        records.append(
                            {
                                "seed": seed,
                                "regime": regime,
                                "effect": effect,
                                "estimator": estimator,
                                "outcome": label,
                                "truth": float(truth[index]) if index < 2 else float(truth.sum()),
                                "estimate": prediction[index],
                                "lower": lower[index],
                                "upper": upper[index],
                                "status": result["status"],
                                "reasons": json.dumps(result.get("reasons", [])),
                                "observed_sha256": sha256_file(data_path),
                                "observed_path": data_path.relative_to(ROOT).as_posix(),
                            }
                        )
        print(f"{phase}: seed {seed} complete", flush=True)
    frame = pd.DataFrame(records)
    frame.to_csv(destination / "records.csv", index=False)
    summary = summarize(frame, protocol)
    summary["gates"]["collinear_x_only_rejection"] = bool(
        len(rejection_checks) == len(seeds) * len(protocol["effects"]) and all(rejection_checks)
    )
    summary.update(
        protocol_id=protocol["protocol_id"],
        phase=phase,
        datasets=len(seeds) * 8,
        records=len(frame),
        elapsed_seconds=time.perf_counter() - started,
        protocol_sha256=sha256_file(PROTOCOL),
        source_hashes=source_hashes(),
        environment=environment(),
    )
    if phase == "assessment" and source_hashes() != frozen["source_hashes"]:
        raise ValueError("Sources changed during assessment")
    write_json(destination / "summary.json", summary)
    print(
        json.dumps(
            {
                "gates": summary["gates"],
                "datasets": summary["datasets"],
                "elapsed_seconds": summary["elapsed_seconds"],
            }
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("development", "freeze", "assessment"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_phase(args.phase, args.output.resolve())


if __name__ == "__main__":
    main()
