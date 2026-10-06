"""Documented command line interface with explicit dataset/model selection."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from gsm_poc.config import DGPS, ESTIMATORS, Config
from gsm_poc.pipeline import Pipeline
from gsm_poc.scenario import ScenarioRequest


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="GSM controlled marketplace PoC (evidence C)")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("ingest", "build", "generate", "fit", "evaluate", "scenario", "run-all"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config", default="configs/demo.toml")
        cmd.add_argument("--run-id", help="Resume only a matching code/config/environment run")
        cmd.add_argument("--dgp", choices=DGPS)
        cmd.add_argument("--seed", type=int)
        cmd.add_argument("--bootstrap-draws", type=int)
        cmd.add_argument(
            "--estimator",
            choices=ESTIMATORS,
            help="Fit just this estimator and use it for scenarios",
        )
        if name in ("generate", "evaluate"):
            cmd.add_argument("--build-id", help="Explicit train-fitted TLC gold artifact ID")
        if name == "fit":
            cmd.add_argument("--dataset-id", help="Observed synthetic dataset to fit")
        if name in ("evaluate", "run-all"):
            cmd.add_argument("--seeds", type=int, help="Number of consecutive seeds per DGP")
        if name == "evaluate":
            cmd.add_argument("--dgps", nargs="+", choices=DGPS)
        if name == "run-all":
            cmd.add_argument(
                "--skip-monte-carlo",
                action="store_true",
                help="Still run one oracle comparison; skip repeated seed evaluation",
            )
        if name == "scenario":
            cmd.add_argument("--model-run-id", required=True)
            cmd.add_argument("--scenario-id", default="price-scenario")
            cmd.add_argument("--delta-x", type=float, default=0.10)
            cmd.add_argument("--delta-y", type=float, default=0.0)
            cmd.add_argument("--baseline-x", type=float, default=1.0)
            cmd.add_argument("--baseline-y", type=float, default=1.0)
            cmd.add_argument("--n-sessions", type=int, default=10000)
            cmd.add_argument("--zone", type=int)
            cmd.add_argument("--target-context-set", default=None)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = Config.load(args.config)
        if args.dgp or args.seed is not None:
            config = dataclasses.replace(
                config,
                simulation=dataclasses.replace(
                    config.simulation,
                    dgp=args.dgp or config.simulation.dgp,
                    seed=config.simulation.seed if args.seed is None else args.seed,
                ),
            )
        if args.estimator:
            config = dataclasses.replace(
                config,
                model=dataclasses.replace(
                    config.model, estimators=(args.estimator,), scenario_estimator=args.estimator
                ),
            )
        updates = {}
        if args.bootstrap_draws is not None:
            updates["bootstrap_draws"] = args.bootstrap_draws
        if getattr(args, "seeds", None) is not None:
            updates["seeds"] = args.seeds
        if getattr(args, "dgps", None):
            updates["dgps"] = tuple(args.dgps)
        if updates:
            config = dataclasses.replace(
                config, evaluation=dataclasses.replace(config.evaluation, **updates)
            )
        pipeline = Pipeline(config, args.run_id)
        if args.command == "run-all":
            pipeline.run_all(include_evaluation=not args.skip_monte_carlo)
        elif args.command == "ingest":
            pipeline.ingest()
        elif args.command == "build":
            pipeline.build()
        elif args.command == "generate":
            pipeline.generate(args.build_id)
        elif args.command == "fit":
            pipeline.fit(args.dataset_id)
            pipeline.method_evaluation()
            pipeline.scenario()
        elif args.command == "evaluate":
            pipeline.evaluate(args.build_id)
        elif args.command == "scenario":
            if args.target_context_set is not None:
                target_context_set = args.target_context_set
            elif args.zone is not None:
                target_context_set = f"zone_{args.zone}"
            else:
                target_context_set = config.scenario.target_context_set
            request = ScenarioRequest(
                args.scenario_id,
                args.baseline_x,
                args.baseline_y,
                args.delta_x,
                args.delta_y,
                args.n_sessions,
                config.evaluation.interval_level,
                target_context_set=target_context_set,
            )
            result = pipeline.scenario(request, args.model_run_id, args.zone)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.command != "run-all":
            pipeline.run.complete()
        print(f"Run: {pipeline.run.run_id}\nArtifacts: {pipeline.run.path}", flush=True)
        return 0
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(f"gsm-poc: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
