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

---

*(Sections 2+ — stock analysis formulas, ML feature engineering and
evaluation protocol, risk-attribution math, Fit Engine formula, stress-test
assumptions, counterfactual search, and the prediction ledger design — are
added as each corresponding phase is implemented, not written in advance.)*
