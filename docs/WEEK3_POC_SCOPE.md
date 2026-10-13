# Current Week-3 PoC scope

Bun's scope decision on 12 October 2026 narrows the runnable PoC to price/demand,
individual trip acceptance and earnings under a fixed online driver population.
This document governs the current increment; broader research requirements in
the original proposal remain separately identified.

## Assumptions and outputs

- Declare the online driver/vehicle roster and its size before each run; hold it
  fixed over the observation horizon and shared across X/Y. Online drivers may
  be idle or busy. Online count is not the count of drivers available for a new trip.
- Drivers decide whether to accept each offered request. Refusal leaves the driver
  online and idle; it does not remove labor hours or create additional drivers.
  Busy drivers cannot serve simultaneous trips. Acceptance is a separate response
  from labor participation or decisions to start/stop working.
- There is no scheduled allocation of hours or model of drivers logging in/out in
  this PoC. The observation horizon bounds measurement, not assigned working shifts.
  Existing fixture shift fields describe legacy operational input constraints;
  they must not be reported as an implemented behavioral scheduling model.
- Use the approved rule that completed trips pay the driver 100% of the displayed
  fare. Preserve the explicit synthetic tariff, quote/pay terms, completed-only
  settlement and income denominators in [USAGE](USAGE.md#week-3-minimal-compensation).
- No incentive policy, bonus response, income-induced hours, schedule builder,
  charging extension or income-supply equilibrium is required for this increment.
  When drivers are busy, refuse offers or cannot match a request, retain the
  request's wait/expiry/cancellation outcome; do not synthesize extra capacity.
- Compare supported baseline and price scenarios using demand X/Y, offers and
  acceptance, completed trips, wait/expiry/cancellation, idle time and gross driver
  earnings. Keep support, units, scope and evidence attached to each output.

## Implemented behavior and validation

Demand handoff, fixed-online operations, individual offer decisions and 100%-fare
earnings settlement run headlessly. The recommended rules are
[`week3_poc.json`](../configs/week3_poc.json), schema version 3:

- The same declared online roster covers the complete observation horizon. Legacy
  snapshot `shift_*` fields validate horizon coverage; they do not allocate work.
- A request offers to an eligible idle driver; the pending offer reserves the
  vehicle in `dispatch` state. The declared Bernoulli acceptance probability is
  0.8, independent of price, with a 3-second response and 10-second timeout.
- Each driver/request pair draws once from a stable seeded decision. A refusal
  releases the reservation and leaves the driver online; attempts are bounded at
  20 per request. The request retains its original pickup deadline.
- Expiry/cancellation withdraws a pending offer. A withdrawn or timed-out offer
  cannot later assign a trip. Busy or reserved drivers cannot receive overlapping
  assignments. Pending offers and their remaining events survive continuation.
- `driver_offers` retains unaccepted and unresolved offers; `offer_events` records
  transitions. Acceptance is accepted divided by accepted + rejected + timed-out
  responses resolved in the current window, including carry-in offers. Withdrawals
  and still-pending offers are excluded and reported separately.
- Immutable displayed fare/pay terms precede the decision. Only completed trips
  settle the 100%-fare ledger, once; all roster drivers remain in income summaries.

No empirical acceptance rate or price-to-acceptance coefficient is available.
The constant decision rule is a synthetic assumption, not an estimated elasticity.
Legacy V1/V2 immediate-acceptance controls remain reproducible under their own
rules; they do not define the current fixed-online PoC.

`evaluate-marketplace` freezes baseline/target demand, rules, compensation and an
independent seed protocol. It compares paired Poisson trajectories, checks a
hand-computable separated-offer mechanism and measures 2/20/100-driver workloads.
Its intervals concern Monte Carlo means conditional on fixed fitted demand/rules;
causal/full-chain intervals remain unavailable. Streamlit displays completed
simulation artifacts separately from choice fits and exports CSV/JSON without
running the engine. See [USAGE](USAGE.md#week-3-fixed-online-poc) and
[the operational protocol](BENCHMARK.md#week-3-fixed-online-operational-assessment).
The scoped PoC is implemented, technically verified and accepted by reviewer Bun
on 12/10/2026 ([week3_poc_acceptance.md](submission/days/20261012/week3_poc_acceptance.md)). The
[12 October closeout](submission/days/20261012/week3_poc_closeout.md) and
[verification](../artifacts/research/20261012/week3_poc_verification.json) record 609
passing tests and 303/303 assessment jobs, with all frozen gates
passed. Replay and pending-offer continuation preserve the applicable request,
offer, state-time and completion-pay accounting. Workloads measured 2/20/100
drivers at about 450 requests; the 10,000-request limit is a cap, not a measured
capacity claim. Technical verification remains synthetic evidence C.
The 100 assessment seeds are separate from the pilot; paired arms and workload
checks intentionally share seeds and are not 303 mutually independent draws.

The [controlled labor package](WEEK3_SUPPLY.md) and its independent RCT/null results
are retained as prior scientific evidence. They are not inputs or required
extensions of the current fixed-online PoC. Do not replace the online roster with
incentive-driven hours or interpret trip acceptance as income/labor elasticity.

## Interpretation limits

Fixing online supply is a PoC assumption, not an estimated zero labor response.
This restricted increment does not complete the original problem's driver labor
supply elasticity or certify the original three-response research deliverable.
Current synthetic behavior remains evidence C, `not_calibrated`; GSM causal
effects, costs/profit/ROI and real driver decisions remain unevaluated.
