"""Documented command line interface with explicit dataset/model selection."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from gsm_poc.causal.scenario import ScenarioRequest
from gsm_poc.core.config import DGPS, ESTIMATORS, Config
from gsm_poc.pipeline.marketplace import evaluate_marketplace_run
from gsm_poc.pipeline.pipeline import Pipeline
from gsm_poc.pipeline.policy import (
    compare_policies_run,
    evaluate_policies_run,
    export_handoff_run,
    plan_experiment_run,
    reconcile_experiment_run,
)
from gsm_poc.pipeline.supply import (
    evaluate_supply_run,
    fit_supply_run,
    generate_supply_run,
    supply_scenario_run,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="GSM controlled marketplace PoC (evidence C)")
    commands = root.add_subparsers(dest="command", required=True)
    for name in (
        "ingest",
        "build",
        "generate",
        "fit",
        "evaluate",
        "scenario",
        "freeze-choice",
        "prepare-inference",
        "prepare-demand",
        "simulate-marketplace",
        "evaluate-marketplace",
        "compare-policies",
        "evaluate-policies",
        "plan-experiment",
        "reconcile-experiment",
        "export-handoff",
        "generate-supply",
        "fit-supply",
        "scenario-supply",
        "evaluate-supply",
        "run-all",
    ):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config", default="configs/demo.toml")
        cmd.add_argument("--run-id", help="Resume only a matching code/config/environment run")
        if name in (
            "compare-policies",
            "evaluate-policies",
            "plan-experiment",
            "reconcile-experiment",
            "export-handoff",
        ):
            cmd.set_defaults(dgp=None, seed=None, bootstrap_draws=None, estimator=None)
            if name == "compare-policies":
                cmd.add_argument("--demand-run-id", required=True)
                cmd.add_argument("--rules", type=Path, required=True)
                cmd.add_argument("--compensation", type=Path, required=True)
            if name in ("evaluate-policies", "plan-experiment"):
                cmd.add_argument("--comparison-run-id", required=True)
            if name == "evaluate-policies":
                cmd.add_argument("--truth-run-id", required=True)
            if name in ("compare-policies", "evaluate-policies", "plan-experiment"):
                cmd.add_argument("--spec", type=Path, required=True)
            if name == "reconcile-experiment":
                cmd.add_argument("--experiment-run-id", required=True)
                cmd.add_argument("--observations", type=Path, required=True)
            if name == "export-handoff":
                cmd.add_argument("--source-run-ids", nargs="+", required=True)
                cmd.add_argument("--max-bytes", type=int, default=268435456)
            continue
        if name == "evaluate-marketplace":
            cmd.set_defaults(dgp=None, seed=None, bootstrap_draws=None, estimator=None)
            cmd.add_argument("--baseline-demand-run-id", required=True)
            cmd.add_argument("--target-demand-run-id", required=True)
            cmd.add_argument("--rules", type=Path, required=True)
            cmd.add_argument("--compensation", type=Path, required=True)
            cmd.add_argument("--protocol", type=Path, required=True)
            continue
        if name.endswith("-supply"):
            cmd.set_defaults(dgp=None, seed=None, bootstrap_draws=None, estimator=None)
            if name in ("generate-supply", "evaluate-supply"):
                cmd.add_argument(
                    "--supply-spec", type=Path, default=Path("configs/week3_supply.json")
                )
            if name == "fit-supply":
                cmd.add_argument("--supply-run-id", required=True)
            if name == "scenario-supply":
                cmd.add_argument("--model-run-id", required=True)
                cmd.add_argument("--incentive-amount", type=float, required=True)
            if name == "evaluate-supply":
                cmd.add_argument("--protocol", type=Path, required=True)
            continue
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
        if name in ("scenario", "prepare-demand"):
            cmd.add_argument("--model-run-id", required=True)
            cmd.add_argument("--scenario-id", default="price-scenario")
            cmd.add_argument("--delta-x", type=float, default=0.10)
            cmd.add_argument("--delta-y", type=float, default=0.0)
            cmd.add_argument("--baseline-x", type=float, default=1.0)
            cmd.add_argument("--baseline-y", type=float, default=1.0)
        if name in ("freeze-choice", "prepare-inference"):
            cmd.add_argument("--model-run-id", required=True)
        if name == "prepare-demand":
            cmd.add_argument("--snapshot", type=Path, required=True)
        if name == "simulate-marketplace":
            cmd.add_argument("--demand-run-id", required=True)
            cmd.add_argument("--rules", type=Path, required=True)
            cmd.add_argument(
                "--compensation",
                type=Path,
                help="Frozen synthetic driver-pay and fare specification",
            )
            cmd.add_argument(
                "--requests", type=Path, help="Prescribed request CSV instead of Poisson arrivals"
            )
            cmd.add_argument(
                "--window-start", help="Offset-aware window start within demand horizon"
            )
            cmd.add_argument("--window-end", help="Offset-aware window end within demand horizon")
            cmd.add_argument(
                "--carry-in-run-id", help="Completed operational checkpoint run to continue"
            )
        if name == "scenario":
            cmd.add_argument(
                "--inference-method", choices=("analytic", "bootstrap"), default="analytic"
            )
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
        if args.command in (
            "compare-policies",
            "evaluate-policies",
            "plan-experiment",
            "reconcile-experiment",
            "export-handoff",
        ):
            stage = args.command.replace("-", "_")
            if set(pipeline.run.manifest["stages"]) - {stage}:
                raise ValueError("Week 4–5 commands require separate output runs")
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
        elif args.command == "freeze-choice":
            result = pipeline.freeze_choice(args.model_run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "prepare-inference":
            result = pipeline.prepare_inference(args.model_run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
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
            result = pipeline.scenario(
                request, args.model_run_id, args.zone, inference_method=args.inference_method
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "prepare-demand":
            result = pipeline.prepare_demand(
                args.model_run_id,
                args.snapshot,
                ScenarioRequest(
                    args.scenario_id,
                    args.baseline_x,
                    args.baseline_y,
                    args.delta_x,
                    args.delta_y,
                    interval_level=config.evaluation.interval_level,
                ),
                estimator=args.estimator,
            )
            print(
                json.dumps(
                    {key: value for key, value in result.items() if key != "blocks"},
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
            )
        elif args.command == "evaluate-marketplace":
            result = evaluate_marketplace_run(
                pipeline.run,
                args.baseline_demand_run_id,
                args.target_demand_run_id,
                args.rules,
                args.compensation,
                args.protocol,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "compare-policies":
            result = compare_policies_run(
                pipeline.run, args.demand_run_id, args.rules, args.compensation, args.spec
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "evaluate-policies":
            result = evaluate_policies_run(
                pipeline.run, args.comparison_run_id, args.truth_run_id, args.spec
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "plan-experiment":
            result = plan_experiment_run(pipeline.run, args.comparison_run_id, args.spec)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "reconcile-experiment":
            result = reconcile_experiment_run(
                pipeline.run, args.experiment_run_id, args.observations
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "export-handoff":
            result = export_handoff_run(pipeline.run, args.source_run_ids, args.max_bytes)
            print(
                json.dumps(
                    {k: v for k, v in result.items() if k != "inventory"},
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
            )
        elif args.command == "simulate-marketplace":
            result = pipeline.simulate_marketplace(
                args.demand_run_id,
                args.rules,
                args.requests,
                window_start=args.window_start,
                window_end=args.window_end,
                carry_in_run_id=args.carry_in_run_id,
                compensation_path=args.compensation,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "generate-supply":
            result = generate_supply_run(pipeline.run, args.supply_spec)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "fit-supply":
            result = fit_supply_run(pipeline.run, args.supply_run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "scenario-supply":
            result = supply_scenario_run(pipeline.run, args.model_run_id, args.incentive_amount)
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == "evaluate-supply":
            result = evaluate_supply_run(pipeline.run, args.supply_spec, args.protocol)
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
