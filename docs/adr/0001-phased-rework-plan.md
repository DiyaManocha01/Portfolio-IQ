# ADR 0001: Adopt a Phased, Research-Grade Rework Plan

**Status:** Accepted
**Date:** 2026-10-21

## Context

The project (then "PortfolioIQ") was originally built as a time-boxed B.Tech
MVP: a working full-stack app demonstrating the Portfolio Fit Engine concept,
built in days under a hard demo deadline. It shipped with simplified,
pragmatic implementations of several subsystems:

- `portfolio/risk_service.py` — sample covariance, not shrinkage-estimated
- `portfolio/fit_service.py` — fixed-weight component sum, not z-scored
  across a candidate universe
- `ml/train.py` — chronological 70/15/15 split per stock, no embargo, no
  probability calibration
- `nlp/` — synthetic template headlines, no real ingestion or evaluation

The project has since been reframed as an "AI Portfolio Intelligence
Platform" with a 23-phase plan intended to support a research paper and an
IP/patent discussion — a materially higher bar for rigor, reproducibility,
and documented methodology than the original MVP needed.

## Decision

Adopt the 23-phase plan as the project's forward roadmap, under these
working rules (recorded in full in `CLAUDE.md`):

1. Work in checkpointed batches of two phases, stopping for review after each.
2. Every phase ends with passing tests, an Alembic migration if the schema
   changed, an updated doc/ADR, and a commit.
3. Never invent data, metrics, or results; mark anything unverified as such.
4. Earlier decisions are not silently changed — a decision that supersedes
   prior code gets its own ADR.

## Consequence for the existing simplified modules

Phases 6 (ML outlook), 8 (portfolio risk), and 10 (Portfolio Fit Engine) in
the new plan call for rebuilding the corresponding subsystems to the new
spec (purged walk-forward + embargo + calibration; Ledoit-Wolf shrinkage +
VaR/CVaR; z-scored multi-factor Fit formula with presets, respectively).

**This ADR does not supersede those modules itself.** It records the
decision to adopt the phased plan and puts the existing MVP-era
`risk_service.py`, `fit_service.py`, and `ml/` pipeline on notice: each will
be formally superseded by its own ADR (0003, 0004, 0005 — numbered when we
reach those phases) at the point its corresponding phase is implemented, not
before. Until then, they remain the live implementation backing the running
app, and nothing about their behavior changes as a result of this ADR alone.

## Alternatives considered

- **Rewrite everything now, before Phase 4/5.** Rejected: the new plan
  explicitly phases this work (Phases 6, 8, 10), and jumping ahead would
  violate the checkpoint rule and risk large, unreviewed changes in one batch.
- **Keep both old and new implementations side by side indefinitely.**
  Deferred, not rejected — worth reconsidering per-phase (e.g. keeping the
  simple Fit formula as a documented baseline for the Phase 13 ablation
  study is plausible), but each case gets its own ADR when we get there.
