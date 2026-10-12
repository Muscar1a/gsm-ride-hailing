# Week 3 controlled labor-supply package

This increment implements the scientific driver-supply branch of the
[proposal](reference/GSM_Causal_Marketplace_Proposal.md). It estimates offered-term
effects independently of marketplace simulation. GSM sources are unavailable:
all behavior and the availability bridge below are synthetic evidence C.

Under Bun's [current PoC scope](WEEK3_POC_SCOPE.md), agreed on 12/10/2026,
this package is retained as independent scientific evidence outside the current
PoC delivery path. The PoC assumes a fixed online roster with per-request
accept/reject decisions; it does not integrate incentive-driven participation,
working-hour forecasts or allocated shifts. Acceptance is not labor supply,
and a fixed online roster cannot identify labor elasticity.

## Estimand and observation contract

The treatment is a predecision offered incentive, baseline 0 versus target 20
`SYNTHETIC_UNIT` per participating shift in the development fixture. These are
illustrative amount levels, not VND, a GSM compensation policy or an income
elasticity. One Bernoulli assignment is made per eligible driver, probability 0.5,
and held fixed across the complete seven-shift follow-up. The eligible cohort is
frozen before announcement; every declared driver/shift opportunity remains in
the observed table, including nonparticipants and zero outcomes.

| Outcome | Reported effect unit | Population |
|---|---|---|
| `participated` | Probability difference; multiply by 100 for percentage points | All eligible driver/shift opportunities |
| `worked_hours` | Hours per eligible driver/shift, including zeros | Same complete cohort |
| `serviceable_hours` | Serviceable hours per eligible driver/shift | Same cohort under the declared availability bridge |

`observed/driver_decisions.parquet` contains exactly these columns:

- `decision_id`, `driver_id`, `shift_id`: nonempty IDs; decision and driver/shift keys unique.
- `eligibility_at`, `offered_at`, `decision_at`, `shift_start`, `shift_end`,
  `outcome_observed_at`: offset-aware timestamps in causal order. Terms must be
  offered strictly before the decision. The full observation must reach shift end.
- `offered_incentive_amount`, `assignment_probability`: one supported term level
  per driver, with the declared randomization probability.
- `participated`, `worked_hours`, `serviceable_hours`: complete observed outcomes;
  missing is rejected, never filled with zero. Hours are bounded by the offered
  shift; nonparticipants have zero hours and serviceable hours cannot exceed labor hours.

The calendar, eligible driver count, shifts per driver, treatment levels, currency,
assignment/inference units and interval settings are pinned in `observed/contract.json`.
Dropping nonparticipants, shifts or drivers violates this contract. This adapter
accepts only its declared synthetic cohort; it cannot be relabeled GSM or evidence A/B.

The default scientific fixture has 800 eligible drivers, seven complete eight-hour
shift opportunities, one shared cohort, and no relocation between regions.
It is separate from the two-hour/two-vehicle operational fixture. It provides no
service-specific labor coefficient or measured relocation response.

## Estimation, baseline and uncertainty

The fixed estimator first averages each outcome over the complete follow-up for
each driver, then compares treatment-arm means. Welch t intervals use the number
and variance of distinct drivers; repeated shifts are not independent replicates.
Its identification relies on the declared independent driver assignment, complete
outcomes, and absence of interference/common market shocks in this generator.
It is not an inference recipe for geographic GSM incentive assignment.

The no-response baseline has effect zero for all three outcomes. Conditional
hours among participating shifts are reported as descriptive selected-population
means, not a separately identified causal effect. No model selection, preprocessing
or nuisance training occurs in this fixed randomized analysis; development and
independent assessment seeds are separate. Future learned response forecasts
will require their own driver/time splits.

Each effect exports point/interval status, support, unit, population, inference
unit, contrast and evidence. Both arms require at least 20 distinct drivers in
the default profile. Unsupported arms withhold effects; zero observed variance
withholds the CI rather than fabricating precision. Intervals are individual,
not simultaneous across all outputs, and are not clipped to physical bounds.

