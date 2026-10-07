# Executed validation

## Weekly reports

PoC reports and short progress updates are saved in
`docs/submission/days/YYYYMMDD/`, using the report cutoff date. The latest report is
[Week 2 — 2026-10-07](submission/days/20261007/weekly_report.md): Swissmetro and the
independent development policy-value benchmark completed;
full repeated-seed coverage is running and statistical acceptance remains pending.
See the [short progress update](submission/days/20261007/progress_update.md).
See the [weekly report index](submission/README.md).

The October 7 final policy implementation passed **131 tests in 40.95 seconds**,
Ruff lint/format checks (36 files including scripts), and ty 0.0.82 on all
`src/gsm_poc` with `--error-on-warning`. The policy run has 40 synthetic seed jobs,
240 valid policy values and seven recorded simple-rule fallbacks. Final manifests
and reuse were verified; rerunning Swissmetro produced unchanged metrics and
predictions. See the [acceptance review](submission/days/20261007/acceptance_review.md)
for exact run IDs, hashes, cutoff and open gates. These checks do not rerun the
historical TLC/browser measurements below. Remote CI remains unverified.

## Historical validation — 2026-10-03

The results below retain the October 3 snapshot. Statements about pending work
refer to that date; later progress is recorded in the weekly reports above.

Verified locally on 2026-10-03, using Windows, Python 3.11.9, uv 0.10.12,
and the checked-in `uv.lock`. Run manifests record package versions, source code
hash, lock hash, effective configuration, data hashes, timings and failures.
Generated data and run artifacts are excluded from Git.

## Automated checks

