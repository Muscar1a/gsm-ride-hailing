# Weeks 4–5: controlled policy decisions and experiment handoff

This increment retains Bun's accepted fixed-online Week-3 scope. It adds finite
price comparisons, propagation of fitted-model uncertainty, declared operational
sensitivity and guardrails, a conditional cost bridge, independent controlled
evaluation, prospective experiments and a verified delivery archive. All behavior
remains synthetic evidence C, `not_calibrated`. Implementation is not reviewer
acceptance or completion of the original GSM research objective.

## Business rules

- One frozen quote population, two hypothetical services and one shared online
  roster. A policy changes X/Y prices once through the existing choice model.
  Offers, refusal, timeout and 100%-fare completed-trip settlement retain V3 rules.
- Declare 2–12 unique finite policies, beginning with unchanged baseline. Support
  and probability gates run for every policy. Out-of-support policies retain
  diagnostics and fail the comparison; no price extrapolation or clipping occurs.
- The frozen criterion declares metric, direction and minimum worthwhile gain.
  The supplied completed-trip objective and wait/income limits are development
  assumptions, not GSM confirmations. A candidate needs a complete stable model
  interval establishing that gain, and must retain its gain under every declared
  rule sensitivity. All declared guardrails must pass for each rule alternative.
- Guardrails currently compare target point means across operational trajectories.
  They do not certify tail safety or simultaneous statistical guarantees.
- Missing costs remain missing. With all three declared cost components present,
  `conditional_surplus = completed fare receipts - driver pay - trip costs -
  online-hour costs - horizon costs`. No additional commission is inferred. Under
  the accepted 100% pay rule, fare receipts and driver pay cancel. The accounting
  scope is the entire shared X/Y roster and horizon, counted once. This is not
  GSM-recognized revenue, profit, driver net income or ROI; those remain unevaluated.

## Uncertainty and independent evaluation

Point-fit comparisons use common operational seeds and Student-t intervals for
paired Monte Carlo mean differences. Each original-day bootstrap model refits
all learned components in the existing fitting stage. Its predictions pass through
the demand bridge and paired operations; per-model replicate mean contrasts feed
percentile intervals. Original-training support determines identification, rather
than repeated/missing bootstrap-day multiplicities.

At least 20 complete model draws are required for a model interval. Every requested
draw and replicate must succeed for that metric; failures and undefined wait or
income denominators cannot improve the available fraction. Half/all-draw width
sensitivity is retained, and unstable intervals cannot qualify a candidate. The
39-draw development profile is a bounded sensitivity exercise, not calibrated 95%
coverage. Finite inner replicates leave Monte Carlo error in these intervals.
Selection uncertainty, changes to quote exposure, model misspecification and unknown
operational rules remain outside the interval. These are individual fixed-candidate
contrasts, not simultaneous intervals or proof that the selected winner is best.

The independent evaluator opens registered oracle data only after the comparison
and its selection are frozen. It verifies matching held-out dataset/block keys,
uses the generator's known conditional response rather than fitted predictions,
and runs every prespecified action with disjoint operational seeds. It exports
forecast error, paired contrasts and evaluator-only finite-reference regret without
reselecting a policy. Infeasible or unselected policies have unavailable regret;
the reference uses Monte Carlo point means, without a certified regret interval.
This establishes
controlled forecast behavior only; operational rules still come from the fixture.

## Run the complete controlled workflow

Use new IDs after code or environment changes. The following commands create a
new reproducible source; they do not reconstruct the six missing files of the
historical Week-3 training run. No external downloads are required.

```powershell
uv run gsm-poc run-all --config configs/week4.toml --skip-monte-carlo --run-id week45-choice-v1
uv run gsm-poc prepare-demand --config configs/week4.toml --model-run-id week45-choice-v1 --snapshot configs/week3_snapshot.json --delta-x 0 --delta-y 0 --run-id week45-demand-v1
uv run gsm-poc compare-policies --config configs/week4.toml --demand-run-id week45-demand-v1 --rules configs/week3_poc.json --compensation configs/week3_compensation.json --spec configs/week4_policies.json --run-id week45-policies-v1
uv run gsm-poc evaluate-policies --config configs/week4.toml --comparison-run-id week45-policies-v1 --truth-run-id week45-choice-v1 --spec configs/week4_assessment.json --run-id week45-assessment-v1
uv run gsm-poc plan-experiment --config configs/week4.toml --comparison-run-id week45-policies-v1 --spec configs/week5_experiment.json --run-id week45-experiment-v1
uv run gsm-poc export-handoff --config configs/week4.toml --source-run-ids week45-assessment-v1 week45-experiment-v1 --run-id week45-handoff-v1
```

