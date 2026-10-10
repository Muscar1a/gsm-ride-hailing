# GSM Causal Marketplace Proposal

Problem 06 | Nguyễn Thành An

GSM source requirements, export formats, keys and units follow
[GSM_DATA_CONTRACT.md](../GSM_DATA_CONTRACT.md). Algorithms follow
[CORE_ENGINE_DESIGN.md](CORE_ENGINE_DESIGN.md). This document defines the target
system; current progress and executed evidence are indexed in [docs README](../README.md).

## Problem and scope

Prices, driver incentives, and subscriptions affect both customer demand and
driver labor supply. Historical dashboards describe outcomes after intervention;
correlation alone does not identify the three responses needed for policy decisions.

| Response | Question | Main source of bias |
|---|---|---|
| Customer price sensitivity | How do requests change when service price rises 1%? | Prices often rise during rain or peak demand, creating positive price-trip correlation despite negative price effects |
| Driver supply response | How do participation and serviceable hours change with predecision offered compensation or incentives? | Incentives target shortages; relocation and shifted charging can resemble extra supply |
| Cross-service substitution | How do X/Y requests and nonbooking probability change when one price changes? | Services share demand shocks; net changes do not identify individual customer switches |

The main objective is to estimate these three causal responses, use identified
responses to predict policy effects and select policies worth testing, and validate
the frozen counterfactuals through experiments. The decision path is identification
-> estimation -> supported policy forecasts -> policy evaluation -> experimental
validation. Its first scope is one cluster and two services.

The reference business question is: **If service X price rises 10% in one zone/time
window, how do demand, serviceable supply, service choice, completed trips, and idle
supply change, and is this policy worth testing under agreed business and service
criteria?** This example is forecast only within supported action bounds. Supply
response depends on offered compensation, expectations formed before the labor
decision, and the decisions drivers can adjust; participation/hours and acceptance
of individual dispatch offers remain separate outcomes.

