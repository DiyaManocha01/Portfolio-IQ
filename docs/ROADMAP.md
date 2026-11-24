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

## Real-Data Upgrade (started 2026-11-24)

A distinct initiative from the numbered phases above: upgrading toward a
real, Indian-market-data-driven platform (additional live-data provider,
richer real-time fields, corporate events, per-endpoint rate limiting,
etc.), requested and lettered Phase A/B/... to avoid colliding with the
numbered phases 1-34 already shipped (see `README.md`'s "What's
implemented" for 23-34, which predate this file's last table update).

| Phase | What shipped |
|---|---|
| A | Full repository audit against the upgrade brief -- `docs/gap-analysis-realtime-upgrade.md`. Found the real-time pipeline, provider abstraction, fundamentals, alerts, and AI assistant architecture already satisfy most of the brief; confirmed a fresh 429/71 passing-test baseline; confirmed this sandbox (like the original dev sandbox) cannot reach `upstox.com`, `nseindia.com`, `bseindia.com`, or `zerodha.com` -- no code changed. |
| B | Fixed a real bug found during Phase A: `average_traded_price` (present on Angel One's wire format) was parsed and then silently dropped before reaching `NormalizedTick`; now wired through. Added `vwap`/`bid_qty`/`ask_qty`/`data_received_at` fields to `NormalizedTick`/`TickOut`, honestly `None` where Angel One's Quote-mode feed structurally can't supply them (documented in `docs/limitations.md`, not silently missing). Upstox integration and the NSE holiday calendar are both deferred -- neither can be done from any sandbox session (DNS-blocked), and the project owner chose to keep Angel One primary for now rather than have an unverified broker adapter built from training-data recollection of Upstox's protobuf feed. |
| C | Historical data pipeline: interval resampling (`candle_resample.py`, 1m->5m/15m/30m/1h) and missing-candle (gap) detection over stored `intraday_candles`, both pure/tested functions wired into `GET /market/candles/{symbol}`; an `adjusted: bool` field added to stock-history endpoints (`LiveYFinanceProvider`=True via real `auto_adjust`, `DevSampleProvider`=True vacuously -- no corporate actions exist in synthetic data to misalign). Historical intraday backfill from a broker's own REST API was scoped but deliberately deferred (more unverified Angel One wire-format code, judged lower-value than what shipped) -- see `docs/limitations.md`. |
| D | Real-time portfolio recalculation: added "today's P&L" (`day_pnl`/`day_pnl_pct`), confirmed genuinely absent anywhere in the codebase during the Phase A audit -- `quantity * (current_price - previous_close)` per holding, summed (not re-derived) for the portfolio total. Wired into `GET /portfolio`, `GET /portfolio/summary`, the dashboard's stat row, `HoldingsTable`, and the AI assistant's `portfolio_summary` context block (same underlying `portfolio_calc` functions, so all four stay consistent by construction, not by separately keeping them in sync). |

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
