# PortfolioIQ Roadmap

History of what was built, phase by phase, and what's still genuinely
out of scope. Each shipped phase has a full write-up in
`docs/methodology.md` (the formulas) and `docs/limitations.md` (the
caveats) — this file is the index, not the detail.

## Shipped (Phases 1-22)

| Phase | What shipped |
|---|---|
| 1-3 | Foundation: auth, portfolio management, market data provider abstraction, stock analytics, first-cut ML prediction, news + sentiment, Portfolio Health Score, Weakness Detector |
| 4 | Alembic migrations (replacing `create_all`), NIFTY 100 symbol list + Parquet cache, data validation |
| 5 | Full stock analysis time series (returns, volatility, drawdown, MA/RSI/MACD, beta vs. NIFTY 50) |
| 6 | ML pipeline rebuild: purged walk-forward CV, baselines, probability calibration (ADR 0003) |
| 7 | Real news ingestion (RSS), FinBERT evaluation protocol, time-decayed sentiment aggregation |
| 8 | Portfolio risk rebuild: Ledoit-Wolf covariance, VaR/CVaR, HHI, diversification ratio (ADR 0004) |
| 9 | Portfolio Optimization: min-variance / max-Sharpe / Hierarchical Risk Parity via PyPortfolioOpt |
| 10 | Portfolio Fit Engine rebuild: z-scored, weighted, logistic-sigmoid scoring (ADR 0005) — the core USP |
| 11 | What-If Simulator: arbitrary hypothetical rebalancing + Indian transaction-cost estimates |
| 12 | Personalized Discovery: sector-exclusion preferences |
| 13 | Backtesting: purged walk-forward backtest, Deflated Sharpe Ratio, paired bootstrap, feature ablation |
| 14 | Risk Attribution: % money vs. % risk per holding, exact Euler's-theorem decomposition |
| 15 | Stress / Scenario Testing: CAPM beta-scaled shocks, historical presets, regex scenario parser |
| 16 | Counterfactual Fit Explanations: exact "why A > B" decomposition + ceteris-paribus "what would help" |
| 17 | Per-Prediction SHAP Explanations (ADR 0006) — supersedes Phase 6's static feature ranking |
| 18 | Verified Public Track Record: hash-chained, DB-trigger-enforced append-only prediction ledger (ADR 0007) |
| 19 | AI Portfolio Assistant: retrieval-and-cite only, system-prompt + regex guardrail |
| 20 | Frontend UI for Phases 9/11/14/16 (Risk Attribution, Portfolio Lab, Fit compare/counterfactual) |
| 21 | Testing & Security: Vitest frontend tests, dependency audit (42 findings -> 1), auth/assistant rate limiting |
| 22 | Deployment: Docker Compose for the full stack |

## Genuinely out of scope (not started)

These were sketched early in the project's planning but never began
implementation — listed here so they're not mistaken for "in progress"
or silently forgotten:

- **Geopolitical Event Intelligence**: ingesting geopolitical/macro news
  distinct from company news, classifying relevance to sectors/stocks,
  and estimating likely sector/stock sensitivity to an event category
  using historical reaction patterns. Would need a new `app/geopolitics/`
  service, a `geopolitical_events` table, and an optional adjustment
  factor plugged into the existing `PortfolioRiskService`/`PortfolioFitService`
  interfaces without changing their public contracts — the same
  provider-abstraction pattern every other phase has used.
- **Alerts**: threshold-based notifications (e.g. concentration crossing
  a limit, a large sentiment shift, a weakness newly triggered). Would
  need a scheduled job runner, which this project doesn't have yet — the
  closest existing piece is the prediction ledger's lazy (request-
  triggered) resolution, not a true background scheduler.
- **Multi-turn assistant memory**: the Phase 19 assistant treats every
  `/assistant/ask` call independently; no conversation state is carried
  between questions.
- **Portfolio Evolution tracking**: trending Health Score / risk /
  allocation drift over time. The `portfolio_scores` history table has
  existed since Phase 1 for this purpose but nothing writes to it yet or
  exposes a time-series endpoint over it.
- **Live data execution**: every live-data path (`LiveYFinanceProvider`,
  real FinBERT, real RSS ingestion) is fully implemented and tested up to
  the network boundary, but has never actually been run against the real
  internet in this project's development sandbox (verified blocked, not
  just untried) — see `docs/limitations.md`'s "Environment / network"
  section. Running it for real, re-measuring every DEV_SAMPLE-labeled
  number in `methodology.md` against real NIFTY data, and re-verifying
  the NIFTY 100 symbol list against an official source are the single
  highest-value things left to do before any result here is cited in a
  paper or IP filing.

## Design principle carried through every phase

Every new capability was added as its own service module behind a narrow
interface, with its own route(s) and, where applicable, frontend page —
existing functionality was never rewritten to make room for new
functionality, except where a phase explicitly superseded earlier
behavior and recorded why in an ADR (`docs/adr/`).
