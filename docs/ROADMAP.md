# PoC and Core Engine Roadmap — Week 1 Review and Weeks 2–5

Source data requests and export requirements follow
[GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md).
Research schemas and artifact conventions follow
[ARCHITECTURE.md](ARCHITECTURE.md#research-table-schemas).
Algorithms follow the [core engine design](reference/CORE_ENGINE_DESIGN.md);
the causal specifications and controlled demand/choice generator equations are in
[IDENTIFICATION.md](IDENTIFICATION.md).

GSM raw data is unavailable. TLC supplies completed-trip context, synthetic truth
supplies controlled behavior/operations, and Swissmetro is a separate choice
baseline. New forecasts remain evidence C; GSM calibration, causal effects,
profit and ROI stay `not_evaluated`.

## Delivery objective

The three-response research objective below remains the broader target.
Bun narrowed the current operational PoC on **12/10/2026** to a fixed online
driver roster, per-request acceptance decisions and 100% displayed-fare driver
pay; [WEEK3_POC_SCOPE.md](WEEK3_POC_SCOPE.md) governs that active scope.
Incentives, endogenous online/offline behavior, shift allocation and income-supply
equilibrium are outside the current PoC. This restriction does not establish
driver labor elasticity or complete the broader original research objective.

Estimate and validate rider-price, driver-labor-supply and own/cross-service
responses for one cluster and two services, using the estimands in
[IDENTIFICATION.md](IDENTIFICATION.md). Use supported results for policy
forecasts, independent finite-policy comparisons and experimental reconciliation
under the business criterion and guardrails in
[BENCHMARK.md](BENCHMARK.md#freeze-the-business-objective).

Simulator, core engine, dashboard and exports support these results. Integrated
forecasts additionally require the correctness, reproducibility, uncertainty and
resource gates in the
[engine delivery standard](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard).
All views/exports use the same versioned results, scope, units and statuses.
Revenue, contribution margin, profit and ROI require their respective confirmed
measurement/accounting inputs; unavailable outcomes retain explicit reasons.

The five-week sequence is a planning target. Acceptance follows recorded evidence
and frozen quality gates; unfinished requirements remain open at handoff.

## Weekly inputs and outputs

These are planning targets, not completion records. Week 3 reflects the current
PoC scope; later research targets remain conditional on their required inputs.

| Week | Required input | Expected output and acceptance |
|---|---|---|
| 1 | Labeled raw/public/synthetic sources, metadata/keys, market/rules/estimands and business decision | Reviewed causal specifications, source/mapping readiness, decision register and evaluation plan; validate available research tables, quality reports, manifests and splits. Pending GSM confirmations keep the corresponding closure conditions open. |
| 2 | Choice/assignment records or controlled blocks; separate Swissmetro data and independent evaluator | Rider demand/choice results, common matrix or identified columns, baseline/support/interval diagnostics and method/choice/policy reports; state unidentified responses and prevent oracle leakage |
| 3 | Frozen supported demand/choice bundle; fixed online driver/vehicle roster, displayed-fare compensation terms, dispatch rules, initial snapshot, seeds and budgets | Separate offer/acceptance diagnostics and supported price/earnings forecasts; request/vehicle trajectories, idle hours, trips/wait/cancel and earnings ledger; accounting, replay, failure and controlled validation evidence. Existing scientific labor-supply evidence is retained independently; labor elasticity and endogenous equilibrium are outside this PoC. |
| 4 | Supported response bundles and validated operational inputs; finance sources/rules to the extent required by the chosen criterion; uncertainty specification, movement/carryover and power assumptions | Independently evaluated finite policy comparisons, intervals and sensitivity, pilot recommendations with guardrail/evidence status; conditional economic comparison/cost bridge, workload checks, experiment/A/A specification and frozen forecasts; dashboard/exports expose the same results |
| 5 | Versioned causal/policy/engine artifacts, correctness/statistical/performance evidence and acceptance records; actual experiment logs if an experiment occurs | Reproducible evidence package, rerun instructions, identified/unidentified scope and gate status; runnable supporting PoC, pilot handoff and forecast-versus-effect reconciliation when experiment data qualify |

## Week 1 specification and closure

Week 1 establishes the questions, data readiness and evaluation decisions for
the three responses. Review these specifications before implementing the driver
models or selecting a GSM policy. Current evidence and unresolved confirmations
are indexed in [README.md](README.md#tiến-độ-hiện-tại).

| Review item | Specification owner | Closure condition |
|---|---|---|
| Causal scope | [IDENTIFICATION.md](IDENTIFICATION.md) | Record treatment/contrast, outcome, population, horizon, units, assignment and inference unit for rider price, labor supply and substitution. Separate conditional quote conversion from total requests, and labor participation/hours from trip acceptance. Mark unidentified components explicitly. |
| Source coverage and mappings | [ARCHITECTURE.md](ARCHITECTURE.md#research-table-schemas) | Record actual availability for each requested group, native-to-logical mappings, keys/grain/units/timezone, coverage and quality checks. Public/synthetic tables qualify only for their declared scope; an export request does not establish GSM receipt or validation. |
| Business decision | [BENCHMARK.md](BENCHMARK.md#freeze-the-business-objective) | Obtain actual confirmation of the primary criterion, minimum worthwhile effect, ownership/accounting scope, action bounds, horizon and service/driver/budget guardrails. Keep unconfirmed GSM values pending; illustrative development choices cannot satisfy this confirmation. |
| Evaluation and experiment planning | [BENCHMARK.md](BENCHMARK.md) | Review baselines, separate development/final evaluation, dependence-aware splits/inference, identification/support and uncertainty gates. Record the proposed assignment strategy, behavioral horizon, carryover/spillover risks, power inputs and A/A checks; freeze new thresholds before a fresh final evaluation. |
| Reproducibility and review | [ARCHITECTURE.md](ARCHITECTURE.md#storage-and-execution) | Link source/configuration/seed/environment identities, completed artifact checksums and scoped validation evidence. Record the reviewer, date, accepted scope and unresolved conditions only after review occurs. |

Controlled-development readiness and GSM readiness have separate conclusions.
The former can be reviewed with labeled synthetic assumptions and validated
public data; the latter remains open without received/validated GSM sources,
a local identification/split review and the required business confirmations.
Preparing specifications does not complete causal measurements or imply reviewer
acceptance; the handoff records its supported scope and remaining conditions.

Week 1 requires the evaluation and experiment strategy. Driver-model
implementation belongs to week 3; executable experiment schedules, calibrated power,
frozen forecasts and A/A/pilot evidence remain week 4–5 work under the
appropriate data and authorization conditions.

## 1. Close week 2

Compute and statistical review are complete: the reporting evaluation has
500/500 seed jobs, Swissmetro has its person-holdout report, and the independent
development policy-value benchmark has 40/40 seed jobs. Results are in the
[Week 2 report](submission/days/20261007/weekly_report.md).
Completion of compute does not close all acceptance gates.

The standalone handoff and saved-model replay are implemented with
[`freeze-choice`](USAGE.md#week-2-choice-handoff). Current technical evidence and
gate conclusions are in the [11/10 verification](submission/days/20261011/choice_handoff_verification.md).
Week 2 is accepted by **Bun, 11/10/2026**, with a technical exception:
[`Technically stable`, residual 88–89% warnings and controlled scope](submission/days/20261011/week2_hybrid_acceptance.md).
The current decisions and remaining limits are:

1. Keep the accepted coverage limitations explicit. The
   [development comparison](submission/days/20261011/interval_method_comparison.md)
   implements percentile/basic/BCa trials with shared draws and original-day
   jackknife; the
   [variance sensitivity](submission/days/20261011/interval_variance_comparison.md)
   reuses these fits for a day-jackknife t candidate with no new independent seeds.
   The [fresh DML pilot](submission/days/20261011/dml_variance_pilot.md) applies
   that candidate to five fresh RCT/null seeds with paired adjusted OLS; it adds
   no percentile/basic/BCa bootstrap comparison on those seeds. These branches
   select no production winner. The
   [score diagnosis](submission/days/20261011/score_inference_diagnostic.md) now
   adds block/day covariance comparisons, larger fresh OLS/DML cohorts, joint
   elasticity/scenario diagnostics and separate fold sensitivity. Its coverage
   checks remain development evidence; full-context scenario support and final
   acceptance are separate gates. The
   [inference closeout](submission/days/20261011/week2_inference_closeout.md)
   completes exact conditional OLS variance diagnosis and the frozen independent
   block-method assessment on 45001–45100: 400/400 fits and 410 repository tests
   pass. Eight individual undercoverage rows remain; zero Holm rejections do not
   certify every interval at 95%. Bun selected hybrid inference: analytic default
   for causal scenario/UI, frozen bootstrap baseline preserved. Full calibration
   of every output remains uncertified. These seeds are assessment evidence,
   not unused tuning data. See [usage](USAGE.md#hybrid-choice-inference).
2. Keep the supported restricted scope explicit: the
   [11/10 support diagnosis](submission/days/20261011/support_interval_diagnostic.md)
   selects 10/20 training strata at the unchanged 20-block minimum, retaining
   67.5% of the evaluation-context session weight. Its replay passes support.
   The all-context forecast remains unsupported; restoring that population needs
   sufficient training coverage and a newly validated fit. Do not lower thresholds,
   silently exclude groups or transfer a historical `ok` to the current revision.
3. Retain the actual reviewer, review date and gate conclusions in the
   [current technical review](submission/days/20261011/choice_handoff_verification.md).
   Reviewer Bun accepted the technical exception on 11/10/2026. The submission
   deadline has not been provided; GSM-specific confirmations still await data.

The current technical review records the six gate conclusions: Data, Effect,
Scenario, Reproducibility, Statistics and Additional benchmarks, retaining the
[historical acceptance review](submission/days/20261007/acceptance_review.md) for
its own revision. The first four permit demand integration in week 3 for a
supported declared scope and matching reproducibility checks. Week 2 acceptance
with the declared technical exception is recorded; support extension and GSM
calibration continue alongside week 3.

Keep the frozen reporting snapshot and evidence unchanged during development.
[Benchmark execution instructions](BENCHMARK.md#reporting-execution-and-compute-provenance)
retain the original seeds, finite job budgets, source identities and resume procedures.

## 2. Implement week 3

Follow the [current PoC scope](WEEK3_POC_SCOPE.md): keep a declared driver roster
online throughout the observation horizon, with freedom to accept or reject
each offered request. Online supply is fixed independently of price, income and
incentives. The PoC does not allocate shifts or infer when drivers open/close the
app. Rejection leaves a driver online; no available willing driver means the
request waits, expires or is canceled under the declared rules.

Keep the quote population fixed and use `reduced_form_policy`. The small demo
has one cluster, 2-4 zones, two services sharing a roster and a two-hour horizon,
starting with a two-vehicle fixture and prescribed requests. These are validation
assumptions, not GSM observations. Fixed online supply does not identify labor
elasticity; trip acceptance remains a separate dispatch response.

Step 1 is implemented with `prepare-demand`: verified choice handoff, versioned
X/Y rates in requests/hour, policy/specs and a validated shared-roster snapshot.
The [runnable development profile](USAGE.md#week-3-demand-handoff) keeps
historical Week 2 reporting unchanged. Block-rate intervals and operational
calibration remain unavailable. Step 2 is implemented with `simulate-marketplace`:
a bounded fixed-roster SimPy run, prescribed or piecewise-Poisson requests,
synthetic matching/OD durations, request and vehicle trajectories, wait/idle/trips
and end-horizon censoring. See [simulation usage](USAGE.md#week-3-fixed-supply-simulation).
The current version-3 rules keep the online roster fixed over the observation
horizon, retain static SOC and introduce bounded individual offers. Each pending
offer reserves an idle vehicle; a stable seeded Bernoulli decision resolves to
acceptance, rejection or timeout. Expiry/cancellation withdraws the offer;
refusal leaves the driver online and the original request deadline unchanged.
The default acceptance probability 0.8 is a declared price-independent synthetic
assumption, with response 3 seconds, timeout 10 seconds and at most 20 offers per
request. No driver/request pair is redrawn. Legacy shift fields validate coverage
of the horizon; they do not implement scheduled hours or online/offline decisions.
State/carryover and cancellation preserve queued/busy requests, pending offers,
reserved vehicles, frozen terms and original event timing. Version-3 checkpoints
require compatible version-3 rules; V1/V2 immediate-acceptance controls remain
separately reproducible.
The independent controlled labor-supply branch is implemented with
`generate-supply`, `fit-supply`, `scenario-supply` and `evaluate-supply`: complete
eligible driver/shift observations, randomized offered-incentive contrasts,
driver-level Welch intervals, support gates and separate RCT/null assessment.
See the [supply contract/protocol](WEEK3_SUPPLY.md). This scientific branch is
preserved independently, outside the current PoC delivery path; its effects and
declared availability fraction do not change the fixed online roster.
Optional minimal compensation
settlement is implemented: drivers receive 100% of displayed app fares on completed
trips under Bun's approved synthetic assumption, with frozen quotes/pay terms,
per-driver earnings and presence-hour denominators, including zero-trip drivers.
Financial continuation preserves the financial context and settles each completion
only once. See [compensation usage](USAGE.md#week-3-minimal-compensation).
`driver_offers` and `offer_events` retain exposure, response, unresolved offers
and immutable predecision terms. Acceptance rates report their actual response
denominator and keep pending/withdrawn offers separate. The read-only dashboard
selects completed simulation runs independently of choice fits and exports the
same metrics/statuses.
Behavioral schedules, incentive response, endogenous online/offline behavior,
income-supply equilibrium and detailed energy/charging are outside this PoC scope.
The [supply increment evidence](submission/days/20261011/week3_supply_progress.md)
records 200 independent RCT/null seed jobs and 472 passing repository tests;
it does not close complete Week-3 or GSM acceptance.
Completing the current PoC does not certify nominal coverage, full-context support
or GSM calibration.

Displayed fare and driver compensation terms precede acceptance decisions;
realized earnings follow completed trips. Retain zero-trip online drivers in
earnings summaries, and count the shared X/Y fleet once. Separate controlled
observations, rules and oracle. Rejecting a trip does not remove an online driver
or multiply physical hours by an acceptance rate.

The customer-and-driver target architecture separates participation/working hours,
dispatch offer exposure and trip acceptance. A driver can reject a trip and remain
idle/serviceable; acceptance probability is not a multiplier on physical hours.
Decision-time offer terms and realized earnings have separate lineage. Follow the
[execution design](reference/CORE_ENGINE_DESIGN.md#23-customer-and-driver-execution)
and [driver models](reference/CORE_ENGINE_DESIGN.md#7-supply-response-engine).

Current Week-3 PoC outputs are supported price forecasts, per-request offer and
acceptance diagnostics, demand X/Y/total and net choice changes, online/serviceable
and idle hours, completed trips, wait/cancel, driver earnings summary and simulated
gross booking value. Include source, unit,
denominator, support, evidence C, and status. Full GSM profit remains conditional
on confirmed accounting definitions and retains the explicit status not_evaluated.

Required tests: request/offer accounting with carry-in/out; nonoverlapping states;
legacy immediate acceptance, zero acceptance, rejection while remaining online,
bounded attempts/timeouts, unchanged driver terms, zero online supply,
insufficient demand support and completion-only settlement without duplicate pay.
Compare baseline errors with controlled truth; do not call this GSM calibration.
Run repository checks and demand regression checks.

The implemented `evaluate-marketplace` compares supported baseline/price scenarios
under the same roster, frozen model/source and paired seeds. It checks Poisson
request means against the frozen rates, a known separated-offer mechanism against
controlled truth and 2/20/100-driver workloads under finite budgets. Its individual
Student-t intervals describe paired Monte Carlo mean differences conditional on
the fitted demand and declared rules; they do not cover causal fitting uncertainty.
The [frozen operational protocol](BENCHMARK.md#week-3-fixed-online-operational-assessment)
separates pilot seeds 72001–72003 from assessment seeds 73001–73100. The
[12 October closeout](submission/days/20261012/week3_poc_closeout.md) records
303/303 assessment jobs with all frozen gates passed, 609 passing tests, replay
and pending-offer continuation checks. The scoped Week-3 PoC is ready for Bun's
review; no reviewer acceptance or original three-response/GSM completion is
implied. Retain every failed/unavailable count and do not tune on these assessment
seeds. Measured workload evidence covers 2/20/100 drivers at about 450 requests,
not the 10,000-request cap. Incentive scenarios, allocated schedules and
income-to-hours feedback are not current prerequisites.

Freeze event budgets and replicates before execution; confirm with independent
seeds. An endogenous equilibrium solver is not required for this fixed-online
PoC. Organize the logical components within the existing packages
under [target architecture](ARCHITECTURE.md); create separate files only where
implementation responsibilities require them.
SimPy is now declared and locked for the implemented fixed-supply simulator.

## 3. Handoff and follow-up

Keep large model/data/run artifacts ignored; every output has a manifest/checksum.
Identification, response-model validity, supported forecast and independent
policy-evaluation evidence take priority in the handoff. Engine correctness,
reproducibility and resource checks remain required for integrated forecasts;
dashboard polish follows these requirements. Preserve conservation and failure
checks when expanding the validated workload or model complexity.

Week 4 adds full-chain uncertainty, explicit sensitivity to unmeasured assumptions,
independent comparison of supported finite candidates under the confirmed
business criterion and guardrails, and conditional financial evaluation when
the corresponding coverage/definitions qualify. A profit-specific comparison
requires a finance-approved all-cost ledger. Deliver power/carryover assumptions,
switchback and A/A specifications, and a frozen prediction ledger. Continue C-level development
without GSM while requesting **eight raw source groups over the latest 12 months**.
When GSM arrives, reassess mapping/quality/identification/calibration before
forecasting; an adapter swap or borrowed synthetic coefficients is insufficient.

Week 5 packages the causal results, independent policy evaluation, limitations
and reproducible experiment handoff, with the supporting engine/PoC, verified
scenario walkthrough and acceptance status. A/A, a pilot and forecast reconciliation
depend on actual GSM data and experiment authorization.
A week-5 pilot prioritizes process checks; impact evaluation may extend according
to the power analysis. A short price switchback need not identify the longer-horizon
shift-participation response; each experiment must match its stated estimand.
