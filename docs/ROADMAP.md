# PoC Roadmap — Week 2 Closeout and Weeks 3–5

Owner: **Nguyễn Thành An**, working solo. Reviewed **2026-10-08**;
latest executed evidence is the **2026-10-07** submission, Asia/Bangkok.
Data, units and interfaces follow [GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md).
Algorithms follow the [core engine design](reference/CORE_ENGINE_DESIGN.md);
the demand/choice specification and generator equations are in
[IDENTIFICATION.md](IDENTIFICATION.md).

GSM raw data is unavailable. TLC supplies completed-trip context, synthetic truth
supplies controlled behavior/operations, and Swissmetro is a separate choice
baseline. New forecasts remain evidence C; GSM calibration, causal effects and
ROI stay `not_evaluated`.

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

| Order/contract stage | Input | Output/acceptance |
|---|---|---|
| Prepare demand/snapshot | Frozen choice model, expected bookings/block, roster/initial state, policy/units | Versioned `demand_plan` in requests/hour = expected bookings/block_hours, snapshot/specs |
| `simulate_marketplace` with fixed supply | Demand plan, fixed shifts, snapshot, matching/service rules | Trajectory; +10% price X changes requests once; no double assignment or fabricated supply response |
| Operational constraints | Synthetic patience/cancel, energy/SOC, station capacity, boundary/return rules | Wait/cancel/idle/charging, state carryover, censoring; reconciled requests/vehicle-hours |
| `fit_supply` and supply prediction | Synthetic offered terms/assignments/eligibility, shift/state outcomes, roster/compensation rules | Supply model, diagnostics, `admission_plan`; distinguish extra shifts, relocation, charging |
| `calibrate_baseline` | Controlled operational truth, separate fit/validation/holdout | Calibration bundle, snapshot, synthetic baseline-error report; GSM remains `not_calibrated` |
| `solve_equilibrium` | Demand/supply/calibration bundle, common snapshot/horizon, policy, seed/budget | `equilibrium_result`, residual trace; one pass for fixed supply; return `not_converged` when appropriate |
| `compare_scenarios` and handoff | Separately solved baseline/target with paired seeds; unchanged, +10% price X, increased bonus amount | `scenario_result` CSV/JSON, artifact-reading demo, week-3 acceptance table |

Offered compensation precedes decisions. Retain eligible nonparticipants and zero
trips. Use an amount treatment for zero-base bonuses; do not count bonuses already
included in expected income twice. Count shared fleet once. Relocation creates
no new hours; charging is not subtracted twice. Separate controlled observations,
rules, and oracle.

Week-3 outputs follow the contract: demand X/Y/total, net choice changes,
serviceable/idle hours, completed trips, wait/cancel, and charging. Include
source, unit, denominator, support, evidence C, and status. Missing intervals or
economics remain unavailable with reasons.

Required tests: request accounting with carry-in/out; nonoverlapping states;
SOC/charger capacity; zero supply/response, zero bonus, relocation, charging
bottlenecks, insufficient support, and nonconvergence. Compare baseline errors
with controlled truth; do not call this GSM calibration. Run repository checks
and demand regression checks.

Use core solver defaults: damping 0.3, at most 50 iterations, 600 seconds/job.
Freeze event budgets/tolerances/replicates before execution; confirm with
independent seeds. Proposed modules: `compensation.py`, `supply.py`,
`marketplace_simulator.py`, `equilibrium.py`, `marketplace_scenario.py`.
Add SimPy and update the lockfile only when implementing the simulator.

## 3. Handoff and follow-up

Keep large model/data/run artifacts ignored; every output has a manifest/checksum.
Prioritize fixed supply -> operational constraints -> supply -> equilibrium.
Defer advanced UI and zone heterogeneity before reducing conservation checks.

Week 4 adds full-chain uncertainty, supported accounting/economics, power/carryover,
switchback specs, and a frozen prediction ledger. Continue C-level development
without GSM while requesting **eight raw source groups over the latest 12 months**.
When GSM arrives, reassess mapping/quality/identification/calibration before
forecasting; an adapter swap or borrowed synthetic coefficients is insufficient.
