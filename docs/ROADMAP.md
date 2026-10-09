# PoC and Core Engine Roadmap — Week 2 Closeout and Weeks 3–5

Owner: **Nguyễn Thành An**, working solo. Reviewed **2026-10-09**;
latest submitted Week 2 evidence is the **2026-10-07** submission, Asia/Bangkok.
Source data requests and export requirements follow
[GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md).
Research schemas and artifact conventions follow
[ARCHITECTURE.md](ARCHITECTURE.md#research-table-schemas).
Algorithms follow the [core engine design](reference/CORE_ENGINE_DESIGN.md);
the demand/choice specification and generator equations are in
[IDENTIFICATION.md](IDENTIFICATION.md).

GSM raw data is unavailable. TLC supplies completed-trip context, synthetic truth
supplies controlled behavior/operations, and Swissmetro is a separate choice
baseline. New forecasts remain evidence C; GSM calibration, causal effects and
ROI stay `not_evaluated`.

## Delivery objective

Deliver an end-to-end PoC backed by a reusable core engine with validated response
models, operational accounting, explicit failure states, reproducible scenarios
and measured resource limits. Its first validated market scope is one cluster
and two services. The PoC demonstrates the path from prepared data and response
models through simulation to baseline/target comparisons, dashboard and exports.
Headless results, dashboard values and CSV/JSON must refer to the same versioned
engine outputs, scope, units and statuses. The two-vehicle fixture establishes a
development case; release requires independent correctness, statistical and
workload checks under the
[engine delivery standard](reference/CORE_ENGINE_DESIGN.md#11-engine-delivery-standard).

The five-week sequence is a planning target. Acceptance follows recorded evidence
and frozen quality gates; unfinished requirements remain open at handoff.

## Weekly inputs and outputs

These are weekly requirements and targets, not completion records.

| Week | Required input | Expected output and acceptance |
|---|---|---|
| 1 | Labeled raw/public/synthetic sources, metadata/keys, market/rules/estimands | Research tables, quality report, manifests, splits and acceptance specification; validate keys/grain/units/totals |
| 2 | Choice/assignment records or controlled blocks; separate Swissmetro data and independent evaluator | Demand/choice bundle, common matrix or identified columns, baseline/support/interval diagnostics and method/choice/policy reports; no oracle leakage |
| 3 | Frozen demand/choice bundle; offered compensation, shift/state/operational records or declared synthetic truth; shared roster, rules, initial snapshot, seeds and budgets | Supply/calibration bundles, versioned plans/snapshots, trajectories, price/incentive comparisons, equilibrium status and baseline-error report; invariant, failure and independent controlled benchmark evidence |
| 4 | Full model/snapshot, accounting rules, uncertainty specification, movement/carryover and power assumptions | Full-chain intervals, supported economics, headless scenario comparisons, workload benchmarks, dashboard/exports, experiment specification and frozen forecast |
| 5 | Versioned engine/artifacts, correctness/statistical/performance evidence and acceptance records; actual experiment logs if an experiment occurs | Runnable end-to-end PoC and reproducible engine package, rerun instructions, validated scope/limits and gate status; conditional A/A/pilot and forecast-versus-effect reconciliation |

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
Energy/charging and the other operational constraints remain to implement.
Completing this bridge does not close the Week 2 reviewer or final reporting gates.

Offered compensation precedes decisions. Retain eligible nonparticipants and zero
trips. Use an amount treatment for zero-base bonuses; do not count bonuses already
included in expected income twice. Count shared fleet once. Relocation creates
no new hours; charging is not subtracted twice. Separate controlled observations,
rules, and oracle.

Week-3 target metrics are demand X/Y/total, net choice changes,
serviceable/idle hours, completed trips, wait/cancel, and charging. Include
source, unit, denominator, support, evidence C, and status. Missing intervals or
economics remain unavailable with reasons.

Required tests: request accounting with carry-in/out; nonoverlapping states;
SOC/charger capacity; zero supply/response, zero bonus, relocation, charging
bottlenecks, insufficient support, and nonconvergence. Compare baseline errors
with controlled truth; do not call this GSM calibration. Run repository checks
and demand regression checks.

Prioritize state transitions and carryover, cancellation, energy/charging,
compensation/supply, baseline validation, then equilibrium and paired scenario
comparison. Each component needs independent checks of its equations/state
accounting and failure behavior before integration. Extend beyond the small
fixture using the [core engine validation protocol](BENCHMARK.md#core-engine-validation-protocol).

Use core solver defaults: damping 0.3, at most 50 iterations, 600 seconds/job.
Freeze event budgets/tolerances/replicates before execution; confirm with
independent seeds. Proposed modules: `compensation.py`, `supply.py`,
`marketplace.py`, `equilibrium.py`, `marketplace_scenario.py`.
SimPy is now declared and locked for the implemented fixed-supply simulator.

## 3. Handoff and follow-up

Keep large model/data/run artifacts ignored; every output has a manifest/checksum.
Engine correctness, model validity, reproducibility and resource benchmarks take
priority over dashboard polish. Preserve conservation and failure checks when
expanding the validated workload or model complexity.

Week 4 adds full-chain uncertainty, supported accounting/economics, power/carryover,
switchback specs, and a frozen prediction ledger. Continue C-level development
without GSM while requesting **eight raw source groups over the latest 12 months**.
When GSM arrives, reassess mapping/quality/identification/calibration before
forecasting; an adapter swap or borrowed synthetic coefficients is insufficient.

Week 5 packages the reproducible engine and PoC handoff, including a verified
scenario walkthrough and acceptance status. A/A, a pilot and forecast reconciliation
depend on actual GSM data and experiment authorization.
A week-5 pilot prioritizes process checks; impact evaluation may extend according
to the power analysis.
