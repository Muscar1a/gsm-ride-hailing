# Benchmark protocol: method accuracy and business value

## Objective and current status

The benchmark should establish where the method works, whether it supports better
pricing decisions, and eventually whether those decisions improve GSM's business.
It must allow zero uplift, negative uplift and a simpler estimator winning.

| Layer | What it establishes | Current status |
|---|---|---|
| Controlled method benchmark | Recovery of known effects under specified assumptions | Implemented in `evaluate.py`; executed results in `VALIDATION.md` |
| Controlled pricing-policy benchmark | Quality of decisions against independent simulated truth | Proposed extension; not implemented or executed |
| GSM offline policy evaluation | Estimated value under verified real-data identification and support | Requires GSM logs and a separate evaluator |
| GSM randomized validation | Incremental realized revenue under the tested deployment | Requires a designed and executed GSM experiment |

Good effect estimates do not by themselves establish revenue uplift. The existing
scenario engine outputs simulated quote choices with a fixed viewer population;
it does not output actual revenue, completed trips or profit.

## 1. Method benchmark

Keep the existing naive OLS, adjusted OLS and LinearDML comparison. Use identical
data, day splits, seeds, weights and evaluation contexts for each estimator.

Run all five existing cases: randomized prices, observed confounding, hidden
confounding, null effects and collinear prices. Record:

- Per-cell theta bias and RMSE, with absolute errors when truth is zero.
- Frozen-test scenario probability RMSE and invalid-probability frequency.
- Bootstrap interval coverage and null false positives, with binomial intervals.
- Attempted/valid/failed counts, identification rejections and runtime.

Fit and validation failures are recorded separately for each estimator on a shared
generated seed. A rejected estimator does not remove another estimator's valid
measurements. A failure to generate the shared data is recorded for every estimator.

The preconfigured technical targets for RCT_SYN are theta RMSE at most 0.10
per cell and scenario probability RMSE at most 0.02. They are controlled-DGP
targets, not business success criteria. Hidden confounding is a stress case;
collinear prices should reject separate effects. Adjusted OLS matches the current
additive DGP well, so DML need not outperform it.

A bounded fresh-seed point-accuracy run uses:

```powershell
uv run python -m gsm_poc evaluate --config configs/demo.toml --seed 10001 --seeds 20 --bootstrap-draws 0 --dgps RCT_SYN OBSERVED_CONFOUNDING HIDDEN_CONFOUNDING NULL_EFFECT COLLINEAR_PRICE
```

This has 20 seeds per case and no bootstrap intervals; coverage and false-positive
performance remain unmeasured by this run. The existing reporting configuration
targets 100 seeds and 199 bootstrap draws. Benchmark one seed before scaling it;
the measured TLC-context 199-draw fit took approximately 8.6 minutes on this
machine. Point accuracy and interval calibration are separate reporting gates.

