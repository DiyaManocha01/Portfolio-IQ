# PortfolioIQ Architecture

## Overview

PortfolioIQ is a full-stack AI portfolio intelligence platform, built
across 22 phases (see `ROADMAP.md`). This document describes the
architecture as it stands after Phase 22 (Docker Compose deployment).

```
frontend (React + TS + Tailwind)
        |  Axios (JWT bearer auth)
        v
FastAPI app (app/main.py)
        |  slowapi rate limiting (auth, assistant endpoints)
        v
API routes (app/api/routes/*) -- thin, no business logic
        |
        v
Services (app/services, app/portfolio, app/ml, app/nlp, app/assistant) -- all business logic
        |
        v
SQLAlchemy models (app/models) <-> PostgreSQL (Alembic-managed)
        |
        v
Provider abstractions (market data, sentiment) -- swappable live/dev-sample
```

Deployed as three Docker Compose services (`db` / `backend` / `frontend`)
— see `DEPLOYMENT.md` — or run manually per `README.md`.

## Backend layout

```
backend/
  app/
    api/
      deps.py              # auth deps (get_current_user, get_current_portfolio)
      routes/               # auth, portfolio, stocks, discover, portfolio_fit, ledger, assistant, market
    models/                 # SQLAlchemy ORM models (14 tables, see below)
    schemas/                # Pydantic request/response models
    services/
      security.py           # password hashing + JWT (PyJWT, Phase 21)
      rate_limit.py          # shared slowapi Limiter (Phase 21)
      analytics.py           # stock analytics (SMA/EMA/RSI/MACD/volatility/beta)
      portfolio_calc.py      # holding P&L + portfolio aggregation + performance series
      news_service.py        # news generation + sentiment orchestration
      screener_service.py    # fundamental + technical stock screener (Phase 26)
      alert_service.py       # alert rule evaluation dispatcher + dedup (Phase 27)
      market_regime_service.py  # rule-based trend/volatility regime classifier (Phase 30)
      market_data/
        providers.py         # MarketDataProvider abstraction (DevSample + LiveYFinance)
        service.py            # MarketDataService: caching layer over a provider
        cache.py               # Parquet cache + OHLCV validation (Phase 4)
        nifty100.py             # symbol universe
        watchlist.py             # Phase 24 real-time watchlist (20 NSE symbols)
        session_calendar.py       # NSE trading-hours/holiday status (Phase 24)
        tick_normalizer.py         # provider dict -> NormalizedTick + TickStatus (Phase 24)
        live_cache.py                # in-process latest-tick-per-symbol cache (Phase 24)
        instrument_registry.py        # symbol -> broker instrument token resolution (Phase 24)
        angelone_auth.py                # Angel One REST login/refresh (Phase 24)
        angelone_ws_client.py            # Angel One WS 2.0 wire protocol (Phase 24)
        ws_connection_manager.py           # owns the one upstream broker connection (Phase 24)
        fixture_replay_provider.py          # FIXTURE-tagged cache fill with no broker feed (Phase 24)
        snapshot_service.py                  # periodic live_cache -> intraday_candles (Phase 24)
      news/
        rss_feeds.py           # Economic Times / Moneycontrol feed list (Phase 7)
        matching.py             # headline-to-stock regex matching
        cache.py                 # JSON headline cache
    ml/
      features.py             # feature engineering + purged walk-forward CV (Phase 6)
      train.py                 # trains + selects LogReg/RandomForest/XGBoost, saves SHAP background
      predict.py               # loads trained model, produces direction/probability/confidence + SHAP
      shap_explain.py          # fast model-specific SHAP explainers (Phase 17)
      backtest.py               # purged walk-forward backtest, DSR, bootstrap, ablation (Phase 13)
      prediction_ledger.py      # hash-chained append-only ledger logic (Phase 18)
    nlp/
      lexicon_sentiment.py    # default sentiment provider (no external deps)
      finbert_sentiment.py     # real FinBERT provider (opt-in, needs internet + transformers/torch)
      sentiment_service.py      # selects provider based on settings.USE_FINBERT
    portfolio/
      risk_service.py         # volatility, Sharpe, drawdown, Ledoit-Wolf covariance, VaR/CVaR, HHI (Phase 8)
      health_service.py        # Portfolio Health Score (docs/PORTFOLIO_SCORING.md)
      weakness_service.py       # rule-based weakness detection
      fit_service.py             # Portfolio Fit Engine (the core USP, Phase 10)
      hypothetical.py             # shared "what if added at X% weight" helper (Phase 10)
      discover_service.py          # ranks candidates by fit for /discover (+ preferences, Phase 12)
      optimization_service.py       # min-variance/max-Sharpe/HRP via PyPortfolioOpt (Phase 9)
      whatif_service.py              # What-If Simulator, arbitrary rebalancing (Phase 11)
      risk_attribution_service.py     # % money vs. % risk per holding (Phase 14)
      stress_test_service.py           # CAPM beta-scaled shock simulation (Phase 15)
      scenario_parser.py                # regex scenario-text -> structured shock params (Phase 15)
      fit_counterfactual_service.py      # "why A > B" / "what would improve this" (Phase 16)
      paper_trading_service.py            # hypothetical account: buy/sell, valuation, performance (Phase 28)
      fit_snapshot_service.py              # caches a Fit result, explains why it moved (Phase 29)
    assistant/
      context_builder.py       # deterministic keyword-based data router (Phase 19)
      assistant_service.py      # system prompt, Claude API call, guardrail filter (Phase 19)
    data/
      seed.py                 # dev seed script: stocks, market data, news, demo user, trains ML
      models/                  # trained model artifacts (joblib) + metadata.json, gitignored
    tests/                    # pytest suite, 378 tests
  Dockerfile                  # multi-stage build (Phase 22)
  docker-entrypoint.sh         # migrate -> seed/train (once) -> uvicorn (Phase 22)
```

