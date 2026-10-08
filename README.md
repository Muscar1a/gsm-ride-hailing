# GSM Causal Marketplace PoC

Start with the [documentation index](docs/README.md) for current progress,
the active roadmap, technical references and submission evidence.

A runnable implementation of the first two weeks in the
[GSM proposal](docs/reference/GSM_Causal_Marketplace_Proposal.md), following the
[shared data contract](docs/GSM_DATA_CONTRACT.md). It builds operational
TLC marts, generates controlled X/Y/NONE choices, compares OLS and DML, evaluates
known effects, and exposes supported price scenarios in Streamlit.

**Simulated behavior is evidence C.** TLC records are completed NYC trips. The
PoC does not estimate GSM elasticity, supply response, canceled demand or ROI.

## Current status

Latest measured evidence: **2026-10-07 17:13:28, Asia/Bangkok**.
Week 2 compute and statistical review are complete: 500/500 reporting seed jobs,
the separate Swissmetro baseline and 40/40 development policy-value jobs have
results. **Full Week 2 acceptance remains open** for interval-calibration
limitations, the final demand/choice handoff and reviewer confirmation.
See the [acceptance review](docs/submission/days/20261007/acceptance_review.md)
and [roadmap](docs/ROADMAP.md) for evidence and remaining work.

## Install and run

Requires Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/). Use the project
environment; no system packages are modified. The checked-in lockfile pins the
versions tested on Python 3.11.9 / Windows.

```powershell
uv sync --locked
uv run python -m gsm_poc run-all --config configs/demo.toml
uv run streamlit run src/gsm_poc/app.py
```

The offline demo needs no raw-data download. It uses explicit synthetic contexts,
1,860 policy blocks and 93,000 quote sessions, three estimators,
10 bootstrap draws and three seeds per configured DGP. The small intervals are
labeled unstable. The dashboard shows the most recent completed model run; choose
another in the sidebar or launch with `-- --run-id <id>`.

To use the public TLC data:

```powershell
uv run python -m gsm_poc run-all --config configs/tlc_quick.toml
```

This downloads the pinned TLC source (~451 MiB) plus zone lookup,
processes the five pickup zones for the month, fits context on the first 20 days, and
shows the first seven days in the operational dashboard. Simulation uses 7,440
blocks / 372,000 sessions and 30 day-bootstrap draws. Dropoffs outside the cluster
are retained. Downloads are bounded and checked by size, schema and SHA-256.

The v0 TLC adapter covers only the pinned source month recorded in configuration
and manifests. TLC ingest and builds reject scopes outside that source coverage.
Synthetic simulations can use other date scopes without claiming observed TLC coverage.

`configs/default.toml` uses all 31 days for operations and targets 100 seeds across
five DGPs and 199 bootstrap draws. This is an expensive reporting configuration.
Measure a bounded run first. Executed profiles and acceptance are recorded in
the [documentation index](docs/README.md) and its linked evidence.

