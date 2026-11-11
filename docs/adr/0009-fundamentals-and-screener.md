# ADR 0009: Fundamental Analysis Data Source & Stock Screener (Phase 26)

**Status:** Accepted
**Date:** 2026-11-11

## Context

`financial_metrics` (pe_ratio, market_cap, eps, dividend_yield, book_value)
has existed since the Phase 1 baseline schema but was never populated or
served by any route -- a dormant table. Phase 26 brings it to life and
adds revenue/profit growth, ROE, ROCE, and debt-to-equity, plus a
screener that filters the stock universe by these fields and (optionally)
technical indicators.

## Decision

### Data source: extend the existing provider abstraction, don't add a new one

Rather than researching and integrating a separate fundamentals API, this
phase extends `MarketDataProvider` with `get_fundamentals()`:
`DevSampleProvider` generates deterministic synthetic values (same seeded
pattern as `get_history`); `LiveYFinanceProvider` reads yfinance's
`Ticker.info` dict, cache-first via a new JSON cache
(`app/services/market_data/cache.py`'s `read/write_fundamentals_cache`,
mirroring the OHLCV Parquet cache's shape but JSON since a fundamentals
snapshot isn't a time series).

This was the pragmatic choice over introducing a new paid/unverified
provider: yfinance is already a vetted, licensed dependency
(`docs/open-source-inventory.md`, Phase 4), already has the cache-first +
locally-run-fetch-script pattern this project uses for OHLCV
(`scripts/fetch_nifty100.py`), and the project's working rules call for
following existing architecture over introducing new infrastructure
without justification.

**Known gap, stated plainly:** yfinance's field coverage for NSE-listed
tickers is **unverified** in this sandbox (no network access to confirm
what actually comes back non-null for Indian stocks) -- this is not
assumed to be complete. `scripts/fetch_fundamentals.py` reports exactly
which fields come back null per symbol when run with real access, rather
than this project claiming a coverage level it hasn't checked.

### ROCE has no source -- stays genuinely null from live data

yfinance has no Return on Capital Employed field at all. Per the
project's rule against inventing data, `LiveYFinanceProvider.get_fundamentals()`
always returns `roce=None`; only `DevSampleProvider`'s synthetic data
populates it, clearly tagged `DEV_SAMPLE`. The frontend shows "Not
available from this data source" rather than a blank or a guess.

### debt_to_equity units are passed through as-is, not rescaled

Yahoo Finance's own convention for `debtToEquity` is reportedly a
percent-like number (e.g. 45.2), not a 0-1 ratio -- but this could not be
confirmed against a live response from this sandbox. Rather than guess a
conversion factor and silently misrepresent the number, this field is
stored and displayed exactly as the source returns it, with the
ambiguity documented (`docs/limitations.md`) instead of hidden behind an
assumed scale.

### Screener: fundamentals filter the DB directly; technical filters run on the narrowed set only

`screener_service.run_screener()` applies fundamental filters (sector,
market cap, P/E, ROE, debt/equity, dividend yield, revenue/profit growth)
as straightforward comparisons against each stock's cached
`FinancialMetric` row. Technical filters (RSI, 10-day momentum) reuse
`app/services/analytics.compute_indicators()` -- no duplicate indicator
logic -- and are computed only when a technical filter is actually
requested, and only via each stock's already-cached OHLCV history. The
screener operates on whatever's in the `stocks` table already (the
seeded demo/discover universe in this environment, same as `GET
/stocks`), not the full unverified NIFTY 100 list.

## Consequences

- One Alembic migration (`fae310e5062f`), additive, no backfill needed.
- No new dependencies -- `docs/open-source-inventory.md` unchanged.
- `app/data/seed.py` now calls `get_fundamentals()` for every seeded
  stock, so the demo DB has real (if synthetic) values to browse/screen.
- Two new routes: `GET /stocks/{symbol}/fundamentals`,
  `GET /screener`. Neither requires auth, matching `stocks.py`'s existing
  (unauthenticated) convention for non-user-scoped stock data -- noted
  here because `docs/ARCHITECTURE.md`'s route table has long claimed
  `stocks.py` requires auth, which the actual code does not enforce; a
  pre-existing discrepancy from before this phase, left as-is since
  fixing auth enforcement is outside Phase 26's scope and deserves its
  own decision.