| Command | Executed result |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q` | 42 passed in 14.03 seconds |
| `.venv/Scripts/python.exe -m ruff check src tests scripts` | Passed |
| `.venv/Scripts/python.exe -m ruff format --check src tests scripts` | 26 files already formatted |
| `git diff --check` | Passed |

Coverage includes source/schema checks, independent quality flags, exact count
reconciliation, preserved duplicate rows, training-only context fitting,
session conservation, all five DGPs, RNG reproducibility, grouped day folds,
oracle rejection, matrix orientation, analytic OLS recovery, holdout isolation,
collinear and constant-price identification, bootstrap failure denominators,
support rejection, invalid probabilities, stage reuse, corrupt artifacts,
CLI execution and Streamlit widget behavior.

A real TLC context run exposed pandas promoting boolean/integer join keys to
object arrays. The regression reproduced the multinomial sampling failure
before the fix. Join keys now share an integer representation and numeric
calculations use explicit floating-point arrays. All five DGPs pass the
regression using context Parquet produced by the TLC build pipeline.

The GitHub Actions workflow contains the same checks. It has not been executed
on a remote runner in this session.

## Public TLC data

Source manifest: `data/bronze/source_manifest.json`.

- January 2024 HVFHV source: 472,757,547 bytes, 19,663,930 rows, 24 columns,
  19 Parquet row groups.
- Trip SHA-256: `9897de352aa52cea36b70348cc6721b8d4494327ce39c85f0dba83d86ecaa098`.
- Zone lookup: 265 rows; SHA-256
  `1a99e105092230f8620f301edcca7f80d3080642ff404d28ed957d3fa222c8ed`.
- Five pickup zones: 161, 162, 163, 164, 170; platforms HV0003/HV0005.
  Dropoffs outside the selected cluster are retained.
- Scoped monthly silver: 970,940 core-valid trips. No source rows have missing
  core keys and no exact duplicate attribute groups were found in this scope.
  No deduplication is applied.
- Positive-price metric: 970,675 valid rows; request-to-pickup metric: 960,950
  valid rows. These flags do not remove completed-trip counts.
- Context: 240 zone/hour/weekend templates, fitted only on January 1–20.
  All templates meet the minimum count without fallback in this source.

| Executed build | Mart cells | Reconciled completed trips | Build time |
|---|---:|---:|---:|
| Seven-day demo, `20261003T130951-df24a7e4` | 3,360 | 175,861 | 7.40 s |
| Full January, `20261003T131251-0b5e2209` | 14,880 | 970,940 | 7.33 s |

The full-month build used `configs/default.toml`. That run executes ingestion
and data construction only; its configured 100-seed evaluation was not run.
Times exclude the first source download and use the verified local source cache.

## Development method evaluation

Run `20261003T130312-737e3a7c` executed:

```powershell
.venv/Scripts/python.exe -m gsm_poc evaluate --config configs/demo.toml --dgps RCT_SYN OBSERVED_CONFOUNDING HIDDEN_CONFOUNDING NULL_EFFECT COLLINEAR_PRICE
```

This is an offline synthetic evaluation: seeds 42–44 for each of five DGPs,
three estimators, 10 day-bootstrap draws per identified estimator. All 15 seed
jobs completed; no seed jobs failed. Evaluation time was 82.12 seconds.

The table reports the **largest per-cell theta RMSE** within each 2×2 matrix.
Scenario RMSE is for X/Y probabilities on frozen test contexts under the configured
scenario (default +10% X price change). If the scenario changes an unidentified price
(such as when only price Y varies), the scenario cannot be forecast and scenario RMSE
is unavailable (None). Units are probability/log-price and probability, respectively.

| DGP | Naive OLS max RMSE | Adjusted OLS max RMSE | DML max RMSE | DML scenario RMSE |
|---|---:|---:|---:|---:|
| RCT_SYN | 0.031174 | 0.036712 | 0.035866 | 0.007710 |
| OBSERVED_CONFOUNDING | 0.102391 | 0.038933 | 0.045676 | 0.007716 |
| HIDDEN_CONFOUNDING | 0.122228 | 0.059755 | 0.055216 | 0.015745 |
| NULL_EFFECT | 0.034957 | 0.034933 | 0.033718 | 0.007747 |
| COLLINEAR_PRICE | Unidentified | Unidentified | Unidentified | Unavailable |

The RCT development errors are below the preconfigured technical targets;
three seeds do not establish reporting performance. Hidden confounding remains
unadjusted and biased. Collinear runs retain all attempted cells in their
denominators and return `not_identified` rather than separate price effects.

Full per-cell bias, RMSE, coverage, false positives, exact binomial intervals,
valid denominators and bootstrap counts are in
`runs/20261003T130312-737e3a7c/evaluation/evaluation_metrics.csv`.
The development intervals are explicitly labeled `development_or_unstable`.
The evaluation with 100 seeds per DGP has not been executed; stable coverage and false-positive
performance are not established.

## Fresh-seed point-accuracy benchmark

Run `20261003T135730-1ae94396` executed the unchanged methods on 20 fresh seeds
per DGP, seeds 10001–10020, across all five cases:

```powershell
.venv/Scripts/python.exe -m gsm_poc evaluate --config configs/demo.toml --seed 10001 --seeds 20 --bootstrap-draws 0 --dgps RCT_SYN OBSERVED_CONFOUNDING HIDDEN_CONFOUNDING NULL_EFFECT COLLINEAR_PRICE
```

All 100 seed jobs completed in 66.59 seconds, with zero failed seed jobs.
The three methods used the same generated data and date splits. This offline
synthetic development profile has 1,860 blocks, 93,000 sessions and 20 trees
per nuisance forest. The seed list and existing technical targets were fixed
before the run; no estimator parameters were changed.

Each coefficient RMSE is computed over the 20 seeds. The table then takes the
largest of the four coefficient RMSEs for each method. Scenario RMSE uses the
same frozen test dates and +10% X / unchanged Y scenario as the earlier study.

| DGP | Naive OLS max RMSE | Adjusted OLS max RMSE | DML max RMSE | DML scenario RMSE |
|---|---:|---:|---:|---:|
| RCT_SYN | 0.028020 | 0.025927 | 0.025527 | 0.007564 |
| OBSERVED_CONFOUNDING | 0.101744 | 0.030885 | 0.032944 | 0.008325 |
| HIDDEN_CONFOUNDING | 0.108117 | 0.036286 | 0.040800 | 0.015712 |
| NULL_EFFECT | 0.027939 | 0.025774 | 0.025640 | 0.007600 |
| COLLINEAR_PRICE | Unidentified | Unidentified | Unidentified | Unavailable |

The RCT point-accuracy targets are met in this development run. Adjustment
reduces error against naive OLS under observed confounding; adjusted OLS has
slightly lower error than DML there. Hidden-confounder results continue to be
stress-test evidence, without an identification guarantee. All 60 collinear
method fits return `not_identified`, preserving 240 attempted coefficient rows.

**No bootstrap draws were requested.** Coverage and false-positive denominators
are zero, with those estimates unavailable. This run does not validate interval
calibration or revenue uplift. There are 20 seeds per case, not 100 per case.
The earlier 199-draw TLC-context run and this fresh-seed point benchmark answer
different questions; their results must not be combined into a coverage claim.

Completed-manifest artifact checksums were verified. Machine-readable results
are in `runs/20261003T135730-1ae94396/evaluation/evaluation_metrics.csv`, with all
1,200 coefficient rows in `seed_metrics.parquet`. The planned independent policy
value and GSM revenue studies are described in [BENCHMARK.md](BENCHMARK.md).

## TLC-context bootstrap and scenario

Completed run: `20261003T130951-df24a7e4`.

```powershell
.venv/Scripts/python.exe -m gsm_poc run-all --config configs/tlc_quick.toml --bootstrap-draws 199 --skip-monte-carlo
```

This uses **real completed-trip contexts and simulated choices**, RCT_SYN seed
42, 7,440 blocks and 372,000 sessions. Training contains 4,800 blocks across
20 original days; the test context is frozen at 1,440 blocks. All three
estimators completed 199/199 day-bootstrap refits without fit failures.
The sensitivity check accepted all three sets of coefficient intervals.

Fit/uncertainty time was 516.21 seconds, method evaluation 6.76 seconds and the
saved example scenario 1.04 seconds. These timings are from this machine and
configuration, not a service latency guarantee.

DML's fitted matrix, with outcome rows and price columns:

| Outcome | Price X | Price Y |
|---|---:|---:|
| X | -0.590036 | 0.169760 |
| Y | 0.101347 | -0.498596 |

The known DGP matrix is `[[-0.60, 0.15], [0.12, -0.50]]`. DML scenario probability
RMSE against that oracle is 0.003678 on the frozen test context. Three of the
four individual DML coefficient intervals contain truth in this one run.
A single run does not establish empirical coverage.

The saved +10% X / unchanged Y scenario has support status `ok`, interval status
`ok`, 199 valid probability draws and zero invalid probability draws. It exports
probability, net-change, coefficient and elasticity percentile intervals.
For 10,000 assumed quote sessions:

| Choice | Before probability (%) | After probability (%) | Change (pp) |
|---|---:|---:|---:|
| X | 31.2280 | 25.6044 | -5.6236 |
| Y | 25.9856 | 26.9516 | 0.9659 |
| NONE | 42.7864 | 47.4441 | 4.6577 |

Expected booking choices change by -465.77, with an individual 95% bootstrap
interval of [-488.62, -439.38]. This is a controlled model output, not observed
GSM impact. All model/scenario artifacts passed completed-manifest checksum
verification.

## Browser verification

The final TLC-context model was checked through installed headless Edge:

```powershell
.venv/Scripts/python.exe scripts/check_dashboard.py --url http://127.0.0.1:8501 --browser "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --run-id 20261003T130951-df24a7e4 --output .cache/dashboard-qa-final
```

All eight checks passed with no browser page errors: the three tabs rendered;
unsupported prices withheld the forecast and recovered when restored; and
320/375/414/768 px layouts had no page overflow. Desktop and narrow-screen
screenshots were inspected. Tables use their own horizontal scroll on small
screens. The QA report and images are ignored intermediates.

## Interpretation and delivery scope

All modeled behavior is synthetic or semi-synthetic, evidence level C.
Operational TLC counts describe completed NYC trips. The implementation has
no GSM quote-session data, cannot establish GSM conversion or elasticity, and
does not infer supply response, charging, matching or ROI. Those proposal
components remain the next phase, with contracts in `GSM_DATA_CONTRACT.md`.

Gemini MCP was unavailable in the active tool catalog. The code was implemented
and verified using the local workspace tools. No commit, push, deployment or
external pricing change was made. The user's existing AGENTS.md edit was retained.