The verified TLC-context example recorded in [validation](docs/submission/days/20261003/validation.md) has
199 valid bootstrap draws per estimator and a supported scenario with intervals. The full-month
data build also completed. This record describes its October 3 run; later
reporting evidence is linked in [Current status](#current-status).

## Commands

Every command accepts `--config`, optional `--run-id`, `--seed`, `--dgp`,
`--estimator` and `--bootstrap-draws`. IDs are printed after successful execution.

| Command | Purpose | Dependency |
|---|---|---|
| ingest | Download / verify immutable TLC sources | Network on first run |
| build | Silver, operational mart, train-only context | Invokes ingest |
| generate | Policy/session/block/oracle tables | TLC needs `--build-id`, or build in the same run |
| fit | Models, uncertainty, oracle method check, example scenario | `--dataset-id` |
| evaluate | Checkpointed repeated-seed evaluation | Optional TLC `--build-id`; `--seeds`, `--dgps` |
| scenario | Scenario from a completed model | `--model-run-id` |
| run-all | Complete batch workflow | Synthetic or TLC profile |

Examples:

```powershell
uv run python -m gsm_poc run-all --config configs/demo.toml --skip-monte-carlo
uv run python -m gsm_poc run-all --config configs/demo.toml --dgp HIDDEN_CONFOUNDING
uv run python -m gsm_poc run-all --config configs/demo.toml --dgp COLLINEAR_PRICE --skip-monte-carlo
uv run python -m gsm_poc generate --config configs/demo.toml --seed 43
uv run python -m gsm_poc fit --config configs/demo.toml --dataset-id <dataset-id> --seed 43
uv run python -m gsm_poc scenario --config configs/demo.toml --model-run-id <run-id> --delta-x 0.10 --delta-y 0 --n-sessions 10000
uv run python -m gsm_poc evaluate --config configs/demo.toml --seeds 20 --dgps RCT_SYN OBSERVED_CONFOUNDING
```

Resume an interrupted stage with its run ID and the same effective CLI overrides.
Reuse requires matching data, config, source code, lockfile/environment and
output checksums. After changing code or dependencies, start a new run. Monte
Carlo checkpoints preserve each attempted seed and its estimator-specific failures;
a failed estimator does not discard another estimator's valid results. Per-seed metrics
record failure types/messages, and checkpoints retain each estimator's status. Seeds
with any estimator failure are retried on resume; successful checkpoints are reused.
No job runs in response to a dashboard slider.

Fit reuse checks both observed blocks and the dataset manifest. Changed metadata
invalidates reuse; a source kind, DGP or seed that conflicts with the run configuration
is rejected before replacing model outputs.

Method-evaluation reuse checks the current observed data, dataset metadata,
oracle, diagnostics, fitted models and bootstrap bundles. Scenario reuse also
checks its evaluation contexts and bootstrap bundle. A changed input reruns the
affected stage even when the dataset ID or model bytes are unchanged.

## Data, models and exports

Ignored `data/` stores source, silver, gold and generated tables. Simulations keep
`observed/` separate from `oracle/`. Ignored `runs/<id>/` stores manifests,
models, diagnostics, effects, bootstrap draws, evaluation and scenario exports.
Only local completed runs with verified artifacts are loaded by the dashboard.

- `effects.csv`: common effect matrix, elasticity, baseline denominator, units,
  individual bootstrap intervals/status, source kind, evidence and run ID.
- `scenario_result.json`: X/Y/NONE probabilities, changes in percentage points,
  assumed sessions, expected bookings, matrix, support and interval status.
- `method_metrics.csv`: one-run estimates against truth; this is not empirical coverage.
- `evaluation/evaluation_metrics.csv`: per-DGP/cell bias, RMSE, coverage, exact
  binomial intervals and the number of attempted/valid runs.
- `manifest.json`: hashes, seed, code revision, package versions, stage status,
  timings and artifact checksums.

For a +10% X price change, the model uses `log(1.1)`, not `0.1`. Rows are choice
outcomes and columns are prices. The formula predicts net probability changes;
it does not identify individual switching customers. Prices outside 0.90–1.10
or missing joint support have no official forecast. Invalid probabilities are
rejected at every context. Small bootstrap runs withhold scenario intervals.

## Verification

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uvx ty check src/gsm_poc --error-on-warning
uv run pytest -q
```

Tests use deterministic fixtures and no network calls.

See the [documentation index](docs/README.md), [roadmap](docs/ROADMAP.md),
[architecture](docs/ARCHITECTURE.md),
[identification](docs/IDENTIFICATION.md), [benchmark protocol](docs/BENCHMARK.md),
and [GSM data contract](docs/GSM_DATA_CONTRACT.md).
Supply, matching/charging simulation, DiD and field switchback are next-phase work.

The [shared data contract](docs/GSM_DATA_CONTRACT.md) requests eight raw source
groups over the latest 12 months and defines formats and stage inputs/outputs.
The separate Swissmetro choice benchmark is implemented with person-level
holdouts, availability-aware multinomial logit and an intercept-only comparator.
The full repeated-seed coverage protocol has a frozen batch/checkpoint runner.
The separate development policy benchmark fits on train, selects constant grid
prices on validation, and scores frozen decisions using independent test truth:

```powershell
uv run python -m gsm_poc.policy_benchmark --config configs/policy_development.toml --run-id week2-policy-final-32001-32020
```

It reports normalized simulated gross booking value, uplift, regret and paired
seed uncertainty. This is evidence C with fixed quote traffic and no capacity or
cost model; it does not establish GSM revenue or interval calibration.
See [week-2 execution and resume instructions](docs/BENCHMARK.md#5-reproducing-week-2-benchmarks) and
[measured results](docs/submission/days/20261007/weekly_report.md).
Compute and statistical review are complete; full Week 2 acceptance remains open.

## Current PoC submission

Submission packages are saved in [docs/submission](docs/submission/README.md)
under `days/YYYYMMDD/`. The latest package has a
[Week 2 PoC report](docs/submission/days/20261007/weekly_report.md) and a
[short progress update](docs/submission/days/20261007/progress_update.md).

The [October 4 submission archive](docs/submission/days/20261004/README.md)
retains the earlier report, progress update, contributor plan and attachments.
The reports compare current progress with the
[full initial proposal](docs/reference/GSM_Causal_Marketplace_Proposal.md).
