# Benchmark protocol: core engine, method accuracy and business value

## Objective and protocol

The benchmark should establish where the method works, whether it supports better
pricing decisions, and eventually whether those decisions improve GSM's business.
It must allow zero uplift, negative uplift and a simpler estimator winning.

| Layer | What it establishes | Implementation / evidence |
|---|---|---|
| Controlled method benchmark | Recovery of known effects under specified assumptions | Implemented in `evaluate.py`; reporting results in the [Week 2 report](submission/days/20261007/weekly_report.md), earlier measurements in [historical validation](submission/days/20261003/validation.md) |
| Separate Swissmetro choice baseline | Predictive choice performance on held-out people | Implemented in `swissmetro.py`; MNL versus intercept-only results in the [Week 2 report](submission/days/20261007/weekly_report.md) |
| Controlled pricing-policy benchmark | Quality of decisions against independent simulated truth | Implemented in `policy.py`; development profile and results in the [Week 2 report](submission/days/20261007/weekly_report.md) |
| Core engine validation | State/accounting correctness, repeatability, failure behavior and measured operating limits | Demand bridge and fixed-supply development checks exist; full engine protocol and release evidence remain required |
| GSM offline policy evaluation | Estimated value under verified real-data identification and support | Requires GSM logs and a separate evaluator |
| GSM randomized validation | Incremental realized revenue under the tested deployment | Requires a designed and executed GSM experiment |

Good effect estimates do not by themselves establish revenue uplift. The choice
scenario stage outputs simulated quote choices with a fixed viewer population.
The separate simulator produces synthetic completed trips and operational metrics;
actual GSM revenue and profit remain unevaluated.

