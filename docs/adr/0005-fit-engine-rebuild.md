# ADR 0005: Rebuild the Portfolio Fit Engine (Phase 10)

**Status:** Accepted
**Date:** 2026-10-21

## Context

The Phase 1-3 MVP `app/portfolio/fit_service.py` computed six independent
0-100 component scores (prediction, risk, diversification, correlation,
sector_balance, user_preference) using hand-tuned clamp formulas (e.g.
`100 - stock_vol * 100 * 1.5`), combined with a fixed weighted sum. It had
no sentiment term at all, despite Phase 7 having built a working sentiment
pipeline. ADR 0001 flagged this service as scheduled for supersession once
Phase 10 was implemented, specifically to match the project's rigorous
formula specification:

```
Fit = w1*Outlook + w2*Sentiment - w3*dRisk + w4*dDiversification - w5*dConcentration
```

This is a materially different structure, not a tuning pass: (1) sentiment
finally enters the score, and (2) risk/diversification/concentration
become **deltas** -- what happens to the *portfolio* if this stock is
added -- rather than standalone descriptors of the stock in isolation.

## Decision

1. **A new shared module, `app/portfolio/hypothetical.py`**, simulates
   adding a candidate stock to the portfolio at a modest target weight
   (10% by default, with existing holdings scaled down proportionally),
   and recomputes annualized volatility, diversification ratio, and
   holdings HHI using the exact same Ledoit-Wolf covariance machinery as
   Phase 8 (`risk_service.py`'s `shrunk_covariance`, `diversification_ratio`,
   `hhi`). Deliberately built as a minimal slice of what Phase 11's
   What-If Simulator becomes, so the portfolio-reweighting math is written
   once.
2. **`current_metrics()` and `hypothetical_metrics_after_adding()` use
   identical methodology** (the same covariance-quadratic-form
   calculation) so that a delta term compares two numbers computed the
   same way. An earlier draft of this phase computed "current" from
   `PortfolioRiskService`'s realized-historical-return-series volatility
   and "hypothetical" from the covariance model -- caught and fixed before
   this ADR was written, since comparing two different estimators and
   calling the difference a "delta" would have been exactly the kind of
   silently-wrong number the project's working rules forbid.
3. **Each raw term is z-scored** against the distribution of that term
   across a batch of stocks (the full universe for the single-stock
   endpoint, the actual candidate set for `/discover`), replacing the old
   per-component hand-tuned clamps with one statistically principled
   standardization.
4. **The weighted z-score sum ("logit") is squashed through a logistic
   sigmoid** to a 0-100 display score -- one monotonic transform applied
   once, instead of six separate ad hoc formulas.
5. **Presets**: `balanced` (default), `risk_averse`, `growth_seeking` --
   selectable via `?preset=` on `/portfolio-fit/{symbol}`, defaulting to a
   mapping from the user's stated risk tolerance
   (`default_preset_for()`). Each preset's weights sum to 1.0.
6. **Correlation becomes a reported diagnostic, not a scoring input.**
   `/discover`'s `correlation_with_portfolio` field is preserved (computed
   the same simple-average way as before) for UI continuity, but it no
   longer feeds the Fit score directly -- the portfolio-level
   diversification/risk deltas now account for correlation properly
   through the covariance matrix, which is more rigorous than a naive
   pairwise average correlation ever was.

## Consequences

- **Per-factor "contribution" values are in pre-sigmoid (logit) units.**
  They sum exactly to the sigmoid's input, NOT linearly to the displayed
  0-100 `fit_score`, since that final transform is nonlinear. This is
  documented in the module docstring, `docs/methodology.md` Section 7, and
  `docs/limitations.md` -- stating otherwise would misrepresent what the
  number means.
- **The same stock's `fit_score` can differ between `/portfolio-fit/{symbol}`
  and `/discover`** for the same portfolio, because they z-score against
  different populations (full universe vs. the unheld-candidate batch).
  This is intentional (a z-score is only meaningful relative to a defined
  population) but must be documented, not discovered as a "bug" later.
- **An already-held stock's risk/diversification/concentration deltas are
  exactly 0** (by construction in `hypothetical.py`), which is a cleaner
  emergent behavior than the old service's explicit `if already_held:
  return 0.0` special case in the diversification component -- it falls
  out of the simulation itself rather than needing a carve-out.
- `PortfolioFitOut`/`PortfolioFitFactor` schemas grow fields additively
  (`preset`, `raw_value`, `z_score`) -- no field removed, so existing
  frontend consumers of `fit_score`/`factors`/`strengths`/`concerns` are
  unaffected, though the UI does not yet surface the new fields (deferred
  to Phase 20).
- `docs/PORTFOLIO_SCORING.md` turns out to only ever have covered the
  Health Score and Weakness Detector, not the Fit Engine -- verified
  before writing this ADR rather than assumed. No pointer note was needed
  there; `docs/methodology.md` Section 7 is simply the first place the
  Fit Engine's methodology has been documented.
- No schema/Alembic migration -- pure computation over existing data.

## Alternatives considered

- **Min-max normalization instead of z-scoring.** Rejected: min-max is
  sensitive to a single outlier stock stretching the whole scale, and the
  roadmap explicitly specified a z-scored formula.
- **Keeping correlation as a direct scoring input alongside the new delta
  terms** (a 6-term formula). Rejected as redundant: the portfolio-level
  dRisk/dDiversification terms already incorporate pairwise correlation
  through the covariance matrix; adding a separate naive correlation term
  on top would double-count the same underlying effect through two
  different (and differently rigorous) estimators.
