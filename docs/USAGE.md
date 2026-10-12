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
| simulate-marketplace | Fixed-online offers, request/vehicle trajectories and operational metrics; optional 100%-fare settlement | `--demand-run-id`, `--rules`; optional `--requests` CSV, `--compensation` and window/carry-in flags |
| evaluate-marketplace | Frozen paired baseline/price, controlled-truth and workload assessment | `--baseline-demand-run-id`, `--target-demand-run-id`, `--rules`, `--compensation`, `--protocol` |
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
| Interval validation/calibration | `technical_checks_only` and `not_evaluated_for_this_run` distinguish numerical stability from empirical coverage; nominal 95% is not a measured coverage guarantee |
| Simulation calibration status: `not_calibrated`, evidence C | A completed synthetic trajectory remains assumption-based and does not establish operational accuracy on GSM |

Missing or unavailable metrics are not zero. Keep failed bootstrap draws in quality
counts and reject invalid probabilities rather than clipping them. The broader
status vocabulary for planned modules is specified in the
[target engine design](reference/CORE_ENGINE_DESIGN.md#133-results-and-status).

## Week 2 choice handoff

`freeze-choice` packages all estimators from a completed fit, method evaluation
and scenario run. It needs no fleet snapshot, simulator, refit or oracle access.
Use a separate output run:

```powershell
uv run python -m gsm_poc freeze-choice --config configs/tlc_quick.toml --model-run-id 20261003T130951-df24a7e4 --run-id week2-choice-handoff-20261011-v2
uv run python -m gsm_poc scenario --config configs/tlc_quick.toml --model-run-id week2-choice-handoff-20261011-v2 --scenario-id price-x-plus10 --delta-x 0.10 --delta-y 0 --inference-method bootstrap --run-id week2-choice-replay-20261011-v2
```

The package keeps the original model/effects/scenario files and source manifest
byte for byte. `choice_handoff.json` records their checksums, source configuration,
training environment, packaging environment, scope, units and review status.
`current_scenario_result.json` separately applies the current support and interval
checks to the saved model/draws and original request. Read its current status;
historical `scenario_result.json` remains evidence for its training revision.
The dashboard and scenario/demand consumers use the original training configuration
and support thresholds. `--estimator` selects another frozen estimator for a
scenario; consumer settings cannot lower those thresholds.

Repeat either command with identical arguments to verify reuse. Resume after a
failed freeze retries the stage, verifying source hashes and replacing incomplete
outputs atomically. A changed output prevents reuse. Code/environment changes
require a new run ID. Replay requires this repository and its environment, but
no original source run, training dataset or oracle files once the package is ready.
This reproduces saved-model inference, not a fresh training/bootstrap run.

The historical TLC package reproduces the numeric outputs but its all-context
scenario fails the current context-specific support gate. Coverage limitations
were accepted by Bun on 11/10/2026 as a
[technical exception](submission/days/20261011/week2_hybrid_acceptance.md).
Technical stability does not certify calibration or close support gaps.

## Hybrid choice inference

Causal `scenario()` and UI default to `inference_method="analytic"`; select
`"bootstrap"` for the frozen day-bootstrap baseline. CLI scenarios default to
analytic. Existing batch `Pipeline.scenario()` calls default to bootstrap for
`fit`, `run-all` and handoff replay; pass analytic explicitly in new integrations.
New point fits persist compact covariance; bootstrap refits do not. Analytic is
qualified for adjusted OLS (HC3/t) and DML (block score/normal), with individual
delta-method elasticity intervals and joint baseline covariance.

Prepare an older frozen package once in a separate run:

```powershell
uv run python -m gsm_poc prepare-inference --config configs/tlc_quick.toml --model-run-id week2-choice-handoff-20261011-v2 --run-id week2-hybrid-inference-20261011-v3
uv run python -m gsm_poc scenario --config configs/tlc_quick.toml --model-run-id week2-hybrid-inference-20261011-v3 --inference-method analytic --run-id week2-hybrid-scenario-20261011-v3
```

Preparation verifies original observed/metadata hashes (early fit manifests use
the fit observed hash plus generation's registered metadata hash), and refits at most once
per qualified estimator, checking point coefficients against the saved baseline.
Original bytes and bootstrap contracts remain intact. No oracle or new bootstrap
draws are needed. Missing/stale covariance is explicitly unavailable/rejected;
UI never fits or silently falls back. `prepare-demand` retains point request rates
and unavailable block-rate intervals. Manifest integrity checks still read
registered bytes, while analytic inference avoids bootstrap deserialization.

Keep `Technically stable` and the 88–89% cross-effect/scenario coverage warning.
The accepted exception does not certify 95% coverage for every output or
calibration of each run. Reproduce historical research with its frozen source
snapshot and original inference engine.

## Week 2 support and interval diagnostics

The support diagnostic reads a completed choice package, freezes eligible
zone/weekend/peak strata using training counts, and replays the unchanged
all-context scenario alongside the restricted scope. Both price points retain
the source support thresholds. Excluded context/session weights are reported;
the restricted forecast describes its own fixed quote population.

```powershell
.venv/Scripts/python.exe scripts/diagnose_week2_support.py --model-run-id week2-choice-handoff-20261011-v2 --run-id week2-support-new-review
```

Use a new run ID on each execution. `runs/<id>/` contains the training support
table, saved scope, restricted contexts, both scenario results and a checksummed
diagnostic report. The source package remains unchanged.

The interval runner preserves fitting and individual day-bootstrap percentile
intervals. It freezes configuration, source hashes, code/environment and fresh
development seeds before generating data, and saves raw coefficient draws and
per-seed metrics. Start with one seed to measure cost:

```powershell
.venv/Scripts/python.exe scripts/diagnose_week2_intervals.py --config configs/default.toml --build-id 214dd5a1184bd3705e66 --output-root .cache/week2-ci-new-probe --seed-start 41001 --seeds 1 --dgps RCT_SYN --estimators adjusted_ols --bootstrap-draws 199
```

The same interface supports the bounded RCT/null development study with
`--seeds 20 --dgps RCT_SYN NULL_EFFECT`, a separate `--estimators dml` probe,
and nested endpoint checks with `--bootstrap-draws 999`. Always use a fresh
output directory. Historical reporting seeds 20001–20100 and probe 19001 are
rejected. The example range reproduces the current development study; an
independent new study needs an unused range. Counts, failures, actual bootstrap SD, empirical SD, widths, tail
misses and exact binomial uncertainty remain visible. The 199-prefix comparison
uses requested draws, preserving failures. A development study or sufficient
draw count does not establish nominal coverage; fit/interval methods and
acceptance thresholds require their own frozen final evaluation.

Measured results and their immutable identities are in the
[11/10 diagnostic evidence](submission/days/20261011/support_interval_diagnostic.md).

### Development interval-method comparison

The standalone comparator reads a completed interval diagnostic with verified
protocol/artifact checksums, raw coefficient draws and the saved source context.
It freezes percentile (baseline), basic and BCa candidates before comparison.
Use a separate, new output directory:

```powershell
.venv/Scripts/python.exe -m scripts.compare_week2_intervals --diagnostic-root .cache/week2-ci-comparison-development-20261011 --output-root .cache/week2-ci-methods-new-review
```

All candidates use the same observed coefficient and 199 saved original-day
bootstrap draws. The comparator reconstructs the seed's dataset, verifies the
refitted point estimates, and deletes each of the 20 original training days in
turn for BCa jackknife refits. Each 19-day fit refits the learned components with
the original seed and original-day fold groups. Quote counts and held-out
contexts stay fixed. Failed refits, unavailable intervals and unresolved BCa
tails remain visible; no clipping or percentile fallback fills missing BCa values.

Outputs are `protocol.json`, `status.json`, `seed_metrics.parquet`, `summary.csv`
and per-job metrics/jackknife Parquet tables with JSON metadata and checksums.
Read `completed_with_failures` and per-effect unavailable reasons alongside the
method summaries and paired common-valid-seed comparisons. Coverage and null
false positives retain exact binomial uncertainty and attempted/valid
denominators. It selects no winner and changes no production
interval, nominal 95% level, support threshold or choice package. Only the four
theta coefficient cells are compared; elasticity and scenario intervals need
their own evaluation. The 20-seed development cohort and single DML probe cannot
establish final calibration. See the
[comparison protocol](BENCHMARK.md#development-interval-method-comparison) and
[11/10 comparison evidence](submission/days/20261011/interval_method_comparison.md).

### Development day-jackknife variance sensitivity

`scripts.compare_week2_variance` reads a completed, checksummed interval-method
comparison and reuses its saved points and all 20 original-day jackknife fits.
It performs no generation, fitting or bootstrap. Use a new output directory:

```powershell
.venv/Scripts/python.exe -m scripts.compare_week2_variance --comparison-root .cache/week2-ci-methods-development-20261011 --output-root .cache/week2-ci-variance-new-review
```

The individual `day_jackknife_t` candidate uses the saved original full-data
point, jackknife variance and a Student-t critical value with 19 degrees of
freedom. A missing, duplicate, failed or nonfinite omission, or degenerate
variance, leaves the candidate unavailable; no omission is dropped and no
fallback replaces it. Baseline percentile/basic/BCa results remain unchanged.

Read coverage, null false positives, widths, attempted/available counts and
paired changes alongside the RMS jackknife SE versus between-seed SD on the
same valid seeds. A single DML probe cannot provide that SD comparison.
This reuses development seeds 42001–42020 and adds no independent evidence or
production method. The frozen t reference and generic jackknife for DML require
empirical assessment. Formula/limits are in
[IDENTIFICATION](IDENTIFICATION.md#development-day-jackknife-variance-sensitivity),
with results in the
[variance evidence](submission/days/20261011/interval_variance_comparison.md).

### Fresh DML day-jackknife pilot

`scripts.pilot_week2_dml_variance` uses the verified comparison's configuration
and source context to generate fresh development seeds 43001–43005 for RCT_SYN
and NULL_EFFECT. DML and adjusted OLS share each generated seed as paired
estimators; each gets an original full-data fit and 20 delete-one-day refits.
It constructs the same individual `day_jackknife_t` candidate, with no bootstrap
draws. The frozen outer study permits at most 20 estimator jobs / 420 fits,
including 210 DML fits; run one RCT seed first to measure cost, then continue the
frozen remaining cohort in new directories without counting that probe twice.

```powershell
.venv/Scripts/python.exe -m scripts.pilot_week2_dml_variance --comparison-root .cache/week2-ci-methods-development-20261011 --output-root .cache/week2-dml-variance-new-probe --seed-start 43001 --seeds 1 --dgps RCT_SYN
```

The remaining RCT jobs use `--seed-start 43002 --seeds 4 --dgps RCT_SYN`; NULL
jobs use `--seed-start 43001 --seeds 5 --dgps NULL_EFFECT`, each with a new output
directory. Only seeds 43001–43005 are permitted. Outputs retain
`protocol.json`, `status.json`, `seed_metrics.parquet`, `summary.csv`,
`paired_estimators.csv`, per-job point/jackknife/metrics tables and metadata,
including DML original-day fold assignments and a saved source context.

The former percentile/basic/BCa candidates are not run on these fresh seeds.
The paired baseline here is adjusted OLS, not the historical interval methods.
Read coverage, null false positives, widths, failure/availability counts and
matched-cohort SE/SD comparisons. Five seeds per DGP provide very limited
precision. The pilot changes no production method and establishes no final
calibration; individual theta results do not transfer to elasticity/scenarios.
See the [pilot protocol](BENCHMARK.md#fresh-dml-day-jackknife-pilot) and
[pilot evidence](submission/days/20261011/dml_variance_pilot.md).

## Week 2 score inference diagnosis

The standalone research controller captures DML out-of-fold residuals without
changing the model point or production percentile intervals. Freeze the protocol
before generating seeds; the plan and every stage require fresh output paths:

```powershell
.venv/Scripts/python.exe -m scripts.diagnose_week2_score_inference --plan .cache/new-score-plan.json --freeze-source .cache/week2-ci-methods-development-20261011
.venv/Scripts/python.exe -m scripts.diagnose_week2_score_inference --plan .cache/new-score-plan.json --output-root .cache/new-score-dml-probe --stage dml_probe
```

Inspect the two probe jobs before expansion; the frozen guard is 30 seconds per
DML fit or any fit/inference failure. Then execute `--stage ols`,
`--stage dml_remainder` and `--stage fold_probe`, each in a different fresh output
directory, with at most two processes and one native thread per process.
The fixed protocol allows 100 OLS seeds and 20 DML seeds per RCT/null DGP;
the probe is included, not discarded. The separate 4/10-fold sensitivity uses
three of those DML seeds and is excluded from coverage denominators.

The study produces joint theta/baseline influence, covariance, individual theta,
elasticity and three scenario intervals, original-day scores, fold diagnostics,
failure counts, source snapshots and checksum registries. Compare block and day
methods on the same seeds; do not compare their gains with historical cohorts as
if paired. Full-context scenario calibration remains a diagnostic when the
existing support gate rejects that population. Replaying older research studies
requires their frozen source revision, since residual capture changes the code
hash even though the default numerical method is unchanged. See the
[protocol](BENCHMARK.md#development-score-inference-diagnosis) and
[evidence](submission/days/20261011/score_inference_diagnostic.md).

## Week 2 conditional variance audit and independent assessment

The oracle variance controller checks the existing OLS development cohort with
no model fits. Freeze first, then use a fresh output directory:

```powershell
.venv/Scripts/python.exe -m scripts.diagnose_week2_oracle_variance --plan .cache/new-oracle-plan.json --freeze-source docs/submission/days/20261011/results/score_inference
.venv/Scripts/python.exe -m scripts.diagnose_week2_oracle_variance --plan .cache/new-oracle-plan.json --output-root .cache/new-oracle-review
```

The independent assessment freezes block methods and its diagnostic family
before generating the reserved 45001–45100 cohort:

```powershell
.venv/Scripts/python.exe -m scripts.validate_week2_inference --plan .cache/new-independent-plan.json --freeze-source docs/submission/days/20261011/results/score_inference
.venv/Scripts/python.exe -m scripts.validate_week2_inference --plan .cache/new-independent-plan.json --output-root .cache/new-independent-rct --dgp RCT_SYN
.venv/Scripts/python.exe -m scripts.validate_week2_inference --plan .cache/new-independent-plan.json --output-root .cache/new-independent-null --dgp NULL_EFFECT
```

Execute the two DGP stages with at most two concurrent experiment processes.
This is a reproduction of the frozen cohort, not a source of additional
independent evidence. There are 400 point fits and no bootstrap or delete-day
refits. Inspect both stage statuses, complete seed/output denominators and
unavailable intervals before combining summaries. `assessment_tests` applies
the frozen binomial/Holm screen to the combined summary, removing repeated
baseline-before tests only; raw metrics retain those rows. Keep the original
source revision for replay. Oracle covariance is an audit reference and is
never used by this assessment's fitting or inference. The
[closeout report](submission/days/20261011/week2_inference_closeout.md) records
results, checksums and the separate support/GSM limits.

## Week 3 demand handoff

`prepare-demand` reads a completed, checksum-verified choice fit or `freeze-choice`
package. It copies the
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
run and never modifies the frozen source run. The fixed-online simulator consumes
this handoff. Endogenous supply response and equilibrium are outside the current PoC.

## Week 3 fixed-online PoC

Use the [current PoC scope](WEEK3_POC_SCOPE.md) and version-3 rules in
`configs/week3_poc.json`. The roster remains online over the observation horizon,
shared across X/Y. Snapshot `shift_start`/`shift_end` fields must cover that horizon;
they are compatibility fields, not scheduled work allocations. Busy/reserved
drivers cannot serve another trip, and refusal leaves the driver online. No
incentive response, online/offline dynamics or income-supply solver is run.

The current verified sources are `week3-poc-demand-baseline-20261012-v3` and
`week3-poc-demand-x-plus10-20261012-v3`. These frozen packages are the recommended
inputs below. Six registered training-data files in the historical
`week3-choice-development-v1` run are missing (actual SHA unavailable), so its
original training-run integrity fails. The directory is preserved; no training-data
repair or refit occurred. Current demand was prepared afresh from verified,
byte-preserved frozen model/context artifacts in the valid baseline demand package.
The [closeout](submission/days/20261012/week3_poc_closeout.md)
records this lineage and gate checks. For a new workspace, prepare matching
baseline/target demand under fresh IDs using the handoff procedure above.
A separate output run freezes verified artifacts, rules, compensation and any prescribed CSV.
No choice fitting or oracle reads occur. Price already enters the demand rates
and changes the displayed fare once through the approved tariff.

```powershell
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-baseline-20261012-v3 --rules configs/week3_poc.json --requests configs/week3_requests.csv --compensation configs/week3_compensation.json --seed 42 --run-id week3-poc-fixture-v3
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-baseline-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --seed 42 --run-id week3-poc-baseline-v3
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-x-plus10-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --seed 42 --run-id week3-poc-x-plus10-v3
```

Matching is FIFO among matchable requests, then minimum pickup ETA/vehicle ID.
Each pending offer reserves a vehicle in `dispatch` state. The declared
price-independent Bernoulli acceptance probability is 0.8, response delay 3 seconds,
timeout 10 seconds and maximum 20 attempts per request. Each driver/request pair
uses one stable seeded draw; refusal cannot trigger a new draw for the same pair.
The original 300-second pickup deadline is not restarted by offers. Customer
cancellation or expiry withdraws pending offers; late responses cannot revive them.
Acceptance, rejection, timeout and withdrawal are recorded separately. SOC stays
fixed; charging is outside this PoC. Limits remain 10,000 requests, 100,000 work
units and 60 seconds per trajectory; exhausted budgets fail the stage.

CSV/Parquet exports are `requests`, `request_events`, `vehicle_intervals`,
`driver_offers` and `offer_events`, plus the financial tables described below.
`driver_offers` includes new offers and those pending at the window start, with
immutable context, displayed fare/driver pay, timestamps and final/current state.
`offer_events` retains transition timestamps. `simulation_result.json` reports
online drivers/hours, request and state-time balances, trip/wait/idle counts,
offer outcomes and the 100%-fare earnings summary. `simulation_spec.json` freezes
the rules/seed/references; `end_snapshot.json` retains continuation state.

Acceptance is `accepted / (accepted + rejected + timed_out)` among responses
resolved in the current window, including carry-in offers. Withdrawn/pending
offers are excluded and shown separately; no responses means an unavailable rate.
Online hours include idle, dispatch reservations, pickup and on-trip time; do not
multiply hours by acceptance. Wait summaries retain observed/censored populations
and show missing wait when no pickup occurs. Single-trajectory CI is unavailable.

For continuation, use consecutive windows and a separate run for each. Keep the
same demand, initial snapshot, rules, compensation and seed; a V3 checkpoint does
not accept legacy V2 rules. Pending offers/reservations, attempts, original
deadlines, remaining responses/timeouts and immutable terms survive the boundary.
Prior completion earnings are not paid again.

```powershell
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-baseline-20261012-v3 --rules configs/week3_poc.json --requests configs/week3_requests.csv --compensation configs/week3_compensation.json --seed 42 --window-start 2024-01-26T08:00:00-05:00 --window-end 2024-01-26T08:00:02-05:00 --run-id week3-poc-window-first-v3
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-baseline-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --seed 42 --window-start 2024-01-26T08:00:02-05:00 --window-end 2024-01-26T10:00:00-05:00 --carry-in-run-id week3-poc-window-first-v3 --run-id week3-poc-window-second-v3
```

### Independent operational assessment

`evaluate-marketplace` freezes two completed supported demand runs with the same
model/source and roster/horizon, V3 rules, compensation and protocol. Use unchanged
baseline pricing and a supported target. Pilot seeds 72001–72003 are development;
assessment seeds 73001–73100 are separate from the pilot and must not be retuned
after use. Paired arms and workload checks intentionally share seeds; the total
job count is not a count of mutually independent draws.
Both protocols cap the evaluator at 600 seconds. See
[the protocol and gates](BENCHMARK.md#week-3-fixed-online-operational-assessment).

```powershell
uv run python -m gsm_poc evaluate-marketplace --config configs/week3_demand.toml --baseline-demand-run-id week3-poc-demand-baseline-20261012-v3 --target-demand-run-id week3-poc-demand-x-plus10-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --protocol configs/week3_poc_pilot.json --run-id week3-poc-pilot-v3
uv run python -m gsm_poc evaluate-marketplace --config configs/week3_demand.toml --baseline-demand-run-id week3-poc-demand-baseline-20261012-v3 --target-demand-run-id week3-poc-demand-x-plus10-20261012-v3 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --protocol configs/week3_poc_assessment.json --run-id week3-poc-assessment-v3
```

Exports are `marketplace_evaluation.json`, `marketplace_seed_records.csv`,
`marketplace_controlled_records.csv` and `marketplace_workload_records.csv`, with
frozen inputs and source snapshots. They retain attempted/available/failed counts,
paired baseline/target/delta means and individual Student-t intervals across seeds.
These intervals measure Monte Carlo mean uncertainty conditional on fixed fitted
demand and rules; they do not cover causal estimation uncertainty, full-chain
coverage or unmeasured driver behavior. Execution and gate status are separate.
The [12 October assessment](submission/days/20261012/week3_poc_closeout.md) completed
303/303 jobs with all frozen gates passed. The scoped PoC is technically verified
and ready for Bun's review; GSM/original research acceptance remains separate.

### View completed simulations

```powershell
uv run streamlit run src/gsm_poc/ui/app.py -- --workspace . --run-id week3-poc-baseline-v3
```

An explicit simulation `--run-id` opens the simulation dashboard directly, before
loading choice artifacts; this route has no outer choice tabs. Without that
explicit ID, choose **Simulation results** and its separate **Simulation run ID**
selector in a mixed workspace. With no choice fit, the simulation view is still available.
The reader verifies completed-run checksums, reports invalid artifacts explicitly
and shows the same online/trip/offer/pay metrics and CSV/JSON exports. It does not
execute the engine. Choice model selectors and analytic inference defaults remain
unchanged. Every simulation stays evidence C, `not_calibrated`; GSM causal effects,
costs/profit/ROI and operational/full-chain CI remain unevaluated.

## Week 3 fixed-supply simulation

The [current PoC scope](WEEK3_POC_SCOPE.md) assumes a fixed online roster and keeps
individual acceptance separate. Incentives, online/offline response and behavioral
scheduling are outside the current increment. This section preserves **legacy
V1/V2 immediate-acceptance controls** and their historical measurements. Use the
[V3 fixed-online commands](#week-3-fixed-online-poc) for the current PoC.

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

The legacy version 2 rules use a 300-second pickup deadline. The fixture has two
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
charging, GSM economics and full-chain intervals are explicitly unavailable. A single
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

## Week 3 minimal compensation

Enable the approved minimum pay assumption with `--compensation`: drivers receive
**100% of the fare displayed on the app for a completed trip**. Without this option,
the existing fixed-supply simulation remains available without financial outputs.
GSM's actual compensation policy is still unknown; this development rule is
synthetic evidence C.
Use a new run ID when adding or removing `--compensation`, so older financial
artifacts cannot be mistaken for the current simulation's outputs.

```powershell
uv run python -m gsm_poc simulate-marketplace --config configs/week3_demand.toml --demand-run-id week3-poc-demand-baseline-20261012-v3 --rules configs/week3_poc.json --requests configs/week3_requests.csv --compensation configs/week3_compensation.json --seed 42 --run-id week3-compensation-fixture-v3
```

The explicit tariff fixture has `baseline_fares` X=Y=1 `SYNTHETIC_UNIT` and fixed
`driver_fare_share=1`. Effective displayed fare is
`baseline_fare * baseline_multiplier * (1 + delta)` using the frozen demand policy.
For example, baseline multiplier 1 with a +10% X price change gives X fare/pay
1.1 per completed trip and Y fare/pay 1. These normalized amounts are not VND or
measured GSM fares. Demand multipliers alone never supply monetary units.

`simulation_inputs/` freezes the compensation specification alongside the demand
policy. Separate CSV/Parquet `quote_terms` and `driver_pay_terms` preserve the
pre-simulation fare and pay conditions; `earnings_ledger` records settlement,
`driver_income` reports all roster drivers and `earnings_result.json` summarizes
the accounting scope/status. Only completed trips earn the quoted amount.
Canceled/expired requests earn zero; trips still open at the window end remain
unsettled. Offering or accepting a trip alone earns no pay under this rule.

Income per presence-hour uses all nonoffline state intervals, including idle and
unavailable time. Zero-trip drivers remain in the roster summary with zero settled
earnings. A driver with zero presence hours has unavailable hourly income, rather
than an invented zero rate. Amounts describe settled gross driver pay; no costs,
net driver earnings, GSM revenue/profit or ROI are inferred.

For financial continuation, pass the same `--compensation` specification and
`--carry-in-run-id` as well as the same demand, policy, rules and seed. The parent
checkpoint's `compensation_context` must match the frozen financial contract and
terms. Each output ledger settles only completions within its current window,
including carry-in trips completing there; prior completions are never paid again.
Changing financial terms or adding/removing compensation across a continuation
requires a fresh scenario from an initial snapshot.

This adds conditional earnings accounting to the fixed roster. Online hours and
the declared V3 acceptance rule remain independent of realized pay; the scientific
incentive-response package stays separate. Realized earnings are not a predecision
income treatment; an income
elasticity or automatic fare-to-hours response is not identified by this rule.
No operational/equilibrium intervals or GSM calibration are supplied.

## Week 3 controlled labor supply

The [supply contract and evaluation protocol](WEEK3_SUPPLY.md) implement the
driver-response scientific package independently of the fixed-roster simulator.
No GSM data or bootstrap-choice files are required. The development profile uses
800 eligible drivers, seven complete eight-hour shift opportunities and offered
incentive levels 0/20 in `SYNTHETIC_UNIT`; these assumptions do not describe GSM.

```powershell
uv run gsm-poc generate-supply --config configs/demo.toml --run-id week3-supply-data --supply-spec configs/week3_supply.json
uv run gsm-poc fit-supply --config configs/demo.toml --run-id week3-supply-fit --supply-run-id week3-supply-data
uv run gsm-poc scenario-supply --config configs/demo.toml --run-id week3-supply-target --model-run-id week3-supply-fit --incentive-amount 20
uv run gsm-poc evaluate-supply --config configs/demo.toml --run-id week3-supply-pilot --supply-spec configs/week3_supply.json --protocol configs/week3_supply_pilot.json
uv run gsm-poc evaluate-supply --config configs/demo.toml --run-id week3-supply-assessment --supply-spec configs/week3_supply.json --protocol configs/week3_supply_assessment.json
```

Use a separate output run for each stage. Source runs must be complete with valid
checksums; do not reuse an unrelated choice run. Supply commands use their explicit
JSON spec/protocol rather than the choice DGP/bootstrap/estimator flags. A synthetic
project configuration is required. Rerun a matching stage/run to verify and reuse
its artifacts; code/environment changes require a new run ID.

Generation stores `supply/observed/driver_decisions.parquet` and `contract.json`,
separate oracle means and generator assumptions. Fit copies only the observed
inputs, exports `models/supply/model_bundle.json` and `supply_effects.csv` with
population, unit, evidence, support and individual CI status. Scenario exports
`supply_scenario.json`; only the baseline and target amount are supported. Hour
changes cover the same frozen eligible cohort/calendar, not a physical schedule.
Benchmark exports per-seed `supply_benchmark_records.csv`, `supply_benchmark.json`,
frozen spec/protocol and source snapshots under the checked run manifest.

Assessment uses 100 fresh RCT seeds and 100 disjoint null seeds. Report unavailable
intervals and exact binomial uncertainty alongside empirical coverage; a controlled
gate pass does not certify nominal coverage or complete Week 3. No pipeline reads
these estimates as a physical driver/vehicle admission plan yet. Supply runs are
not added to the existing choice-only dashboard selector.

## Verification

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uvx ty check src/gsm_poc --error-on-warning
uv run pytest -q
```

Tests use deterministic fixtures and no network calls.
