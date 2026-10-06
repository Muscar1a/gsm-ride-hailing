# GSM Data Contract and Stage Inputs/Outputs

This is the repository standard for data requests, formats, units, and stage
interfaces. `docs/general/` describes the design; `docs/task/` defines weekly
work and acceptance. Executed results are recorded in [VALIDATION.md](VALIDATION.md).
GSM interfaces remain proposed until native schemas and adapters are confirmed.

The previously cited `GSM Causal Marketplace - Data Requirements.pdf` is absent
from the repository. These requirements carry forward the existing contract.

## 1. GSM data requirements

Request **eight raw source groups covering the latest 12 months**, including
relevant services, neighboring zones, and controls. Extend history to cover
policy changes. For shorter retention, supply all retained records and report
actual coverage. The initial one-cluster, two-service model does not reduce the
source request or exclude controls.

GSM exports existing tables, event logs, and snapshots at their native schema
and sampling rate, with stable pseudonyms, join keys, and business definitions.
Nguyễn Thành An maps, joins, checks quality, constructs research tables, and
estimates effects. GSM need not prepare 30-minute aggregates, training data,
elasticities, or counterfactual labels.

| Source group | Records and fields to retain | Purpose |
|---|---|---|
| 1. Booking & Demand | Request/booking/trip and status events; customer/session/quote/request/trip/driver/vehicle IDs, retry/parent; request/dispatch/accept/arrival/pickup/dropoff/cancel/expiry; event/ingestion times; status, cancel actor/reason; zones, expected/actual distance and duration; fare/refund/payment status/transaction | Funnel and operational outcomes, including cancellations, timeouts, and no-driver requests |
| 2. Pricing & Promotion | Tariff/version/effective time; quote/service/zone; base/distance/time/minimum/surge/surcharges/taxes; prices before/after discounts and currency; voucher rules/eligibility/exposure/redemption/budget/funder; subscription fee/benefits/enrollment/lifecycle/balance | Prices and benefits visible before choice; separate quotes from payments/refunds |
| 3. Driver Supply & Status | Driver/contract, vehicle assignments, compensation/service eligibility; scheduled/offered/accepted/actual/absent shifts; online/offline/available/dispatch/pickup/on-trip/break/charging; timestamp, zone, ineligibility, sampling/gaps | Serviceable vehicle-hours; separate extra hours, relocation, and charging; retain drivers/shifts with zero trips |
| 4. Driver Earnings & Incentive | Versioned pay/incentive rules; amount/threshold/stacking/cap/eligibility, applicable zone/time; announced/assigned/displayed/acknowledged times, including eligible nonrecipients; displayed expected/guaranteed earnings/progress where available; earnings ledger/transaction, trip/shift/driver/incentive keys, pay/share/commission/bonus/deductions, earned/paid times | Offered terms are treatment; realized earnings are outcomes. If displayed expectations are absent, supply rules and source inputs |
| 5. Matching & Operations | Every dispatch attempt/response; dispatch/request/driver/vehicle keys, attempt, offer/receive/respond, accept/reject/timeout/deadline/reason/version; candidates/ranks where available; quote/dispatch/acceptance ETA and actual pickup; vehicle eligibility/maintenance/SOC; charging session/station/charger keys, queue/plug/start/end/unplug, kWh/power/cost, capacity/outages | Calibrate matching, timing, capacity, and charging; identify which queue is measured |
| 6. Customer Choice / Cross-service | Search/quote-generation/display/refresh/interaction; customer/session/quote-set/quote/event keys and times; selected quote/service, request link; displayed/available/reason/position, price/discount/ETA/distance/duration/zone/policy; click/book/exit/end, observation end | Actual displayed choice sets, unchosen options, and nonbooking sessions |
| 7. Policy & Context | Policy/version, prior/new values, announced/effective time, eligibility/allocation reason/rule; assignment unit/key/time, arm, assigned/applied/exposure/override; cluster/block schedule, probability/strata/seed where available, washout/stopping/concurrent changes; zone/grid versions, weather/traffic/events/outages | Identification, support, interference, and carryover; researchers join external context separately |
| 8. Finance & Cost | Revenue/payment/cost/adjustment ledgers and rules; transaction/request/trip/driver/vehicle/shift/promotion/incentive/charging keys; occurred/posted times; fare/payment/discount/refund/tax/toll/pay/bonus/funder/electricity/payment fee/variable cost; currency/reconciliation/allocation version | Revenue and contribution margin; distinguish fixed/variable costs and prevent double counting |