## Database schema (20 tables)

`users` -> `user_profiles` (1:1), `users` -> `portfolios` (1:many) ->
`holdings` / `transactions` / `portfolio_scores`. `holdings`/`transactions`
reference `stocks`, which own `market_data`, `financial_metrics`,
`predictions`, `intraday_candles` (Phase 24), and (optionally) `news` ->
`news_sentiment` (1:1). `predictions` feed `prediction_ledger` (Phase 18,
append-only, DB-trigger-enforced — see `methodology.md` Section 15), which
stands somewhat apart from the rest: it is intentionally written once and
never updated. `intraday_candles` is a separate table from `market_data`
(unique on `(stock_id, timestamp)` rather than `market_data`'s
`(stock_id, date)`) — see ADR 0008 for why it isn't a widened
`market_data`. `users` -> `alert_rules` (1:many, Phase 27) -> `alert_events`
(1:many) -- one generic rule table covering all 8 alert types via a
`rule_type` enum rather than eight near-identical tables, see ADR 0010.
`users` -> `paper_accounts` (1:1, Phase 28) -> `paper_holdings` /
`paper_transactions` -- wholly separate from `portfolios`/`holdings`/
`transactions`, never joined to or mutating them, see ADR 0011.
`fit_score_snapshots` (Phase 29) is an append-only cache of Fit Engine
results keyed by `(portfolio_id, stock_id, preset)`, written once per
recompute and never updated -- this is what lets a later request
explain how a score changed, not just what it is now. See ADR 0012.

See `backend/app/models/*.py` for exact columns; relationships use
SQLAlchemy 2.0 typed `Mapped[...]` declarations with cascading deletes.
Schema changes go through Alembic (`backend/alembic/`) as of Phase 4 —
`Base.metadata.create_all()` is no longer used anywhere.

## API routes (12 route modules)

| Module | Mounted at | Auth | Notes |
|---|---|---|---|
| `auth.py` | `/auth` | mixed | register/login rate-limited (Phase 21) |
| `portfolio.py` | `/portfolio` | required | holdings, risk, health, optimize, what-if, stress-test, risk-attribution |
| `stocks.py` | `/stocks` | **none** | quote, history, analysis, prediction (+SHAP), news, sentiment, fundamentals (Phase 26) -- not user-scoped data, so never required `get_current_user`; this table previously (incorrectly) said "required" here, corrected in Phase 26, see ADR 0009 |
| `discover.py` | `/discover` | required | personalized candidate ranking (via `get_current_portfolio`, which itself requires auth) |
| `portfolio_fit.py` | `/portfolio-fit` | required | fit breakdown, compare, counterfactual (same `get_current_portfolio` path) |
| `ledger.py` | `/ledger` | **none** | the one deliberately public surface (Phase 18) |
| `assistant.py` | `/assistant` | required | rate-limited (Phase 21) |
| `market.py` | `/market`, `/ws/market` | required (JWT as `?token=` on the WS) | status poll, intraday candles, push feed (Phase 24/25) |
| `screener.py` | `/screener` | **none** | fundamental + technical stock screener (Phase 26) |
| `alerts.py` | `/alerts` | required | configurable alert rules + triggered events, user-scoped (Phase 27) |
| `paper_trading.py` | `/paper-trading` | required | hypothetical account: buy/sell, holdings, transactions, performance (Phase 28) |

