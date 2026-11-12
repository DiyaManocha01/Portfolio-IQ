# PortfolioIQ Backend API Contract

Current through Phase 19 (the last phase to add a new endpoint; Phases
20-22 added frontend UI, tests/security, and deployment without changing
this contract). Every shape below is what the code actually returns, not
an aspirational spec — see `docs/methodology.md` for the formula behind
each field and `docs/limitations.md` for what each number does and
doesn't mean.

Base URL (local dev): `http://localhost:8000`

All endpoints except `/auth/register` and `/auth/login` require:
`Authorization: Bearer <access_token>`

Interactive OpenAPI docs available at `http://localhost:8000/docs` when the backend is running.

Demo login: `demo@portfolioiq.app` / `demo1234`

---

## Auth

### POST /auth/register
Body: `{ "email": str, "password": str (>=6 chars), "full_name": str }`
Response 201:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": { "id": 1, "email": "a@b.com", "full_name": "A B", "created_at": "2026-01-01T00:00:00Z" }
}
```

### POST /auth/login
Body: `{ "email": str, "password": str }` -> same response shape as register (200).

### GET /auth/me
Response: `{ "id", "email", "full_name", "created_at" }`

### GET /auth/me/preferences (Phase 12)
Response: `{ "excluded_sectors": ["Energy"] }` (empty list if never set).

### PUT /auth/me/preferences (Phase 12)
Body: `{ "excluded_sectors": ["Energy", "Healthcare"] }` -> echoes the same
shape back (200). Stocks in an excluded sector are hard-filtered out of
`/discover` entirely (not a scoring penalty). A sector name that doesn't
match anything real is a silent no-op, not an error. If excluding every
present sector would empty the discovery list, discovery falls back to
unfiltered rather than returning nothing.

---

## Portfolio (all require auth; operate on the current user's single portfolio)

### GET /portfolio -> list[Holding]
```json
[{
  "id": 1, "symbol": "TCS", "name": "Tata Consultancy Services", "sector": "Information Technology",
  "quantity": 10.0, "avg_buy_price": 3200.0, "current_price": 3489.71,
  "invested_value": 32000.0, "current_value": 34897.1, "pnl": 2897.1, "return_pct": 9.05
}]
```

### POST /portfolio/holdings
Body: `{ "symbol": "TCS", "quantity": 10, "avg_buy_price": 3200 }` -> Holding (201). Adding an existing symbol merges into a weighted-average position. Phase 31: also logs a BUY transaction (see `/portfolio/transactions` below).

### POST /portfolio/holdings/{holding_id}/sell (Phase 31)
Body: `{ "price": 3600, "quantity": 4 }` (`quantity` optional -- omit to sell the entire position). Reduces or removes the holding, computes `realized_pnl = (price - avg_buy_price) * quantity`, and logs a SELL transaction. Returns `400` if `quantity` exceeds what's held, `404` if the holding doesn't exist.
```json
{ "id": 12, "symbol": "TCS", "type": "SELL", "quantity": 4, "price": 3600,
  "realized_pnl": 400.0, "transaction_date": "2026-11-12" }
```
Distinct from `DELETE` below, which stays a plain removal with no price and no transaction logged (for correcting a mis-entered holding, not recording a sale) -- see `docs/adr/0014-portfolio-transaction-ledger.md`.

### DELETE /portfolio/holdings/{holding_id} -> 204
Unchanged since before Phase 31: removes the holding outright, no transaction logged.

### GET /portfolio/transactions (Phase 31)
Newest first. Only includes transactions logged since Phase 31 shipped -- holdings added or removed before then have no history (never backfilled).
```json
[{ "id": 12, "symbol": "TCS", "type": "SELL", "quantity": 4, "price": 3600,
   "realized_pnl": 400.0, "transaction_date": "2026-11-12" },
 { "id": 11, "symbol": "TCS", "type": "BUY", "quantity": 10, "price": 3500,
   "realized_pnl": null, "transaction_date": "2026-11-10" }]
```

### GET /portfolio/summary
```json
{ "portfolio_id": 1, "portfolio_value": 252702.01, "invested_amount": 248200.0,
  "total_pnl": 4502.01, "return_pct": 1.81, "holdings_count": 7,
  "portfolio_risk": "Low" | "Moderate" | "High", "health_score": 81.2 }
```

### GET /portfolio/performance?days=180
```json
{ "points": [{ "date": "2026-01-01", "value": 250000.0, "invested": 248200.0 }, ...],
  "data_source": "DEV_SAMPLE" | "LIVE" }
