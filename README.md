# GSM Causal Marketplace PoC

A runnable implementation of the first two weeks in the GSM proposal and
[detailed design](docs/GSM_PoC_Hai_Tuan_Dau_Thiet_Ke_Cuoi.md). It builds operational
TLC marts, generates controlled X/Y/NONE choices, compares OLS and DML, evaluates
known effects, and exposes supported price scenarios in Streamlit.

**Simulated behavior is evidence C.** TLC records are completed NYC trips. The
PoC does not estimate GSM elasticity, supply response, canceled demand or ROI.

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
1,860 policy blocks and 93,000 quote sessions, all January dates, three estimators,
10 bootstrap draws and three seeds per configured DGP. The small intervals are
labeled unstable. The dashboard shows the most recent completed model run; choose
another in the sidebar or launch with `-- --run-id <id>`.

To use the public TLC data:

```powershell
uv run python -m gsm_poc run-all --config configs/tlc_quick.toml
```

This downloads the immutable January 2024 source (~451 MiB) plus zone lookup,
processes the five pickup zones for the month, fits context on January 1–20, and
shows the first seven days in the operational dashboard. Simulation uses 7,440
blocks / 372,000 sessions and 30 day-bootstrap draws. Dropoffs outside the cluster
are retained. Downloads are bounded and checked by size, schema and SHA-256.

`configs/default.toml` uses all 31 days for operations and targets 100 seeds across
five DGPs and 199 bootstrap draws. This is an expensive reporting configuration.
Measure a bounded run first; the profile is not a claim that this evaluation has
been completed. See [actual validation](docs/VALIDATION.md).

The verified TLC-context example is `20261003T130951-df24a7e4`: 199 valid bootstrap
draws per estimator and a supported scenario with intervals. The full-month
data build also completed. See the validation record for exact counts, measured
errors and the remaining 100-seed evaluation.

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
Carlo checkpoints preserve each attempted seed and its failures. No job runs in
response to a dashboard slider.

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
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run pytest -q
```

Tests use deterministic fixtures and no network calls. The optional browser smoke
script uses a separately launched local dashboard and an installed browser:

```powershell
uv run python scripts/check_dashboard.py --url http://127.0.0.1:8501 --browser "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
```

See [architecture](docs/ARCHITECTURE.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md),
[identification](docs/IDENTIFICATION.md), [benchmark protocol](docs/BENCHMARK.md),
and [GSM data contract](docs/GSM_DATA_CONTRACT.md).
Supply, matching/charging simulation, DiD and field switchback are next-phase work.
