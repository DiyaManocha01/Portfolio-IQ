# PortfolioIQ Architecture

## Overview

PortfolioIQ is a full-stack AI portfolio intelligence platform. This
document describes the architecture of the MVP milestone (foundation
through the Portfolio Fit Engine) and how it's structured to extend
cleanly into later phases (see `ROADMAP.md`).

```
frontend (React + TS + Tailwind)
        |  Axios (JWT bearer auth)
        v
FastAPI app (app/main.py)
        |
        v
API routes (app/api/routes/*) -- thin, no business logic
        |
        v
Services (app/services, app/portfolio, app/ml, app/nlp) -- all business logic
        |
        v
SQLAlchemy models (app/models) <-> PostgreSQL
        |
        v
Provider abstractions (market data, sentiment) -- swappable live/dev-sample
```

## Backend layout

```
backend/
  app/
    api/
      deps.py            # auth dependency (get_current_user, get_current_portfolio)
      routes/            # auth, portfolio, stocks, discover, portfolio_fit
    models/               # SQLAlchemy ORM models (12 tables, see below)
    schemas/              # Pydantic request/response models
    services/
      security.py         # password hashing + JWT
      analytics.py         # reusable stock analytics (SMA/EMA/RSI/volatility/...)
      portfolio_calc.py    # holding P&L + portfolio aggregation + performance series
      news_service.py      # news generation + sentiment orchestration
      market_data/
        providers.py       # MarketDataProvider abstraction (DevSample + LiveYFinance)
        service.py          # MarketDataService: caching layer over a provider
    ml/
      features.py           # feature engineering (time-safe, no look-ahead)
      train.py               # trains + selects LogReg/RandomForest/XGBoost
      predict.py             # loads trained model, produces direction/probability/confidence
    nlp/
      lexicon_sentiment.py   # default sentiment provider (no external deps)
      finbert_sentiment.py   # real FinBERT provider (opt-in, needs internet + transformers/torch)
      sentiment_service.py   # selects provider based on settings.USE_FINBERT
    portfolio/
      risk_service.py        # volatility, Sharpe, drawdown, correlation, risk contribution
      health_service.py      # Portfolio Health Score (see docs/PORTFOLIO_SCORING.md)
      weakness_service.py    # rule-based weakness detection
      fit_service.py         # Portfolio Fit Engine (the core USP)
      discover_service.py    # ranks candidates by fit for /discover
    data/
      seed.py                 # dev seed script: stocks, market data, news, demo user, trains ML
      models/                  # trained model artifacts (joblib) + metadata.json, gitignored
    tests/                    # pytest suite
```

## Database schema (12 tables)

`users` -> `user_profiles` (1:1), `users` -> `portfolios` (1:many) ->
`holdings` / `transactions` / `portfolio_scores`. `holdings`/`transactions`
reference `stocks`, which own `market_data`, `financial_metrics`,
`predictions`, and (optionally) `news` -> `news_sentiment` (1:1).

See `backend/app/models/*.py` for exact columns; relationships use
SQLAlchemy 2.0 typed `Mapped[...]` declarations with cascading deletes.

## Provider abstraction (the key extensibility pattern)

Two subsystems in this MVP follow the same pattern, so a real external
integration can be dropped in later without touching calling code:

1. **Market data** (`app/services/market_data/providers.py`):
   `MarketDataProvider` is an ABC with `get_history`/`get_quote`.
   `DevSampleProvider` (default) generates deterministic, seeded synthetic
   OHLCV data with a shared market factor for realistic cross-stock
   correlation, tagged `DataSource.DEV_SAMPLE`. `LiveYFinanceProvider` is a
   real implementation behind the same interface, tagged `DataSource.LIVE`,
   enabled via `USE_LIVE_MARKET_DATA=true`. This development sandbox has no
   outbound network access to market-data vendors, so the live provider is
   implemented but not exercised here.
2. **Sentiment** (`app/nlp/`): `SentimentService` selects between
   `lexicon_sentiment` (default, a small weighted financial-word lexicon,
   zero external dependencies) and `finbert_sentiment` (a real
   `transformers` pipeline against `ProsusAI/finbert`, enabled via
   `USE_FINBERT=true` on a machine with internet access to Hugging Face).

Every response that depends on one of these carries a `data_source` /
`model_used` field so the frontend can label it honestly.

## ML pipeline

`app/ml/train.py` pools OHLCV-derived features across all seeded stocks,
splits **chronologically per stock** (never shuffled) into 70% train / 15%
validation / 15% test, trains Logistic Regression, Random Forest, and
XGBoost, and selects the model with the best validation ROC-AUC. The
selected model is re-evaluated once on the untouched test split for an
honest, non-cherry-picked metric, and both are persisted to
`model_metadata.json` alongside the model artifact -- the API never
fabricates an accuracy number, it reads whatever training actually
produced. `app/ml/predict.py` loads that model and derives a
direction (POSITIVE/NEGATIVE/NEUTRAL) and a confidence bucket
(LOW/MEDIUM/HIGH) purely from how far the predicted probability sits from
0.5 -- a documented, non-arbitrary rule.

## Portfolio Fit Engine

The core USP (`app/portfolio/fit_service.py`) answers "how well does this
stock fit MY portfolio", not "is this a good stock". It combines six
independently-computed 0-100 components (prediction, risk, diversification,
correlation, sector balance, user preference) via configurable weights
(`DEFAULT_WEIGHTS`), and returns every component's contribution plus
generated strengths/concerns text -- never a bare number.

## Frontend layout

```
frontend/src/
  components/   # shared UI pieces (cards, badges, tables, nav)
  pages/         # one file per route (Dashboard, Portfolio, StockDetail, Discover, Intelligence, ...)
  layouts/       # app shell (sidebar + top nav + protected-route wrapper)
  services/      # axios client + one module per API resource
  hooks/         # data-fetching hooks
  types/         # TypeScript interfaces mirroring docs/API_CONTRACT.md
  charts/        # Recharts wrapper components
  utils/         # formatting helpers (currency, percent, date)
```

## Why this milestone stops where it does

Sections 1-10 of the product vision (through the Portfolio Fit Engine) are
fully implemented end-to-end with real calculations. Geopolitical
intelligence, the AI assistant, full backtesting, and alerting are
intentionally deferred -- see `ROADMAP.md` -- but every service above is
structured so those phases plug in as new services/routes rather than
requiring a rewrite.
