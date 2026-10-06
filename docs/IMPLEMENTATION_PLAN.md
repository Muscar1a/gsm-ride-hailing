# Implementation plan

## Source and scope

Source documents:

- `GSM_Causal_Marketplace_Proposal.docx`, supplied in the user's Downloads directory; SHA-256 `f4ac5a707aa491599dcbee3bca1a61ef4f672df57e9bbd00d2ee82ddd15ae8db`.
- `docs/task/GSM_POC_WEEKS_1_2_DESIGN.md`, the first-two-week specification, stored locally with task plans.

Shared source requirements, formats, units and stage inputs/outputs are defined
in [GSM_DATA_CONTRACT.md](GSM_DATA_CONTRACT.md). The general proposal and core
design follow that contract; local task documents define weekly acceptance.

This delivery implements the first two weeks of the proposal. It estimates a common
2×2 matrix of choice probability responses under controlled data generating
mechanisms. Results have evidence level C. TLC records describe completed trips;
they do not identify GSM conversion, unserved demand, supply response, or ROI.

## Build order

1. **Foundation:** Python 3.11, uv environment and lockfile, validated TOML
   configuration, atomic artifact writes, source and run manifests, CLI.
2. **Observed data:** bounded downloads, 24-column schema check, immutable bronze,
   stable physical-row IDs, independent quality flags, complete 30-minute grid,
   count reconciliation, train-only context templates and fallback provenance.
3. **Controlled data:** five DGPs, separate RNG streams, price assignment audit,
   one choice per session, conservation checks, isolated oracle, day splits.
4. **Estimation:** naive and adjusted OLS, multi-output EconML LinearDML,
   GroupKFold by original day, feature allowlist, residual rank and support
   diagnostics, fitted probability baseline.
5. **Inference and evaluation:** day bootstrap with complete refits, explicit
   failures, fixed evaluation contexts, checkpointed Monte Carlo, per-cell
   bias/RMSE/coverage and binomial intervals.
6. **Scenarios:** log price ratios, joint support, learned baseline, probability
   checks on every context and bootstrap draw, X/Y/NONE and expected bookings,
   CSV/JSON exports with units and provenance.
7. **Demo and handoff:** artifact-only Streamlit dashboard, observed / method /
   scenario tabs, identification and GSM data contract documentation, regression
   tests, offline end-to-end run, bounded TLC run when network access permits.

## Verification gates

- No source rows are silently deduplicated or overwritten.
- Mart counts exactly reconcile with core-valid silver rows in the same scope;
  empty counts become zero only for a complete source.
- Session one-hot labels and block totals conserve the session count.
- Train, validation, and test dates are disjoint; bootstrap duplicates of one
  original day stay in one cross-fitting fold.
- Estimation and scenarios have no oracle dependency. Forbidden fields never
  enter the estimator feature matrix.
- Independent prices recover the analytic matrix in deterministic regression
  fixtures; collinear prices return `not_identified`.
- +10% uses `log(1.1)` and the documented matrix orientation.
- Invalid probabilities and out-of-support prices return explicit statuses.
- Failed bootstrap draws and seed runs remain in the output denominators.
- CLI stages and the Streamlit application run using the locked environment.

## Compute profiles

`demo.toml` is a bounded, offline synthetic development run. Small bootstrap and
Monte Carlo counts are labeled as development results. `tlc_quick.toml` uses a
seven-day observed dashboard and train-only context from the month. `default.toml`
uses the full prescribed scope and reporting targets (100 seeds, 199 bootstrap
draws). Reporting targets are configuration, not claims of completed evaluation.

Gemini MCP was not available in the active tool catalog; implementation uses the
local workspace tooling. No production systems or pricing policies are changed.

## Completion record

Actual checks, runtime, completed seed/draw counts, and limitations are recorded
in `docs/VALIDATION.md` after verification. Numerical outputs live in ignored
`data/` and `runs/` directories with manifests.