Full request/response shapes: `API_CONTRACT.md`.

## Provider abstraction (the key extensibility pattern)

Two subsystems follow the same pattern, so a real external integration
can be dropped in without touching calling code:

1. **Market data** (`app/services/market_data/providers.py`):
   `MarketDataProvider` is an ABC with `get_history`/`get_quote`/
   `get_fundamentals` (Phase 26). `DevSampleProvider` (default) generates
   deterministic, seeded synthetic OHLCV and fundamentals data with a
   shared market factor for realistic cross-stock correlation, tagged
   `DataSource.DEV_SAMPLE`. `LiveYFinanceProvider` is a real implementation
   behind the same interface, tagged `DataSource.LIVE`, enabled via
   `USE_LIVE_MARKET_DATA=true`, reading local caches
   (`app/services/market_data/cache.py`: Parquet for OHLCV, JSON for
   fundamentals) populated by `scripts/fetch_nifty100.py` /
   `scripts/fetch_fundamentals.py` run locally. ROCE has no yfinance
   equivalent and is always null from the live provider -- see ADR 0009.
2. **Sentiment** (`app/nlp/`): `SentimentService` selects between
   `lexicon_sentiment` (default, zero external dependencies) and
   `finbert_sentiment` (a real `transformers` pipeline against
   `ProsusAI/finbert`, enabled via `USE_FINBERT=true`).

Every response that depends on one of these carries a `data_source` /
`model_used` field so the frontend can label it honestly.

## Real-time market data (Phase 24)

A third, push-based path alongside the two pull-based providers above:

```
ws_connection_manager.py  (asyncio bg task, the ONE upstream Angel One
                            connection; reconnect/backoff/heartbeat/dedup)
        -> tick_normalizer.py (provider dict -> NormalizedTick + TickStatus)
        -> live_cache.py (in-process, lock-guarded, latest tick/symbol)
                -> GET /market/status (REST poll)
                -> WS  /ws/market (per-client push loop, ~1s)
                -> snapshot_service.py -> intraday_candles (periodic, market hours only)

fixture_replay_provider.py writes the SAME live_cache (tagged FIXTURE)
whenever the real feed isn't connected -- this is the default (
ENABLE_REALTIME_FEED=false), so /market/status and /ws/market work with
zero broker setup, always honestly labeled.
```

`instrument_registry.py` resolves the Phase 24 watchlist
(`app/services/market_data/watchlist.py`, 20 NSE symbols) against Angel
One's official scrip master, fetched locally via
`scripts/fetch_angelone_instruments.py` (never fabricates a token for an
unresolved symbol). Full rationale, provider comparison, and
verified-vs-not status: `docs/adr/0008-realtime-market-data-angelone.md`.

## Market Regime Detection (Phase 30)

`GET /market/regime` (no auth, no new table) classifies the current
regime -- TRENDING_UP, TRENDING_DOWN, SIDEWAYS, HIGH_VOLATILITY, or
LOW_VOLATILITY -- for the NIFTY 50 benchmark by default, or any stock
symbol. `app/services/market_regime_service.py` is a transparent,
rule-based classifier (deterministic thresholds on a trend z-statistic
and a volatility z-score), not a trained model -- there is no
ground-truth regime label to train or validate against. Confidence is
a bounded (0-1), non-probabilistic measure of distance from the
decision threshold, and every factor used is returned with its own
plain-language explanation. Full design rationale (including a caught
bug -- the trend feature's first draft was self-referentially z-scored
and so misclassified a textbook sustained uptrend as sideways) and the
"defensible evaluation without ground-truth labels" approach:
`docs/adr/0013-market-regime-detection.md`.

## ML pipeline

`app/ml/train.py` pools OHLCV-derived features across all seeded stocks,
splits via **purged walk-forward cross-validation** (5 folds, 1-day
embargo — not a single shuffled split; see `methodology.md` Section 3.3),
trains Logistic Regression, Random Forest, and XGBoost, and selects the
model with the best mean validation ROC-AUC. The selected model is
calibrated (`CalibratedClassifierCV`, sigmoid), re-evaluated once on the
final fold's held-out test split, and persisted to `model_metadata.json`
alongside the model artifact and a SHAP background sample — the API never
fabricates an accuracy number. `app/ml/predict.py` loads that model,
derives direction/confidence from the calibrated probability, and attaches
a per-prediction SHAP explanation (`app/ml/shap_explain.py`, Phase 17) that
falls back gracefully to Phase 6's static feature ranking if unavailable.
Every genuinely new (stock, model, day) prediction is appended to the
hash-chained `prediction_ledger` (Phase 18).

## Portfolio Fit Engine