```
Note: assumes current holding quantities held constant across the window (documented MVP simplification).

### GET /portfolio/performance/advanced?days=180 (Phase 31)
Builds on the same `points` series above with daily/cumulative returns,
a NIFTY 50 benchmark comparison, a running drawdown series, sector- and
holding-level P&L contribution, and the realized/unrealized split. See
`app/portfolio/portfolio_performance_service.py` and ADR 0014.
```json
{
  "points": [{ "date": "2026-01-01", "value": 250000.0, "invested": 248200.0 }],
  "daily_returns": [{ "date": "2026-01-02", "return_pct": 0.42 }],
  "cumulative_returns": [{ "date": "2026-01-02", "cumulative_return_pct": 0.42 }],
  "drawdown": [{ "date": "2026-01-02", "drawdown_pct": -1.3 }],
  "benchmark": [{ "date": "2026-01-01", "value": 250000.0 }],
  "holding_contributions": [{ "symbol": "TCS", "name": "Tata Consultancy Services", "pnl": 2897.1, "contribution_pct": 31.5 }],
  "sector_contributions": [{ "sector": "Information Technology", "pnl": 8206.65, "contribution_pct": 42.2 }],
  "unrealized_pnl": 4502.01, "realized_pnl": 400.0, "total_pnl": 4902.01,
  "annualized_volatility_realized": 0.2008,
  "data_source": "DEV_SAMPLE"
}
```
`unrealized_pnl` matches `PortfolioSummary.total_pnl`. `realized_pnl` is
the sum of SELL transactions logged since Phase 31 (0 until a real sale
happens via `/portfolio/holdings/{id}/sell`). `annualized_volatility_realized`
is computed directly from this series' own realized daily returns -- a
second, independently-derived volatility figure from `GET
/portfolio/risk`'s `annualized_volatility` (the two can differ, since
they're computed from different underlying return series). `benchmark`
is NIFTY 50 bought-and-held normalized to the same starting value as
`points[0]` -- not a backtested strategy. Corporate actions
(splits/dividends): handled via `auto_adjust=True` on the underlying
`yfinance` call, not separate logic here -- see ADR 0014.

### GET /portfolio/allocation
```json
{ "by_stock": [{ "label": "TCS", "value": 34897.1, "pct": 13.8 }, ...],
  "by_sector": [{ "label": "Information Technology", "value": 78874.85, "pct": 31.2 }, ...] }
