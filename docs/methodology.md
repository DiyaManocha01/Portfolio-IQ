# Methodology

Started in Phase 4, extended every batch. This is the document a research
paper or IP filing would cite for "how was this computed" — every formula
implemented in the codebase should have a corresponding entry here, with a
pointer to the exact function that implements it. If a number in the app or
a paper draft can't be traced to an entry here and a script in the repo,
treat that number as unverified (see `docs/limitations.md`).

## 1. Data (Phase 4)

### 1.1 Universe

`backend/app/services/market_data/nifty100.py` defines `SYMBOLS`: an
approximate, **unverified-against-a-live-source** list of ~100 large NSE
equities, standing in for the NIFTY 100 index until it's checked against an
official NSE Indices snapshot (see `docs/limitations.md`). The benchmark
for beta calculations (Phase 5) is the NIFTY 50 index, `^NSEI`.

### 1.2 Source and adjustment

Real price history comes from Yahoo Finance via `yfinance`
(`LiveYFinanceProvider`), requested with `auto_adjust=True` — i.e. OHLC
values are adjusted for splits and dividends by the data provider before
this project ever sees them. This project does not perform its own
corporate-action adjustment; it relies on yfinance's.

### 1.3 Caching

`backend/app/services/market_data/cache.py`: one Parquet file per symbol
under `app/data/cache/`, written by `scripts/fetch_nifty100.py` (run
locally — see ADR 0002 for why). `LiveYFinanceProvider` reads this cache
before ever calling the network.

### 1.4 Validation (`cache.validate_ohlcv`)

Given a raw OHLCV DataFrame for a symbol, checks (and returns
human-readable warnings for, rather than silently discarding):

| Check | Rule |
|---|---|
| Required columns present | `date, open, high, low, close, volume` |
| Non-empty | at least one row |
| Positive prices | `open, high, low, close > 0` for every row |
| Non-negative volume | `volume >= 0` for every row |
| High/low consistency | `high >= low` for every row |
| Trading gaps | flags any gap between consecutive trading dates longer than `max_gap_days` (default 10 calendar days) — a possible halt, delisting, or provider outage, not assumed to be a holiday |
| Likely-unadjusted split | flags any single-day `abs(pct_change(close)) > 0.40` — real large-cap single-day moves of that size are rare; this usually means a split/bonus wasn't reflected in the adjusted series |

### 1.5 Known data-quality limitations

See `docs/limitations.md` — survivorship bias in the symbol universe,
no official re-verification of the NIFTY 100 list, no real fixture
committed yet.

## 2. Stock Analysis (Phase 5)

Implemented in `backend/app/services/analytics.py`, served via
`GET /stocks/{symbol}/analysis` (`backend/app/api/routes/stocks.py`).

### 2.1 Returns, volatility, drawdown, moving averages, RSI

Unchanged from the Phase 1-3 implementation: `daily_returns`,
`cumulative_returns`, `volatility_annualized` (std of daily returns ×
√252), `max_drawdown` (largest peak-to-trough decline of cumulative
value), `sma`/`ema`, `rsi` (14-period, Wilder-style gain/loss ratio).

### 2.2 MACD (`analytics.macd`)

Standard definition: `MACD line = EMA(12) - EMA(26)`, `signal line =
EMA(9) of the MACD line`, `histogram = MACD line - signal line`. Returned
as a full time series (all three columns), not just the latest value, so
the frontend can plot the histogram crossing zero.

### 2.3 Beta vs. NIFTY 50 (`analytics.beta`)

`beta = Cov(stock_returns, benchmark_returns) / Var(benchmark_returns)`,
computed over daily returns aligned by date (inner join, so only trading
days present in both series count). Benchmark is NIFTY 50 (`^NSEI`),
fetched via `MarketDataService.get_benchmark_history()` — same
provider/cache path as any other symbol, never persisted to the
`stocks`/`market_data` tables (it isn't a holding or a discoverable stock).

**Returns `None`, not 0 or 1, when fewer than 20 overlapping observations
exist** — a missing beta must never be silently presented as "beta of
zero" (implying no market sensitivity) or "beta of one" (implying average
market sensitivity); both would be a specific, false claim about an
unknown quantity.

**Known instability, verified empirically, not just asserted:** on the
synthetic `DevSampleProvider` data (TCS seeded with an embedded
`BETAS["TCS"] = 0.85`), the measured beta over a 120-day window came out
as **-0.22** — wrong sign, nowhere near the embedded value — purely from
small-sample noise (idiosyncratic daily volatility dominates the signal at
that window length). Over the full ~287-day seeded history, it recovers to
**0.85**, exactly matching the embedded value. **Conclusion: a beta
computed on fewer than ~250 trading days (about a year) should be treated
as unreliable**, regardless of data source — this is a property of the
estimator on noisy daily data, not specific to synthetic data, and the
same caution applies once this runs on real cached NIFTY data. The 20-row
floor in `analytics.beta()` is a crash-guard against a degenerate
calculation, not a claim of statistical stability at that sample size —
callers should prefer the endpoint's default window (400 calendar days)
over a short one when beta matters.

### 2.4 Synthetic benchmark construction (DevSampleProvider only)

A broad index like NIFTY 50 is approximately the diversified market factor
itself — single-stock idiosyncratic noise averages out across its ~50
constituents. `DevSampleProvider` models this by generating the `^NSEI`
series with `beta = 1.0` (fixed) and an idiosyncratic-noise multiplier of
0.08 versus 0.7 for individual stocks (an illustrative modeling choice, not
calibrated against real index tracking-error data). `LiveYFinanceProvider`
fetches the real index level instead once real data is available (Phase 4
cache, populated locally).

---

*(Sections 3+ — ML feature engineering and evaluation protocol,
risk-attribution math, Fit Engine formula, stress-test assumptions,
counterfactual search, and the prediction ledger design — are added as
each corresponding phase is implemented, not written in advance.)*
