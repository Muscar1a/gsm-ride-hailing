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
The [current Week-3 PoC scope](docs/WEEK3_POC_SCOPE.md), agreed with Bun on
12/10/2026, holds an explicit driver roster online throughout the observation
horizon. Drivers may accept or reject individual requests; rejection must not
remove an online driver or create additional supply. Version-3 simulation implements
bounded per-offer acceptance, rejection, timeout and withdrawal, with frozen driver
terms and continuation checkpoints. The declared acceptance probability is synthetic
and independent of price; it is not an estimated GSM response.
The current PoC does not require incentives, endogenous online/offline decisions,
shift allocation or income-supply equilibrium.
The independent controlled supply package estimates offered-incentive effects on
participation and eligible-cohort labor/serviceable hours with driver-level
intervals and RCT/null benchmarks; it is preserved as separate scientific evidence,
outside the current PoC delivery path. The optional compensation fixture pays drivers
100% of the displayed app fare for completed trips and exports frozen terms,
earnings and presence-hour income. This is Bun's synthetic assumption while GSM
policy is unavailable. Fixed online supply and trip acceptance do not identify
driver labor elasticity; that part of the broader research target remains open.
`evaluate-marketplace` compares supported baseline/price scenarios with paired seeds,
controlled operational truth and bounded workload checks. Its Monte Carlo intervals
condition on the fitted demand and rules. Streamlit reads completed simulation runs
and exports the same results. The scoped Week-3 PoC is implemented, verified, and accepted by Bun on 12/10/2026
([acceptance](docs/submission/days/20261012/week3_poc_acceptance.md)): 609 tests and 303/303 assessment jobs passed.
See the [Week-3 closeout](docs/submission/days/20261012/week3_poc_closeout.md).
This technical result does not complete the original three-response research
objective or establish GSM behavior.

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
