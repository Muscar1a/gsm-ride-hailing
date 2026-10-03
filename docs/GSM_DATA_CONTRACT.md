# GSM data request and next-phase interfaces

These are proposed contracts for discussion with GSM. They are not claims about
GSM's current schemas and are not an implemented real-data adapter.

| Table | Grain / proposed key | Minimum fields |
|---|---|---|
| quote_session | One viewer session / session_id | pseudonymous customer_id, timestamp + timezone, origin/destination zones or distance band, session status |
| quote_option | One visible service / session_id + service_id | quoted total, currency, displayed discount/promotion, quoted ETA, availability, policy_id |
| booking_event | One event / event_id | booking_id, session_id, service_id, timestamp, status, cancellation actor/reason |
| policy_assignment | One assignment / policy_id + assignment_unit + assigned_at | unit type, effective start/end, offered price/bonus, control arm, probability or rule version, assignment reason |
| driver_offer_shift | One offer/shift / driver_id + shift_id + offer_time | pseudonymous driver_id, bonus offered, eligibility, compensation scheme |
| driver_vehicle_state | One state interval / vehicle_id + start | pseudonymous driver/vehicle IDs, start/end, zone, online/idle/busy/charging, state of charge |
| payment_cost | One booking/shift item / booking_id or shift_id + cost item | collected revenue, driver pay, bonus paid, variable cost, currency |

Request one cluster, two services, and initially 8–12 contiguous weeks, with policy
change logs and compensation definitions. This is an exploration sample request;
sample sufficiency depends on independent assignments, variation and effect size.
Include nonbookers, unchosen visible options, and eligible drivers who decline
offers or do not add shifts. Completed trips alone omit essential comparisons.

Confirm join cardinality, pseudonymization, retention, timestamps, timezones,
currency, status transitions and the precise moment each feature becomes known.
Offered incentives and expected compensation must precede decisions; realized
payments are later outcomes or intermediate variables.

## Review before adaptation

1. Verify schema, keys, duplicate events, missingness, time ordering and joins.
2. Define quote conversion and requested services separately from completed trips.
3. Review the DAG, estimand, policy assignment mechanism, support and resampling
   unit. Merely replacing a TLC adapter does not establish identification.
4. Establish the response measure permitted by compensation: added shifts/hours,
   acceptance behavior, relocation or charging adjustments.
5. Establish cost definitions before producing margin or ROI. A zero baseline
   bonus uses a money-denominated treatment, not a percentage elasticity.

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
