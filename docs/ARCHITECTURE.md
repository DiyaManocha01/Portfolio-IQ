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
      routes/               # auth, portfolio, stocks, discover, portfolio_fit, ledger, assistant
    models/                 # SQLAlchemy ORM models (13 tables, see below)
    schemas/                # Pydantic request/response models
    services/
      security.py           # password hashing + JWT (PyJWT, Phase 21)
      rate_limit.py          # shared slowapi Limiter (Phase 21)
      analytics.py           # stock analytics (SMA/EMA/RSI/MACD/volatility/beta)
      portfolio_calc.py      # holding P&L + portfolio aggregation + performance series
      news_service.py        # news generation + sentiment orchestration
      market_data/
        providers.py         # MarketDataProvider abstraction (DevSample + LiveYFinance)
        service.py            # MarketDataService: caching layer over a provider
        cache.py               # Parquet cache + OHLCV validation (Phase 4)
        nifty100.py             # symbol universe
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
    assistant/
      context_builder.py       # deterministic keyword-based data router (Phase 19)
      assistant_service.py      # system prompt, Claude API call, guardrail filter (Phase 19)
    data/
      seed.py                 # dev seed script: stocks, market data, news, demo user, trains ML
      models/                  # trained model artifacts (joblib) + metadata.json, gitignored
    tests/                    # pytest suite, 233 tests
  Dockerfile                  # multi-stage build (Phase 22)
  docker-entrypoint.sh         # migrate -> seed/train (once) -> uvicorn (Phase 22)
```

## Database schema (13 tables)

`users` -> `user_profiles` (1:1), `users` -> `portfolios` (1:many) ->
`holdings` / `transactions` / `portfolio_scores`. `holdings`/`transactions`
reference `stocks`, which own `market_data`, `financial_metrics`,
`predictions`, and (optionally) `news` -> `news_sentiment` (1:1).
`predictions` feed `prediction_ledger` (Phase 18, append-only, DB-trigger-
enforced — see `methodology.md` Section 15), which stands somewhat apart
from the rest: it is intentionally written once and never updated.

See `backend/app/models/*.py` for exact columns; relationships use
SQLAlchemy 2.0 typed `Mapped[...]` declarations with cascading deletes.
Schema changes go through Alembic (`backend/alembic/`) as of Phase 4 —
`Base.metadata.create_all()` is no longer used anywhere.

## API routes (7 route modules)

| Module | Mounted at | Auth | Notes |
|---|---|---|---|
| `auth.py` | `/auth` | mixed | register/login rate-limited (Phase 21) |
| `portfolio.py` | `/portfolio` | required | holdings, risk, health, optimize, what-if, stress-test, risk-attribution |
| `stocks.py` | `/stocks` | required | quote, history, analysis, prediction (+SHAP), news, sentiment |
| `discover.py` | `/discover` | required | personalized candidate ranking |
| `portfolio_fit.py` | `/portfolio-fit` | required | fit breakdown, compare, counterfactual |
| `ledger.py` | `/ledger` | **none** | the one deliberately public surface (Phase 18) |
| `assistant.py` | `/assistant` | required | rate-limited (Phase 21) |

Full request/response shapes: `API_CONTRACT.md`.

## Provider abstraction (the key extensibility pattern)

Two subsystems follow the same pattern, so a real external integration
can be dropped in without touching calling code:

1. **Market data** (`app/services/market_data/providers.py`):
   `MarketDataProvider` is an ABC with `get_history`/`get_quote`.
   `DevSampleProvider` (default) generates deterministic, seeded synthetic
   OHLCV data with a shared market factor for realistic cross-stock
   correlation, tagged `DataSource.DEV_SAMPLE`. `LiveYFinanceProvider` is a
   real implementation behind the same interface, tagged `DataSource.LIVE`,
   enabled via `USE_LIVE_MARKET_DATA=true`, reading a local Parquet cache
   (`app/services/market_data/cache.py`) populated by
   `scripts/fetch_nifty100.py` run locally.
2. **Sentiment** (`app/nlp/`): `SentimentService` selects between
   `lexicon_sentiment` (default, zero external dependencies) and
   `finbert_sentiment` (a real `transformers` pipeline against
   `ProsusAI/finbert`, enabled via `USE_FINBERT=true`).

Every response that depends on one of these carries a `data_source` /
`model_used` field so the frontend can label it honestly.

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

## Frontend layout

```
frontend/src/
  components/   # shared UI pieces (cards, badges, tables, nav)
  pages/         # one file per route:
                 #   Dashboard, Portfolio, Stocks, StockDetail, Discover,
                 #   Intelligence (risk + risk attribution),
                 #   PortfolioFit (+ compare/counterfactual, Phase 20),
                 #   PortfolioLab (What-If + Optimization tabs, Phase 20)
  layouts/       # app shell (sidebar + top nav + protected-route wrapper)
  services/      # axios client + one module per API resource
  hooks/         # data-fetching hooks (useAsync)
  types/         # TypeScript interfaces mirroring API_CONTRACT.md
  charts/        # Recharts wrapper components
  utils/         # formatting helpers (currency, percent, date)
  test/          # Vitest setup (Phase 21)
```

37 Vitest + React Testing Library tests cover `utils/format.ts` and
smoke-level rendering (loading/error/data states, form submission) of the
Phase 20 UI.

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
