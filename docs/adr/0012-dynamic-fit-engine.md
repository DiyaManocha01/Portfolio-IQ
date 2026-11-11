# ADR 0012: Dynamic Portfolio Fit Engine (Phase 29)

**Status:** Accepted
**Date:** 2026-11-11

## Context

Phase 29 asked for the Fit Engine to recalculate rankings as inputs
change, explain *why* a ranking moved, and cache results to avoid
pointless recompute. `PortfolioFitService.compute_fit` (Phase 10) is
expensive: it runs the ML prediction pipeline, the sentiment summary,
and a hypothetical-addition portfolio simulation (Ledoit-Wolf
covariance) every single call. It was already being called unconditionally
on every page load of `/portfolio-fit/{symbol}` AND, more importantly,
on every ~30-second background evaluation tick for every enabled
`FIT_RANKING_CHANGE` alert rule (Phase 27) -- the exact "pointless
recompute" this phase names.

## Decision

### Cache keyed by an input fingerprint, not a time-to-live

A naive TTL cache ("good for 60 seconds") would serve a stale score
after a real change (new price, retrained model, portfolio edited) and
recompute a fresh score when genuinely nothing changed. Instead,
`fit_snapshot_service.compute_input_fingerprint` hashes exactly what
`compute_fit`'s result depends on:

- the stock's latest price **date** (not `close` -- a new trading day's
  bar landing is the signal, not a specific price's bits)
- the trained model's `model_version` (a retrain invalidates every cached
  score)
- the stock's time-decayed sentiment score, rounded to 2 decimals (so a
  sub-cent-equivalent rounding difference can't force a spurious miss)
- the portfolio's full holdings composition (symbol:quantity:avg_price
  for every holding) -- the risk/diversification/concentration delta
  terms depend on the WHOLE portfolio, not just the stock being scored

A cache hit (fingerprint unchanged since the last snapshot) returns the
stored result with no recompute at all. A miss recomputes exactly once
via the existing `PortfolioFitService.compute_fit` -- nothing about the
Phase 10 formula changes.

### Append-only snapshot history, not a single "latest row" per stock

`FitScoreSnapshot` (`fit_score_snapshots` table) is written once per
recompute and never updated, keyed by `(portfolio_id, stock_id, preset)`
with `computed_at` for ordering. This is what makes "explain why it
moved" possible at all: a change explanation is always a diff between
the new result and the row most recently superseded. A single
UPSERT-style "latest score" column would have the caching benefit but
lose this comparison the moment it overwrote the previous value.

### One-factor change explanation, not a full diff

`_explain_change` reports the overall point delta plus the single factor
whose contribution shifted the most ("...mainly because ML Outlook
became more favorable"), not all five factors' deltas. Explaining a
move with five simultaneous micro-changes reads as noise; the factor
that moved the most is, by construction of the additive logit, also the
factor that explains the most of the move. The full per-factor
breakdown is still available in the ordinary `factors` list for anyone
who wants it.

### Wired into the one place that actually mattered: alerts

`GET /portfolio-fit/{symbol}` gets the caching and the `change` field
as an additive, backward-compatible response field. But the real
target was `app/services/alert_service.py`'s `FIT_RANKING_CHANGE`
evaluator, which runs on every background tick for every enabled rule
-- that evaluator now calls `fit_snapshot_service.get_fit_with_change`
instead of `PortfolioFitService.compute_fit` directly, so a portfolio
with no real change since the last tick costs one cheap fingerprint
computation instead of a full ML + sentiment + covariance recompute.

### `/discover`'s batch ranking is deliberately left uncached

`PortfolioFitService.compute_fit_batch` z-scores every candidate against
the full stock universe in one pass -- caching it per-stock would mean
recomputing the batch's mean/std from a mix of cached and fresh raw
values, which either silently breaks the z-score's statistical meaning
or requires caching raw terms separately from the final score (a
genuinely different, more complex design). That is out of scope for
this phase; `/discover` continues to recompute on every call, as it did
before Phase 29.

## Consequences

- One Alembic migration (`87834f83a4e5`): `fit_score_snapshots`.
- No new dependencies.
- 8 new backend tests, plus 2 new frontend tests for the `change`
  banner. `fit_score_snapshots` grows unboundedly over time (one row per
  recompute, never pruned) -- acceptable for this project's scope, not
  something a production deployment would leave unaddressed indefinitely.
- **Not verified beyond this sandbox's synthetic/dev-sample data**: no
  cache hit/miss has ever been driven by a real market-data change or a
  real model retrain in production, since this environment has no live
  feed and the demo model is trained once at seed time (see
  docs/limitations.md and the existing Phase 10/24/27 ADRs for why).
