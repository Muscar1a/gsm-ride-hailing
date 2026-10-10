# GSM Data Request

This document specifies the source data and export information requested from
GSM. Provide existing raw tables, event logs and snapshots with their native
schemas, keys and metadata.

## 1. GSM data requirements

Request **eight raw source groups covering the latest 12 months**, including
relevant services, neighboring zones, and controls. Extend history to cover
policy changes. For shorter retention, supply all retained records and report
actual coverage.

GSM exports existing tables, event logs, and snapshots at their native schema
and sampling rate, with stable pseudonyms, join keys, and business definitions.
GSM need not prepare aggregates, training data, elasticities, or counterfactual
labels. Requested fields describe their meaning; retain native field names
and provide the corresponding dictionary.

| Source group | Records and fields to retain | Purpose |
|---|---|---|
| 1. Booking & Demand | Request/booking/trip and status events; customer/session/quote/request/trip/driver/vehicle IDs, retry/parent; request/dispatch/accept/arrival/pickup/dropoff/cancel/expiry; event/ingestion times; status, cancel actor/reason; zones, expected/actual distance and duration; fare/refund/payment status/transaction | Funnel and operational outcomes, including cancellations, timeouts, and no-driver requests |
| 2. Pricing & Promotion | Tariff/version/effective time; quote/service/zone; base/distance/time/minimum/surge/surcharges/taxes; prices before/after discounts and currency; voucher rules/eligibility/exposure/redemption/budget/funder; subscription fee/benefits/enrollment/lifecycle/balance | Prices and benefits visible before choice; separate quotes from payments/refunds |
| 3. Driver Supply & Status | Driver/contract, vehicle assignments, compensation/service eligibility; scheduled/offered/accepted/actual/absent shifts; online/offline/available/dispatch/pickup/on-trip/break/charging; timestamp, zone, ineligibility, sampling/gaps | Serviceable vehicle-hours; separate extra hours, relocation, and charging; retain drivers/shifts with zero trips |
| 4. Driver Earnings & Incentive | Versioned pay/incentive rules; amount/threshold/stacking/cap/eligibility, applicable zone/time; announced/assigned/displayed/acknowledged times, including eligible nonrecipients; displayed expected/guaranteed earnings/progress where available; earnings ledger/transaction, trip/shift/driver/incentive keys, pay/share/commission/bonus/deductions, earned/paid times | Offered terms are treatment; realized earnings are outcomes. If displayed expectations are absent, supply rules and source inputs |
| 5. Matching & Operations | Every dispatch attempt/response; dispatch/request/driver/vehicle keys, attempt, offer/receive/respond, accept/reject/timeout/deadline/reason/version; candidates/ranks where available; quote/dispatch/acceptance ETA and actual pickup; vehicle eligibility/maintenance/SOC; charging session/station/charger keys, queue/plug/start/end/unplug, kWh/power/cost, capacity/outages | Calibrate matching, timing, capacity, and charging; identify which queue is measured |
| 6. Customer Choice / Cross-service | Search/quote-generation/display/refresh/interaction; customer/session/quote-set/quote/event keys and times; selected quote/service, request link; displayed/available/reason/position, price/discount/ETA/distance/duration/zone/policy; click/book/exit/end, observation end | Actual displayed choice sets, unchosen options, and nonbooking sessions |
| 7. Policy & Context | Policy/version, prior/new values, announced/effective time, eligibility/allocation reason/rule; assignment unit/key/time, arm, assigned/applied/exposure/override; cluster/block schedule, probability/strata/seed where available, washout/stopping/concurrent changes; zone/grid versions, weather/traffic/events/outages | Identification, support, interference, and carryover; researchers join external context separately |
| 8. Finance & Cost | Existing revenue/payment/cost/adjustment, payroll and asset-expense ledgers and rules; transaction/request/trip/driver/vehicle/shift/promotion/incentive/charging keys; occurred/posted times and accounting period; fare/payment/discount/refund/tax/toll/pay/bonus/funder/electricity/payment fee, variable/fixed/shared cost and cost category; vehicle lease/depreciation, maintenance, insurance and overhead where recorded; native allocation inputs/bases, scope, currency, reconciliation/allocation version | Reconcile GSM-recognized revenue and all costs within an agreed scope, including fixed/shared expenses, without double counting |

Retain nonbookers, unchosen/unavailable options, failed requests, and eligible
drivers who receive no incentive or decline shifts. Completed transactions
alone do not provide adequate comparison groups.

## 2. Export formats and accompanying information

Provide **Parquet, UTF-8 CSV, or existing native exports**, separated by source
table/log. Preserve native field names, data types, timestamps, sampling rates
and recorded units.

Include the following information with each export:

| Information | What GSM should provide |
|---|---|
| Source inventory | Table/log names, purpose, record grain, time range, row count, retention and known gaps |
| Data dictionary | Native field names/types, business definitions, status/code meanings, units and null definitions |
| Keys and relationships | Primary/event keys, links between tables, retry/parent relationships and driver/vehicle/shift assignments |
| Timestamp metadata | Timezone/offset, timestamp precision and meaning; distinguish event, ingestion, announcement and effective times |
| Schema and rule history | Schema changes and applicable tariff, policy, promotion, compensation and accounting versions/effective periods |
| Availability | Mark missing sources/fields as `not_recorded` or `not_applicable`; report actual coverage for available data |
| Reconciliation references | Existing totals and their definitions, where available, to check the exported records |

Report unavailable fields explicitly. Preserve missing, unknown and not-applicable
values rather than replacing them with zero.

## 3. Identifiers, relationships and units

Customer, driver and vehicle pseudonyms must be stable across sources and time;
direct personal identifiers are unnecessary. Preserve native keys and document
the relationships linking:

```text
customer -> session -> quote_set -> quote -> request/booking -> trip
request -> dispatch -> driver/vehicle -> shift/charging_session
```

Include zone/grid definitions, boundary versions, geographic precision and
coordinate transformations where applicable. Identify vehicles shared by services
through the same vehicle key.

| Quantity | Information to preserve or declare |
|---|---|
| Timestamp | Preserve native timestamp types and declare timezone/offset; use ISO 8601 for CSV timestamps without assuming UTC |
| Prices, incentives, earnings and costs | Currency and per-trip/per-shift/per-hour basis; distinguish offered/displayed terms from realized payments/refunds |
| Demand and choice | Separate quote sessions, displayed options, requests, bookings and completed trips; retain their keys and status history |
| Driver/vehicle status | Native state events or snapshots, sampling rate, shift links, eligibility and coverage gaps, including zero-trip shifts |
| Duration, distance and energy | Preserve source values and declare units, including SOC scale; do not silently convert units |

For sessions without a booking, include observation start/end and log coverage
so nonbooking can be distinguished from incomplete observation. Preserve quote
refreshes with their original session/quote relationships. Retain driver status
records independently of trip activity.
