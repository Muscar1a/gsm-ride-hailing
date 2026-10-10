# GSM Causal Marketplace PoC

An end-to-end proof of concept under development to estimate and validate causal
rider-price sensitivity, driver labor supply and cross-service substitution in a
ride-hailing marketplace. The target uses identified responses for supported
policy forecasts, independent decision evaluation and experimental reconciliation,
with uncertainty, evidence and agreed service/driver guardrails. A reusable core
engine, operational simulation, marketplace equilibrium, dashboard and exports
support these outputs; real economics require the appropriate GSM definitions/data.
The code builds NYC TLC completed-trip marts, generates controlled X/Y/NONE
choices, compares OLS and DML, evaluates known effects, and exposes supported
price scenarios in Streamlit. The demand bridge converts choice forecasts into
requests per hour for an explicit zone/time scope and initial fleet snapshot.
The fixed-supply simulator turns those rates into synthetic request/vehicle
trajectories, completed trips, waiting times and idle vehicle-hours.

Synthetic and semi-synthetic behavior is evidence C. Public TLC trips provide
operational context; current results do not establish GSM elasticity, supply
response, revenue, profit or ROI. The [documentation index](docs/README.md) describes scope,
progress, technical specifications and submission evidence.

## Code structure

```text
gsm-ride-hailing/
├── src/gsm_poc/              # Core application package
│   ├── core/                 # Infrastructure, configuration, and artifact lifecycle
│   ├── data/                 # Medallion data pipeline (ingest, silver, marts, context)
│   ├── causal/               # Causal estimation, uncertainty, and price scenarios
│   │   └── benchmarks/       # Choice and pricing-policy benchmarks
│   ├── simulation/           # DGP generation, demand planning, and marketplace
│   ├── pipeline/             # Stage orchestration and artifact DAG execution
│   └── ui/                   # Streamlit dashboard application and view tabs
│       └── tabs/             # Operations, method evaluation, and scenario tabs
├── configs/                  # TOML profiles and pipeline configurations
├── scripts/                  # Coverage runners, compute benchmarks, and probes
├── tests/                    # Deterministic unit, integration, and coverage tests
├── docs/                     # Architecture, technical contracts, and roadmap
└── data/                     # Raw, processed, and synthetic artifacts (.gitignored)
```
