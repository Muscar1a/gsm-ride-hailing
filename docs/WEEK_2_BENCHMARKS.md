# Week 2 benchmark execution

The Swissmetro benchmark and repeated-seed method evaluation are independent.
Both retain evidence C for this PoC. Neither estimates GSM elasticity, revenue,
or ROI. The independent pricing-policy benchmark uses a separate development
protocol described in [BENCHMARK.md](BENCHMARK.md#2-controlled-pricing-policy-benchmark).

Executed results and acceptance status are in the
[Week 2 report](submission/days/20261007/weekly_report.md).

## Swissmetro

Download the public source without modifying it:

```powershell
New-Item -ItemType Directory -Force data/raw/swissmetro
Invoke-WebRequest -Uri https://transp-or.epfl.ch/data/swissmetro.dat -OutFile data/raw/swissmetro/swissmetro.dat -TimeoutSec 60
.venv/Scripts/python.exe -m gsm_poc.swissmetro --seed 31001
```

The module uses existing NumPy/SciPy dependencies; Biogeme is not required.
The fixed specification is two alternative-specific constants (Swissmetro
reference) and generic time/cost coefficients. The comparator fits only the
two constants. Both normalize over available alternatives.

All SP trip purposes are retained; unknown `CHOICE=0` and non-SP rows are
excluded with counts. Exact duplicate attributes are retained as separate
survey tasks. Time and cost are minutes and CHF, scaled by 100 for fitting.
The EPFL preparation convention sets incremental Train/Swissmetro cost to
zero for annual GA pass holders. No headway is interpreted as pickup ETA.

Seed 31001 permutes sorted person IDs into 70%/15%/15% train/validation/test
groups. Repeated responses stay together. Both models are specified before
evaluation, fit on train only, and reported on every split. There is no tuning
or selection on final test. `source_row` identifies a preserved source task;
`person_id` identifies the repeated respondent.

Outputs under `runs/<run_id>/swissmetro/`:

- `source_manifest.json`: source/dictionary/preparation URLs, SHA-256, byte
  count, verification time, and license limitation.
- `splits.json`: person membership and row counts.
- `report.json`: quality/exclusion counts, coefficients, optimizer/rank
  diagnostics, test log-loss difference, units and limitations.
- `metrics.csv` and `predictions.parquet`: row/person mean log loss, accuracy,
  probabilities and availability checks.

Use the printed run ID with `--run-id` to verify/reuse unchanged outputs.
Changed source bytes, code, environment or configuration invalidate reuse.
Raw data and run artifacts are ignored. The
[EPFL/Biogeme Data section](https://biogeme.epfl.ch/) explicitly lists these
datasets for research and education (reviewed 2026-10-07). This supplies use
evidence for the academic PoC. A dataset-specific license and redistribution
or commercial permission remain unconfirmed; do not infer them from the
software license. This supplementary review does not rewrite the sealed run's
source manifest or outputs.

References: [EPFL dictionary](https://transp-or.epfl.ch/biogeme-2.5/swissmetro.pdf),
[EPFL preparation](https://biogeme.epfl.ch/sphinx/_modules/biogeme/data/swissmetro.html),
[MNL specification](https://biogeme.epfl.ch/sphinx/auto_examples/swissmetro/plot_b01a_logit.html).

## Frozen coverage protocol

The runner targets 100 seeds per DGP across all five DGPs, with 199 original-day
bootstrap refits per identified estimator. Reporting seeds are 20001–20100.
Probe seed 19001 is excluded from final reporting. Order is randomized,
observed-confounding, null, hidden-confounding and collinear cases. Model/data
parameters remain those in `configs/default.toml`.

The current snapshot is `.cache/week2-evaluation-574cf501-20261007`, with
train-fitted TLC context build `214dd5a1184bd3705e66`. It preserves source,
effective config, lock and context bytes from revision
`574cf501304a777827c2e04704d96a1ab563e1b2`. An existing snapshot is never
overwritten. Changing the Git revision, environment or snapshot bytes will
refuse resume; ongoing development belongs outside this snapshot.

Run or resume the complete protocol:

```powershell
.venv/Scripts/python.exe scripts/run_week2_coverage.py --snapshot .cache/week2-evaluation-574cf501-20261007 --build-id 214dd5a1184bd3705e66
```

Do not start another runner while one is active: an OS lock rejects it.
The launched background process runs sequentially, at most five seeds per
batch, with native numerical libraries limited to one thread and a three-hour
timeout per batch. Keep the computer awake. Closing Codex does not serve as
a checkpoint or guarantee that a Windows process survives sleep/restart.

Progress and outputs are under `<snapshot>/week2_reporting/`:

- `frozen_spec.json`: reporting seed/action-free method protocol, code/lock/
  context hashes, environment, runner hash, batch size and technical targets.
- `status.json`: active batch, process ID, completed counts by DGP, process
  status and artifact hashes. Counts advance after a completed batch.
- `logs/`: each child batch's log; background stdout/stderr logs are beside it.
- `seed_metrics.parquet` and `evaluation_metrics.csv`: pooled completed
  batches, including failed/unidentified estimator cells and exact binomial
  intervals for coverage/null false positives. Summaries retain the expected
  denominator of 100 seeds/DGP even while partial.

Per-seed checkpoints remain in `<snapshot>/runs/<batch_id>/evaluation/`.
An interrupted seed is recomputed; successful seed checkpoints are verified
and reused with identical config/code/environment. A failed batch stops the
runner and records the error rather than retrying forever. To resume, first
confirm the recorded runner process has exited, resolve the external failure,
then issue the same command. Changes to the runner require a new frozen spec;
do not rewrite an active spec or weaken the reporting profile.

The first background start failed because a result folder named `coverage`
shadowed Numba's optional module. Its spec and log are retained under
`<snapshot>/failed-coverage-start/`. The corrected output directory is
`week2_reporting`; no completed reporting seeds were discarded.

`complete` means all planned seeds have metric rows; it does not automatically
mean the statistical gate passed. Review coverage, null false positives,
failure/interval quality, RCT theta RMSE <= 0.10 and scenario probability
RMSE <= 0.02. Hidden confounding is a stress case and collinear effects must
remain unidentified. Do not average batch coverage/RMSE summaries: pool the
per-seed rows, checking duplicate cells and code/config compatibility.
