# GSM Causal Marketplace PoC

An end-to-end proof of concept under development for causal modeling and scenario
evaluation in a ride-hailing marketplace, built on a reusable core engine.
The target combines demand/choice, compensation and supply, operational simulation,
equilibrium and traceable uncertainty, demonstrated through a dashboard and exports.
The code builds NYC TLC completed-trip marts, generates controlled X/Y/NONE
choices, compares OLS and DML, evaluates known effects, and exposes supported
price scenarios in Streamlit. The demand bridge converts choice forecasts into
requests per hour for an explicit zone/time scope and initial fleet snapshot.
The fixed-supply simulator turns those rates into synthetic request/vehicle
trajectories, completed trips, waiting times and idle vehicle-hours.

Synthetic and semi-synthetic behavior is evidence C. Public TLC trips provide
operational context; current results do not establish GSM elasticity, supply
response or ROI. The [documentation index](docs/README.md) describes scope,
progress, technical specifications and submission evidence.

## Code structure

```text
src/gsm_poc/
  __init__.py             Python package
  __main__.py             module entry point
  app.py                  Streamlit artifact reader
  artifacts.py            atomic files, hashes and run lifecycle
  build_context.py        train-only context templates
  build_marts.py          completed-trip operational marts
  build_silver.py         TLC normalization and quality flags
  cli.py                  command-line entry points
  config.py               configuration and date-scope validation
  demand.py               choice-to-request bridge and snapshot validation
  estimate.py             OLS / LinearDML and fitted model bundles
  evaluate.py             known-truth evaluation and seed checkpoints
  features.py             feature encoding and day-based splits
  generate.py             controlled choices and isolated oracle
  ingest.py               pinned TLC source ingestion
  marketplace_simulator.py fixed-supply event simulation and operational accounting
  pipeline.py             batch-stage orchestration and artifact reuse
  policy_benchmark.py     independent synthetic pricing-policy evaluation
  scenario.py             supported price scenarios
  swissmetro.py           separate public choice baseline
  uncertainty.py          day bootstrap with complete model refits
  validate.py             TLC schema and probability validation
  ui.css                  dashboard styles

configs/                  TOML profiles, synthetic snapshot, rules and request fixture
scripts/                  reporting runners, compute probes and statistical review
tests/                    deterministic fixtures and behavior coverage
docs/                     usage, architecture, contracts, roadmap and evidence
.github/workflows/        repository checks in CI
.streamlit/               Streamlit configuration
pyproject.toml            package, dependencies and tool configuration
uv.lock                   locked dependencies
```