`week4_assessment.json` freezes the same actions, criterion, costs and guardrails,
uses new seeds and has no fitted-model draws or sensitivity changes. All protocols
must be frozen before their evaluation; reused assessment seeds are not new evidence.
Policy work is bounded by 10,000 trajectories and a maximum one-hour wall budget;
supplied development/assessment specs use ten minutes. Every failed trajectory is
retained, and an incomplete evaluation cannot produce a completed source run.

Artifacts include policy plans, raw trajectory counts, paired summaries, decisions,
frozen rules/costs, copied source artifacts and manifests. Source runs are unchanged.
Same-run reuse verifies checksums; modified source inputs invalidate reuse.

Open completed outputs in the browser dashboard:

```powershell
uv run gsm-web --workspace . --run-id week45-policies-v1
```

The **Policies and experiments** view also selects independent evaluations,
experiment plans, reconciliation and delivery packages. Tables and downloads read
the same registered artifacts. Browsing starts no fit or simulation; the separate Run & data view explicitly starts bounded Python jobs.

## Experiment plan and reconciliation

The supplied experiment is an illustrative A/A calendar, with a synthetic future
date, one cluster, two-hour blocks and a declared 30-minute washout. Both arms apply
baseline; randomized order is balanced within each pair. A/B mode applies the frozen
candidate in the treatment arm. Changing mode, timing or assumptions requires a new
plan/run. Planning does not authorize any real deployment.

Power uses a two-sided normal approximation for the mean of independent paired
block differences: `ceil(((z(1-alpha/2)+z(power))*paired_sd/minimum_effect)^2)`, with
at least two independent pairs. Missing variance yields unavailable sample size,
not a fabricated result. The variance, effect size, independence, block horizon,
interference and washout need local validation before GSM use. Session counts are
not independent assignment units. Future-block forecasts additionally require the
declared transport assumption; horizon/cluster mismatch leaves A/B reconciliation
unavailable instead of rescaling two-hour totals.

Record one row per scheduled block in UTF-8 CSV, with exactly:

| Column | Contract |
|---|---|
| `block_id` | Unique ID from the frozen calendar |
| `applied_policy_id` | Exactly the policy assigned to that block |
| `metric` | Frozen primary metric |
| `unit` | Exact unit in the frozen prediction |
| `value` | Finite numeric block outcome |
| `source_kind` | `synthetic` for this validated reconciliation path |

```powershell
uv run gsm-poc reconcile-experiment --config configs/week4.toml --experiment-run-id week45-experiment-v1 --observations path/to/synthetic_outcomes.csv --run-id week45-reconciliation-v1
```

Duplicate/unknown blocks, incorrect exposure, mixed units or invalid outcomes fail
validation. Missing blocks remain counted; incomplete pairs prevent final effect
intervals. Complete pairs produce a mean treatment-minus-control contrast and
Student-t interval under the declared independence assumption, a sample-ratio
diagnostic and A/A zero-effect check. The frozen prediction is copied unchanged;
matching-scope forecast error is recorded without retroactively refitting it.
Real GSM experiment ingestion and causal acceptance require a separate validated
data/assignment contract; this synthetic path explicitly rejects real-data labels.

## Week-5 handoff and remaining external gates

`export-handoff` validates checksums, follows source-run dependencies, and includes
registered source data, model/run artifacts, code, tests, configuration, documentation
and `uv.lock`. The archive contains an inventory of SHA256 checksums and rerun
instructions. Unsafe paths, symlinks, missing sources and byte/file budgets stop
export. Default uncompressed limit is 256 MiB; no valuable source data is changed.
The archive is local and ignored by Git. Copy it to a clean directory, verify the
inventory, run `uv sync --locked`, then rerun with fresh run IDs under that environment.

The broader research target still requires received/validated GSM sources and
mappings, approved decision/accounting/guardrail definitions, causal identification
review, calibrated uncertainty, experiment authorization and real execution. Driver
participation, endogenous online supply, incentive equilibrium, charging and 10,000-
request capacity certification remain outside this accepted fixed-online increment.
No reviewer acceptance or GSM impact is inferred from technical completion.
