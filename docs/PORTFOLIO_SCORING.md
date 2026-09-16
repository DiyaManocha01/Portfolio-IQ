# Portfolio Scoring Methodology

This document is the single source of truth for how PortfolioIQ computes the
**Portfolio Health Score** and its five components, and how the
**Portfolio Weakness Detector** decides what to flag. Every number described
here is computed live from the user's actual holdings and cached market
data -- nothing is hardcoded or randomly generated.

Implementation: `backend/app/portfolio/health_service.py` and
`backend/app/portfolio/weakness_service.py`.

## 1. Inputs

For a portfolio with holdings `h_1..h_n`, each in stock `s_i` with quantity
`q_i` and current price `p_i`:

- Value weight: `w_i = (q_i * p_i) / sum_j(q_j * p_j)`
- Daily return series `r_i` for each stock, from up to 180 days of cached
  OHLCV close prices (`app/services/analytics.py`).
- Portfolio daily return: `R_t = sum_i(w_i * r_i,t)` (current weights applied
  across the whole lookback window -- see Limitations below).

## 2. The five components (each scored 0-100)

### Diversification
`HHI = sum_i(w_i^2)` (Herfindahl-Hirschman Index of position weights).
`effective_n = 1 / HHI` (the "effective number of equally-weighted
positions" your portfolio behaves like).
`score = min(100, effective_n / 10 * 100)` -- a fully-diversified 10-stock
equal-weight portfolio scores 100; a single-stock portfolio scores ~10.

### Concentration
`top_stock_pct = max_i(w_i) * 100`
`top_sector_pct` = the largest single-sector weight, as a percentage.
`score = max(0, 100 - max(top_stock_pct, top_sector_pct))`

### Risk
`annualized_volatility = std(R_t) * sqrt(252)`
`score = max(0, 100 - min(100, annualized_volatility * 100 * 2))`
(A portfolio volatility of 25% or higher drives this component to 50 or
below; the "x2" multiplier is a documented, fixed scaling choice, not a
statistical constant.)

### Correlation
`avg_corr` = the mean of all pairwise Pearson correlations between holding
return series over the lookback window.
`score = 100 * (1 - max(0, avg_corr))`
With fewer than 2 holdings (no pairs to measure), this defaults to a
neutral 70 rather than claiming perfect or zero correlation.

### Drawdown
`max_drawdown` = the largest peak-to-trough decline of the cumulative
portfolio value series over the lookback window (always <= 0).
`score = max(0, 100 - min(100, abs(max_drawdown) * 100 * 2))`

## 3. Overall Health Score

```
Overall Health = (Diversification + Concentration + Risk + Correlation + Drawdown) / 5
```

A simple, transparent, equally-weighted average. All five components and
the overall score are persisted to the `portfolio_scores` table each time
they're computed, so score history can be tracked over time in a later
phase.

## 4. Portfolio Weakness Detector

The weakness detector (`weakness_service.py`) re-uses the exact same risk
metrics above and applies fixed, documented thresholds -- it never
duplicates or re-derives its own numbers:

| Rule | Medium threshold | High threshold |
|---|---|---|
| Single-stock concentration | weight >= 30% | weight >= 50% |
| Sector concentration | sector weight >= 40% | sector weight >= 55% |
| Portfolio volatility | annualized vol >= 25% | annualized vol >= 35% |
| Holding correlation | avg pairwise corr >= 0.60 | avg pairwise corr >= 0.75 |
| Drawdown | max drawdown <= -20% | max drawdown <= -30% |
| Low diversification | fewer than 4 holdings (flat MEDIUM severity) | -- |

Each triggered weakness carries a human-readable explanation and the exact
supporting metric value, so nothing is a black-box warning.

## 5. Documented limitations (MVP scope)

- **Static weights over the lookback window**: portfolio-level returns use
  *current* holding weights applied across the whole historical window,
  rather than re-basing weights transaction-by-transaction. This is
  standard for a fast "as-if-I-held-this-today" view but is not a full
  historical performance reconstruction.
- **Correlation/volatility come from synthetic development data** by
  default in this environment (see `docs/ARCHITECTURE.md` for the market
  data provider abstraction) -- the math is real, the inputs are
  clearly-labeled sample data unless a live provider is configured.
- **Risk-free rate** for the Sharpe ratio is a fixed 6% annual assumption
  (approximate Indian T-bill yield), not fetched live.