```

### GET /portfolio/risk
```json
{
  "annualized_volatility": 0.1975, "sharpe_ratio": 0.222, "max_drawdown": -0.0498,
  "risk_contributions": [{ "symbol": "INFY", "risk_contribution_pct": 24.92 }, ...],
  "correlation_matrix": [{ "symbol_a": "TCS", "symbol_b": "RELIANCE", "correlation": 0.261 }, ...],
  "sector_concentration": [{ "label": "Information Technology", "value": 78874.85, "pct": 31.2 }, ...],
  "top_stock_concentration_pct": 17.4,
  "var_95": 0.0177, "cvar_95": 0.0211, "var_99": 0.0224, "cvar_99": 0.0257,
  "hhi_holdings": 0.1464, "hhi_sector": 0.2264,
  "effective_number_of_bets": 6.83, "diversification_ratio": 1.412,
  "covariance_method": "ledoit_wolf" | "sample", "shrinkage_intensity": 0.0412,
  "data_source": "DEV_SAMPLE"
}
```
Phase 8 fields: `var_95`/`cvar_95`/`var_99`/`cvar_99` are historical-simulation
VaR/CVaR on realized portfolio daily returns, reported as positive loss
fractions (never negative). `hhi_holdings`/`hhi_sector` are Herfindahl
indices (range `1/n` to `1`). `effective_number_of_bets` is the
weight-concentration definition (`1/hhi_holdings`) — NOT a
correlation/PCA-aware measure, see `docs/methodology.md` Section 5.5.
`covariance_method`/`shrinkage_intensity` report whether Ledoit-Wolf
shrinkage was used for the covariance matrix behind `risk_contributions`
and `diversification_ratio` (falls back to `"sample"` with intensity `0.0`
when there are fewer than 2 holdings or fewer return observations than
holdings).

### GET /portfolio/optimize?method=min_variance|max_sharpe|risk_parity (Phase 9)
```json
{
  "method": "min_variance", "feasible": true, "note": null,
  "allocations": [
    { "symbol": "ITC", "current_weight_pct": 16.88, "suggested_weight_pct": 62.67, "delta_pct": 45.79 },
    ...
  ],
  "expected_annual_return": 0.0281, "expected_annual_volatility": 0.1681, "expected_sharpe_ratio": -0.19,
  "risk_free_rate_assumed": 0.06, "lookback_days": 180, "data_source": "DEV_SAMPLE",
  "disclaimer": "This is a hypothetical target allocation from a portfolio-optimization model, computed over historical data. It is a simulation, not a trade instruction or a guarantee of future performance -- it never modifies your actual holdings."
}
```
Never mutates real holdings -- purely computed, nothing is written to the
DB. `method=risk_parity` uses Hierarchical Risk Parity (HRP), NOT naive
equal-risk-contribution -- see `docs/methodology.md` Section 6.2.
`feasible: false` (empty `allocations`, `note` explaining why) can happen
for `max_sharpe` when no held stock's historical return exceeds the
assumed risk-free rate, or for any method with fewer than 2 holdings.
Unknown `method` values return 400. ALWAYS render the disclaimer and never
phrase this as an instruction to rebalance.

### POST /portfolio/what-if (Phase 11)
Body: `{ "changes": [{ "symbol": "TCS", "new_quantity": 0 }, { "symbol": "SUNPHARMA", "new_quantity": 20 }], "include_costs": true }`
`new_quantity` is an ABSOLUTE target (not a delta): `0` fully exits a
position; a symbol not currently held with `new_quantity > 0` is a
hypothetical new buy. `changes` must have at least 1 entry;
`new_quantity` must be `>= 0`.
```json
{
  "before": { "annualized_volatility": 0.1975, "sharpe_ratio": 0.42, "var_95": 0.0177, "cvar_95": 0.0211, "var_99": 0.0224, "cvar_99": 0.0257, "diversification_ratio": 1.412, "hhi_holdings": 0.1464 },
  "after": { "annualized_volatility": 0.1868, "sharpe_ratio": 0.507, "var_95": 0.0171, "cvar_95": 0.0199, "var_99": 0.0202, "cvar_99": 0.0239, "diversification_ratio": 1.454, "hhi_holdings": 0.1291 },
  "deltas": { "annualized_volatility": -0.0107, "sharpe_ratio": 0.087, "...": "..." },
  "trades": [
    { "symbol": "SUNPHARMA", "quantity_delta": 15.0, "trade_value": 27475.2, "action": "buy",
      "estimated_cost": { "brokerage": 0.0, "stt": 27.48, "stamp_duty": 4.12, "exchange_charges": 0.82, "sebi_fee": 0.03, "gst": 0.15, "total": 32.6 } }
  ],
  "total_estimated_cost": 32.6, "risk_free_rate_assumed": 0.06, "lookback_days": 180, "data_source": "DEV_SAMPLE",
  "disclaimer": "This is a hypothetical simulation of portfolio changes computed over historical data. It never modifies your actual holdings, is not a trade instruction, and transaction cost estimates are illustrative approximate rates, not quotes from any specific broker."
}
```
**Never writes to the database** -- the real portfolio is read, never
mutated (verified by a dedicated test). `estimated_cost` fields use
illustrative, commonly-cited approximate NSE equity delivery-trade rates
(STT/stamp duty/exchange charges/SEBI fee/GST), NOT sourced from any
specific broker's live rate card -- see `docs/limitations.md`. Pass
`include_costs: false` to omit cost estimation (`estimated_cost` and
`total_estimated_cost` become `null`). No-op changes (requesting the
current quantity) produce an empty `trades` list and all-zero `deltas`.
ALWAYS render the disclaimer; never phrase this as a trade instruction.

### GET /portfolio/risk-attribution (Phase 14)
```json
{
  "portfolio_annualized_volatility": 0.1975,
  "attributions": [
    { "symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Financial Services",
      "weight_pct": 14.62, "risk_contribution_pct": 19.87,
      "marginal_contribution_to_vol": 0.2594, "risk_concentration_ratio": 1.359 },
    { "symbol": "ITC", "name": "ITC Limited", "sector": "Consumer Staples",
      "weight_pct": 16.88, "risk_contribution_pct": 10.44,
      "marginal_contribution_to_vol": 0.118, "risk_concentration_ratio": 0.618 }
  ],
  "data_source": "DEV_SAMPLE"
}
```
`attributions` sorted by `risk_contribution_pct` descending. `weight_pct`
(% of portfolio money) and `risk_contribution_pct` (% of portfolio risk)
each independently sum to ~100% across all holdings.
`risk_concentration_ratio = risk_contribution_pct / weight_pct` -- `>1`
means a holding contributes disproportionately MORE risk than its money
weight; `<1` means less. `marginal_contribution_to_vol` is the raw
sensitivity `d(portfolio_vol)/d(weight_i)`, same units as
`portfolio_annualized_volatility`. See `docs/methodology.md` Section 11.

### POST /portfolio/stress-test (Phase 15)
Body: exactly one of:
- `{ "scenario_preset": "covid_2020_crash" | "gfc_2008" | "moderate_correction" }`
- `{ "scenario_text": "IT stocks crash 20%" }` (parsed via a narrow regex matcher, NOT an LLM -- unparseable text returns 400)
- `{ "market_shock_pct": -0.20 }`
- `{ "sector_shocks": { "Information Technology": -0.25 } }` (overrides beta-scaling for that sector)

```json
{
  "market_shock_pct": -0.2, "sector_shocks": {},
  "total_value_before": 267660.63, "total_value_after": 218825.17,
  "total_loss": -48835.46, "total_loss_pct": -18.25,
  "breakdown": [
    { "symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Financial Services",
      "value_before": 39124.5, "value_after": 29161.2, "loss": -9963.3,
      "shock_applied_pct": -0.2547, "beta_used": 1.273, "used_fallback_beta": false,
      "sector_shock_applied": false }
  ],
  "data_source": "DEV_SAMPLE",
  "disclaimer": "This is a hypothetical, single-factor (CAPM beta) stress simulation, not a prediction or a literal historical replay. It never modifies your actual holdings. Real crises often involve correlation spikes and idiosyncratic effects this simple model does not capture -- see docs/limitations.md.",
  "scenario_preset": null, "scenario_label": null, "scenario_note": null
}
```
`breakdown` sorted by `loss` ascending (largest loss first). Never writes
to the database -- the real portfolio is read, never mutated (verified by
a dedicated test). `beta_used: null` + `sector_shock_applied: true` means
a sector override replaced beta-scaling for that holding entirely.
`used_fallback_beta: true` means the holding's real beta couldn't be
estimated (< 20 overlapping trading days with the benchmark) and a
market-average beta of 1.0 was substituted. Scenario presets' magnitudes
are illustrative, publicly well-known approximate figures, NOT a literal
historical day-by-day replay -- see `docs/methodology.md` Section 12.2.
ALWAYS render the disclaimer.

### GET /portfolio/health
```json
{
  "overall_health": 81.2,
  "components": [
    { "name": "Diversification", "score": 68.2, "description": "..." },
    { "name": "Concentration", "score": 68.8, "description": "..." },
    { "name": "Risk", "score": 79.1, "description": "..." },
    { "name": "Correlation", "score": 100.0, "description": "..." },
    { "name": "Drawdown", "score": 90.0, "description": "..." }
  ],
  "computed_at": "2026-09-16T11:28:37Z"
}
```
Full methodology: `docs/PORTFOLIO_SCORING.md`.

### GET /portfolio/weaknesses
```json
{ "weaknesses": [
  { "title": "High IT Sector Concentration", "severity": "HIGH" | "MEDIUM" | "LOW",
    "explanation": "...", "supporting_metric": "Information Technology = 58.0% of portfolio" }
]}
```
Empty array is a valid, common response (means no weaknesses detected) -> show a positive empty state.

---

## Stocks

### GET /stocks -> list[{ id, symbol, name, sector, industry, exchange }]
Seeded universe: TCS, RELIANCE, HDFCBANK, INFY, ICICIBANK, LT, ITC (held in demo portfolio) plus
HINDUNILVR, BHARTIARTL, SBIN, WIPRO, MARUTI, SUNPHARMA (unheld -- these populate /discover).

### GET /stocks/{symbol}
```json
{
  "quote": { "symbol": "TCS", "name": "...", "sector": "...", "current_price": 3489.71,
    "previous_close": 3480.0, "change": 9.71, "change_percent": 0.28, "volume": 2500000,
    "data_source": "DEV_SAMPLE" },
  "indicators": { "sma_20": .., "sma_50": .., "ema_20": .., "rsi_14": .., "volatility_annualized": ..,
    "momentum_10d": .., "daily_return": .., "cumulative_return_30d": .., "avg_volume_20d": .. },
  "history": [{ "date": "2025-08-01", "open": .., "high": .., "low": .., "close": .., "volume": .. }, ...]
}
```

### GET /stocks/{symbol}/history?days=200 -> `{ symbol, data_source, points: [OHLCV...] }`

### GET /stocks/{symbol}/analysis?days=400 (Phase 5)
Full time series (not just latest values) for charting -- returns,
volatility, drawdown, SMA/EMA/RSI/MACD per day, plus beta vs. NIFTY 50.
```json
{
  "symbol": "TCS", "data_source": "DEV_SAMPLE",
  "returns": { "daily_return": 0.025, "cumulative_return_30d": -0.06, "cumulative_return_90d": 0.165, "cumulative_return_1y": 0.171 },
  "volatility_annualized": 0.286, "max_drawdown": -0.126,
  "beta_vs_nifty50": 0.85, "benchmark_data_source": "DEV_SAMPLE",
  "series": [{ "date": "2026-10-21", "close": 3615.99, "sma_20": 3431.28, "ema_20": 3445.89,
               "rsi_14": 52.1, "macd_line": -2.17, "macd_signal": -20.44, "macd_histogram": 18.28 }],
  "disclaimer": "Historical analysis only. Not a prediction, recommendation, or guarantee of future performance."
}
```
`beta_vs_nifty50` is `null` (never 0 or 1) when fewer than 20 overlapping
trading days exist with the benchmark -- see docs/methodology.md for why a
missing beta must never be presented as a specific value. Beta on short
windows (<~250 days) is empirically noisy; prefer the default 400-day
window when beta matters for a decision.

### GET /stocks/{symbol}/prediction
```json
{
  "symbol": "TCS", "direction": "POSITIVE" | "NEGATIVE" | "NEUTRAL", "probability": 0.6,
  "confidence": "LOW" | "MEDIUM" | "HIGH", "model_name": "logistic_regression",
  "model_version": "6a16cbbc7b76",
  "prediction_date": "2026-09-16",
  "important_features": ["5-day momentum", "Exponential moving average trend", "Moving average trend"],
  "shap_values": { "return_1d": 0.00851, "return_5d": 0.37576, "...": "one entry per feature column" },
  "shap_base_value": -0.0101, "shap_output_space": "log_odds" | "probability",
  "disclaimer": "This is a model-generated estimate, not financial advice or a guaranteed outcome."
}
```
ALWAYS render the disclaimer text and use "Potentially Positive/Negative"
style language in the UI, never "will go up". `important_features`
(Phase 17) is now a genuine PER-PREDICTION SHAP ranking -- it legitimately
differs between stocks on the same model, not a fixed global list.
`shap_values`/`shap_base_value`/`shap_output_space` are `null` if SHAP
explanation wasn't available for this prediction (falls back
gracefully, never fails the prediction itself).
**`shap_output_space` differs by model type** -- `"probability"` for
`random_forest`, `"log_odds"` for `logistic_regression`/`xgboost`; never
compare raw `shap_values` magnitudes without checking this field first.
`shap_base_value + sum(shap_values)` reconstructs the UNCALIBRATED base
model's own score, not the exact served `probability` (calibration is a
separate, monotonic remapping step) -- see `docs/methodology.md`
Section 14.2.

### GET /stocks/{symbol}/news?limit=10 -> list of
```json
{ "id": 1, "headline": "...", "source": "Economic Times", "url": null,
  "published_at": "2026-09-10T08:00:00Z", "sentiment_label": "POSITIVE", "sentiment_score": 0.62 }
