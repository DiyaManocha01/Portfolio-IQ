# ADR 0010: Intelligent Alerts & Notifications (Phase 27)

**Status:** Accepted
**Date:** 2026-11-11

## Context

Phase 27 asked for configurable alerts across 8 distinct signal types
(price threshold, daily % move, volume spike, RSI threshold, sentiment
change, portfolio volatility change, sector concentration change,
Portfolio Fit ranking change), each explaining its own trigger, with
excessive/duplicate notifications explicitly avoided.

## Decision

### One generic rule table, not eight

`AlertRule` has a `rule_type` enum and a small set of shared columns
(optional `stock_id`, optional `direction`, a `threshold`, and dedup
state) rather than eight near-identical tables. A dispatcher in
`app/services/alert_service.py` maps each type to an evaluator function
that calls into existing, already-tested calculation code -- nothing
here duplicates a metric another service owns:

| Rule type | Reuses |
|---|---|
| `PRICE_THRESHOLD`, `PRICE_PCT_MOVE` | `MarketDataService.get_quote` |
| `VOLUME_SPIKE`, `RSI_THRESHOLD` | `app/services/analytics.py` (`avg_volume`, `rsi`) |
| `SENTIMENT_CHANGE` | `NewsService.get_sentiment_summary` (`average_score_time_decayed`) |
| `PORTFOLIO_VOLATILITY_CHANGE`, `SECTOR_CONCENTRATION_CHANGE` | `PortfolioRiskService.compute` (`annualized_volatility`, `sector_concentration`) |
| `FIT_RANKING_CHANGE` | `PortfolioFitService.compute_fit` (`fit_score`) |

### Dedup: three different mechanisms for three different shapes of signal

A single mechanism doesn't fit all 8 types honestly:

1. **Crossing types** (`PRICE_THRESHOLD`, `RSI_THRESHOLD`): a threshold
   has a *side* (`direction`: ABOVE/BELOW). These fire only when the
   metric actually crosses from one side to the other between this
   evaluation and the last (`AlertRule.last_value`, refreshed every
   evaluation) -- never while it merely continues to sit on one side,
   which is what "avoid excessive notifications" rules out most directly
   here.
2. **Already-a-delta-today types** (`PRICE_PCT_MOVE`, `VOLUME_SPIKE`):
   the metric itself (today's % move, today's volume ratio) is already a
   point-in-time comparison, not a running state. These fire at most
   once per calendar day -- re-firing on every 30-second evaluation tick
   while a stock stays volatile for hours would be exactly the noise
   this phase was asked to avoid.
3. **"Change since last check" types** (`SENTIMENT_CHANGE`,
   `PORTFOLIO_VOLATILITY_CHANGE`, `SECTOR_CONCENTRATION_CHANGE`,
   `FIT_RANKING_CHANGE`): these rebaseline `last_value` only when they
   actually fire (not every tick), so the comparison is always "how far
   has this moved since the last alert," not "how far did it move in
   the last 30 seconds" -- the latter would make a real slow drift
   invisible if no single evaluation interval's step reaches the
   threshold.

All three mechanisms share a blanket 60-second cooldown
(`AlertRule.last_fired_at`) as a last safety net against two evaluation
paths (the background loop and a manual `POST /alerts/evaluate`)
overlapping. A rule's very first-ever evaluation only establishes a
baseline and never fires -- there is nothing to have changed or crossed
from yet, and firing immediately on rule creation would itself be a
kind of spurious notification.

### No new scheduler -- reuses Phase 24's existing background loop

This project has no background job runner (Celery/APScheduler/RQ) by
design (see the Phase 24 audit). Rather than add one for alerts,
evaluation hooks into the loop `app/main.py` already runs every 30
seconds for the real-time market-data fixture refresh -- one more
cheap, already-open DB session query per tick. This keeps the same
honest limitation already documented for that loop (alerts only
evaluate while the server process is running) rather than introducing
new infrastructure the architecture doesn't otherwise need. A manual
`POST /alerts/evaluate` endpoint exists alongside it for on-demand
checks (e.g. when a user opens the Alerts page).

### Alerts are user-scoped (unlike `/stocks/*`)

`/alerts/*` requires auth via the existing `get_current_user` dependency
-- a rule and its triggered events belong to one user, unlike the
`/stocks/*` and `/screener` endpoints (see ADR 0009), which serve
data that isn't scoped to anyone.

## Consequences

- One Alembic migration (`c50d80addfc2`): `alert_rules`, `alert_events`.
- No new dependencies.
- 17 new backend tests exercise every dedup mechanism directly (not just
  through the API), plus route-level CRUD, validation, and user
  isolation.
- **Not verified beyond this sandbox's synthetic/dev-sample data**: no
  rule has fired against a real market move, a real sentiment shift, or
  a real portfolio-composition change, since this environment has no
  live data feeding those services (see docs/limitations.md and the
  existing Phase 24/26 ADRs for why).
