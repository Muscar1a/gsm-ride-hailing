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
| Driver supply response | How do serviceable hours change with expected earnings or incentives? | Incentives target shortages; relocation and shifted charging can resemble extra supply |
| Cross-service substitution | How do X/Y requests and nonbooking probability change when one price changes? | Services share demand shocks; net changes do not identify individual customer switches |

Build causal response models and combine them in a marketplace simulator. The
reference business question is: **If service X price rises 10% in one zone/time
window, how do demand, serviceable supply, service choice, completed trips, and idle
supply change?** Supply response depends on compensation, offer dispatch, and the
trip acceptance decisions drivers can adjust. Commercial outcomes (simulated gross
booking value) are reported alongside operational service quality; real GSM profit
and ROI require confirmed cost and financial policies from GSM and remain conditional.

Deliver an end-to-end PoC built on a reusable core engine with verified
state/accounting, model validity, explicit failure handling, reproducible execution
and measured workload limits. Its first validated scope is one cluster and two services.
The PoC demonstrates supported scenario comparisons through a dashboard and exports
using engine results; delivery quality follows the
[engine standard](CORE_ENGINE_DESIGN.md#11-engine-delivery-standard).

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
| Marketplace | One-cluster simulator, equilibrium and idle supply per scenario | Citywide competition model |
| Validation | Switchback design and forecast reconciliation ledger; cluster pilot subject to GSM approval | Broad rollout |
| Delivery | End-to-end PoC with a validated core engine, headless scenario execution, dashboard and CSV/JSON | Production trip-level dispatch optimization |

Expected use: evaluate pricing and incentive policies by their operational and
commercial marketplace impact, with traceable accounting and uncertainty, and explain
customer, driver and service quality outcomes to GSM leadership and regulators.
These are objectives, not measured benefits.

## System and data

Pricing and driver operations teams choose a service, zone, horizon, and price
or incentive change. The system compares it with the current policy, reports
operational/economic outcomes and uncertainty, and prepares approved actions
for experimentation within GSM limits.

| Recipient | Output | Handoff |
|---|---|---|
| Pricing and driver operations | Price/incentive scenario comparisons | Interactive demo |
| Group 4 - Mobility Assistant | Price sensitivity and 2x2 response matrix | CSV/JSON |
| Group 1 | Supply response with battery/charging constraints | CSV/JSON |
| GSM leadership and regulators | Customer/driver impact explanation | Report |

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
| `fit_demand_choice`, `fit_supply`, `validate_benchmarks` | Choice/assignment or offer/state tables, estimands, splits | Model bundles, baselines, effect matrix/supply response, diagnostics, independent benchmarks |
| `calibrate_baseline`, `simulate_marketplace`, `solve_equilibrium` | Request rates, admission plan, snapshot/rules/calibration, seed/budget | Trajectories, operational metrics, equilibrium or nonconvergence status |
| `compare_scenarios` | Common baseline/target scope, snapshot, paired seeds; accounting/uncertainty where available | Scenario CSV/JSON with demand/supply/choice/operations, completion rate, simulated booking value, evidence and intervals; real profit/ROI conditional on GSM cost policies |
| `design_switchback`, `reconcile_experiment`, `handoff` | Supported actions, experiment spec, frozen forecast; actual logs where available | Schedule/ledger, valid experimental reconciliation, dashboard, reproducible package |

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

Each effect specifies outcome, policy variation, population/horizon, and causal
assumptions. Estimate only at resolutions supported by data. Prefer quoted
prices or tariff multipliers adjusted for trip characteristics; average realized
fares are distorted by selection and distance mix. Subscription benefits affect
the effective price shown to subscribers.

| Response | Outcome | Preferred identification | Interpretation |
|---|---|---|---|
| Customer price sensitivity | Request change per 1% price change; quote conversion reported separately | Randomized prices -> historical tariff change/DiD -> DML | Historical estimates require identification assumptions |
| Supply | Serviceable hours versus expected earnings/incentives | Randomized incentives -> shift incentive changes/DiD | Use amount effects for incentives starting at zero |
| Cross-service | Each service's response to both prices; 2x2 matrix | Separately identifiable price variation; optional nested logit with choice logs | Changing only X identifies one column |

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

Customer prices affect supply only through offered compensation/expected income
and adjustable driver decisions. Fixed shifts/salaries may imply zero additional
hours; extra shifts, acceptance, and charging timing need separate outcomes.
Track neighbors to distinguish extra total supply from relocation.

Two matrix columns require independent residual price variation. Report request
X/Y/total and conversion separately. `NONE` means no booking in a complete
observation window; it does not establish departure from GSM or competitor choice.

## Marketplace simulation and switchback validation

The simulator combines request flows, eligible drivers/vehicles, compensation,
and matching rules. It includes pickup/service time, waiting cancellation,
return to availability, and charging. Preserve states across analysis windows.

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

Before execution, freeze forecasts/model versions, metrics, horizon, analysis,
and stopping rules; run A/A and validate inference by repeated simulation.
During execution, monitor agreed wait/cancel guardrails; draw efficacy conclusions
on the planned analysis schedule. Afterwards, inspect spatial/time dependence,
compare measured causal effects with frozen forecasts, then update models.

## Five-week roadmap

One cluster and two services; synthetic data allows progress without GSM.
Source data requests follow the [GSM data request](../GSM_DATA_CONTRACT.md).

| Week | Input | Review output |
|---|---|---|
| 1 | Eight-group/12-month raw request; public/synthetic sources; market/rules/estimands | Mapping/quality/manifest, split/acceptance specs, identification design |
| 2 | Prepared choice/assignment or controlled blocks; separate Swissmetro | Demand/choice bundle, pooled/partial matrix, baseline/support/interval; method, choice, independent policy-value reports |
| 3 | Demand bundle; offered compensation/states/operations or synthetic truth; roster/rules | Supply model, calibration/snapshot, trajectories, price/incentive scenarios, equilibrium status, baseline-error report |
| 4 | Full model/snapshot/scenario, accounting/uncertainty, movement/carryover/power | Full-chain intervals, supported economics, dashboard/export, experiment spec, frozen prediction ledger |
| 5 | Completed artifacts/acceptance; actual experiment logs if available | Reproducible package, instructions, gate status; conditional reconciliation/A/A/pilot and next steps |

Without GSM, real calibration, causal effects, profit and ROI stay `not_evaluated`.
Synthetic recovery/coverage establishes only performance under tested conditions,
with evidence C. Approval alone is not A. GSM data/pricing/driver-operations
contacts confirm business definitions. A week-5 pilot prioritizes process checks;
power requirements may extend impact evaluation beyond five weeks.

| Deliverable | Content | Needs GSM data? |
|---|---|---|
| System | End-to-end PoC backed by a reusable core engine, versioned models, one-cluster simulator, headless scenarios, benchmark evidence, dashboard and CSV/JSON | No; controlled sources support technical development and validation within their declared conditions |
| Design | Identification, switchback, frozen forecast ledger | No |
| Documentation | Code/configuration, rerun instructions, assumptions | No |
| GSM results | Causal effects, real calibration, profit, ROI, experimental impact | Yes |

Outputs declare zone/service/horizon, uncertainty, support, evidence, and missing
sources. Unsupported components include a collection/experiment plan.

| Acceptance criterion | Requirement | Verification |
|---|---|---|
| Engine robustness | State/accounting invariants, explicit failures, validated carryover and bounded workloads | [Core engine validation protocol](../BENCHMARK.md#core-engine-validation-protocol) and recorded [release gates](CORE_ENGINE_DESIGN.md#173-acceptance-gates) |
| Reproducibility | Trace every metric to data/model/config/assumptions | Rerun saved versions and seeds |
| Completeness | Price/incentive scenarios return demand/supply/choice/idle and supported operations/economics | Headless scenarios on independent seeds and supported contexts |
| PoC integration | Dashboard and exports expose the same supported engine results, scope, units, evidence and statuses | Verified scenario walkthrough and artifact comparison |
| Transparency | Intervals, support/extrapolation, evidence beside metrics | Review dashboard and exports |
| Estimation | Parameter recovery, coverage, null/placebo behavior | Repeated controlled benchmarks |
| Simulator | Baseline trip/wait/cancel/idle errors within frozen thresholds | Separate holdout baseline |
| Counterfactual accuracy | Forecast agrees with identified measured effects | Valid experiment or historical identification |

Freeze error/runtime thresholds after week-1 inspection and before final holdout.
Unavailable evidence remains unevaluated. GSM confirms eight groups/12 months,
compensation/finance definitions, variation, action bounds, assignments, and
guardrails. Missing sources leave dependent outputs unavailable; C development
continues.

| End-of-week-5 decision | Condition |
|---|---|
| Expand pilot | Core engine passes technical gates; adequate data/design and passing A/A/logging checks |
| Collect more data | Insufficient power or identification; specify missing sources and next review |
| Pause rollout | Process checks fail or data/approved experiment bounds are unavailable |

### Method references

Chernozhukov et al. (2018), *Double/debiased machine learning for treatment and
structural parameters*. [Implementation documentation](https://www.pywhy.org/EconML/spec/estimation/dml.html).

Callaway and Sant'Anna (2021), *Difference-in-Differences with multiple time
periods*. [Method documentation](https://bcallaway11.github.io/did/).

Bojinov, Simchi-Levi, and Zhao, *Design and Analysis of Switchback Experiments*.
[Manuscript](https://arxiv.org/abs/2009.00148).