```

### GET /stocks/{symbol}/sentiment
```json
{ "symbol": "TCS", "positive_pct": 61.0, "neutral_pct": 24.0, "negative_pct": 15.0,
  "average_score": 0.18, "average_score_time_decayed": 0.156, "sentiment_half_life_days": 7.0,
  "trend": "IMPROVING" | "DECLINING" | "STABLE",
  "article_count": 10, "model_used": "lexicon-v1" | "finbert" }
```
`average_score` is a simple equal-weighted mean across recent articles;
`average_score_time_decayed` (Phase 7) weighs more recent articles more
heavily (`0.5 ** (age_days / sentiment_half_life_days)`) — both are
returned so neither silently replaces the other. News source is
`DataSource.DEV_SAMPLE` (synthetic) by default, or real RSS-ingested
headlines when `USE_LIVE_NEWS=true` and a local cache exists (see
`docs/methodology.md` Section 4).

### GET /stocks/{symbol}/fundamentals (Phase 26)
```json
{
  "symbol": "TCS", "data_source": "DEV_SAMPLE", "as_of": "2026-11-11",
  "pe_ratio": 25.81, "market_cap": 8113187789344.73, "eps": 133.67,
  "dividend_yield": 2.47, "book_value": 969.59,
  "revenue_growth_yoy": 0.2076, "profit_growth_yoy": 0.2744,
  "roe": 0.1535, "roce": null, "debt_to_equity": 46.24,
  "disclaimer": "Fundamental ratios are sourced data, not investment advice. Fields shown as unavailable are genuinely missing from the data source, not computed or estimated by PortfolioIQ."
}
```
Cached per (stock, day) -- fundamentals don't change intraday. `roce` is
**always null** when `data_source` is `LIVE` (no yfinance equivalent);
only `DEV_SAMPLE` populates it. `debt_to_equity`'s scale is whatever the
underlying source uses verbatim, unconverted -- see
`docs/limitations.md` before assuming a 0-1 ratio vs. a percent. This
endpoint does **not** require auth (same as every other `/stocks/*`
route -- stock data isn't user-scoped).

---

## Screener (Phase 26)

### GET /screener?sector=&market_cap_min=&market_cap_max=&pe_min=&pe_max=&roe_min=&debt_to_equity_max=&dividend_yield_min=&revenue_growth_min=&profit_growth_min=&rsi_min=&rsi_max=&momentum_10d_min=
Every param is optional; an empty query returns the whole universe this
environment has seeded (not the full, separately-unverified NIFTY 100
list -- same scope as `GET /stocks`).
```json
{
  "count": 1,
  "results": [{
    "symbol": "TCS", "name": "Tata Consultancy Services", "sector": "Information Technology",
    "industry": "IT Services", "data_source": "DEV_SAMPLE", "current_price": 3615.99,
    "market_cap": 8113187789344.73, "pe_ratio": 25.81, "eps": 133.67, "dividend_yield": 2.47,
    "roe": 0.1535, "roce": 0.2194, "debt_to_equity": 46.24,
    "revenue_growth_yoy": 0.2076, "profit_growth_yoy": 0.2744,
    "rsi_14": 52.1, "momentum_10d": 0.034
  }],
  "disclaimer": "Screener results are filtered from sourced fundamentals and technical indicators. This is not a recommendation to buy or sell any stock."
}
```
`rsi_14`/`momentum_10d` are only computed (non-null) when at least one of
`rsi_min`/`rsi_max`/`momentum_10d_min` is supplied -- a bare fundamentals
query leaves them `null` rather than doing unrequested work. No auth
required (same rationale as `/stocks/*`).

---

## Discover & Portfolio Fit (the core USP)

### GET /discover?limit=20&preset=balanced|risk_averse|growth_seeking&sector=... -> list, already sorted by portfolio_fit descending
```json
[{ "symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries", "sector": "Healthcare",
   "current_price": 1831.68, "ml_outlook": "NEUTRAL", "prediction_probability": 0.494,
   "volatility": 0.2012, "portfolio_fit": 75.6, "correlation_with_portfolio": 0.259,
   "diversification_benefit": "High" | "Moderate" | "Low",
   "top_factor": { "name": "Diversification Impact", "explanation": "Adding this stock would change the diversification ratio by +0.047." } }]
```
Page title MUST be "Stocks That May Fit Your Portfolio" -- never "Best
Stocks" / "Stocks You Should Buy". `preset` (Phase 10) overrides the
user's risk-tolerance-derived default for this call; `sector`
(case-insensitive) restricts to one sector. Candidates in any sector the
user has excluded via `/auth/me/preferences` (Phase 12) never appear here
at all. `top_factor` is the single highest-contribution factor from that
stock's Fit breakdown -- render it as the one-line "why" in the list;
drill into `/portfolio-fit/{symbol}` for the full breakdown.

### GET /portfolio-fit/{symbol}?preset=balanced|risk_averse|growth_seeking (Phase 10)
```json
{
  "symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries", "fit_score": 72.0,
  "preset": "balanced",
  "factors": [
    { "name": "Diversification Impact", "contribution": 0.64, "raw_value": 0.0474, "z_score": 2.562,
      "explanation": "Adding this stock would change the diversification ratio by +0.047." },
    { "name": "Risk Impact", "contribution": 0.499, "raw_value": -0.0114, "z_score": -2.496,
      "explanation": "Adding this stock would change portfolio volatility by -1.14 pts." },
    { "name": "Concentration Impact", "contribution": 0.162, "raw_value": -0.0178, "z_score": -1.08,
      "explanation": "..." },
    { "name": "News Sentiment", "contribution": -0.079, "raw_value": 0.059, "z_score": -0.527, "explanation": "..." },
    { "name": "ML Outlook", "contribution": -0.277, "raw_value": -0.0043, "z_score": -1.109, "explanation": "..." }
  ],
  "strengths": ["..."], "concerns": ["..."],
  "weights_used": { "outlook": 0.25, "sentiment": 0.15, "risk_delta": 0.2, "diversification_delta": 0.25, "concentration_delta": 0.15 },
  "change": null,
  "cached": false
}
```
`factors` is sorted by contribution descending -- render as a
bar/waterfall breakdown plus the strengths/concerns lists. This screen is
the single most important screen in the whole demo. **`contribution` is
in pre-sigmoid (logit) units** -- factors sum to the sigmoid's input, NOT
linearly to `fit_score` (that transform is nonlinear) -- see
`docs/methodology.md` Section 7.4; never sum contributions in the UI and
display the total as if it were the fit score. Risk/Diversification/Concentration
"Impact" factors are deltas -- what happens to the PORTFOLIO if this stock
is added at a modest hypothetical weight -- not standalone properties of
the stock. An already-held stock's three delta factors are always exactly
0 (raw_value). `preset` defaults to a mapping from the user's risk
tolerance if not given; unknown `preset` values return 400. **The same
symbol's `fit_score` can legitimately differ between this endpoint and
`/discover`** -- each z-scores against a different population (full
universe vs. the candidate batch) -- see Section 7.3.

**`change` / `cached` (Phase 29, see ADR 0012):** the result is cached
against a fingerprint of everything it depends on (latest price date,
model version, sentiment score, portfolio composition). `cached: true`
means nothing relevant has changed since the last call and this is the
stored result, not a fresh computation. `change` is `null` on a cache
hit, on the very first computation ever for this `(portfolio, stock,
preset)`, or if the score rounds to the same display value -- otherwise
it explains the move:
```json
{ "score_delta": 2.3, "biggest_factor": "ML Outlook", "biggest_factor_delta": 0.041,
  "message": "Fit score improved by 2.3 points since the last check, mainly because ML Outlook became more favorable.",
  "previous_computed_at": "2026-11-11T09:00:00+00:00" }
```

---

### GET /portfolio-fit/{symbol}/compare/{other_symbol}?preset=... (Phase 16)
```json
{
  "symbol_a": "SUNPHARMA", "symbol_b": "WIPRO", "fit_score_a": 72.0, "fit_score_b": 53.6,
  "logit_gap": 0.8015,
  "term_deltas": [
    { "term": "diversification_delta", "name": "Diversification Impact", "contribution_a": 0.6404, "contribution_b": -0.191, "delta": 0.8315 },
    { "term": "risk_delta", "name": "Risk Impact", "contribution_a": 0.4993, "contribution_b": 0.1208, "delta": 0.3784 }
  ],
  "preset": "balanced",
  "note": "term_deltas sum exactly to logit_gap (an algebraic identity, not an approximation) -- sorted by absolute contribution to the gap, largest first."
}
```
Both stocks are z-scored against the SAME population (the full stock
universe) so the comparison is valid -- do not compare a logit from this
endpoint against one from `/discover` (different, batch-scoped
population; see Section 7.3).

### GET /portfolio-fit/{symbol}/counterfactual?target_symbol=...|target_score=...&preset=... (Phase 16)
Exactly one of `target_symbol` or `target_score` (strictly between 0 and
100) is required; both or neither returns 400.
```json
{
  "symbol": "WIPRO", "fit_score": 53.6, "target": "SUNPHARMA", "already_meets_target": false,
  "term_scenarios": [
    { "term": "outlook", "name": "ML Outlook", "current_raw_value": 0.0245,
      "required_z_delta": 3.206, "required_raw_delta": 0.0664, "target_raw_value": 0.0909 }
  ],
  "note": "Each scenario is CETERIS PARIBUS -- 'if ONLY this term changed, holding every other term fixed, this is how much it would need to move to close the gap.' This is NOT a joint, minimal-change search across all terms simultaneously, and a required change being numerically small does not mean it is realistically easy to achieve -- see docs/limitations.md."
}
```
`already_meets_target: true` means the stock already meets/exceeds the
target and `term_scenarios` is empty (nothing to compute). Each scenario
is independent of the others -- never sum or combine `required_raw_delta`
values across terms as if they were a joint plan.

## Prediction Ledger (Phase 18, PUBLIC -- no auth required)

The first unauthenticated data surface in this app -- the whole point of
a public track record is third-party verifiability without an account.

### GET /ledger/entries?symbol=&limit=50&offset=0
```json
[{
  "id": 42, "entry_type": "prediction" | "resolution",
  "previous_hash": "a1b2...", "entry_hash": "c3d4...",
  "created_at": "2026-10-22T10:00:00Z",
  "stock_id": 1, "symbol": "TCS", "model_name": "logistic_regression", "model_version": "6a16cbbc7b76",
  "direction": "POSITIVE", "probability": 0.62, "confidence": "MEDIUM", "prediction_date": "2026-10-22",
  "resolves_entry_id": null, "realized_direction": null, "realized_return": null
}]
```
`"resolution"` entries have `direction`/`probability`/etc. `null` and
`resolves_entry_id`/`realized_direction`/`realized_return` populated
instead. `limit` max 500.

### GET /ledger/verify
```json
{ "valid": true, "total_entries": 27, "first_broken_entry_id": null, "reason": null }
```
Recomputes every entry's hash from its own stored payload and checks the
whole chain. `valid: false` names the first entry where it broke.

### GET /ledger/track-record
```json
{
  "total_predictions": 27, "resolved_count": 3, "pending_count": 24,
  "directional_predictions_resolved": 2, "directional_hit_rate": 1.0,
  "paper_trading": {
    "n_resolved_positions": 3, "cumulative_return": 0.05, "sharpe_ratio_unannualized": 0.707,
    "note": "Long when the prediction was POSITIVE, flat otherwise -- same strategy definition as Phase 13's backtest, but computed here from real, already-made, append-only predictions rather than a retrospective walk-forward simulation."
  },
  "note": "This track record grows only from genuinely new predictions made since Phase 18 shipped -- no history has been backdated or fabricated. A thin or empty record reflects how new this ledger is, not a data gap.",
  "disclaimer": "Historical track record only, computed from real recorded predictions. Not a guarantee of future performance and not financial advice."
}
```
`directional_hit_rate` excludes `NEUTRAL` predictions (not a directional
bet) -- always read alongside `directional_predictions_resolved`.
ALWAYS render the disclaimer and the "thin record" note together; never
present a small sample as if it were a mature track record.

## AI Portfolio Assistant (Phase 19)

### POST /assistant/ask
Body: `{ "question": "How risky is my portfolio?" }` (1-2000 chars)
```json
{
  "answer": "Your portfolio's annualized volatility is 19.75%, with ICICIBANK contributing the most to risk at 19.87% (vs. 14.62% of your money) -- a concentration ratio of 1.36...",
  "sources_used": ["portfolio_summary", "portfolio_health", "portfolio_weaknesses", "portfolio_risk", "risk_attribution"],
  "guardrail_tripped": false,
  "guardrail_matched_phrase": null,
  "model": "claude-sonnet-5-5",
  "disclaimer": "PortfolioIQ is an educational and analytical decision-support system. Its predictions and portfolio analytics are model-based estimates and are not guaranteed financial advice."
}
```
Answers ONLY from already-computed data (never computes a new figure
itself) and NEVER gives buy/sell advice or predicts future
prices/returns -- enforced by both the system prompt and a separate
keyword guardrail; if the guardrail trips, `answer` is replaced with a
fixed safe-fallback message and `guardrail_tripped`/`guardrail_matched_phrase`
say so. `sources_used` lists exactly which computed data blocks were
available to the model for this question (always
`portfolio_summary`/`portfolio_health`/`portfolio_weaknesses`; more are
added when the question mentions a held/known stock symbol, risk/
volatility, "new stock"/discovery, or track record/accuracy). Returns
**503** if `ANTHROPIC_API_KEY` isn't configured on the backend. ALWAYS
render the disclaimer. Requires auth (unlike the public `/ledger/*`
endpoints) -- this answers questions about the current user's own
portfolio.

## Real-Time Market Data (Phase 24/25)

### GET /market/status
```json
{
  "market_status": "OPEN",
  "feed_status": "DISABLED",
  "server_time": "2026-11-11T10:00:00Z",
  "ticks": [
    {
      "symbol": "RELIANCE", "exchange": "NSE", "price": 2950.0,
      "previous_close": 2940.0, "change": 10.0, "change_percent": 0.34,
      "open": 2941.0, "high": 2960.0, "low": 2938.0, "close": 2940.0,
      "volume": 1200000, "last_traded_time": "2026-11-11T09:59:00Z",
      "status": "FIXTURE", "source": "FIXTURE"
    }
  ]
}
```
`market_status` is `OPEN | CLOSED | HOLIDAY | WEEKEND` (session hours
only -- see `docs/limitations.md` for the holiday-calendar gap).
`feed_status` is `DISABLED | MISCONFIGURED | CONNECTING | CONNECTED |
RECONNECTING | STOPPED`. Each tick's own `status` is
`LIVE | DELAYED | STALE | CLOSED | FIXTURE | UNAVAILABLE` -- **always
render this status next to any price from this endpoint**; never imply a
`FIXTURE` or `STALE` tick is a live price. `ticks` only contains symbols
the cache currently has something for -- may be `[]` briefly after
startup.

### GET /market/candles/{symbol}?limit=390
```json
{ "symbol": "RELIANCE", "candles": [ { "timestamp": "...", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0, "status": "LIVE" } ] }
```
Returns real intraday candles from `intraday_candles` only -- an empty
`candles` array means no snapshot exists yet (common until the real-time
feed has actually run), not an error. Never fabricate a candle to fill
this; the frontend hides the intraday chart entirely when this is empty.

### WS /ws/market?token=&lt;JWT&gt;
Pushes the same shape as `GET /market/status` roughly every second.
Token is the same JWT from `POST /auth/login`, passed as a query param
(browsers can't set a WebSocket's auth header). Closes with code 1008 if
the token is missing or invalid. Multiple connected clients share one
upstream broker connection server-side -- see
`docs/adr/0008-realtime-market-data-angelone.md`.

### GET /market/regime?symbol=... (Phase 30, no auth -- same reasoning as `/stocks/*`)
Omit `symbol` for the NIFTY 50 market-wide regime; pass any stock
symbol for that stock's own regime (same underlying classifier).
```json
{
  "symbol": "NIFTY50", "regime": "LOW_VOLATILITY", "display_name": "Low Volatility",
  "confidence": 0.519,
  "factors": [
    { "name": "Trend", "raw_value": 0.0221, "z_score": 0.371,
      "explanation": "60-day cumulative return is +2.21%, 0.37 standard deviations above zero given recent volatility." },
    { "name": "Volatility", "raw_value": 0.1223, "z_score": -2.149,
      "explanation": "20-day annualized volatility is 12.23%, 2.15 standard deviations below its trailing 252-day average." }
  ],
  "as_of": "2026-11-12", "note": null, "data_source": "DEV_SAMPLE"
}
```
`regime` is one of `TRENDING_UP` / `TRENDING_DOWN` / `SIDEWAYS` /
`HIGH_VOLATILITY` / `LOW_VOLATILITY`, from a transparent, rule-based
classifier -- NOT a trained model, and `confidence` is NOT a
probability (there is no ground-truth regime label to calibrate
against). See `docs/adr/0013-market-regime-detection.md` for the full
method, including why volatility extremes always override trend.
`note` is non-null (and `factors` empty) only when there isn't enough
price history yet to classify, in which case the response defaults to
`SIDEWAYS` with `confidence: 0`.

## Alerts (Phase 27, requires auth -- unlike `/stocks/*` and `/screener`)

### POST /alerts/rules
```json
{ "rule_type": "PRICE_THRESHOLD", "symbol": "RELIANCE", "direction": "ABOVE", "threshold": 2900 }
```
`symbol` is required for stock-scoped types (`PRICE_THRESHOLD`,
`PRICE_PCT_MOVE`, `VOLUME_SPIKE`, `RSI_THRESHOLD`, `SENTIMENT_CHANGE`,
`FIT_RANKING_CHANGE`) and rejected (422) for portfolio-level types
(`PORTFOLIO_VOLATILITY_CHANGE`, `SECTOR_CONCENTRATION_CHANGE`).
`direction` (`ABOVE`/`BELOW`) is required for `PRICE_THRESHOLD` and
`RSI_THRESHOLD` only, and rejected (422) for every other type, whose
`threshold` is a magnitude, not a side. Returns `201` with:
```json
{
  "id": 1, "rule_type": "PRICE_THRESHOLD", "symbol": "RELIANCE", "direction": "ABOVE",
  "threshold": 2900, "enabled": true, "last_value": null,
  "last_evaluated_at": null, "last_fired_at": null, "created_at": "2026-11-11T09:00:00Z"
}
```

### GET /alerts/rules -> list of the above, for the current user only
### PATCH /alerts/rules/{id} `{ "enabled": false }` or `{ "threshold": 3000 }` -> updated rule
### DELETE /alerts/rules/{id} -> 204

### POST /alerts/evaluate
Evaluates every enabled rule the current user owns right now and
returns only the ones that actually fired (usually `[]` -- see ADR 0010
for exactly why most evaluations fire nothing). The same evaluation also
runs automatically roughly every 30 seconds while the backend process is
up (piggybacking on the Phase 24 background loop, no new scheduler).
```json
[{ "id": 10, "rule_id": 1, "rule_type": "PRICE_THRESHOLD", "symbol": "RELIANCE",
   "triggered_at": "2026-11-11T09:30:00Z", "value": 2905.3,
   "message": "RELIANCE crossed above ₹2900.00 (now ₹2905.30)", "is_read": false }]
```
Every event's `message` explains what happened in plain language --
never a bare number.

### GET /alerts/events?unread_only=false&limit=50 -> list of events (same shape), newest first, for the current user's rules only
### POST /alerts/events/{id}/read -> marks it read, returns the updated event

## Paper Trading (Phase 28, requires auth)

A hypothetical account funded with virtual cash (default Rs 10 lakh),
never the real portfolio -- see ADR 0011. Every response below carries a
`disclaimer` field naming it hypothetical.

### GET /paper-trading/account
Creates the account on first call (idempotent). Returns:
```json
{
  "starting_cash": 1000000.0, "cash_balance": 965000.0, "holdings_value": 35500.0,
  "total_value": 1000500.0, "unrealized_pnl": 500.0, "realized_pnl": 0.0,
  "total_pnl": 500.0, "total_return_pct": 0.05,
  "holdings": [
    { "symbol": "TCS", "name": "Tata Consultancy Services", "quantity": 10,
      "avg_buy_price": 3500.0, "current_price": 3550.0, "invested_value": 35000.0,
      "current_value": 35500.0, "unrealized_pnl": 500.0, "unrealized_pnl_pct": 1.43 }
  ],
  "data_source": "DEV_SAMPLE",
  "disclaimer": "This is a hypothetical paper-trading account. No real money, real orders, or brokerage integration is involved -- prices are real (or dev-sample) market data, but every trade here is simulated."
}
```
`total_pnl` is `total_value - starting_cash`, not `unrealized_pnl +
realized_pnl` -- see ADR 0011 for why those two don't always sum to it
(open positions' fees).

### POST /paper-trading/account/reset -> wipes holdings/transactions, restores starting cash, same shape as above

### POST /paper-trading/buy `{ "symbol": "TCS", "quantity": 10 }`
Executes at the current real-or-dev-sample quote; fees use the same
illustrative NSE delivery-trade cost model as the What-If Simulator
(Phase 11). `quantity` must be `> 0` (422 otherwise). Returns `400` if
cash is insufficient (fees included). Returns:
```json
{ "id": 1, "symbol": "TCS", "type": "BUY", "quantity": 10, "price": 3550.0,
  "fees": 12.8, "realized_pnl": null, "executed_at": "2026-11-11T09:00:00Z" }
```

### POST /paper-trading/sell `{ "symbol": "TCS", "quantity": 4 }`
Returns `400` if the quantity held is insufficient. Same shape as above,
with `realized_pnl` populated: `(sell_price - avg_buy_price) * quantity - fees`.

### GET /paper-trading/holdings -> list of the `holdings` entries above, for the current user's account only
### GET /paper-trading/transactions -> list of the above transaction shape, newest first

### GET /paper-trading/performance?days=180
Account total value over time vs. a NIFTY 50 buy-and-hold benchmark with
the same starting cash (see ADR 0011 for the simplifications -- current
holdings assumed constant across the window, same as the real
portfolio's performance series).
```json
{
  "points": [{ "date": "2026-05-15", "value": 1000000.0 }, ...],
  "benchmark_points": [{ "date": "2026-05-15", "value": 1000000.0 }, ...],
  "account_return_pct": 0.05, "benchmark_return_pct": 1.2,
  "data_source": "DEV_SAMPLE",
  "disclaimer": "..."
}
```

## Error shape
FastAPI default: `{ "detail": "message" }` with 401/404/400/503 status codes as appropriate. 503 specifically means the ML model hasn't been trained yet (won't happen against the seeded demo DB).

## Cross-cutting frontend requirements
- Global disclaimer footer/banner: "PortfolioIQ is an educational and analytical decision-support system. Its predictions and portfolio analytics are model-based estimates and are not guaranteed financial advice."
- Every prediction/outlook display must show direction + probability + confidence + disclaimer, never a bare number.
- Any place showing `data_source` should subtly label DEV_SAMPLE data as such (e.g. small badge/tooltip "Development sample data") vs LIVE.
