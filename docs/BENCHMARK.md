# Benchmark protocol: core engine, method accuracy and business value

## Objective and protocol

The benchmark should establish where the method works, whether it supports better
pricing decisions, and eventually whether those decisions improve GSM's business.
The primary scientific targets are causal rider-price, driver-labor-supply and
own/cross-service responses, with supported policy forecasts and experimental
reconciliation. Simulator correctness supports forecasts that require operational
translation; it does not establish identification or real-world policy value.
It must allow zero uplift, negative uplift and a simpler estimator winning.

| Layer | What it establishes | Implementation / evidence |
|---|---|---|
| Controlled method benchmark | Recovery of known effects under specified assumptions | Implemented in `evaluate.py`; reporting results in the [Week 2 report](submission/days/20261007/weekly_report.md), earlier measurements in [historical validation](submission/days/20261003/validation.md) |
| Controlled offered-incentive benchmark | Recovery of participation and eligible-cohort labor/serviceable-hour effects, driver-level intervals and null false positives | Implemented in `causal/benchmarks/supply.py`; separate [contract/protocol](WEEK3_SUPPLY.md) and [independent assessment](submission/days/20261011/week3_supply_progress.md). Retained scientific evidence; schedule/income feedback are outside the current fixed-online PoC |
| Separate Swissmetro choice baseline | Predictive choice performance on held-out people | Implemented in `swissmetro.py`; MNL versus intercept-only results in the [Week 2 report](submission/days/20261007/weekly_report.md) |
| Controlled pricing-policy benchmark | Quality of decisions against independent simulated truth | Implemented in `policy.py`; development profile and results in the [Week 2 report](submission/days/20261007/weekly_report.md) |
| Fixed-online operational assessment | Conditional baseline/price simulation, known offer-mechanism recovery and workload measurements | Implemented in `simulation/evaluation.py` through `evaluate-marketplace`; [frozen Week-3 protocol](#week-3-fixed-online-operational-assessment). [12 October closeout](submission/days/20261012/week3_poc_closeout.md): 303/303 jobs and frozen gates passed for synthetic PoC scope, ready for Bun's review |
| Core engine validation | State/accounting correctness, repeatability, failure behavior and measured operating limits | Fixed-online offer, checkpoint and compensation checks implemented; broader energy/supply/equilibrium capabilities remain outside current PoC. Release conclusions require recorded evidence for the applicable scope |
| GSM offline policy evaluation | Estimated value under verified real-data identification and support | Requires GSM logs and a separate evaluator |
| GSM randomized validation | Measured causal effects and the preregistered business outcome under the tested deployment | Requires a designed and executed GSM experiment |

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

## Week 1 evaluation specification (prospective)

Week 1 defines how each causal result will be evaluated; it does not certify a
new model or rewrite an executed protocol. Estimands and identification rules
follow [IDENTIFICATION.md](IDENTIFICATION.md); decision populations, source grains
and proposed interfaces follow [ARCHITECTURE.md](ARCHITECTURE.md#research-table-schemas).
Milestone requirements follow [ROADMAP.md](ROADMAP.md#weekly-inputs-and-outputs).
The specification records, for each estimand, its population, treatment/outcome
units, horizon, identified scope, assumptions, baseline, split and inference plan,
diagnostics, acceptance criteria and unresolved inputs.

### Baselines and learner/evaluator separation

Declare the simplest valid comparator for each estimand before fitting. These
are the Week-1 baseline specifications; current controlled supply implementation
uses the no-response baseline and a fixed randomized driver-mean contrast under
its [separate protocol](WEEK3_SUPPLY.md). Conditional-hours regression and
operational driver-response integration remain prospective:

| Estimand | Baseline specification |
|---|---|
| Rider own-price response | No price response under unchanged policy, plus a simple covariate-adjusted price regression on the same outcome/population; retain naive OLS as a confounding diagnostic where applicable |
| Own/cross-service substitution | No policy-induced change, plus a simple joint-price response model on matched X/Y request-rate or conditional-choice outcomes; NONE/outside-option outcomes require complete quote/outcome logs; compare only the matrix columns/cells supported by assignment variation, not an invented full matrix |
| Driver participation and working hours | No incentive response, plus simple participation and conditional-hours regressions using eligible drivers, offered compensation and pretreatment context; evaluate total-hours response with nonparticipants/zero outcomes retained |
| Trip acceptance, if separately estimated | Constant acceptance among actual eligible offers, plus a simple response model using predecision offer terms; preserve its offer denominator and do not use it as the labor-supply baseline |

Conditional hours among participants is a descriptive/model component unless
separately identified: treatment can change who participates. The primary hours
response uses the eligible cohort and retains nonparticipants and zero outcomes.

Use the same data identity, splits, weights, support and outcome definition for
every method being compared. Fit preprocessing and response/nuisance models on
training data; validation selects policies and tuning settings. The learner sees
observed inputs;
controlled truth/oracle artifacts are isolated for the independent evaluator.
Freeze learned models and selected policies before final evaluation. An
evaluator may use controlled truth or a justified real-data identification design;
the learner's own fitted scenario score cannot be its sole evidence of value. See
[Athey and Wager](https://arxiv.org/abs/1702.02896).

### Split, inference and horizon specification

Distinguish quote/session or driver-decision observation units from policy
assignment clusters/blocks, analysis aggregates and the effect horizon. Keep
all records from an assignment episode and linked decision/outcome window
together; never treat quotes or offers inside one assigned block as independent
randomizations. Freeze temporal train/development/final boundaries and any gap
or washout around boundaries from the chosen horizon/carryover assumptions.
Fit transformations only on training data, using features available before each
decision; future earnings, waits and outcomes cannot enter pretreatment context.

Specify repeated-rider/driver handling against the generalization objective.
A new-entity holdout groups each entity's records; a future-period holdout may
retain repeated entities only with chronological feature availability and an
explicit dependence/inference plan. Preserve original entity, assignment and time
keys through nuisance folds and resampling. Choose clustering, block resampling
or randomization inference to match assignment, repeated entities, temporal
dependence and interference; independent quote-row resampling is insufficient.
Record the number of independent units and restrictions when too few clusters or
effective blocks support the requested uncertainty. Short price blocks must not
stand in for an unobserved longer-horizon shift-participation response.

Name the uncertainty target: bootstrap the complete fit-and-select procedure for
learning-procedure performance; resampling an already frozen policy's outcomes
targets that policy instead. This does not change the executed seed-level
Student-t intervals reported below.

After changing a method in response to final results, develop the revision on
development data and freeze a new protocol with a fresh final holdout or independent
evaluation seeds. Do not tune on old final outcomes or present their reuse as
fresh confirmation; retain historical conclusions for their original revision.
Freeze DGPs, seeds, action constraints and new stress cases before fresh evaluation;
do not change them after final results to obtain positive uplift.

### Prospective statistical gates and experiment strategy

Freeze estimand-specific tolerances before new final evaluation: known-truth
recovery bias/RMSE, supported forecast error, null/placebo behavior, nominal
interval coverage and false-positive rates, and interval availability/stability
under bounded refits and independent replicates. Report uncertainty for coverage
and false-positive rates, widths/endpoint stability, attempted/expected/valid/
failed/rejected counts and unavailable intervals. Coverage among valid intervals
must accompany its valid/attempted denominator; missing or failed intervals
cannot improve a pass rate. Placebo conclusions and stress cases retain their
identification limits. Initial controlled supply thresholds and their independent
assessment are recorded in [WEEK3_SUPPLY.md](WEEK3_SUPPLY.md); they do not certify
nominal coverage or GSM readiness. The historical demand targets below remain
confined to their frozen DGP/protocol.

Week 1 also records a preliminary experiment strategy: candidate assignment
unit, treatment/effect horizon, interference and carryover risks, required power
inputs (variance, dependence, exposure and worthwhile effect), and A/A logging,
assignment and applicable ledger checks. Specify model/policy/assignment and
snapshot references, scope, forecast points/intervals and an analysis plan to freeze
before treatment outcomes. Reconciliation compares measured causal effects at
matching population, units and horizon, preserves the forecast, and reports
forecast error/uncertainty and assumptions of separately versioned updates.
Executable assignment/calendar, power calculation, washout/stopping choices
and A/A logs belong to Weeks 4–5,
when supporting inputs and authorization exist. GSM data is unavailable: the
plans remain unevaluated, synthetic tests remain evidence C, and actual GSM
split/calendar/power and causal effects remain unconfirmed or `not_evaluated`.
Pending decisions are recorded below rather than
inventing sample sizes, thresholds, ownership or dates.

### Freeze the business objective

Confirm and preregister the following register before GSM policy selection or
final evaluation. Its current entries remain pending:

| Decision | Required confirmation | Current state |
|---|---|---|
| Primary metric | Named outcome/estimand, definition, units and denominator; no default profit objective | `pending_gsm_confirmation` |
| Minimum worthwhile effect | Business-relevant effect in declared units, decision rule and owner | `pending_gsm_confirmation` |
| Scope and service ownership | Native cluster/services, eligible populations, controllable policies and ownership; one cluster/two services is the proposed initial scope | `pending_gsm_confirmation` |
| Accounting | Outcome-specific revenue/cost coverage, currency, recognition/allocation rules and finance approval where required | `pending_gsm_confirmation` |
| Guardrails | Waiting, cancellation, driver income and budget definitions and limits | `pending_gsm_confirmation` |
| Action bounds | Allowed price/incentive candidates, operational limits and responsible owner; the controlled price grid is not a GSM approval | `pending_gsm_confirmation` |
| Measurement horizon | Assignment/exposure period, effect horizon, carryover/washout assumptions and comparable measurement window | `pending_gsm_confirmation` |

Each guardrail needs its definition, population/denominator, threshold,
measurement window, action on breach and responsible owner. Each register entry
also needs the source of confirmation, owner and version/date when confirmed;
these values remain unset until GSM supplies them. Week 1 may deliver the
specification with pending items recorded, but cannot close the corresponding
GSM selection or experiment gates. No financial threshold or safety limit is
invented to complete the register.

Report demand, labor supply, substitution, completed trips, fulfillment, wait,
cancellation and idle vehicle-hours as causal/operational outcomes as supported;
their priority depends on that declared decision criterion. Evaluate revenue,
contribution margin, profit or ROI only when the corresponding measurement inputs
and accounting definitions qualify. If Y is a competitor, keep its price
fixed and exclude its bookings from GSM revenue. If both services belong to GSM,
include substitution between them. Missing financial inputs leave the respective
economic outcome unavailable; operational improvements or booking value do not
establish a financial success claim.

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

### Development interval-method comparison

The standalone `scripts.compare_week2_intervals` compares the existing individual
95% percentile intervals with basic and BCa candidates. Production fitting,
configuration, support gates and interval selection remain unchanged. Candidate
definitions are frozen before the comparison; the development study was frozen
before generation in its
[study plan](submission/days/20261011/results/interval_comparison/development_plan.json).

The fresh adjusted-OLS cohort uses seeds 42001–42020 for RCT_SYN and NULL_EFFECT,
199 original-day bootstrap draws and the same fixed TLC-derived context. A
separate DML seed 42001 is a bounded execution probe. All candidates share each
seed's observed point and bootstrap draws; BCa additionally uses 20
delete-one-original-day fits, refitting all learned components on the remaining
19 days with the original seed and fold groups. Reconstruction must match the
diagnostic point estimates before intervals are compared. Scope remains the
four theta coefficient cells, with fixed quote counts and held-out contexts;
these results cannot calibrate elasticity or scenario intervals by transfer.

Report per method/cell coverage, null false positives, widths, tail misses,
exact binomial uncertainty and expected/attempted/valid/failed/unavailable
counts. Compare methods on paired common-valid seeds as well as their full
attempted denominators; a missing interval is never a coverage success.
BCa adjusted quantiles outside the saved draw resolution are unavailable rather
than clipped or replaced by another method. Technical availability/stability
and empirical calibration are separate results. Method formulas and the tail
guard are in [IDENTIFICATION.md](IDENTIFICATION.md#development-interval-candidates),
and reproduction is in [USAGE.md](USAGE.md#development-interval-method-comparison).

This development comparison selects no automatic winner or production method.
The 20 seeds give limited coverage precision, and a single DML seed cannot
measure coverage. The 20 fixed calendar-day clusters in this semi-synthetic
design are not a literal IID sample of GSM days. Freeze any selected method and
acceptance criteria before an independent final evaluation with unused seeds;
the October 7 historical final results remain immutable. Measured results are
recorded separately in the
[11/10 comparison evidence](submission/days/20261011/interval_method_comparison.md).

### Development day-jackknife variance sensitivity

The standalone `scripts.compare_week2_variance` reuses the completed comparison
points and original-day jackknife fits to compare `day_jackknife_t` with
percentile/basic/BCa. Its
[frozen plan](submission/days/20261011/results/interval_variance/development_plan.json)
defines the jackknife variance, original-point centering and Student-t reference
with 19 degrees of freedom before postprocessing. There are no new fits or
bootstrap draws, and no new independent seeds: the cohort remains 40 adjusted-OLS
RCT/null jobs and one DML execution probe from the comparison above.

Require all 20 distinct successful finite day omissions for each candidate;
incomplete or degenerate variance is unavailable without dropping omissions or
fallback. Preserve full attempted/available counts and paired comparisons.
Report RMS jackknife SE versus between-seed SD on a matching valid cohort;
the DML probe is insufficient for a between-seed SD. See the
[formula and assumptions](IDENTIFICATION.md#development-day-jackknife-variance-sensitivity)
and [reproduction command](USAGE.md#development-day-jackknife-variance-sensitivity).

This is a variance sensitivity check for individual theta cells. The t reference,
day dependence and DML fold changes require empirical assessment; saved calendar
days are not asserted IID. It tunes no multipliers, selects no production winner
and closes no final-calibration gate. Record results in the
[variance evidence](submission/days/20261011/interval_variance_comparison.md),
then freeze any selected method and criteria before independent final evaluation.

### Fresh DML day-jackknife pilot

The separate `scripts.pilot_week2_dml_variance` pilot evaluates the frozen
`day_jackknife_t` candidate on fresh development seeds 43001–43005 for RCT_SYN
and NULL_EFFECT. The
[outer plan](submission/days/20261011/results/dml_variance_pilot/development_plan.json)
preserves the existing context/model settings and caps compute at 20 estimator
jobs / 420 fits, of which 210 are DML. Each shared seed is fitted with DML and
adjusted OLS, including the original fit and 20 original-day omissions per
estimator. There are no day-bootstrap draws. Measure one RCT seed first, then
execute the frozen remaining cohort; the cost probe counts once in the cohort.

Adjusted OLS is the cheap paired estimator baseline on the same generated data.
Percentile/basic/BCa are not rerun here, so the old cohort is not a paired method
comparison for these new seeds. Preserve attempted/available/failure counts,
exact binomial uncertainty, common-valid estimator comparisons and matched-cohort
RMS jackknife SE versus between-seed SD. Five seeds per DGP remain a pilot,
especially for null false positives. Changing DML folds after a day omission and
the fixed-calendar design retain the
[variance assumptions](IDENTIFICATION.md#development-day-jackknife-variance-sensitivity).
It selects no production default, tunes no variance multiplier and closes no
final-calibration gate. Reproduction is in
[USAGE](USAGE.md#fresh-dml-day-jackknife-pilot), with results in the
[pilot evidence](submission/days/20261011/dml_variance_pilot.md).

### Development score inference diagnosis

The [frozen plan](submission/days/20261011/results/score_inference/development_plan.json)
uses unused development seeds 44001–44100 for adjusted OLS and 44001–44020 for
DML, each under RCT_SYN and NULL_EFFECT. It caps compute at 252 point fits:
200 OLS, 40 DML, and 12 additional DML fits with 4/10 folds on three shared seeds.
No bootstrap or delete-day refits are performed; the two DML cost-probe jobs are
included in the 20-seed cohorts. Native threads are limited to one, with at most
two concurrent processes. The separate independent assessment uses reserved
45001–45100 under its own frozen protocol; the development study chooses no
production winner.

The point model, context, support threshold and nuisance settings remain fixed.
OLS block HC3/t uses weighted-regression leverage and residual degrees of freedom.
DML block inference uses its actual out-of-fold residuals and orthogonal-score
Jacobian, with a normal reference. Both also receive a day-summed CR1/t19
sensitivity interval, whose small-group validity is not assumed. Compare the same
points under block/day covariance, and inspect bias, RMS SE versus empirical SD,
coverage, null false positives, widths and complete failure denominators.

Joint theta/baseline covariance propagates to four baseline elasticities and
three fixed scenarios: +10% X, +10% Y, and +10% both, at 10,000 quote sessions.
Scenario contrasts are linear; elasticity ratios use a first-order delta method.
All 38 outputs have individual intervals. Exact binomial flags are exploratory
per output, without simultaneous coverage or automatic acceptance. Support
status is retained separately, so statistical coverage cannot authorize an
unsupported all-context policy. The fold-sensitivity cohort is never pooled with
the main coverage cohorts. See [method assumptions](IDENTIFICATION.md#development-score-inference)
and [execution/results](submission/days/20261011/score_inference_diagnostic.md).

### Conditional variance audit and independent inference assessment

`scripts.diagnose_week2_oracle_variance` reconstructs the existing 200 OLS fits
algebraically, without estimator refits. Conditional on the frozen contexts and
assigned prices, each block's X/Y rate covariance is
`(diag(p_xy) - p_xy p_xy') / n_sessions`. The observed OLS linear map transforms
this covariance into joint theta/baseline covariance. Oracle probabilities are
evaluator references only, never an input to fitting or reported inference.
The joint linear covariance is exact for this DGP; elasticity transforms remain
delta-method approximations. The audit preserves old evidence and uses no new
independent seeds.

The [independent frozen plan](submission/days/20261011/results/final_inference/frozen_plan.json)
fixes 100 previously unused seeds per RCT/null DGP, paired OLS/DML datasets,
OLS block HC3/t and DML block orthogonal-score/normal intervals. The cap is
400 point fits, no bootstrap/jackknife refits, retries or cohort expansion,
one native thread and at most two experiment processes. Model settings,
probability checks, full fixed test population and support thresholds stay fixed.

Report all 38 individual outputs and every attempted/unavailable denominator.
Baseline-before probabilities repeated by three scenarios count once in the
assessment family, while every original row remains in evidence. The frozen
screen uses exact one-sided binomial tests for coverage below .95 and NULL
false positives above .05, followed by Holm adjustment in one family across
both estimators/DGPs. This controls the diagnostic test family; it does not
make the underlying intervals simultaneous. Also report unadjusted exploratory
flags. Absence of rejection is not certification of nominal 95% coverage or
permission to use an unsupported policy. No automatic method promotion or
accepted exception follows automatically. Bun subsequently accepted the technical
exception and selected hybrid integration on 11/10/2026; see the
[decision record](submission/days/20261011/week2_hybrid_acceptance.md).
Results and remaining gates are in the
[closeout report](submission/days/20261011/week2_inference_closeout.md).

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

### Controlled booking-value objective

The executed controlled pricing-policy protocol above remains frozen: normalized
fares, fixed quote population and simulated gross booking value are its declared
objective. The broader GSM decision criterion does not rewrite that protocol,
its selected policies or its results.

GSM monetary outcomes remain unavailable until their required inputs qualify.
The controlled study uses illustrative normalized fares and reports
**simulated gross booking value**. TLC fares must not silently
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

Apply the [learner/evaluator separation](#baselines-and-learnerevaluator-separation)
specified above; the executed protocol retains its training/validation/test and
oracle separation as recorded in this section.

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

The current DGP may give several estimators the same best grid action; then their
policy values tie even if coefficient RMSE differs.
Revisions follow the [fresh-evaluation and inference rules](#split-inference-and-horizon-specification).

## 3. GSM offline validation

Validate GSM source mappings, join keys and predecision feature availability
against the [research schemas](ARCHITECTURE.md#research-table-schemas) and
[decision register](#freeze-the-business-objective). Completed TLC trips cannot
supply the required quote, driver-decision or financial histories.

When financial and accounting data become available from GSM, the full economic
comparison may evaluate the preregistered outcome at its supported accounting
scope. A profit-specific comparison is
`delta_profit = profit(target) - profit(baseline)`.
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
operational and demand benchmarks; a supported partial margin must keep its own label.

When assignment propensities and the identification assumptions are credible,
use an independent policy evaluator with inverse-propensity and doubly robust
estimates, overlap diagnostics and effective sample size, under the
[separation](#baselines-and-learnerevaluator-separation) and
[inference specification](#split-inference-and-horizon-specification). Doubly robust evaluation
combines outcome and assignment models; it does not remove missing support or
hidden confounding. See the original
[Dudik, Langford and Li paper](https://www.microsoft.com/en-us/research/publication/doubly-robust-policy-evaluation-and-learning-2/).

GSM actions require confirmed bounds from the [decision register](#freeze-the-business-objective)
and support in GSM logs; the controlled grid above is not a GSM-approved action
set. Arbitrary continuous prices need an explicitly justified evaluation approach; exact action
matching and discrete inverse-propensity formulas do not automatically apply.
If logs cannot support the proposed actions, report value as unidentifiable.

## 4. GSM profit-impact experiment

This optional profit-specific experiment applies only when GSM confirms profit
in the [decision register](#freeze-the-business-objective) and complete financial
measurement qualifies. It follows the [experiment strategy and gates](#prospective-statistical-gates-and-experiment-strategy);
the register governs guardrails and any other primary criterion.
Execution must meet the core design's
[A/A and pilot requirements](reference/CORE_ENGINE_DESIGN.md#152-aa-and-pilot)
and [immutable prediction-ledger requirements](reference/CORE_ENGINE_DESIGN.md#153-prediction-ledger).

Compare the frozen candidate policy against existing pricing using a randomized
design appropriate for the marketplace. A zone/time switchback is a candidate;
interference between zones and carryover determine whether it is suitable.
Block duration, washout and inference require design, not a generic A/B toggle.
See [Bojinov, Simchi-Levi and Zhao](https://arxiv.org/abs/2009.00148).

Measure profit over comparable assigned zones/blocks or a declared common
exposure period. Include all owned-service revenue to capture substitution and
all applicable driver pay, incentives and other costs, including allocated
fixed/shared expenses under the same approved basis. Revenue, contribution
margin and completion, cancellation, wait, availability and customer effects
are explanatory outcomes or guardrails. Revenue per quote may also be useful,
but quote traffic may itself respond to pricing; do not silently hold that
denominator fixed.

Report profit uplift with its confidence interval and cost bridge against the
confirmed register. A positive point estimate with an interval spanning zero is
inconclusive; incomplete financial measurement leaves profit unavailable and
cannot establish profit success from trips or revenue alone.

Only an executed, appropriately analyzed GSM study can support a claim about
GSM profit impact in the population, prices and operating conditions tested.
Neither synthetic recovery nor simulated policy uplift establishes that claim.

## Core engine validation protocol

This protocol defines required validation as engine capabilities are implemented.
The two-vehicle development fixture is one correctness case. Release conclusions
require evidence for the implemented scope under the
[engine delivery standard](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard).
The table also covers broader research extensions. The
[current fixed-online PoC](WEEK3_POC_SCOPE.md) does not require behavioral schedules,
incentive policies, charging or endogenous equilibrium; apply those cases only
when the corresponding capability enters the authorized scope.

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

## Week 3 fixed-online operational assessment

`evaluate-marketplace` evaluates frozen supported baseline/target demand plans with
the same choice model/source, initial roster and two-hour horizon, version-3 offer
rules and 100%-displayed-fare compensation. It does not fit demand, acceptance or
labor responses, read the choice oracle or select a policy as optimal. The
baseline has unchanged pricing; the target remains inside demand support.

The checked-in [pilot](../configs/week3_poc_pilot.json) uses 72001–72003; the
[independent assessment](../configs/week3_poc_assessment.json) uses 73001–73100.
Rules, gates and profiles are frozen before assessment. These seeds cannot become
tuning data for the same assessment claim. Both profiles bound the full evaluator
at 600 seconds, keeping failed attempts and their reasons in exported records.
The [12 October closeout](submission/days/20261012/week3_poc_closeout.md) and
[verification](submission/days/20261012/week3_poc_verification.json) record
`week3-poc-assessment-20261012-v3`: 200 paired Poisson trajectories, 100 controlled
trajectories and three workload checks, **303/303 succeeded**, zero failed jobs,
all frozen gates passed, 100.158 seconds total. Controlled mean completions/pay were
14.47 against truth 15, and idle hours 1.733833 against truth 1.725, within their
preregistered tolerances. This supports the scoped synthetic technical package,
ready for Bun's review; it does not record reviewer acceptance or GSM calibration.

| Layer | Independent check and frozen gate |
|---|---|
| Paired price scenarios | One baseline and target Poisson trajectory per seed under the same roster, OD/arrival seed plan and declared acceptance rule; retain trips/wait/idle/offer/earnings means, paired differences and attempted/available/failed denominators |
| Poisson request generation | Compare zone/service mean created requests with the sum of frozen expected bookings; all seeds available and absolute standardized mean error at most 4. Zero-rate strata must stay exactly zero |
| Known offer mechanism | 30 separated X requests, one driver, acceptance 0.5, response 3 seconds, pickup 0, trip 60 seconds, one offer per request, no overlapping service. Expected completions/acceptances 15, gross pay 15 × frozen baseline X fare, dispatch 0.025 hours, on-trip 0.25 hours, idle 1.725 hours and online 2 hours |
| Controlled recovery | All seeds available; completed/accepted mean error at most 1.2, pay mean error at most 1.2 × fare; on-trip/idle mean error at most 0.02 hours. Created/offered counts, dispatch and online hours use numerical tolerance 1e-12 |
| Declared workload | Target trajectories with 2/20/100 shared-roster drivers, at most 10,000 requests and 500,000 work units each; complete within 60 seconds and peak traced Python allocation at most 256 MiB. Python allocation is not process RSS or a production hardware guarantee |
| Accounting and failures | Retain request/offer/state-time/ledger identities and every failed/unavailable output. Exhaustion/invalid input cannot publish a successful-looking partial forecast; execution completion and statistical gate status remain separate |

Measured target workloads used 452 requests each under seed 73001:

| Online drivers | Wall time (seconds) | Peak traced Python allocation (MB, decimal) |
|---:|---:|---:|
| 2 | 2.447 | 5.135 |
| 20 | 5.068 | 8.797 |
| 100 | 7.712 | 10.856 |

These are bounded local measurements for the recorded environment; they do not
validate execution at the 10,000-request cap or measure process RSS. Replay of the
fixture and same-policy Poisson case matched 22 output files byte for byte.
Pending-offer continuation retained request/offer traces, settled earnings and
final checkpoint. Full repository verification passed 609 tests with two historical
Pandas FutureWarnings. Exact source recovery/checksum scope is in the dated report;
the damaged original Week-3 training run is not claimed intact.

The default operational assumption is acceptance 0.8 independent of fare, response
3 seconds, timeout 10 seconds and at most 20 attempts per request. No repeated draw
for the same driver/request pair is allowed. Constant acceptance is a declared
synthetic baseline, not evidence that driver response to price or pay is zero.
Withdrawn and pending offers stay outside the resolved-response acceptance rate;
timeouts remain in its denominator. Refusal does not remove online hours.

Individual Student-t intervals across independent seeds concern the **mean paired
trajectory difference conditional on fixed fitted demand and declared rules**.
They describe Monte Carlo integration uncertainty, not a future single trajectory,
causal demand-parameter uncertainty, full-chain coverage, simultaneous intervals
or GSM effects. Missing waits/rates retain unavailable counts rather than invented
zeros. No GSM calibration, profit/ROI or original driver labor elasticity is
certified by these checks.

Exports are `marketplace_evaluation.json`, `marketplace_seed_records.csv`,
`marketplace_controlled_records.csv` and `marketplace_workload_records.csv`, with
frozen input/source identities, environment and hashes. Commands and read-only
UI/export usage are in [USAGE](USAGE.md#week-3-fixed-online-poc); dated evidence
belongs to the submission records.

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