Retain nonbookers, unchosen/unavailable options, failed requests, and eligible
drivers who receive no incentive or decline shifts. Completed transactions
alone do not provide adequate comparison groups.

## 2. Formats, keys, and units

| Layer | Format | Requirements |
|---|---|---|
| GSM export | Parquet, UTF-8 CSV, or existing native export | Separate tables/logs; preserve native names/rate; include dictionary, keys, schema history, coverage/retention, timezone, units, and null definitions |
| Research tables/context/trajectories | Parquet | Explicit grain/keys, source/version, quality flags, and denominators; never overwrite raw data |
| Specs, manifests, diagnostics | UTF-8 JSON | Scope, mapping, config/data/code/lock hashes, environment, seeds, stage status, timings, failures, and checksums |
| Models | Implementation-specific bundle; current PoC uses `.joblib` | Feature/outcome/treatment order, baseline, support, and manifest; the full `response_bundle` remains a proposed interface |
| Result handoff | UTF-8 CSV and JSON | Consistent metrics, units, sources, evidence, intervals/support/status, and unavailability reasons |

GSM supplies inventories, time ranges, row counts, and existing reconciliation
totals. Researchers produce quality and join-rate reports after export.
Customer/driver/vehicle pseudonyms must be stable across sources and time;
direct identifiers are unnecessary. Zone/grid metadata includes boundary
versions, precision, and transformations.

```text
customer -> session -> quote_set -> quote -> request/booking -> trip
request -> dispatch -> driver/vehicle -> shift/charging_session
```

Check cardinality, effective periods, retries/parents, and failed links.
Nearest-time joins require uncertainty labels. Mark source/field availability
as `available`, `not_recorded`, or `not_applicable`. Never replace null, unknown,
or unobserved values with zero. Assign `NONE` only after a complete observation
window with complete logs; it does not establish competitor choice. No trips
does not establish that a driver was offline.

| Quantity | Unit/definition |
|---|---|
| Timestamp | Preserve Parquet timestamp types; use ISO 8601 in JSON/CSV. Follow source timezone metadata without assuming UTC. Keep naive TLC wall-clock timestamps with `assumed_timezone=America/New_York`; declare simulator timezone |
| Prices, incentives, earnings | Declare currency and per-trip/per-shift/per-hour basis; separate predecision offered/displayed terms from realized payments/earnings |
| Demand | `quote_sessions` -> choice probability -> requests; `request_rate` is requests/hour; the simulator produces completed trips |
| Supply | `serviceable_hours` = idle + reserved/dispatch + pickup + on-trip; exclude charging/charging_queue/break/ineligible. `idle_hours` is a subset; count shared fleet once |
| Duration, distance, energy | Seconds, km, kWh; SOC in [0,1]. Preserve original TLC miles/USD and add km; currency conversion does not transfer behavior |
| Analysis window | Default 30 minutes; distinct from driver shifts, event times, and experiment blocks/washout |

## 3. Shared research tables

These are researcher-built logical interfaces, **not tables GSM must prepare**.
Map and validate native keys before applying these grains.

| Interface | Grain/key | Main content |
|---|---|---|
| `quote_session` | One session / `session_id` | Customer key, context, observation window, outcome/censoring |
| `quote_option` | One option per display/refresh / quote-set + quote + display-event key | Service, displayed/available, visible price/discount/ETA/position, policy version |
| `booking_event` | One native status event / event key | Request/booking/trip/session links, status/time, cancel actor/reason, retry/parent |
| `policy_assignment` | One assignment / assignment key | Unit/time, arm, offered/assigned/applied, probability/rule, exposure/override |
| `driver_offer_shift` | One offer/shift decision event / native decision key | Driver/shift, eligibility, terms known before decision, acceptance/rejection, outcome |
| `driver_vehicle_state` | Native state event or constructed interval / source + event/interval key | Driver/vehicle/shift, zone, state/eligibility/SOC, gaps/coverage |
| `payment_cost` | One ledger item / native ledger key | Business links, revenue/refund/pay/bonus/cost/funder/currency, rule version |
| `operational_event` | One dispatch/trip/charging event / source + native event key | Attempts/responses, timestamps/duration/distance, station/energy, matching version |
| `demand_block` | Zone x time block x service | Quote exposure, requests, conversion, pretreatment context, completeness |
| `baseline_snapshot` | One baseline window / snapshot version | Initial states, roster, request rates, calibration/rules, quality |

