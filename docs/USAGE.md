# Running the PoC

Run commands from the repository root. This guide covers installation, CLI
profiles, exports, the demand handoff and repository checks. Current progress
is in the [documentation index](README.md); benchmark-specific commands and
frozen reporting procedures are in [BENCHMARK.md](BENCHMARK.md#5-reproducing-week-2-benchmarks).

## Install and run

Requires Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/). Use the project
environment; no system packages are modified. The checked-in lockfile pins the
versions tested on Python 3.11.9 / Windows.

```powershell
uv sync --locked
uv run python -m gsm_poc run-all --config configs/demo.toml
uv run streamlit run src/gsm_poc/ui/app.py
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
the [documentation index](README.md) and its linked evidence.

The verified TLC-context example recorded in [validation](submission/days/20261003/validation.md) has
199 valid bootstrap draws per estimator and a supported scenario with intervals. The full-month
data build also completed. This record describes its October 3 run; later
reporting evidence is indexed in the [documentation index](README.md).

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
| prepare-demand | Freeze choice handoff; prepare request rates and initial snapshot | `--model-run-id`, `--snapshot` |
| simulate-marketplace | Fixed-supply request/vehicle trajectories and operational metrics | `--demand-run-id`, `--rules`; optional `--requests` CSV |
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

### Reading result statuses

Read execution, result quality and interval quality separately:

| Field/category | Interpretation |
|---|---|
| Manifest stage status: `pending`, `running`, `succeeded`, `failed` | Whether the batch stage completed; success alone does not establish a supported forecast |
| Effect/scenario status and support diagnostics | `not_identified`, `insufficient_support` or invalid probabilities withhold affected estimates/forecasts; retain the reason and attempted/failed counts |
| Interval status: `ok`, `interval_unstable`, `interval_unavailable` | A valid point estimate can coexist with a withheld interval; the quality rules are in [IDENTIFICATION.md](IDENTIFICATION.md#estimation-and-inference) |
| Simulation calibration status: `not_calibrated`, evidence C | A completed synthetic trajectory remains assumption-based and does not establish operational accuracy on GSM |

Missing or unavailable metrics are not zero. Keep failed bootstrap draws in quality
counts and reject invalid probabilities rather than clipping them. The broader
status vocabulary for planned modules is specified in the
[target engine design](reference/CORE_ENGINE_DESIGN.md#133-results-and-status).

## Week 3 demand handoff

`prepare-demand` reads a completed, checksum-verified choice run. It copies the
selected model/diagnostics/bootstrap, effects, splits, original scenario and held-out
contexts into `demand_bundle/`, preserving the source config/environment manifest.
It exports X/Y requests/hour as `expected_bookings / block_hours`, with baseline
rates alongside target rates. The quote population stays fixed in each block;
NONE contributes no requests. Prices affect choice once.

For a bounded synthetic development handoff, separate from Week 2 reporting:

```powershell
uv run python -m gsm_poc run-all --config configs/week3_demand.toml --run-id week3-choice-development-v1 --skip-monte-carlo
uv run python -m gsm_poc prepare-demand --config configs/week3_demand.toml --model-run-id week3-choice-development-v1 --snapshot configs/week3_snapshot.json --delta-x 0 --scenario-id baseline --run-id week3-demand-baseline-v1
uv run python -m gsm_poc prepare-demand --config configs/week3_demand.toml --model-run-id week3-choice-development-v1 --snapshot configs/week3_snapshot.json --delta-x 0.10 --scenario-id price-x-plus10 --run-id week3-demand-x-plus10-v1
```

The profile uses two zones, 15-minute blocks, seed 42, adjusted OLS and three
development bootstrap draws. It retains the default support threshold of 20
training blocks per selected context/price corner. The snapshot has two shared
X/Y vehicles and a two-hour horizon on January 26, 2024, in America/New_York to
match the frozen choice contexts. Fleet, shifts and SOC are synthetic assumptions;
they remain `not_calibrated`. The profile evaluates one development seed only.

Outputs in each demand run are `demand_plan.csv`/`.parquet`, `demand_result.json`
(X/Y/NONE reconciliation and availability), `baseline_snapshot.json`,
`demand_spec.json`, the frozen handoff and checksums in `manifest.json`.
`demand_result.usable_for_simulation` must be true before downstream use.
Insufficient support, unidentified effects or invalid probabilities withhold
rates as missing, with reasons. Execution may succeed while the forecast is
unavailable; check this gate rather than only the CLI exit code.

The bridge uses the source run's timezone, block duration and support thresholds;
current CLI config cannot relax them. It requires complete, nonoverlapping blocks
covering every snapshot zone; partial blocks or uncovered horizons are rejected.
Zero quote counts yield zero requests. `quote_sessions` is shared by X/Y rows;
use the result summary for the unduplicated population. Intervals remain
`interval_unavailable` for these block rates. These are expected requests at
evidence C, not completed trips or GSM operational forecasts.

Resume with the same demand run ID and arguments. Source, snapshot, policy, code,
environment and output checksums must match. The command uses a separate output
run and never modifies the frozen source run. The fixed-supply simulator consumes
this handoff; supply response, operational constraints and equilibrium remain later work.

## Week 3 fixed-supply simulation

`simulate-marketplace` reads a completed demand run with
`demand_result.usable_for_simulation=true` and verified checksums. Use a separate
output run. Its `simulation_inputs/` freezes the demand artifacts, source manifest,
rules and optional prescribed-request CSV. A continuation also freezes its parent
checkpoint and manifest. It reads no choice oracle and does no
model fitting. Prices are already reflected in the request rates.

First validate the two-vehicle fixture with three prescribed requests:

```powershell
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-demand-baseline-v1 --rules configs/week3_simulation.json --requests configs/week3_requests.csv --seed 42 --run-id week3-simulation-fixture-v2-verified
```

The current version 2 rules use a 300-second pickup deadline. The fixture has two
completed trips with 60-second waits, one request expiring at 08:06 local time,
and exactly four shared-fleet vehicle-hours. Its expected idle time is
`4 - 1320 / 3600` hours. Setting `max_wait_seconds` to `null` restores the
no-expiry fixture: three completed trips with waits of 60/60/660 seconds and idle
time `4 - 2280 / 3600` hours.
Prescribed mode bypasses the rate sampler and tests the event/state engine.

Then run baseline and target with the same snapshot, rules and seed:

```powershell
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-demand-baseline-v1 --rules configs/week3_simulation.json --seed 42 --run-id week3-simulation-baseline-v2
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-demand-x-plus10-v1 --rules configs/week3_simulation.json --seed 42 --run-id week3-simulation-x-plus10-v2
```

The development rules use piecewise Poisson arrivals; separate arrival and OD
streams are keyed by seed/zone/service/block, excluding policy and rate for paired
scenarios. The declared closed cluster has equally likely destinations in 161/162,
60-second same-zone or 180-second cross-zone pickup, and 600/900-second trips,
shared by X/Y. These are synthetic assumptions. Poisson realizes expected rates;
it does not replay finite quote sessions and can generate more requests than quotes.

Matching uses FIFO among matchable requests, then minimum pickup ETA and vehicle
ID. Acceptance is immediate, maximum pickup is 300 seconds, and a trip must finish
within the vehicle's fixed shift. Offline vehicles already in a shift remain
offline; future shifts activate. Static SOC below 0.1 is ineligible. SOC depletion,
charging, open-cluster boundaries and supply response remain unmodeled. Version 2
adds a nullable `max_wait_seconds` deadline from creation to pickup and an optional
`cancel_at` column in the prescribed-request CSV. Both terminate only queued or
pickup requests. A pickup completion wins a simultaneous termination event;
zero patience expires before dispatch. A canceled/expired pickup vehicle finishes
its existing leg before release, retaining that activity in the checkpoint.
Limits are 10,000 requests over the full demand horizon, 100,000 work units (SimPy
events, arrival draws and candidate checks) and 60 seconds. Exhaustion fails the
stage; it never publishes a completed forecast from partial processing.

Output CSV/Parquet tables are `requests`, `request_events` and `vehicle_intervals`.
JSON outputs are `simulation_result` (total/service counts, state-time accounting,
wait/idle/trips), `simulation_spec` and `end_snapshot`. Wait includes queue plus
pickup travel. In version 2, summary wait uses only pickups occurring in the
current window and retains each request's original creation time. Open requests
without pickup are censored; cancellation/expiry before pickup is a terminal
outcome with observed duration and no completed wait. No pickups gives missing
wait. p95 uses linear interpolation. The
half-open arrival horizon includes completions exactly at the end. Unfinished
requests remain open. Version 2 `end_snapshot.json` is an operational checkpoint:
it retains the full frozen arrival schedule, request history, shared roster,
pending events and event counters. The next window must start at its timestamp,
using the same demand plan, initial snapshot, rules and seed. Windows stay inside
the original demand horizon. Version 1 end snapshots cannot be continued.

Run two consecutive windows with separate output run IDs:

```powershell
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-demand-baseline-v1 --rules configs/week3_simulation.json --requests configs/week3_requests.csv --seed 42 --window-start 2024-01-26T08:00:00-05:00 --window-end 2024-01-26T08:04:00-05:00 --run-id week3-window-first-v2
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-demand-baseline-v1 --rules configs/week3_simulation.json --seed 42 --window-start 2024-01-26T08:04:00-05:00 --window-end 2024-01-26T10:00:00-05:00 --carry-in-run-id week3-window-first-v2 --run-id week3-window-second-v2
```

The continuation uses the checkpoint's arrival schedule; omit `--requests` or
supply the identical full schedule. Created/completed/canceled/expired counts
refer to events in this window. Request accounting is
`open_start + created = completed + canceled + expired + open_end`.
Request-table rows cover new arrivals and requests open at window start. Previously
terminal requests remain in checkpoint history, including those linked to an
unfinished aborted pickup, and do not count as carry-in demand.
CLI reuse with the same run ID reuses verified artifacts; `--carry-in-run-id`
continues operational time into a new output run.

Every output remains synthetic evidence C and `not_calibrated`; cancellation-rate,
charging, economics and full-chain intervals are explicitly unavailable. A single
paired trajectory does not estimate a stable policy effect. Use a new run ID after
code/environment changes; changing rules/requests within a compatible run invalidates
stage reuse. Historical demand runs remain valid frozen inputs with their original
code/environment metadata.

Historical version 1 development check on **2026-10-09, Asia/Bangkok**, using the frozen
`week3-demand-baseline-v1` / `week3-demand-x-plus10-v1` inputs and seed 42:

| Simulation run | Created requests | Completed trips | Open at end | Serviceable hours | Idle hours |
|---|---:|---:|---:|---:|---:|
| `week3-simulation-fixture-v1` | 3 | 3 | 0 | 4.0 | 3.366667 |
| `week3-simulation-baseline-v1` | 479 | 16 | 463 | 4.0 | 0.233333 |
| `week3-simulation-x-plus10-v1` | 436 | 17 | 419 | 4.0 | 0.116667 |

The two-vehicle fixture is capacity constrained under the sampled demand. All
remaining requests are queued under the no-cancellation assumption. The target's
extra completed trip reflects this particular arrival/OD trajectory, not evidence
of improved GSM throughput. Results and source/config/environment/checksums are
in each ignored `runs/<id>/` manifest and outputs. A fresh baseline replay
(`week3-simulation-baseline-replay-v1`) reproduced all nine CSV/Parquet/JSON output
artifacts byte for byte; CLI resume reused verified outputs. Source demand
artifacts/manifests were unchanged. Verification passed all 241 tests, Ruff
check/format, `ty`, request/time accounting and artifact checksums. No GSM
calibration or full-chain intervals were evaluated.

Version 2 development verification on **2026-10-09, Asia/Bangkok** used the same
frozen baseline demand and prescribed requests: `week3-simulation-fixture-v2-verified`
completed two trips, expired one request, conserved four vehicle-hours and recorded
3.633333 idle hours. The 08:00–08:04 / 08:04–10:00 runs
`week3-window-first-v2` and `week3-window-second-v2` used the same source-code
checksum and reproduced the continuous request event trace and final checkpoint
exactly. The parent checkpoint was frozen byte for byte; all five demand source
artifact/manifest checksums remained unchanged, and CLI reuse verified existing
outputs. All 286 tests, Ruff check/format and `ty` passed. Tests include aborted
pickup carryover, expiry/cancel timing, malformed checkpoint rejection, budget
failures and fractional-duration shift boundaries. These remain synthetic evidence
C checks; energy/charging, operational calibration and full-chain intervals were
not evaluated.

## Verification

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uvx ty check src/gsm_poc --error-on-warning
uv run pytest -q
```

Tests use deterministic fixtures and no network calls.
