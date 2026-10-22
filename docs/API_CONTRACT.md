# PortfolioIQ Backend API Contract (v0.1 - MVP)

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
Body: `{ "symbol": "TCS", "quantity": 10, "avg_buy_price": 3200 }` -> Holding (201). Adding an existing symbol merges into a weighted-average position.

### DELETE /portfolio/holdings/{holding_id} -> 204

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
  "weights_used": { "outlook": 0.25, "sentiment": 0.15, "risk_delta": 0.2, "diversification_delta": 0.25, "concentration_delta": 0.15 }
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

## Error shape
FastAPI default: `{ "detail": "message" }` with 401/404/400/503 status codes as appropriate. 503 specifically means the ML model hasn't been trained yet (won't happen against the seeded demo DB).

## Cross-cutting frontend requirements
- Global disclaimer footer/banner: "PortfolioIQ is an educational and analytical decision-support system. Its predictions and portfolio analytics are model-based estimates and are not guaranteed financial advice."
- Every prediction/outlook display must show direction + probability + confidence + disclaimer, never a bare number.
- Any place showing `data_source` should subtly label DEV_SAMPLE data as such (e.g. small badge/tooltip "Development sample data") vs LIVE.
