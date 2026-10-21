# ADR 0004: Rebuild Portfolio Risk Analytics (Phase 8)

**Status:** Accepted
**Date:** 2026-10-21

## Context

The Phase 1-3 MVP `app/portfolio/risk_service.py` computed annualized
volatility, Sharpe ratio, max drawdown, correlation matrix, and raw
sector/stock percentage breakdowns using a plain sample covariance matrix
for risk-contribution attribution. ADR 0001 flagged this as scheduled for
supersession once Phase 8 was implemented. Two concrete gaps motivated the
rebuild:

1. The sample covariance matrix is known to be poorly conditioned when the
   number of holdings is comparable to the lookback window length -- a
   realistic regime for this app's typical portfolio sizes (5-15 holdings)
   against a 180-day window.
2. "Risk" was only reported as volatility and correlation. There was no
   tail-risk measure (what happens on a genuinely bad day) and no formal
   concentration/diversification scalar -- just a sorted list of
   percentages a reader has to eyeball.

## Decision

Rewrote `app/portfolio/risk_service.py`, adding (all in
`docs/methodology.md` Section 5):

1. **Ledoit-Wolf shrinkage covariance** (`sklearn.covariance.LedoitWolf`,
   already a dependency -- no new package) replaces the raw sample
   covariance for the risk-contribution calculation. The estimator's
   chosen shrinkage intensity is returned in the API response
   (`shrinkage_intensity`, `covariance_method`) rather than hidden --
   `covariance_method` falls back to `"sample"` when there are fewer than
   2 holdings or fewer observations than holdings, since shrinkage is
   degenerate in that regime.
2. **Historical-simulation VaR and CVaR** at 95% and 99% confidence on the
   realized portfolio daily-return series. Deliberately historical, not
   parametric (no normality assumption), consistent with this project's
   "never invent a number you can't trace to code" rule -- it's a direct
   empirical quantile/tail-mean of the actual observed returns.
3. **HHI (Herfindahl-Hirschman Index)** for both holding weights and sector
   weights, replacing "a list of percentages" with an actual scalar
   concentration score.
4. **Effective number of bets** = `1 / HHI(weights)`. Documented explicitly
   as the *weight-concentration* definition, not the PCA/eigenvalue-based
   "effective independent bets" that accounts for correlation between
   holdings -- conflating the two would misrepresent what's being measured.
5. **Diversification ratio** (Choueifaty & Coignard): weighted-average
   standalone volatility over portfolio volatility.

All five new pure functions (`hhi`, `effective_number_of_bets`,
`historical_var_cvar`, `diversification_ratio`, `shrunk_covariance`) are
module-level and independently unit-tested against hand-worked values in
`app/tests/test_portfolio_risk.py`, separate from the DB-backed integration
test.

The existing internal dict keys (`_weights`, `_returns_df`,
`_portfolio_variance`) that `health_service.py` and `weakness_service.py`
depend on are unchanged -- this is a strict additive extension of the
`compute()` return value, not a breaking change to its consumers.

## Consequences

- `docs/limitations.md` gains entries: shrinkage intensity is
  auto-selected per computation (not a fixed/tuned constant), VaR/CVaR are
  historical-simulation (sensitive to the lookback window and assume the
  recent past is representative), and the effective-number-of-bets vs.
  PCA-based-effective-bets distinction.
- `GET /portfolio/risk` response grows nine new fields; `docs/API_CONTRACT.md`
  updated. This is additive (no field removed/renamed), so existing
  frontend consumers of the old fields are unaffected, though the frontend
  does not yet render the new ones (deferred to Phase 20, UI polish).
- No schema/Alembic migration -- this phase is pure computation over
  existing cached OHLCV data, no new persisted columns.

## Alternatives considered

- **A PCA/eigenvalue-based "effective number of independent bets"**
  (Meucci-style) instead of or alongside the weight-concentration version.
  Deferred: it requires decomposing the (now shrunk) covariance matrix's
  eigenspectrum and a principled cutoff for "how much variance explained
  counts as one bet" -- a real methodological choice worth its own
  dedicated treatment rather than bolting on under this phase's scope.
- **Parametric (variance-covariance) VaR** instead of historical
  simulation. Rejected: it would assume normally-distributed returns,
  which is both a stronger assumption than the data supports and harder to
  defend in a paper/IP write-up than "this is literally the empirical
  quantile of what happened."