This fresh-seed run completed as `20261003T135730-1ae94396`: all 100 seed jobs
finished with no failed jobs. Its measured results and limitations are recorded
in [VALIDATION.md](VALIDATION.md#fresh-seed-point-accuracy-benchmark).

## 2. Proposed pricing-policy benchmark

### Freeze the business objective

Specify which services GSM owns, which prices it can change, baseline fares,
currency, and the payment/cost definitions. If Y is a competitor, keep its price
fixed and exclude its bookings from GSM revenue. If both services belong to GSM,
include substitution between them in the total business objective.

Until these inputs are supplied, monetary results are unavailable. A toy study
may use explicitly declared illustrative fares or normalized price units, with
the output named **simulated gross booking value**. TLC fares must not silently
be substituted for hypothetical X/Y fares.

For that controlled study, value is:

```text
V(policy) = sum_contexts N(context) ×
            sum_owned_services p(service | context, policy) ×
            baseline_fare(service, context) × price_multiplier(service, context)
```

This assumes the quote population is fixed and each booking completes and pays
the stated fare. It omits cancellations, capacity, traffic response, refunds and
operating costs. It cannot be labeled realized GSM revenue or contribution margin.

### Compare decisions fairly

Use the same supported action set for every learner, initially the finite
0.90/1.00/1.10 grid for controllable prices. Check joint/context support and
probability validity for every candidate. Include:

1. The unchanged-price policy, always available as a fallback.
2. A declared simple pricing rule.
3. A pricing policy selected using naive OLS.
4. A pricing policy selected using adjusted OLS.
5. A pricing policy selected using DML.
6. The oracle's best policy within the same action/constraint set, as an upper
   reference available only in a controlled benchmark.

Fit on training days; use validation days to choose the policy and any tuning
settings. Freeze it before final-test evaluation. Learners cannot access oracle
parameters or probabilities. Only the evaluator may score the frozen policies
using held-out oracle outcomes. Evaluating a policy only with the same fitted
model that selected it would make the benchmark circular. Policy learning and
independent value evaluation have distinct roles; see
[Athey and Wager](https://arxiv.org/abs/1702.02896).

Report on the same test contexts for all policies:

- Value per 1,000 quote sessions, in the explicitly declared units.
- Absolute and relative uplift over unchanged pricing; relative uplift is
  unavailable when baseline value is zero.
- Paired differences against the simple rule and both OLS policies.
- Regret: oracle value minus learned-policy value, within the shared action set.
- Conversion/expected-choice changes, rejected candidates, fallback frequency
  and runtime.
- Per-seed results and uncertainty for paired differences, preserving failed
  seeds. Separate variability across independent simulated seeds from day
  resampling within one dataset.

Bootstrap the complete fit-and-select procedure if the target is performance of
the learning procedure. Resampling outcomes for an already frozen policy measures
a different uncertainty target. Name the target explicitly and keep final-test
data out of policy selection.

Do not change the DGP, seed list or constraints after seeing final results to
obtain positive uplift. The current DGP may give several estimators the same best
grid action; then their policy values tie even if coefficient RMSE differs.
More challenging cases must be motivated and declared before fresh evaluation.

## 3. GSM offline validation

Required data include nonbooking quote sessions, displayed options and prices,
policy assignments and their probabilities/rules, completion/cancellation
events, collected payments/refunds, promotions, driver compensation, variable
costs and operational availability. Agree join keys, currency, timestamps and
feature availability before fitting. Completed TLC trips cannot supply this.

Define the actual GSM revenue ledger measure and report contribution margin
separately. Do not count competitor bookings, gross customer payments or driver
payments as interchangeable revenue measures.

When assignment propensities and the identification assumptions are credible,
use an independent policy evaluator with inverse-propensity and doubly robust
estimates, overlap diagnostics, effective sample size and clustered uncertainty.
Keep policy learning and final evaluation separate. Doubly robust evaluation
combines outcome and assignment models; it does not remove missing support or
hidden confounding. See the original
[Dudik, Langford and Li paper](https://www.microsoft.com/en-us/research/publication/doubly-robust-policy-evaluation-and-learning-2/).

The current discrete price grid is convenient for this comparison. Arbitrary
continuous prices need an explicitly justified evaluation approach; exact action
matching and discrete inverse-propensity formulas do not automatically apply.
If logs cannot support the proposed actions, report value as unidentifiable.

## 4. GSM revenue-impact experiment

Compare the frozen candidate policy against existing pricing using a randomized
design appropriate for the marketplace. A zone/time switchback is a candidate;
interference between zones and carryover determine whether it is suitable.
Block duration, washout and inference require design, not a generic A/B toggle.
See [Bojinov, Simchi-Levi and Zhao](https://arxiv.org/abs/2009.00148).

Pre-register the primary outcome, minimum worthwhile uplift, power calculation,
assignment unit, analysis period, uncertainty method and stopping rule. Use an
A/A logging and assignment check before the treatment comparison.

An economic outcome such as total GSM revenue per assigned zone/block hour
captures changes in traffic as well as conversion. Revenue per quote is also
useful, but quote traffic may itself respond to pricing; do not silently hold
that denominator fixed in a field revenue claim. Track all owned-service revenue
to capture substitution and use equal assignment exposure when comparing arms.

Report revenue uplift with its confidence interval, contribution margin and
completion, cancellation, wait, availability and customer guardrails. A business
success criterion should require the agreed worthwhile benefit and acceptable
guardrails. A positive point estimate with an interval spanning zero is
inconclusive. A losing policy is a valid benchmark outcome.

Only an executed, appropriately analyzed GSM study can support a claim about
GSM revenue impact in the population, prices and operating conditions tested.
Neither synthetic recovery nor simulated policy uplift establishes that claim.
