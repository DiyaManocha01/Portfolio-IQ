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
  "important_features": ["Recent price momentum", "RSI (relative strength)", "Trading volume"],
  "disclaimer": "This is a model-generated estimate, not financial advice or a guaranteed outcome."
}
```
ALWAYS render the disclaimer text and use "Potentially Positive/Negative" style language in the UI, never "will go up".

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

### GET /discover?limit=20 -> list, already sorted by portfolio_fit descending
```json
[{ "symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries", "sector": "Healthcare",
   "current_price": 1831.68, "ml_outlook": "NEUTRAL", "prediction_probability": 0.494,
   "volatility": 0.2012, "portfolio_fit": 75.6, "correlation_with_portfolio": 0.259,
   "diversification_benefit": "High" | "Moderate" | "Low" }]
```
Page title MUST be "Stocks That May Fit Your Portfolio" -- never "Best Stocks" / "Stocks You Should Buy".

### GET /portfolio-fit/{symbol}
```json
{
  "symbol": "LT", "name": "Larsen & Toubro", "fit_score": 48.6,
  "factors": [
    { "name": "Prediction", "contribution": 12.9, "explanation": "Model outlook is neutral with 52% estimated probability (low confidence)." },
    { "name": "Correlation", "contribution": 11.9, "explanation": "Average historical correlation with current holdings is 0.41." },
    { "name": "Risk", "contribution": 8.4, "explanation": "Standalone annualized volatility of 29.2%." },
    { "name": "Sector Balance", "contribution": 8.3, "explanation": "..." },
    { "name": "User Preference", "contribution": 7.1, "explanation": "..." },
    { "name": "Diversification", "contribution": 0.0, "explanation": "..." }
  ],
  "strengths": ["..."], "concerns": ["..."],
  "weights_used": { "prediction": 0.25, "risk": 0.15, "diversification": 0.2, "correlation": 0.2, "sector_balance": 0.1, "user_preference": 0.1 }
}
```
`factors` is sorted by contribution descending -- render as a bar/waterfall breakdown plus the strengths/concerns lists. This screen is the single most important screen in the whole demo.

---

## Error shape
FastAPI default: `{ "detail": "message" }` with 401/404/400/503 status codes as appropriate. 503 specifically means the ML model hasn't been trained yet (won't happen against the seeded demo DB).

## Cross-cutting frontend requirements
- Global disclaimer footer/banner: "PortfolioIQ is an educational and analytical decision-support system. Its predictions and portfolio analytics are model-based estimates and are not guaranteed financial advice."
- Every prediction/outlook display must show direction + probability + confidence + disclaimer, never a bare number.
- Any place showing `data_source` should subtly label DEV_SAMPLE data as such (e.g. small badge/tooltip "Development sample data") vs LIVE.