Refreshing quotes does not create independent customers. The initial PoC selects
one decision/session under a rule frozen before fitting. Refresh sequences need
a separate estimand.

| Artifact exchanged between modules | Minimum content |
|---|---|
| `demand_plan` | `zone_id`, `service_id`, `block_start`, `block_end`, `request_rate`; model/source versions, exposure mode, support |
| `admission_plan` | Driver/vehicle/shift keys, shift start/end, service eligibility, roster reference, target serviceable hours, compensation version |
| `scenario_result` | Scenario/run/model/snapshot IDs, scope; metric baseline/target/delta; unit/population/denominator, source/evidence, interval/support/status/reason |
| `prediction_record` | Frozen model/snapshot/policy/assignment versions, forecast, analysis plan; reconciliation never overwrites the frozen record |

Each output has a schema/version and run/source references in its manifest.
New logical fields require implementation mapping; they are not claims about
current code support.

## 4. Stage inputs and outputs

Stage/output names are logical interfaces; new bundles and schemas require
implementation mapping. Downstream stages use completed outputs with compatible
versions, scopes, and units.

| Stage | Input | Output | Gate for downstream use |
|---|---|---|---|
| `prepare_data` - week 1 | Source exports + dictionary/keys/coverage, or labeled public/synthetic sources | Research tables, quality report, manifest; TLC silver/marts/train-only context | Keys/grain/cardinality, timestamps, missingness, and totals reconciled |
| `fit_demand_choice` - week 2 | Quotes/options + assignments + outcomes, or controlled `choice_block`; estimand/split | Demand/choice bundle, 2x2 matrix or identified columns, baseline probabilities, effects, diagnostics, bootstrap | No oracle leakage; pretreatment features; valid rank/support/probabilities |
| `validate_benchmarks` - week 2 | Frozen estimators/policies + observed synthetic data; evaluator-only oracle; separate Swissmetro data | `method_metrics.csv`, `evaluation/evaluation_metrics.csv`, choice-baseline report, policy-value report | Independent holdout; explicit counts/failures/coverage; policy selection model cannot grade itself |
| `fit_supply` - week 3 | Offered compensation/incentives + assignments/eligibility + shift/state outcomes; roster/rules | Supply model, compensation rules, diagnostics; predictions become `admission_plan` | Separate extra hours/relocation/charging; use amounts for zero-base bonuses; realized earnings are not treatment |
| `calibrate_baseline` - week 3 | Operational events/states/rules and separate baseline splits | Calibration bundle, `baseline_snapshot`, holdout baseline-error report | Calibrate from available sources; missing operational logs leave dependent metrics `not_calibrated` |
| `simulate_marketplace` - week 3 | `demand_plan` in requests/hour + `admission_plan` + snapshot/policy/compensation/calibration + seed/budget | Request/vehicle/charging trajectories and earnings ledger | Reconcile requests/state-time/SOC/chargers/ledger; apply elasticity only to demand |
| `solve_equilibrium` - week 3 | Demand/supply/calibration bundle + snapshot/policy + seed/budget; invokes simulator | `equilibrium_result`, trajectories, residual trace, convergence status | Fixed supply takes one pass; candidates restart from the same snapshot; never report nonconverged output as equilibrium |
| `compare_scenarios` - weeks 3-4 | Baseline/target with common scope/snapshot/paired seeds; accounting rules and uncertainty spec when available | `scenario_result`, CSV/JSON: demand/choice/supply/trips/wait/cancel/charging; supported economics/intervals | Week 3 validates operations at C; week 4 adds full-chain uncertainty and supported economics; missing outputs retain reasons |
| `design_switchback` - week 4 | Supported actions, movement/carryover, power/guardrails, model/snapshot | Experiment spec, assignment schedule, frozen `prediction_record` | Freeze estimand/block/washout/analysis before outcomes; A/A before pilot |
| `reconcile_experiment` - week 5, conditional | Frozen prediction + validated assignment/exposure/applied logs + outcomes | Forecast delta versus causal effect at the same estimand/horizon; next model version | A requires an executed, valid experiment; unexecuted work remains `not_evaluated` |
| `handoff` - week 5 | Completed bundles/results/specs + acceptance table | Artifact-reading dashboard, CSV/JSON, rerun instructions, status report | No fit/bootstrap during UI rendering; trace data/config/code/seeds |