The reporting coverage protocol uses a frozen snapshot, batches of at most five
seeds, and reporting seeds 20001–20100. Runtime probe 19001 is excluded.
[Execution and resume instructions](#reporting-execution-and-compute-provenance)
below record the frozen source and executed CPU schedule. Current progress is
indexed in [README.md](README.md); gate
conclusions are recorded in the [acceptance review](submission/days/20261007/acceptance_review.md).
Execution completion and statistical acceptance are separate statuses.

## 1. Method benchmark

Keep the existing naive OLS, adjusted OLS and LinearDML comparison. Use identical
data, day splits, seeds, weights and evaluation contexts for each estimator.

Run all five existing cases: randomized prices, observed confounding, hidden
confounding, null effects and collinear prices. Record:

- Per-cell theta bias and RMSE, with absolute errors when truth is zero.
- Frozen-test scenario probability RMSE and invalid-probability frequency.
- Bootstrap interval coverage and null false positives, with binomial intervals.
- Attempted/valid/failed counts, identification rejections and runtime.

Fit and validation failures are recorded separately for each estimator on a shared
generated seed. A rejected estimator does not remove another estimator's valid
measurements. A failure to generate the shared data is recorded for every estimator.

The preconfigured technical targets for RCT_SYN are theta RMSE at most 0.10
per cell and scenario probability RMSE at most 0.02. They are controlled-DGP
targets, not business success criteria. Hidden confounding is a stress case;
collinear prices should reject separate effects. Adjusted OLS matches the current
additive DGP well, so DML need not outperform it.

A bounded fresh-seed point-accuracy run uses:

```powershell
uv run python -m gsm_poc evaluate --config configs/demo.toml --seed 10001 --seeds 20 --bootstrap-draws 0 --dgps RCT_SYN OBSERVED_CONFOUNDING HIDDEN_CONFOUNDING NULL_EFFECT COLLINEAR_PRICE
```

This has 20 seeds per case and no bootstrap intervals; coverage and false-positive
performance remain unmeasured by this run. The existing reporting configuration
targets 100 seeds and 199 bootstrap draws. Benchmark one seed before scaling it;
the measured TLC-context 199-draw fit took approximately 8.6 minutes on this
machine. Point accuracy and interval calibration are separate reporting gates.

This fresh-seed run completed as `20261003T135730-1ae94396`: all 100 seed jobs
finished with no failed jobs. Its measured results and limitations are recorded
in [VALIDATION.md](submission/days/20261003/validation.md#fresh-seed-point-accuracy-benchmark).

## 2. Controlled pricing-policy benchmark

The initial implementation uses `configs/policy_development.toml`: independent
seeds **32001–32020**, RCT_SYN and OBSERVED_CONFOUNDING, synthetic contexts,
7,440 blocks / 372,000 quote sessions per seed, 50-tree nuisance forests,
five original-day folds and no day-bootstrap refits. This development protocol
is separate from the frozen 500-job coverage evaluation.

Both X and Y are declared owned hypothetical services, each with a normalized
baseline fare of 1. The policy class is one constant joint price action for all
contexts. Every method uses the same nine-action grid. Unchanged prices and a
prespecified 10% X discount with unchanged Y are the simple comparators. Support
requires at least one training block per joint action and zone/weekend/peak
stratum; that development minimum does not establish operational overlap.

Models fit training days only. Each learner selects the highest predicted gross
booking value on validation, checking each candidate's support and probability
simplex. Ties prefer unchanged prices, then grid order. Decisions are saved in
`selected_policies.json` before the evaluator accesses test truth. The evaluator
joins held-out oracle baselines by dataset/block keys and applies the known DGP
matrix, independently of the learner. Its upper reference is the best constant
test action within the same train-supported grid. Unchanged nonintervention is
always retained as the fallback/reference; a support or learning failure is
recorded explicitly. Test rejection records an unavailable value and never
selects a replacement using test results.

Run the fixed development profile:

```powershell
.venv/Scripts/python.exe -m gsm_poc.causal.benchmarks.policy --config configs/policy_development.toml --run-id week2-policy-final-32001-32020
```

`runs/<run_id>/policy/` contains the frozen protocol, per-seed decisions/results,
model bundles, `seed_results.csv`, `summary.csv`, `paired_differences.csv` and
`report.json`. The run manifest records config/code/lock/environment and every
output checksum. Repeating the command reuses verified completed outputs;
changing code/config/environment requires a new run ID. An interrupted policy
stage is recomputed in full; its per-seed files are audit records, unlike the
resumable coverage checkpoints.

Summary intervals are unadjusted 95% Student-t intervals for means across
independent seeds, including paired policy differences on common test contexts.
They describe development variability across seeds, not day-bootstrap calibration
or uncertainty for one deployed policy. Failed values retain attempted/expected
denominators; fallback values retain learning failures and reasons. Zero or
negative uplifts and ties are kept.

### Freeze the business objective

Specify which services GSM owns, which prices it can change, baseline fares,
and currency. Completed trips, fulfillments, wait times, cancellations, and idle
vehicle-hours constitute the primary operational benchmark; simulated gross booking
value provides commercial comparison. If Y is a competitor, keep its price
fixed and exclude its bookings from GSM revenue. If both services belong to GSM,
include substitution between them. Real GSM profit and ROI are conditional on
confirmed financial policies from GSM.

Until these inputs are supplied, monetary results are unavailable. A toy study
may use explicitly declared illustrative fares or normalized price units, with
the output named **simulated gross booking value**. TLC fares must not silently
be substituted for hypothetical X/Y fares.

For that controlled study, value is:

```text
V(policy) = sum_contexts N(context) ×
            sum_owned_services p(service | context, policy) ×
            baseline_fare(service, context) × price_multiplier(service, context)
```

This assumes the quote population is fixed and each booking completes and pays
the stated fare. It omits cancellations, capacity, traffic response, refunds and
operating costs. It cannot be labeled realized GSM revenue, contribution margin
or profit.

### Compare decisions fairly

Use the same supported action set for every learner, initially the finite
0.90/1.00/1.10 grid for controllable prices. Check joint/context support and
probability validity for every candidate. Include:

1. The unchanged-price policy, always available as a fallback.
2. A declared simple pricing rule.
3. A pricing policy selected using naive OLS.
4. A pricing policy selected using adjusted OLS.
5. A pricing policy selected using DML.
6. The oracle's best policy within the same action/constraint set, as an upper
   reference available only in a controlled benchmark.

Fit on training days; use validation days to choose the policy and any tuning
settings. Freeze it before final-test evaluation. Learners cannot access oracle
parameters or probabilities. Only the evaluator may score the frozen policies
using held-out oracle outcomes. Evaluating a policy only with the same fitted
model that selected it would make the benchmark circular. Policy learning and
independent value evaluation have distinct roles; see
[Athey and Wager](https://arxiv.org/abs/1702.02896).

Report on the same test contexts for all policies:

- Value per 1,000 quote sessions, in the explicitly declared units.
- Absolute and relative uplift over unchanged pricing; relative uplift is
  unavailable when baseline value is zero.
- Paired differences against the simple rule and both OLS policies.
- Regret: oracle value minus learned-policy value, within the shared action set.
- Conversion/expected-choice changes, rejected candidates, fallback frequency
  and runtime.
- Per-seed results and uncertainty for paired differences, preserving failed
  seeds. Separate variability across independent simulated seeds from day
  resampling within one dataset.

Bootstrap the complete fit-and-select procedure if the target is performance of
the learning procedure. Resampling outcomes for an already frozen policy measures
a different uncertainty target. Name the target explicitly and keep final-test
data out of policy selection.

Do not change the DGP, seed list or constraints after seeing final results to
obtain positive uplift. The current DGP may give several estimators the same best
grid action; then their policy values tie even if coefficient RMSE differs.
More challenging cases must be motivated and declared before fresh evaluation.

## 3. GSM offline validation

Required data include nonbooking quote sessions, displayed options and prices,
policy assignments and their probabilities/rules, completion/cancellation
events, recognized revenue/payment adjustments, promotions, driver payroll and
incentives, other direct costs, fixed/shared expense sources and allocation
inputs, plus operational availability. Agree join keys, accounting scope,
currency, recognition periods, cost categories and feature availability before
fitting. Completed TLC trips cannot supply this.

When financial and accounting data become available from GSM, the full economic
comparison is evaluated as `delta_profit = profit(target) - profit(baseline)`.
Each profit equals confirmed GSM-recognized revenue minus every applicable
direct and allocated cost under one finance-approved
definition. Reconcile category totals and source coverage in both arms, including
zero-trip driver pay. Use the same approved allocation bases and versions; do
not double-subtract bonuses already recorded in payroll. Do not count competitor
bookings, gross customer payments or driver payments as interchangeable revenue.
This is profit for the declared GSM scope, not company-wide net income.

Report `contribution_margin = revenue - variable_cost` separately only when
variable costs are complete. Calculate the optional
`incentive_roi = delta_profit / delta_incentive_cost` only for an isolated
incentive contrast at the same customer price, when profit is supported and
incremental incentive cost is positive. A combined price/incentive policy needs
the price-only policy as its comparator for this ratio. Profit already subtracts
incentives once. Missing cost pools, coverage or allocation rules leave profit
and profit-based ROI `not_evaluated` with reasons, without invalidating completed
operational and demand benchmarks; a supported partial margin
must keep its own label. The toy policy benchmark reports simulated gross
booking value; it does not measure GSM contribution margin, profit, ROI or
economic impact.

When assignment propensities and the identification assumptions are credible,
use an independent policy evaluator with inverse-propensity and doubly robust
estimates, overlap diagnostics, effective sample size and clustered uncertainty.
Keep policy learning and final evaluation separate. Doubly robust evaluation
combines outcome and assignment models; it does not remove missing support or
hidden confounding. See the original
[Dudik, Langford and Li paper](https://www.microsoft.com/en-us/research/publication/doubly-robust-policy-evaluation-and-learning-2/).

The current discrete price grid is convenient for this comparison. Arbitrary
continuous prices need an explicitly justified evaluation approach; exact action
matching and discrete inverse-propensity formulas do not automatically apply.
If logs cannot support the proposed actions, report value as unidentifiable.

## 4. GSM profit-impact experiment

Compare the frozen candidate policy against existing pricing using a randomized
design appropriate for the marketplace. A zone/time switchback is a candidate;
interference between zones and carryover determine whether it is suitable.
Block duration, washout and inference require design, not a generic A/B toggle.
See [Bojinov, Simchi-Levi and Zhao](https://arxiv.org/abs/2009.00148).

Pre-register incremental GSM profit in the declared scope as the primary
business outcome, its minimum worthwhile uplift, accounting/coverage rules,
power calculation, assignment unit, analysis period, uncertainty method and
stopping rule. Use an A/A logging, ledger-reconciliation and assignment check
before the treatment comparison.

Measure profit over comparable assigned zones/blocks or a declared common
exposure period. Include all owned-service revenue to capture substitution and
all applicable driver pay, incentives and other costs, including allocated
fixed/shared expenses under the same approved basis. Revenue, contribution
margin and completion, cancellation, wait, availability and customer effects
are explanatory outcomes or guardrails. Revenue per quote may also be useful,
but quote traffic may itself respond to pricing; do not silently hold that
denominator fixed.

Report profit uplift with its confidence interval and cost bridge. A business
success criterion requires the agreed worthwhile profit gain and acceptable
guardrails. A positive point estimate with an interval spanning zero is
inconclusive. If complete financial measurement is unavailable, report the
profit outcome as unavailable rather than declaring success from trips or
revenue alone. A losing policy is a valid benchmark outcome.

Only an executed, appropriately analyzed GSM study can support a claim about
GSM profit impact in the population, prices and operating conditions tested.
Neither synthetic recovery nor simulated policy uplift establishes that claim.

## Core engine validation protocol

This protocol defines required validation as engine capabilities are implemented.
The two-vehicle development fixture is one correctness case. Release conclusions
require evidence for the implemented scope under the
[engine delivery standard](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard).

| Layer | Cases and independent checks |
|---|---|
| Deterministic correctness | Hand-computable trajectories and stock/flow balances; request partition, vehicle state-time, shared fleet, energy/chargers and ledgers; no double assignment |
| Continuation and replay | Frozen prescribed event schedules across window boundaries versus one continuous run, including busy vehicles/open requests; seeded replay and operational checkpoint restoration preserve applicable scheduler/random state |
| Statistical and scenario validation | Existing five demand DGPs; controlled supply/compensation truth; independent baseline holdout; unchanged policy, price/incentive actions and paired-seed comparisons; retain bias/error/coverage and failed counts |
| Stress and failure behavior | Zero demand/supply/response, zero-base bonuses, fixed/variable compensation, zone heterogeneity/relocation, saturation, long waits/cancellation, low SOC/charging bottlenecks, carryover, corrupt inputs/artifacts, insufficient support, nonconvergence and budget exhaustion |
| Workload and integration | Headless scenarios at fixture, representative and declared upper workloads; vary fleet size, request volume, horizon and repeated seeds within the validated market scope |
| PoC integration | A supported scenario walkthrough from baseline/target comparison to dashboard and CSV/JSON; displayed/exported values, units, denominators, model/run references and statuses agree with the engine artifacts |

Freeze scope, datasets/configuration, development and evaluation seeds, baselines,
tolerances, repetitions and resource budgets before final evaluation. Measure
wall time, peak memory, request/event/candidate work counts and failure rates;
record hardware/environment and distinguish cold execution from artifact reuse.
Choose numerical budgets from bounded development measurements. No performance
or statistical acceptance is implied before the corresponding runs are recorded.

Keep stage reuse distinct from continuing operational time. Continuation checks
compare the same event schedules and modeled conditions; stochastic distribution
checks use independent seeds. Failed/rejected attempts remain in reported counts.
Analytic accounting, controlled statistical accuracy and real GSM calibration
have separate conclusions. Release gates are maintained in the
[core design](reference/CORE_ENGINE_DESIGN.md#173-acceptance-gates).

## 5. Reproducing Week 2 benchmarks

Run commands from the repository root with the configured environment.
Metrics and acceptance remain in the dated submission records.

### Swissmetro choice baseline

Download the public source without modifying it:

```powershell
New-Item -ItemType Directory -Force data/raw/swissmetro
Invoke-WebRequest -Uri https://transp-or.epfl.ch/data/swissmetro.dat -OutFile data/raw/swissmetro/swissmetro.dat -TimeoutSec 60
.venv/Scripts/python.exe -m gsm_poc.swissmetro --seed 31001
```

The module uses existing NumPy/SciPy dependencies; Biogeme is not required.
The fixed specification is two alternative-specific constants (Swissmetro
reference) and generic time/cost coefficients. The comparator fits only the
two constants. Both normalize over available alternatives.

All SP trip purposes are retained; unknown `CHOICE=0` and non-SP rows are
excluded with counts. Exact duplicate attributes are retained as separate
survey tasks. Time and cost are minutes and CHF, scaled by 100 for fitting.
The EPFL preparation convention sets incremental Train/Swissmetro cost to
zero for annual GA pass holders. No headway is interpreted as pickup ETA.

Seed 31001 permutes sorted person IDs into 70%/15%/15% train/validation/test
groups. Repeated responses stay together. Both models are specified before
evaluation, fit on train only, and reported on every split. There is no tuning
or selection on final test. `source_row` identifies a preserved source task;
`person_id` identifies the repeated respondent.

Outputs under `runs/<run_id>/swissmetro/`:

- `source_manifest.json`: source/dictionary/preparation URLs, SHA-256, byte
  count, verification time, and license limitation.
- `splits.json`: person membership and row counts.
- `report.json`: quality/exclusion counts, coefficients, optimizer/rank
  diagnostics, test log-loss difference, units and limitations.
- `metrics.csv` and `predictions.parquet`: row/person mean log loss, accuracy,
  probabilities and availability checks.

Use the printed run ID with `--run-id` to verify/reuse unchanged outputs.
Changed source bytes, code, environment or configuration invalidate reuse.
Raw data and run artifacts are ignored. The
[EPFL/Biogeme Data section](https://biogeme.epfl.ch/) explicitly lists these
datasets for research and education (reviewed 2026-10-07). This supplies use
evidence for the academic PoC. A dataset-specific license and redistribution
or commercial permission remain unconfirmed; do not infer them from the
software license. This supplementary review does not rewrite the sealed run's
source manifest or outputs.

References: [EPFL dictionary](https://transp-or.epfl.ch/biogeme-2.5/swissmetro.pdf),
[EPFL preparation](https://biogeme.epfl.ch/sphinx/_modules/biogeme/data/swissmetro.html),
[MNL specification](https://biogeme.epfl.ch/sphinx/auto_examples/swissmetro/plot_b01a_logit.html).

### Reporting execution and compute provenance

The reporting run uses seeds 20001–20100 for all five DGPs, with 199 original-day
bootstrap refits per identified estimator. Probe 19001 is excluded. The executed
snapshot is `.cache/week2-evaluation-574cf501-20261007`, with TLC context build
`214dd5a1184bd3705e66` from revision
`574cf501304a777827c2e04704d96a1ab563e1b2`.

The original sequential runner accepts the following command:

```powershell
.venv/Scripts/python.exe scripts/run_week2_coverage.py --snapshot .cache/week2-evaluation-574cf501-20261007 --build-id 214dd5a1184bd3705e66
```

The final reporting execution used the parallel coordinator with at most
30 workers, a 5 GiB RAM reserve, batches of five seeds and a six-hour batch timeout:

```powershell
.venv/Scripts/python.exe -u scripts/run_week2_parallel.py --snapshot .cache/week2-evaluation-574cf501-20261007 --build-id 214dd5a1184bd3705e66 --workers 30 --ram-reserve-gib 5 --batch-timeout-seconds 21600
```

Do not launch another runner while one is active; the shared OS lock rejects it.
Resume only after the recorded process exits, using the same source, config,
environment and context. Successful checkpoints are verified and reused;
an interrupted seed is rerun. Failures stop scheduling and retain useful error
context. Changed source/config/environment requires a new frozen spec rather
than rewriting the original evidence.

Outputs reside under `<snapshot>/week2_reporting/`: frozen spec, status,
execution metadata, pooled metrics and logs. Checkpoints reside under
`<snapshot>/runs/<batch_id>/evaluation/`. The local snapshot/cache is ignored by
Git. The [submitted result bundle](submission/days/20261007/results/week2/README.md)
preserves the frozen source/config/lock/context, scripts, logs and checkpoints in
`reproducibility.zip`, alongside metrics and checksums.

The final run completed 500/500 jobs on October 7. The snapshot source was kept
unchanged; the bounded checkpoint I/O adapter and recovery are identified in
the bundle's `execution.json` and `recovery_audit/`. Numerical results, recovery
hashes and acceptance are recorded in the
[acceptance review](submission/days/20261007/acceptance_review.md) and
[statistical review](submission/days/20261007/statistical_review.md).
