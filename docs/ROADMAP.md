# PortfolioIQ Roadmap

## Phase 1 (this milestone) -- shipped

Foundation, auth, portfolio management, market data, stock analytics, ML
direction prediction, news + sentiment, portfolio risk analytics, Portfolio
Health Score, Portfolio Weakness Detector, and the Portfolio Fit Engine +
Discover. See `README.md` for what's runnable today.

## Phase 2 -- Geopolitical Intelligence

- **Geopolitical Event Intelligence**: ingest geopolitical/macro news
  distinct from company news, classify relevance to sectors/stocks.
- **Geopolitical Market Impact Engine**: estimate likely sector/stock
  sensitivity to a given event category using historical reaction patterns.
- **Historical Similar Event Matching**: retrieve past events with similar
  characteristics and show how comparable portfolios reacted, as context
  (not prediction).

Planned integration point: a new `app/geopolitics/` service package plus a
`geopolitical_events` table (event, date, category, affected sectors,
affected stocks), surfaced as a new `/global-impact` API + frontend page.
The existing `PortfolioRiskService` and `PortfolioFitService` would gain an
optional geopolitical-adjustment factor without changing their public
interfaces.

## Phase 3 -- Simulation & Explainability

- **What-If Simulator**: let a user hypothetically add/remove/resize a
  holding and see projected impact on health score, risk, and allocation
  before committing -- reuses `PortfolioHealthService`/`PortfolioRiskService`
  against a simulated (not persisted) holdings set.
- **Stress Testing**: replay historical stress scenarios (e.g. a sharp
  sector-wide drawdown) against the current portfolio composition.
- **Explainable AI**: richer SHAP-style feature attribution for ML
  predictions, beyond the current top-3-feature-importance summary.
- **Model Disagreement**: surface when the three candidate models
  (Logistic Regression / Random Forest / XGBoost) disagree on direction, as
  an explicit uncertainty signal.

## Phase 4 -- Backtesting & Evolution

- **Backtesting Lab**: simulate how a portfolio (or a Portfolio-Fit-ranked
  strategy) would have performed historically, with clear "simulation, not
  guarantee" framing throughout.
- **Portfolio Evolution**: track Health Score / risk / allocation drift
  over time using the already-persisted `portfolio_scores` history table.

## Phase 5 -- Alerts & Assistant

- **Alerts**: threshold-based notifications (e.g. concentration crossing a
  limit, a large sentiment shift, a weakness newly triggered).
- **AI Portfolio Assistant**: a conversational layer over the existing
  services (risk, health, fit, discover) for natural-language Q&A about the
  user's own portfolio -- explicitly scoped to explain existing
  analytics, not to give unscoped financial advice.

## Design principle carried through every phase

Every new capability is added as its own service module behind a narrow
interface (mirroring the market-data/sentiment provider pattern already in
place), with its own route(s) and frontend page, so existing functionality
is never rewritten to make room for new functionality.
