# GSM raw-data request and research interfaces

The canonical request is the supplied
[GSM Causal Marketplace — Data Requirements](<GSM Causal Marketplace - Data Requirements.pdf>).
This document summarizes that request and separates GSM's source exports from
the research interfaces proposed below. It does not describe a confirmed GSM
schema or an implemented GSM adapter. The earlier 8–12-week sample suggestion
is superseded by the canonical request for **the latest 12 months**.

## Scope and responsibilities

Request all eight source groups for the relevant services and areas, including
neighboring and control areas. Extend history when needed to cover policy
changes. For sources retained for less than 12 months, export all available
history and state the actual coverage. Include nonbookers, cancellations,
timeouts, no-driver cases, unchosen options and eligible drivers/shifts without
trips or incentives. Completed transactions alone omit essential comparisons.

GSM extracts existing tables, event logs and snapshots in their native schemas,
provides stable pseudonyms and explains business definitions. Field names below
are logical names for mapping; they do not require renaming native fields.
Export at the recorded sampling rate. GSM is not asked to join tables, create
30-minute aggregates, infer queues or prepare training data, elasticities,
expected earnings or counterfactual labels.

**Nguyễn Thành An, the sole researcher,** maps schemas and native keys, verifies
joins and data quality, constructs conversion funnels and supply hours, builds
zone/time aggregates and features, and performs estimation. If a forecast was
not recorded, the researcher reconstructs it only where the source data and
rules support doing so, with assumptions and uncertainty recorded.

## Eight source groups

Keep source tables and logs separate. The canonical PDF contains the full field
request; this catalog groups the principal native records and their use.

| Source group | Existing records and principal fields requested | Research use and interpretation |
|---|---|---|
| 1. Booking & Demand | Request/booking/trip tables and status events; request, booking, trip, customer, driver, vehicle, session and selected-quote IDs; retry/parent mappings; request/dispatch/accept/arrival/pickup/dropoff/cancel/expiry timestamps; event versus ingestion time; statuses and cancellation actor/reason; planned/actual zones, distance and duration; final fare, refund, payment status and transaction ID | Separate requests from completed trips; construct funnels and operational outcomes. Include retries, cancellations, timeouts and no-driver requests. |
| 2. Pricing & Promotion | Tariff IDs/versions and effective dates; quote/service/zone IDs; base, distance/time, minimum, surge, surcharge, tax and fee components; quoted price before/after discount, currency and tax inclusion; promotion/voucher rules, eligibility, exposure/redemption, budgets and funder; subscription versions, fees, benefits, enrollment/lifecycle and balance changes | Reconstruct the price and benefits visible before choice. Preserve quote, realized payment and refund separately. |
| 3. Driver Supply & Status | Driver/contract and vehicle-assignment history; pay/commission rules, service eligibility and shift flexibility; scheduled/offered/accepted/actual shifts and absences; timestamped online/offline, available, dispatching, pickup, on-trip, break and charging states; zone/grid, ineligibility reasons, sampling rate and gaps | Derive available/busy/charging hours and distinguish net supply growth from relocation. Retain drivers/shifts with no trips; absence of trips does not establish offline status. |
| 4. Driver Earnings & Incentive | Versioned pay/incentive rules, amounts, thresholds, stacking/caps, eligibility and geography/time; announced/assigned/displayed/acknowledged timestamps, including eligible nonrecipients; expected/guaranteed earnings and progress displays if recorded; realized earnings ledger with transaction, trip/shift, driver and incentive keys, base pay/revenue share, commission, bonus, deductions, earned/paid times | Offered terms and information known before decisions are treatments; realized earnings are later outcomes. If displayed expectations were not recorded, provide rules and source inputs for research reconstruction. |
| 5. Matching & Operations | Every dispatch attempt and response: dispatch/request/driver/vehicle IDs, attempt number, offer/receive/respond times, accept/reject/timeout, deadline/reason and matching version; candidate sets/ranks if recorded; ETA at quote/dispatch/accept and actual pickup; vehicle eligibility, availability/maintenance and battery telemetry; charging sessions, station/charger keys, queue/plug/charge/unplug times, state of charge, kWh/power/cost and station capacity/outages | Calibrate matching, waiting and service capacity from actual recorded logs. Keep native rates and distinguish measured queues from unavailable observations. |
| 6. Customer Choice / Cross-service | Search, quote-generation, display/refresh and interaction logs; customer/session/quote-set/quote/event keys and times; selected quote/service and request links; displayed/available flags and reasons, position, visible price/discount, ETA, planned distance/time, zones and policy/tariff versions; click/book/exit/end events and observation end | Reconstruct each displayed choice set, including unchosen and unavailable alternatives and sessions without bookings. Server-generated quotes are distinct from displayed quotes. |
| 7. Policy & Context | Policy IDs/versions, prior/new values, announced/effective times, eligibility and allocation reason/rule; assignment unit/key/time, treatment/control arm, assigned/applied value, exposure/execution and override reason; experiment cluster/block schedules, probabilities/strata/seed when recorded, washout/stopping rules and concurrent changes; versioned zone boundaries/grid, weather/traffic/events and operational outages | Review causal identification, support, spillover and carryover. Preserve controls. External context can be joined by the researcher if GSM has not recorded it. |
| 8. Finance & Cost | Revenue/payment/cost/adjustment ledgers and rules; transaction/request/trip/driver/vehicle/shift/promotion/incentive/charging keys; occurred/posted times; gross fare, customer payment, discounts/refunds, taxes/tolls, driver pay/bonus, funding party, charging/electricity, payment fees and variable costs; currency/reconciliation status, versioned allocation rules and effective dates | Reconcile realized revenue and incremental contribution margin. Separate fixed costs from scenario-dependent costs and avoid counting the same payment, promotion or bonus twice. |