The core USP (`app/portfolio/fit_service.py`) answers "how well does this
stock fit MY portfolio", not "is this a good stock". It combines five
z-scored, weighted terms (ML outlook, news sentiment, risk delta,
diversification delta, concentration delta) into a logistic-sigmoid
0-100 score, and returns every term's exact pre-sigmoid contribution plus
generated strengths/concerns text — never a bare number. Because the
underlying logit is additive, Phase 16 makes two further explanations
exactly computable (not approximated): why one candidate outranks
another, and what a single term would need to become to close a gap to a
target. Full formula: `methodology.md` Section 7.

Phase 29 wraps the single-stock path (`compute_fit`) in
`fit_snapshot_service.py`: a result is cached against a fingerprint of
everything it actually depends on (latest price date, model version,
sentiment score, portfolio composition), so a request with nothing
relevant changed is served from `fit_score_snapshots` instead of
recomputed, and a genuine change comes back with a plain-language
explanation of which factor moved the most. This is wired into
`GET /portfolio-fit/{symbol}` (additive `change`/`cached` fields) and,
more importantly, into the `FIT_RANKING_CHANGE` alert evaluator (Phase
27), which previously recomputed the full pipeline on every ~30s
background tick regardless of whether anything had changed. `/discover`'s
batch ranking is deliberately left uncached -- see ADR 0012.

## Frontend layout

```
frontend/src/
  components/   # shared UI pieces (cards, badges, tables, nav;
                 #   RegimeCard, Phase 30 -- used on both Market and StockDetail)
  pages/         # one file per route:
                 #   Dashboard, Portfolio, Market (Phase 25; + regime card, Phase 30), Stocks,
                 #   StockDetail (+ live price/intraday chart, Phase 25;
                 #   + Fundamentals tab, Phase 26; + regime card, Phase 30), Screener (Phase 26),
                 #   Alerts (rule builder + triggered-event feed, Phase 27),
                 #   PaperTrading (hypothetical buy/sell + performance, Phase 28),
                 #   Discover, Intelligence (risk + risk attribution),
                 #   PortfolioFit (+ compare/counterfactual, Phase 20),
                 #   PortfolioLab (What-If + Optimization tabs, Phase 20)
  layouts/       # app shell (sidebar + top nav + protected-route wrapper)
  services/      # axios client + one module per API resource
  hooks/         # data-fetching hooks: useAsync (fetch-once), useMarketFeed
                 #   (Phase 25 -- persistent WebSocket with reconnect/backoff,
                 #   the one hook that does NOT follow useAsync's fetch-once
                 #   model, since /ws/market is a push feed, not a request)
  types/         # TypeScript interfaces mirroring API_CONTRACT.md
  charts/        # Recharts wrapper components (incl. IntradayChart, Phase 25;
                 #   PaperPerformanceChart, Phase 28)
  utils/         # formatting helpers (currency, percent, date)
  test/          # Vitest setup (Phase 21)
```

61 Vitest + React Testing Library tests cover `utils/format.ts`,
`useMarketFeed`, and smoke-level rendering (loading/error/data states,
form submission) of the Phase 20, 25, 26, 27, 28, 29, and 30 UI.

## Security (Phase 21)

- JWT via PyJWT (swapped from `python-jose` — see `security-review.md` for
  why), bcrypt password hashing (unchanged since Phase 1).
- `slowapi`-based IP rate limiting on `/auth/login`, `/auth/register`
  (10/min) and `/assistant/ask` (20/min, bounding paid-API-call rate).
- A startup warning fires if `SECRET_KEY` is a known placeholder or under
  32 characters.
- Full dependency-vulnerability audit and what was fixed vs. deliberately
  deferred (with reasoning): `security-review.md`.

## Deployment (Phase 22)

Three Docker Compose services — see `DEPLOYMENT.md` for the full picture,
including the build-time-vs-runtime caveat on the frontend's
`VITE_API_BASE_URL` and an honest account of what has and hasn't been
verified end-to-end from this project's own development sandbox.

## Design principle carried through every phase

Every new capability was added as its own service module behind a narrow
interface (mirroring the market-data/sentiment provider pattern from
Phase 1), with its own route(s) and, where applicable, frontend page — so
earlier functionality was never rewritten to make room for new
functionality. Where a phase's addition genuinely does supersede earlier
behavior (the Phase 6 ML pipeline rebuild, the Phase 8 risk rebuild, the
Phase 10 Fit Engine rebuild, the Phase 17 SHAP explanations, the Phase 18
ledger), that decision is recorded as an ADR under `docs/adr/` rather than
applied silently — see `CLAUDE.md` rule 9.