`scenario-supply` accepts only the two supported amount levels and the same frozen
cohort/calendar. It scales hour effects and their intervals by the fixed number
of eligible driver/shift opportunities; participation retains probability units.
The CI targets the policy change, not future realized hours or predictive intervals.
A baseline-to-baseline comparison has a deterministic zero change. Intermediate
or larger incentives return `unsupported_action`; missing support stays explicit.

## Controlled generator and oracle isolation

Driver-specific participation and hours variation induce repeated-driver dependence.
Separate random streams generate contexts, assignment and responses. Known
conditional means and the declared serviceable fraction live in
`oracle/driver_expectations.parquet`; generator assumptions live in
`generator_spec.json`. Fitting copies and reads only the observed table and its
contract. Oracle values are used after fitting for evaluation, never as features
or fitting targets. The evaluator records observed/oracle value identities and seeds.

The initial availability bridge is a declared driver-specific fraction, 0.75-0.95
of labor hours. It represents excluded unavailable/break time in controlled data;
it is not charging calibration or a physical admission schedule. No trip acceptance
probability enters this fraction. This fraction does not set the current PoC's
online roster or allocate driver/vehicle schedules.

## Frozen evaluation protocol

[Profile](../configs/week3_supply.json),
[pilot](../configs/week3_supply_pilot.json) and
[assessment](../configs/week3_supply_assessment.json) are explicit, bounded inputs.

| Phase | RCT seeds | Null seeds | Purpose |
|---|---|---|---|
| Pilot | 51001-51005 | 52001-52005 | Development/resource checks only |
| Assessment | 61001-61100 | 62001-62100 | Independent controlled assessment of the fixed estimator |

The null generator sets both participation and conditional-hours treatment effects
to zero. Each benchmark retains every attempted seed and every outcome's point/CI
availability, coverage, interval width, bias/RMSE and null false positives. Coverage
and false-positive proportions include exact binomial uncertainty; unavailable
intervals are reported separately and cannot improve the acceptance result.

Development limits are frozen before assessment: absolute bias <=0.04 probability
or <=0.20 hours; RMSE <=0.08 probability or <=0.30 hours; coverage >=0.90;
null false-positive rate <=0.10; every point/interval available. These are initial
controlled diagnostic gates, not certification of nominal 95% coverage and not
Bun's acceptance of Week 3. The Week-2 technical exception is not inherited.

Each job has a 600-second limit and at most 500 seeds per DGP. Budget exhaustion
fails the stage instead of publishing a completed assessment. Protocol/spec,
source snapshots, source/config/lock hashes, environment and per-seed identities
are retained in the run manifest. Reusing assessment seeds for tuning invalidates
their independent assessment role; a changed method needs a fresh protocol/cohort.

## Relationship to the current PoC

Minimal compensation settlement is implemented independently through
`simulate-marketplace --compensation`: Bun's approved assumption pays drivers
100% of displayed app fares for completed trips. It uses explicit synthetic
tariff/pay terms and presence-hour income, including zero-trip drivers; see
[usage](USAGE.md#week-3-minimal-compensation). The scientific supply bundle above
is unchanged. Realized earnings do not become its predecision treatment and no
price-to-hours response is inferred automatically.

The next PoC increment is bounded dispatch offers and accept/reject decisions
within the fixed online roster, followed by supported price/earnings scenarios
and operational validation. Immediate acceptance is still the implemented
baseline; reject behavior is not yet implemented. Incentives, endogenous
online/offline decisions, shift allocation and income-supply equilibrium are
outside this PoC scope, not prerequisites for its next increment.
Income elasticity, operational/equilibrium intervals and GSM economics remain
unidentified or unevaluated. Headless JSON/CSV handoffs for this separate
scientific package remain runnable through
[USAGE](USAGE.md#week-3-controlled-labor-supply).