## Delivery, keys and missingness

Accept Parquet, UTF-8 CSV or existing export formats, preserving native names,
individual tables and sampling rates. Include available data dictionaries/code
lists, keys, units, timezone, null definitions, schema history, retention and
sampling coverage. Provide a file inventory with time ranges/row counts where
available, plus existing request/trip/hour/finance reconciliation totals.
Research quality reports and join-rate calculations are produced after export.

Customer, driver and vehicle pseudonyms must be consistent across sources and
time. Names, phone numbers, identity documents and home addresses are not needed.
Use zone/grid locations with boundary versions and transformation/precision
definitions. Preserve vehicle reassignment and policy-version history.

The required native-key chains are:

```text
customer → session → quote_set → quote → request/booking → trip
request → dispatch → driver/vehicle → shift/charging_session
```

When native keys differ, provide existing mappings and key definitions. Check
cardinality, effective dates and failed links explicitly. A nearest-time match
must not be treated as a certain join. Request retries and service changes need
their parent keys or recorded mapping tables.

For each source and field, state **Known/available (Có)**, **Not recorded (Chưa
ghi nhận)** or **Not applicable (Không áp dụng)**. Preserve null, missing,
unobserved and actual zero as distinct states; unknown information must not be
filled with zero. Missing request links do not automatically label a session as
nonbooking: define its observation window and logging completeness first.
Nonbooking within that window does not establish leaving GSM or choosing a
competitor.

Quoted prices, displayed promotions and offered bonuses must precede the
decision they explain. Realized fares, refunds, pay and earnings are later
outcomes or intermediate variables. Realized hourly earnings do not substitute
for the information drivers knew before choosing a shift or accepting an offer.

For financial evaluation, confirm revenue, funding and cost-allocation
definitions, reconciliation status and which costs change with policy. Customer
payment minus driver pay is not automatically profit. Contribution margin
requires the agreed relevant variable costs; report ROI as unavailable when
required costs are missing. Incentive ROI requires a positive incremental-cost
denominator. No GSM revenue, margin or profit impact is measured in the current
PoC.

## Research-derived interfaces (proposed, not source exports)

These seven logical interfaces are internal research proposals after native
schema mapping. They are **not seven tables GSM must prepare**, not GSM schema
names, and not a replacement for the eight source groups. Their exact keys and
grain must follow the native event history. They are not yet a GSM adapter.

