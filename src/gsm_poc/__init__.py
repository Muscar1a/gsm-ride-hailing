"""Controlled first-two-week GSM Causal Marketplace proof of concept."""

from __future__ import annotations

import sys

# Direct submodules
import gsm_poc.causal.benchmarks.policy as _policy
import gsm_poc.causal.benchmarks.swissmetro as _swissmetro
import gsm_poc.causal.estimate as _estimate
import gsm_poc.causal.evaluate as _evaluate
import gsm_poc.causal.features as _features
import gsm_poc.causal.scenario as _scenario
import gsm_poc.causal.uncertainty as _uncertainty
import gsm_poc.core.artifacts as _artifacts
import gsm_poc.core.config as _config
import gsm_poc.core.validators as _validators
import gsm_poc.data.context as _data_context
import gsm_poc.data.ingest as _data_ingest
import gsm_poc.data.marts as _data_marts
import gsm_poc.data.silver as _data_silver
import gsm_poc.pipeline.pipeline as _pipeline_pipeline
import gsm_poc.simulation.demand as _demand
import gsm_poc.simulation.dgp as _dgp
import gsm_poc.simulation.marketplace as _marketplace
import gsm_poc.ui.app as _ui_app

# Subpackages
from gsm_poc import causal, core, data, pipeline, simulation, ui

# Backward-compatible attribute access on package
artifacts = _artifacts
config = _config
validators = _validators
validate = _validators
build_silver = _data_silver
build_marts = _data_marts
build_context = _data_context
ingest = _data_ingest
features = _features
estimate = _estimate
uncertainty = _uncertainty
scenario = _scenario
evaluate = _evaluate
policy = _policy
policy_benchmark = _policy
swissmetro = _swissmetro
generate = _dgp
demand = _demand
marketplace = _marketplace
marketplace_simulator = _marketplace
app = _ui_app

# Forward legacy module names in sys.modules
sys.modules["gsm_poc.artifacts"] = artifacts
sys.modules["gsm_poc.config"] = config
sys.modules["gsm_poc.validators"] = validators
sys.modules["gsm_poc.validate"] = validate
sys.modules["gsm_poc.build_silver"] = build_silver
sys.modules["gsm_poc.build_marts"] = build_marts
sys.modules["gsm_poc.build_context"] = build_context
sys.modules["gsm_poc.ingest"] = ingest
sys.modules["gsm_poc.features"] = features
sys.modules["gsm_poc.estimate"] = estimate
sys.modules["gsm_poc.uncertainty"] = uncertainty
sys.modules["gsm_poc.scenario"] = scenario
sys.modules["gsm_poc.evaluate"] = evaluate
sys.modules["gsm_poc.policy"] = policy
sys.modules["gsm_poc.policy_benchmark"] = policy
sys.modules["gsm_poc.swissmetro"] = swissmetro
sys.modules["gsm_poc.generate"] = generate
sys.modules["gsm_poc.demand"] = demand
sys.modules["gsm_poc.marketplace"] = marketplace
sys.modules["gsm_poc.marketplace_simulator"] = marketplace
sys.modules["gsm_poc.app"] = app

Config = _config.Config
Pipeline = _pipeline_pipeline.Pipeline

__version__ = "0.1.0"

__all__ = [
    "Config",
    "Pipeline",
    "__version__",
    "app",
    "artifacts",
    "build_context",
    "build_marts",
    "build_silver",
    "causal",
    "config",
    "core",
    "data",
    "demand",
    "estimate",
    "evaluate",
    "features",
    "generate",
    "ingest",
    "marketplace",
    "marketplace_simulator",
    "pipeline",
    "policy",
    "policy_benchmark",
    "scenario",
    "simulation",
    "swissmetro",
    "ui",
    "uncertainty",
    "validate",
    "validators",
]