The week-2 `scenario_result.json` contains X/Y/NONE, net probability changes,
and expected bookings for a fixed session population. Bridge to the simulator
with `request_rate = expected_bookings / block_hours`. Expected bookings are not
completed trips. Full forecasts combine demand/choice, supply, and calibration;
a DML model alone is not a full response bundle.

## 5. Validation, evidence, and status

| Source | Use | Limits |
|---|---|---|
| NYC TLC HVFHV, version pinned in manifests | Schema, completed-trip marts, context; implemented | Missing quotes/nonbookers/failed requests/driver-online/bonus/SOC; realized fares are not prechoice quotes; platforms are not GSM services |
| Synthetic/semi-synthetic with truth | Effect recovery; tests for implemented supply/simulator/solver components | Behavior is evidence C; isolate oracle from fitting/scenarios. Supply/simulator/solver remain planned |
| EPFL Swissmetro | Separate choice baseline; implementation remains pending in validation | Stated preference; `CHOICE=0` is unknown; travel time/headway are not pickup ETA; never join to TLC/GSM |
| GSM | Fit/calibration/economics/experiments when sources qualify | Raw data unavailable; public/synthetic coefficients cannot be transferred directly |

A/B/C describe effect evidence, not raw observations. Synthetic effects are C;
valid historical GSM identification is B; executed valid experiments are A.
Combined forecasts retain dependency-level evidence and may be `mixed_evidence`.

Before fitting/calibrating GSM, reassess DAG/estimand, assignment, pretreatment
features, support, compensation, and inference/resampling units using local
splits. DML does not remove hidden confounding; swapping adapters does not
establish identification or coefficient transferability.

Demand/choice validation retains five DGPs: `RCT_SYN`, `OBSERVED_CONFOUNDING`,
`HIDDEN_CONFOUNDING`, `NULL_EFFECT`, and `COLLINEAR_PRICE`. Reporting targets are
**100 seeds per DGP, 199 day-bootstrap draws per identified estimator**; these
are targets, not completed results. Refit nuisance/effect/baseline models and
keep each original day in one fold. Report bias/RMSE, coverage/null false
positives with binomial intervals, valid/failed counts, and runtime. Hidden
confounding is a stress case; collinear prices must be rejected. RCT_SYN targets:
theta RMSE <= 0.10, scenario probability RMSE <= 0.02. Flag draw failures above
5% and unstable intervals.

Stage execution uses `pending/running/succeeded/failed`. Metric/scenario status
uses `ok/partial`, `not_identified`, `insufficient_support/out_of_support`,
`invalid_probability/invalid_state`, `not_calibrated`, `not_converged`,
`budget_exceeded`, `not_evaluated`, or `sensitivity_only`. Interval status is
separate: `ok`, `interval_unstable`, or `interval_unavailable`. Do not clip
probabilities, discard failed draws, or fill zeros to manufacture success.

Use the confirmed revenue ledger and `contribution_margin = revenue - variable_cost`.
Calculate `incentive_roi = delta_contribution_margin / delta_incentive_cost`
only with positive incremental incentive cost and complete required costs.
Contribution margin already subtracts incentives once. Missing costs/rules leave
economics unavailable. Toy policy benchmarks report only `simulated gross booking
value`; the PoC has not measured GSM economic impact.