Deliver three causal result packages, supported counterfactual comparisons,
decision evidence, and an executable switchback design with a frozen forecast
ledger. A reusable core engine, marketplace simulator, dashboard, and exports
support these outputs. Their state/accounting, explicit failures, reproducibility
and workload limits follow the
[engine standard](CORE_ENGINE_DESIGN.md#11-engine-delivery-standard). Passing
technical gates does not establish causal identification or real GSM policy impact.
Real GSM profit and ROI require confirmed cost and financial policies from GSM and
remain conditional.

| Forecast | Interpretation | Dependency |
|---|---|---|
| Demand | Change in requests | Customer price sensitivity |
| Service choice | Net X/Y/nonbooking changes within the observation window | Cross-service response |
| Supply | Change in serviceable vehicle-hours under offered terms | Driver supply and attendance |
| Trip acceptance | Acceptance probability conditional on an actual dispatch offer | Offer terms and driver acceptance response |
| Completed trips & operations | Fulfilled trips, wait times, cancellations, and idle vehicle-hours | Marketplace simulation combining demand, supply, and matching |
| Simulated gross booking value | Completed trips multiplied by effective policy fares | Operations and scenario tariff |
| GSM incremental profit & ROI (conditional) | Policy difference after complete costs; unavailable without confirmed GSM financial policy | GSM-recognized revenue and finance-approved cost ledgers |

Validate forecasts through switchback experiments alternating policies by
geographic cluster and time block, with frozen forecasts compared to outcomes.

| Item | Five-week scope | Later work |
|---|---|---|
| Policy | Prices and driver incentives; subscription benefits as effective price changes for observed subscribers | Automatic production pricing |
| Estimation | Three responses by supported zone/time/service resolution, intervals, evidence A/B/C | Individual customer pricing |
| Marketplace | Supported demand/supply forecasts; one-cluster simulation for operational effects and equilibrium when justified | Citywide competition model |
| Decision | Finite supported price/incentive candidates, agreed business criterion, uncertainty and operational guardrails | Automatic policy optimization |
| Validation | Executable switchback design, A/A protocol and frozen forecast reconciliation ledger; cluster pilot subject to GSM approval | Broad rollout |
| Delivery | Causal result packages, decision evidence and experiment package, presented through a validated core engine, dashboard and CSV/JSON | Production trip-level dispatch optimization |

Expected use: evaluate pricing and incentive policies by their operational and
commercial marketplace impact, with traceable accounting and uncertainty, and explain
customer, driver and service quality outcomes to GSM leadership and regulators.
These are objectives, not measured benefits.

## System and data

Pricing and driver operations teams define a service, zone, horizon, and finite
set of supported price/incentive candidates. Before selection and final evaluation,
agree the primary business metric, minimum worthwhile effect, wait/cancel/driver
income/budget guardrails and action bounds with GSM. No default objective maximizes
gross booking value or profit. Compare each candidate with the current policy,
report operational/economic outcomes and uncertainty, and give a reasoned decision:
worth testing, more evidence needed, or outside approved limits. Policy selection
uses development data; final evaluation uses independent held-out data or valid
experimental outcomes. Do not use the selecting model as its own proof of policy
value. These outputs support approved experimentation; they do not execute or
deploy pricing policies automatically.

| Recipient | Output | Handoff |
|---|---|---|
| Pricing and driver operations | Candidate comparisons, uncertainty, guardrail status and policies worth testing | Decision report and interactive demo |
| Group 4 - Mobility Assistant | Price sensitivity and identified full/partial 2x2 response matrix | CSV/JSON |
| Group 1 | Labor participation/hours response with battery/charging constraints and separate acceptance response | CSV/JSON |
| GSM leadership and regulators | Traceable customer/driver/economic impact explanation and evidence limits | Report |

Request **eight raw source groups over the latest 12 months**, including
neighboring/control zones. GSM exports existing Parquet, UTF-8 CSV, or native
sources with original schema/rate, keys, and metadata. Researchers construct
research tables; field/grain requirements follow the data contract.

| Source group | Use |
|---|---|
| Booking & Demand | Funnel, requests, completed trips |
| Pricing & Promotion | Prices/benefits displayed before choice |
| Driver Supply & Status | Vehicle-hours, shifts, relocation, charging |
| Driver Earnings & Incentive | Offered terms, compensation, realized earnings |
| Matching & Operations | Dispatch, pickup/service/cancel, charging calibration |
| Customer Choice / Cross-service | Choice sets, nonbookers, own/cross effects |
| Policy & Context | Assignment, identification, support, context |
| Finance & Cost | Recognized revenue, direct/fixed/shared costs, approved allocation, incremental profit, contribution margin and ROI |

| Block/contract stage | Input | Output |
|---|---|---|
| `prepare_data` | Labeled raw/public/synthetic sources, metadata, mapping | Parquet research tables, quality report, JSON manifest |
| `fit_demand_choice`, `fit_supply`, `validate_benchmarks` | Choice/assignment or offer/state tables, estimands, splits | Three causal result packages, model bundles, baselines, full/partial effect matrix, supply response, diagnostics and independent benchmarks |
| `calibrate_baseline`, `simulate_marketplace`, `solve_equilibrium` | Request rates, admission plan, snapshot/rules/calibration, seed/budget | Trajectories, operational metrics, equilibrium or nonconvergence status |
| `compare_scenarios` | Finite supported candidates, agreed business metric/guardrails; common baseline/target scope, snapshot, paired seeds; accounting/uncertainty where available | Candidate CSV/JSON with demand/supply/choice/operations, supported economics, evidence, intervals and decision reasons; real profit/ROI conditional on GSM cost policies |
| `design_switchback`, `reconcile_experiment`, `handoff` | Supported actions, assignment/power/analysis spec, A/A protocol, frozen forecast; actual logs where available | Executable experiment package, schedule/ledger, valid experimental reconciliation, dashboard and reproducible package |

Request input is requests/hour. Supply is serviceable vehicle-hours; idle hours
are a subset. Tables/draws/trajectories use Parquet, specs/manifests JSON, models
implementation-specific bundles, and handoffs CSV/JSON. Stage execution and
metric/interval statuses are distinct.

The feedback cycle is schedule -> GSM policy execution and logs -> measured
impact versus frozen forecast -> updated model version. Evidence A applies only
to components supported by executed valid experiments.

Confounder features must precede intervention; post-treatment variables are
outcomes or mediators. Check duplicates, missingness, timezones, and joins.
Use Python/SQL, EconML or DoWhy for causal analysis, SimPy for discrete events,
and Streamlit for the demo. Store data/config/model versions for reproducibility.
GSM approves operational policy execution.

## Estimating the three responses

Each causal result specifies treatment and contrast, outcome and unit, population,
zone/service, behavioral horizon, policy variation, and identification assumptions.
Report an absolute effect; report elasticity only when its definition and positive
price/outcome denominators make it valid. Each package includes a point estimate,
confidence interval/status, simple comparison baseline, supported action range,
diagnostics, evidence A/B/C, and any unidentified component with its reason and
collection/experiment plan. These results can be handed off independently of a
completed simulator. Estimate only at resolutions supported by data. Prefer quoted
prices or tariff multipliers adjusted for trip characteristics; average realized
fares are distorted by selection and distance mix. Subscription benefits affect
the effective price shown to subscribers.

| Response | Outcome | Preferred identification | Interpretation |
|---|---|---|---|
| Customer price sensitivity | Total request effect; request elasticity when identifiable; quote conversion reported separately with complete quote exposure logs | Randomized prices -> historical tariff change/DiD -> DML | Conversion among observed quote opportunities alone does not identify total request demand |
| Supply | Labor participation, worked hours and serviceable hours under predecision offered compensation/incentives | Randomized incentives -> shift incentive changes/DiD | Use amount effects for incentives starting at zero; distinguish extra total supply from relocation |
| Cross-service | Each service's request response to both prices; full/partial 2x2 matrix and total X/Y effect | Separately identifiable price variation; optional nested logit with choice logs | Changing only X identifies one column; nonbooking requires complete opportunity windows |

| Method | Conditions | Assumptions/gate | Evidence |
|---|---|---|---|
| Randomized switchback/incentives | Executed assignments and validated logs/outcomes | Valid assignment/exposure/interference/carryover; A/A before pilot | A |
| DiD | Policy change with treated/control groups | Parallel trends and no unaccounted concurrent changes | B |
| DML | Historical data with sufficient observed context | No remaining unobserved confounding and adequate overlap | B |
| Known-parameter simulation | Controlled recovery tests without real data | Establishes behavior under declared simulated conditions | C |

DML residualizes observed context; it does not remove endogeneity from missing
shocks. Compare with correlation and adjusted regression baselines. Differences
show sensitivity, not which estimate is correct. Before DiD, inspect allocation,
anticipated demand, and concurrent changes.

Customer prices affect supply only through offered compensation, expected income
and adjustable driver decisions. Offered terms and expectations used for labor
response must be available before participation/hours decisions; realized post-shift
income is an outcome/mediator and cannot be substituted as a predecision treatment.
An expected-income causal channel requires its own identification basis. Fixed
shifts/salaries may imply zero additional hours; extra shifts, acceptance, and
charging timing need separate outcomes. Track neighbors to distinguish extra total
supply from relocation.

Two matrix columns require independent residual price variation. Report request
X/Y/total and conversion separately. `NONE` means no booking in a complete
observation window; it does not establish departure from GSM or competitor choice.

## Marketplace simulation and switchback validation

Identified causal responses produce demand and supply forecasts. The simulator
translates these forecasts into conditional operational and economic outcomes by
combining request flows, eligible drivers/vehicles, compensation, and matching
rules. It includes pickup/service time, waiting cancellation, return to availability,
and charging. Preserve states across analysis windows. Simulator convergence and
accounting validity are technical conditions; behavioral validity requires separate
identification and empirical checks.

The income-supply loop is expected earnings -> serviceable hours -> simulated
utilization and earnings -> updated expectations. Convergence requires consistent
income and supply summaries; preserve assumptions about shifts and unmodeled
behavior. The core design defines damping, finite budgets, and nonconvergence
handling. Fixed supply needs one pass.

Calibrate and assess on separate baseline data before comparing policies.
Match completed trips, wait, cancellations, and idle hours, including zone/time
errors. Without GSM logs, validation is against synthetic truth only.

| Metric | Definition | Requirement |
|---|---|---|
| Completed trips | Simulator outcome from requests, supply, and acceptance | Apply elasticity to requests once, never again to completion |
| Idle supply | Idle vehicle-hours or eligible idle vehicles at a point in time | State-time accounting; charging/ineligible separate; request-capacity gap is only a proxy |
| Wait/cancellation | Matching trajectories | Validate against separate baseline data |
| Simulated gross booking value | Completed trips multiplied by scenario fares | Illustrative/declared price units; does not imply realized GSM profit |
| Incremental GSM profit & ROI (conditional) | Target minus baseline recognized revenue less in-scope costs | Finance-approved scope and complete cost coverage; unavailable without confirmed GSM policy |
| Incremental contribution margin (conditional) | Policy difference after applicable variable costs | Confirm variable-cost classification and ledger with GSM; never label it total profit |

Resample appropriate clusters/time blocks, refit models, and rerun paired
baseline/target simulations. Separate statistical uncertainty, simulation
variability, and sensitivity to operational assumptions. Unsupported actions
retain explicit flags and cannot become supported forecasts through extrapolation.

Switchback randomizes policies by geographic cluster/time block. Design choices:

| Element | Basis | Risk addressed |
|---|---|---|
| Cluster and block length | Trip duration, driver movement, carryover | Neighbor contamination |
| Washout | Exclude designated transition observations | Residual effects from prior blocks |
| Price x incentive factorial | Separate supported action combinations | Confounded policy levers |
| Separate X/Y price schedules | Identifiable variation for each service | Missing matrix columns |
| Sample size | Worthwhile detectable effect and actual variability | Insufficient power |

The behavioral horizon must match the estimand. Short price switchbacks can test
request responses without identifying drivers' shift participation or added hours;
labor responses need assignments, exposure and horizons compatible with those
decisions. The experiment package contains:

1. Assignment, exposure, cluster/block/washout, power and analysis specifications,
   with agreed primary metric, guardrails and stopping rules.
2. An A/A protocol checking assignment/exposure logs, metric reconstruction and
   inference under no policy effect; executed results only when logs are available.
3. A frozen ledger of model/data/policy versions, forecast point estimates and
   intervals/statuses, population/horizon, support and assumptions.
4. A live monitor for agreed wait/cancel/driver-income/budget guardrails, separate
   from efficacy inference on the planned analysis schedule.
5. A reconciliation plan comparing identified measured effects with frozen
   forecasts for the same population and horizon, diagnosing deviations and then
   recording the next model version.

Before execution, freeze this package, run A/A and validate inference by repeated
simulation. Afterwards, inspect spatial/time dependence and reconcile forecasts.
Without valid actual logs, hand over the executable design and mark experimental
impact/reconciliation unevaluated. Real-time monitoring does not authorize repeated
unplanned efficacy tests. GSM approval remains required for live policy execution.

## Five-week roadmap

One cluster and two services; synthetic data allows progress without GSM.
Source data requests follow the [GSM data request](../GSM_DATA_CONTRACT.md).

| Week | Input | Review output |
|---|---|---|
| 1 | Eight-group/12-month raw request; public/synthetic sources; market/rules | Causal questions/estimands, mapping/quality/manifest, identification and split/acceptance specs, agreed business metric/guardrails and evaluation plan |
| 2 | Prepared choice/assignment or controlled blocks; separate Swissmetro | Demand/choice causal packages, full/partial matrix, baselines, diagnostics, support/intervals and independent method/choice reports |
| 3 | Predecision offered compensation/states; operations or synthetic truth; roster/rules | Labor participation/hours package; supported integrated forecasts, calibration/snapshot, trajectories, equilibrium status and baseline-error report |
| 4 | Finite supported candidates, independent policy-value evaluation, accounting/uncertainty, movement/carryover/power | Decision comparison with reasons/guardrails and separate uncertainty sources; experiment specification, A/A protocol and frozen forecast ledger; supporting dashboard/export |
| 5 | Completed scientific/technical artifacts; actual experiment logs if available | Reproducible evidence package, limits and gate status; executable pilot plan and conditional A/A/reconciliation results with next steps |

Without GSM, real calibration, causal effects, profit and ROI stay `not_evaluated`.
Synthetic recovery/coverage establishes only performance under tested conditions,
with evidence C. Approval alone is not A. GSM data/pricing/driver-operations
contacts confirm business definitions. A week-5 pilot prioritizes process checks;
power requirements may extend impact evaluation beyond five weeks.

| Deliverable | Content | Needs GSM data? |
|---|---|---|
| Three causal result packages | Estimands, absolute effects/valid elasticities, baselines, confidence intervals/statuses, support, assumptions, diagnostics and unidentified parts | Real GSM estimates require GSM data; controlled recovery/coverage and method packages can be delivered with evidence C |
| Policy decision evidence | Finite candidate comparisons, independent evaluation, agreed business criterion/guardrails, supported outcomes, uncertainty and reasoned testing decisions | Real GSM impact/economics require applicable GSM sources; synthetic comparisons remain conditional |
| Experiment package | Identification, executable switchback/A/A protocols, frozen forecasts, monitoring and reconciliation plan | Design can be prepared without GSM data; actual assignment, power calibration and reconciliation require appropriate GSM inputs/logs |
| Supporting system | Reusable core engine, versioned models, one-cluster simulator, headless scenarios, benchmark evidence, dashboard and CSV/JSON | No; controlled sources support technical development and validation within their declared conditions |
| Documentation | Code/configuration, rerun instructions, assumptions, evidence limits and missing-data/experiment plans | No |
| GSM results | Causal effects, real calibration, profit, ROI, experimental impact | Yes |

Outputs declare zone/service/horizon, uncertainty, support, evidence, and missing
sources. Unsupported components include a collection/experiment plan.

| Acceptance criterion | Requirement | Verification |
|---|---|---|
| Identification | Defined treatment/outcome/population/horizon, adequate variation/overlap and assumptions for each published causal result | Assignment/history review and identification/support diagnostics; unresolved parts stay unidentified |
| Estimation | Simple baseline, no leakage, parameter recovery, coverage and null/placebo behavior under declared conditions | Independent/repeated controlled benchmarks and valid historical/experimental diagnostics where available |
| Policy prediction and decision | Finite supported comparisons use an agreed business criterion and guardrails, independent evaluation and explicit uncertainty/decision reasons | Held-out evaluation with frozen selection/analysis rules; retain rejected candidates and conditional economics |
| Experimental validation | Executable design, frozen forecasts and reconciliation of identified effects on the same scope/horizon | A/A and inference checks; actual counterfactual accuracy remains unevaluated until valid experiment or historical identification is available |
| Simulator | Operational/economic forecasts require baseline trip/wait/cancel/idle errors within frozen thresholds | Separate holdout baseline; synthetic accuracy is evidence C only |
| Engine robustness | State/accounting invariants, explicit failures, validated carryover and bounded workloads | [Core engine validation protocol](../BENCHMARK.md#core-engine-validation-protocol) and recorded [release gates](CORE_ENGINE_DESIGN.md#173-acceptance-gates) |
| Reproducibility | Trace every metric to data/model/config/assumptions | Rerun saved versions and seeds |
| Completeness and transparency | Causal packages and supported scenarios report scope, units, intervals/statuses, evidence and missing parts | Independent seeds/contexts, package review; unidentified results include a collection/experiment plan |
| PoC integration | Dashboard and exports expose the same supported results, scope, units, evidence and statuses | Verified scenario walkthrough and artifact comparison |

Agree minimum worthwhile effects, business/guardrail criteria, coverage and
prediction/baseline error tolerances after week-1 inspection and before policy
selection/final evaluation; freeze runtime thresholds before final holdout. Do not
require complex models to win or policies to produce positive uplift. An explicit
unidentified result is transparent delivery, but the corresponding GSM measurement
remains open. Unavailable evidence remains unevaluated. GSM confirms eight groups/12 months,
compensation/finance definitions, variation, action bounds, assignments, and
guardrails. Missing sources leave dependent outputs unavailable; C development
continues.

| End-of-week-5 decision | Condition |
|---|---|
| Expand pilot | Causal scope/support and worthwhile candidate rationale are documented; required technical gates pass, data/design are adequate and A/A/logging checks pass; live execution remains subject to GSM approval |
| Collect more data | Insufficient power or identification; specify missing sources and next review |
| Pause rollout | Process checks fail or data/approved experiment bounds are unavailable |

### Method references

Chernozhukov et al. (2018), *Double/debiased machine learning for treatment and
structural parameters*. [Implementation documentation](https://www.pywhy.org/EconML/spec/estimation/dml.html).

Callaway and Sant'Anna (2021), *Difference-in-Differences with multiple time
periods*. [Method documentation](https://bcallaway11.github.io/did/).

Bojinov, Simchi-Levi, and Zhao, *Design and Analysis of Switchback Experiments*.
[Manuscript](https://arxiv.org/abs/2009.00148).
