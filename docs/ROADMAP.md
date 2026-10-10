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

These are weekly requirements and targets, not completion records.

| Week | Required input | Expected output and acceptance |
|---|---|---|
| 1 | Labeled raw/public/synthetic sources, metadata/keys, market/rules/estimands and business decision | Reviewed causal specifications, source/mapping readiness, decision register and evaluation plan; validate available research tables, quality reports, manifests and splits. Pending GSM confirmations keep the corresponding closure conditions open. |
| 2 | Choice/assignment records or controlled blocks; separate Swissmetro data and independent evaluator | Rider demand/choice results, common matrix or identified columns, baseline/support/interval diagnostics and method/choice/policy reports; state unidentified responses and prevent oracle leakage |
| 3 | Frozen demand/choice bundle; offered compensation, dispatch decisions, eligible participation/shift/state records or declared synthetic truth; shared roster, rules, initial snapshot, seeds and budgets | Driver labor-supply results and separate acceptance diagnostics; supported integrated forecasts with feasible plans/snapshots, offer/operational trajectories, earnings ledger, equilibrium status and baseline-error report; invariant, failure and independent controlled benchmark evidence |
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
implementation belongs to week 3; executable schedules, calibrated power,
frozen forecasts and A/A/pilot evidence remain week 4–5 work under the
appropriate data and authorization conditions.

## 1. Close week 2

Compute and statistical review are complete: the reporting evaluation has
500/500 seed jobs, Swissmetro has its person-holdout report, and the independent
development policy-value benchmark has 40/40 seed jobs. Results are in the
[Week 2 report](submission/days/20261007/weekly_report.md).
Completion of compute does not close all acceptance gates.

The remaining work is:

1. Resolve how interval-calibration limitations are accepted. Record the reviewer's
   actual conclusion or accepted exception. If the method changes, use development
   data and a new holdout under a protocol frozen before evaluation; do not tune on
   the existing final seeds.
2. Freeze the final demand/choice handoff: model bundles, `effects.csv`,
   `scenario_result.json`, diagnostics, config/scope/code/environment metadata,
   checksums and instructions. Verify a corresponding rerun/resume. Historical
   model runs remain evidence for their own revision.
3. Record the actual reviewer, review date and gate conclusions in the
   [acceptance review](submission/days/20261007/acceptance_review.md#điều-kiện-còn-lại-để-đóng-week-2).
   Reviewer confirmation and the submission deadline have not been provided.

The [acceptance review](submission/days/20261007/acceptance_review.md) owns the six
gate conclusions: Data, Effect, Scenario, Reproducibility, Statistics and
Additional benchmarks. The first four permit demand integration in week 3 once
the final bundle and matching reproducibility checks are ready. Full Week 2
acceptance requires all six; open work continues alongside week 3.

Keep the frozen reporting snapshot and evidence unchanged during development.
[Benchmark execution instructions](BENCHMARK.md#reporting-execution-and-compute-provenance)
retain the original seeds, finite job budgets, source identities and resume procedures.

## 2. Implement week 3

Keep the quote population fixed and use `reduced_form_policy`. Start with a
two-vehicle fixture and prescribed requests. The small demo has one cluster,
2-4 zones, two services sharing a roster, and a two-hour horizon. These are
validation assumptions, not GSM observations.

Step 1 is implemented with `prepare-demand`: verified choice handoff, versioned
X/Y rates in requests/hour, policy/specs and a validated shared-roster snapshot.
The [runnable development profile](USAGE.md#week-3-demand-handoff) keeps
historical Week 2 reporting unchanged. Block-rate intervals and operational
calibration remain unavailable. Step 2 is implemented with `simulate-marketplace`:
a bounded fixed-roster SimPy run, prescribed or piecewise-Poisson requests,
synthetic matching/OD durations, request and vehicle trajectories, wait/idle/trips
and end-horizon censoring. See [simulation usage](USAGE.md#week-3-fixed-supply-simulation).
It uses immediate acceptance, trips finishing within fixed shifts and static SOC.
The state/carryover and cancellation portion of step 3 is implemented: version 2
accepts queued/busy checkpoints, retains pending operational events and original
timestamps, and supports pickup expiry and explicit prepickup cancellation.
Compensation, driver participation/trip acceptance, energy/charging and the other
operational constraints remain to implement.
Completing this bridge does not close the Week 2 reviewer or final reporting gates.

Offered compensation precedes decisions. Retain eligible nonparticipants and zero
trips. Use an amount treatment for zero-base bonuses; do not count bonuses already
included in expected income twice. Count shared fleet once. Relocation creates
no new hours; charging is not subtracted twice. Separate controlled observations,
rules, and oracle.

The customer-and-driver target architecture separates participation/working hours,
dispatch offer exposure and trip acceptance. A driver can reject a trip and remain
idle/serviceable; acceptance probability is not a multiplier on physical hours.
Decision-time offer terms and realized earnings have separate lineage. Follow the
[execution design](reference/CORE_ENGINE_DESIGN.md#23-customer-and-driver-execution)
and [driver models](reference/CORE_ENGINE_DESIGN.md#7-supply-response-engine).

Week-3 primary outputs are driver participation/conditional-hours estimates,
their intervals, decision populations, support and evidence, followed by
supported demand/supply forecasts. Acceptance remains a separate dispatch
response. Integrated forecast metrics include demand X/Y/total, net choice changes,
offer exposure
and trip acceptance, serviceable/idle hours, completed trips, wait/cancel,
driver earnings summary and simulated gross booking value. Include source, unit,
denominator, support, evidence C, and status. Full GSM profit remains conditional
on confirmed accounting definitions and retains the explicit status not_evaluated.

Required tests: request/offer accounting with carry-in/out; nonoverlapping states;
legacy immediate acceptance, zero acceptance, unchanged driver terms, feasible
participation, zero supply/bonus, relocation, insufficient support and nonconvergence.
Energy extensions also require SOC/charger-capacity and charging-bottleneck checks.
Compare baseline errors with controlled truth; do not call this GSM calibration.
Run repository checks and demand regression checks.

After the implemented state/carryover and cancellation work, prioritize compensation
and bounded trip offers/acceptance with the existing fixed roster and static SOC.
Then add participation, feasible driver/vehicle schedules, income-supply equilibrium
and paired price-only, incentive-only and combined policy comparisons. Validate
baseline behavior and each component's equations, accounting and failures throughout.
Detailed energy/charging remains an open operational extension rather than a
prerequisite for the first driver-response integration; retain availability
assumptions and any unimplemented acceptance requirements explicitly.
Extend beyond the small fixture using the
[core engine validation protocol](BENCHMARK.md#core-engine-validation-protocol).

Use core solver defaults: damping 0.3, at most 50 iterations, 600 seconds/job.
Freeze event budgets/tolerances/replicates before execution; confirm with
independent seeds. Organize the logical components within the existing packages
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