| Logical interface | Illustrative grain / key | Research content |
|---|---|---|
| quote_session | One observed session / session_id | Stable customer key, timestamps/timezone, zones, observation window and recorded session outcome |
| quote_option | One alternative in a quote-set display/refresh / quote_set_id + quote_id + display event | Display/availability, visible price/discount/ETA, position and policy version, including unchosen options |
| booking_event | One status event / native event key | Request/booking/trip/session links, status/time and cancellation actor/reason |
| policy_assignment | One assignment / native assignment key | Unit, timing, offered value, control arm, rule/probability, exposure, application and overrides |
| driver_offer_shift | One offer/shift decision event / native offer or event key | Driver/shift links, offered terms, eligibility, decision time and compensation rule |
| driver_vehicle_state | One state interval or native state event | Driver/vehicle/shift links, region, online/availability/busy/charging state and measured battery information |
| payment_cost | One native ledger item / transaction key | Trip/shift/charging links, revenue/refund/pay/bonus/cost components, funding, currency and rule version |

## Public benchmarks while awaiting GSM

- **NYC TLC HVFHV: implemented.** Used for trip-schema validation, operational
  marts and completed-trip contexts. `hvfhs_license_num` identifies a platform,
  not a GSM service; `base_passenger_fare` is a trip fare, not a prechoice quote.
  TLC lacks the full request funnel, nonbookers, visible choice sets, driver
  identity/online history and incentive assignment. Recorded request-to-pickup
  time concerns trips present in the file.
- **Known-parameter synthetic/semi-synthetic benchmark: implemented.** OLS/DML
  and the price-response matrix are tested against controlled truth, including
  TLC-derived operational contexts. This is evidence C, not GSM effects.
- **EPFL Swissmetro: requested separate choice baseline, not implemented here.**
  The canonical request adds a stated-preference choice benchmark using choice,
  alternative cost/travel time and availability fields. It must remain separate
  from TLC and GSM. `CHOICE=0` is unknown, not nonpurchase; travel time/headway
  are not pickup ETA. This repo does not claim a locally verified Swissmetro
  row/person count, completed adapter or fitted baseline.

Do not join records or transfer effect estimates between New York, Switzerland
and GSM. Public benchmarks validate individual modules and do not reduce the
eight-group GSM request. The Swissmetro baseline is an outstanding item relative
to the canonical two-week public-data plan; see [VALIDATION.md](VALIDATION.md)
for the actually executed TLC and simulation work. Supply response, operational
calibration and GSM ROI need their corresponding data before real-world claims.

## Review before GSM adaptation

1. Verify schema, keys, duplicate events, missingness, time ordering, coverage
   and join cardinality against native definitions.
2. Define quote conversion, requests and completed trips separately; fit
   preprocessing only on training data and preserve unavailable outcomes.
3. Review the DAG, estimand, assignment mechanism, support and resampling unit.
   More observations or replacing a TLC adapter does not establish causal
   identification; DML cannot remove unobserved confounding by itself.
4. Establish the response permitted by compensation: extra shifts/hours,
   acceptance, relocation or charging changes. A zero baseline bonus uses a
   money-denominated treatment rather than percentage elasticity.
5. Agree economic definitions and guardrails before policy-value evaluation,
   and keep estimated offline results distinct from executed GSM experiments.

## Supply and simulator interface (planned)

| Quantity | Unit / meaning |
|---|---|
| Demand input | Requests per hour, by service, zone and time |
| Supply input | Available eligible vehicle hours, excluding charging |
| Service duration | Seconds per trip with pickup/service components |
| Vehicle state | Idle/busy/charging and state of charge, with transition rules |
| Compensation | Offered expected pay by shift/trip, with fixed and variable components |
| Simulator output | Completed trips, waiting, cancellations, idle vehicle hours, charging |

Apply price response to incoming requests exactly once. A future matching
simulator produces completed trips from those requests and available supply.
Specify finite iterations, timeouts and explicit non-convergence before adding an
equilibrium loop. Calibrate on a separate operational baseline period.

## Switchback design (planned)

Document assignment units, geographic interference, block duration, transition
washout, separate price schedules, price × bonus factorial structure, safety
metrics, analysis schedule and independent sample size. Freeze predictions,
model versions and the analysis plan before observing experimental outcomes.
Run and validate A/A assignment/logging checks first. Authorization to experiment
does not establish evidence A until the experiment is executed and validated.
