# PortfolioIQ -- AI Portfolio Intelligence

> PortfolioIQ doesn't just analyze stocks -- it understands an investor's
> existing portfolio and evaluates stocks based on how they may fit into
> that portfolio.

B.Tech AI & Data Science final-year project, built in 22 phases through a
documented checkpoint process (every phase: code, passing tests, updated
docs, a git commit — see `CLAUDE.md` for the working rules this project
was built under). The core contribution is the **Portfolio Fit Engine**:
ranking candidate stocks by how they'd change *your specific* portfolio
(risk, diversification, sector concentration), not by whether the stock
is "good" in the abstract. Everything else — risk analytics, optimization,
a What-If simulator, stress testing, counterfactual explanations,
per-prediction SHAP attributions, a tamper-evident public prediction
ledger, and an AI assistant that only cites already-computed numbers —
builds outward from that same honesty-first design principle: never
invent a number, always show the formula and the caveat next to it.
See `docs/ROADMAP.md` for phase-by-phase history and what's still
genuinely out of scope.

**Disclaimer**: PortfolioIQ is an educational and analytical
decision-support system. Its predictions and portfolio analytics are
model-based estimates and are not guaranteed financial advice.

## Tech stack

- **Frontend**: React, TypeScript, Tailwind CSS, Recharts, React Router 7, Axios, Vitest + React Testing Library
- **Backend**: Python, FastAPI, SQLAlchemy, Pydantic, Alembic, slowapi (rate limiting)
- **Database**: PostgreSQL
- **ML**: pandas, NumPy, scikit-learn, XGBoost, SHAP (per-prediction explanations)
- **Portfolio math**: PyPortfolioOpt (optimization), scipy (Deflated Sharpe Ratio / backtesting stats)
- **NLP**: Hugging Face Transformers / FinBERT (optional, see below), with a
  lexicon-based sentiment provider as the offline default
- **AI assistant**: Anthropic Claude API (retrieval-and-cite only — see `docs/methodology.md` Section 16)
- **Testing**: pytest (backend, 233 tests), Vitest (frontend, 37 tests)
- **Deployment**: Docker Compose (see `docs/DEPLOYMENT.md`)

## Project structure

```
backend/app/   api/ models/ schemas/ services/ ml/ nlp/ portfolio/ assistant/ database/ data/ tests/
frontend/src/  components/ pages/ layouts/ services/ hooks/ types/ charts/ utils/ test/
docs/          ARCHITECTURE.md  ROADMAP.md  API_CONTRACT.md  PORTFOLIO_SCORING.md
               methodology.md  limitations.md  security-review.md  DEPLOYMENT.md
               open-source-inventory.md  adr/
```

## Prerequisites

- Python 3.11+
- Node.js 18+ (this project was built/tested on Node 22)
- PostgreSQL 14+ running locally

**Or skip all of the above and run the full stack with Docker Compose**
(`docker compose up --build` — see `docs/DEPLOYMENT.md` for setup and,
importantly, what has and hasn't actually been verified end-to-end).
The manual steps below are still the better path while actively
developing (faster iteration, no rebuild step).

## 1. Database setup

```bash
sudo service postgresql start   # or however Postgres runs on your machine
sudo -u postgres psql -c "CREATE USER portfolioiq WITH PASSWORD 'portfolioiq_dev_pw';"
sudo -u postgres psql -c "CREATE DATABASE portfolioiq OWNER portfolioiq;"
```

## 2. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # defaults already match the DB created above
python -m app.data.seed       # creates tables, seeds demo data, trains the ML model
uvicorn app.main:app --reload --port 8000
```

Backend now running at http://localhost:8000 (interactive docs at `/docs`).

Run tests (with the backend's venv active, DB seeded, and the server importable):

```bash
python -m pytest app/tests/ -v   # 233 tests
```

### Demo login
```
email:    demo@portfolioiq.app
password: demo1234
```
The seeded portfolio holds TCS, RELIANCE, HDFCBANK, INFY, ICICIBANK, LT,
ITC. Six additional stocks (HINDUNILVR, BHARTIARTL, SBIN, WIPRO, MARUTI,
SUNPHARMA) are seeded with market data/news but not held, so `/discover`
has real candidates to rank.

## 3. Frontend setup

```bash
cd frontend
npm install
cp .env.example .env    # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Frontend now running at http://localhost:5173 (Vite default).

Run frontend tests:

```bash
npm test   # 37 tests (Vitest + React Testing Library)
```

## Data sources: LIVE vs DEVELOPMENT SAMPLE

This project defaults to `USE_LIVE_MARKET_DATA=false` and `USE_FINBERT=false`
in `backend/.env` because this development environment has no outbound
network access to market-data or Hugging Face vendors. In this mode:

- **Market data** comes from a deterministic, seeded synthetic OHLCV
  generator (`DevSampleProvider`) -- clearly tagged `"data_source":
  "DEV_SAMPLE"` in every API response that includes price data. A real
  `yfinance`-backed provider (`LiveYFinanceProvider`) is fully implemented
  behind the same interface and can be enabled by flipping
  `USE_LIVE_MARKET_DATA=true` on a machine with internet access.
- **News sentiment** comes from a lightweight financial-lexicon scorer
  (`"model_used": "lexicon-v1"`). A real FinBERT transformer pipeline is
  fully implemented and can be enabled with `USE_FINBERT=true` (requires
  `transformers`/`torch` and internet access to download `ProsusAI/finbert`
  on first run).

No live data is ever mislabeled as real -- see `docs/ARCHITECTURE.md` for
the full provider-abstraction pattern.

## What's implemented

**Foundation (Phases 1-9)**
- **Auth**: register/login/JWT, rate-limited (Phase 21), protected portfolio APIs.
- **Portfolio management**: add/remove holdings, live P&L/return calculation.
- **Dashboard**: summary cards, performance chart, allocation, AI market outlook.
- **Stock analysis**: price history, SMA/EMA/RSI/MACD/volatility/momentum/beta,
  AI stock outlook with per-prediction SHAP explanations (Phase 17), news + sentiment.
- **ML prediction**: Logistic Regression / Random Forest / XGBoost, selected
  by purged walk-forward cross-validation (Phase 6) -- the best model's
  real, honestly-measured AUC is read from `model_metadata.json` after
  seeding, never asserted.
- **Portfolio risk** (Phase 8): volatility, Sharpe, max drawdown, Ledoit-Wolf
  shrinkage covariance, historical VaR/CVaR, HHI, diversification ratio.
- **Portfolio Optimization** (Phase 9): min-variance / max-Sharpe / Hierarchical
  Risk Parity target allocations via PyPortfolioOpt -- never auto-executed.
- **Portfolio Health Score** and **Weakness Detector**: see `docs/PORTFOLIO_SCORING.md`.
- **Portfolio Fit Engine + Discover**: the core USP -- see `docs/API_CONTRACT.md`.

**Simulation & explainability (Phases 10-17)**
- **What-If Simulator** (Phase 11): hypothetical buy/sell/add with before/after
  risk metrics and illustrative Indian transaction-cost estimates -- never
  writes to the database (verified by a dedicated test).
- **Personalized Discovery** (Phase 12): sector-exclusion preferences.
- **Backtesting** (Phase 13): purged walk-forward backtest of the ML strategy
  vs. buy-and-hold/momentum, with Deflated Sharpe Ratio and a paired
  bootstrap significance test -- genuinely run, not simulated (see
  `docs/methodology.md` Section 10 for the honest, underwhelming-on-synthetic-data result).
- **Risk Attribution** (Phase 14): % of portfolio money vs. % of portfolio
  risk per holding, with an exact Euler's-theorem decomposition.
- **Stress / Scenario Testing** (Phase 15): CAPM beta-scaled shocks, named
  historical presets, and a narrow regex-based (not LLM) scenario-text parser.
- **Counterfactual Fit Explanations** (Phase 16): exact "why did A rank above
  B" decomposition and ceteris-paribus "what would need to change" scenarios.

**Trust & production hardening (Phases 18-22)**
- **Verified Public Track Record** (Phase 18): a hash-chained, DB-trigger-
  enforced append-only prediction ledger with a public (no-auth) verify
  endpoint -- tamper-evident, demonstrated against a simulated privileged tamper.
- **AI Portfolio Assistant** (Phase 19): retrieval-and-cite only (never
  computes a new number itself), with a system-prompt + regex-guardrail
  defense against advice-like language.
- **Frontend UI for Phases 9/11/14/16** (Phase 20): Risk Attribution section,
  a tabbed Portfolio Lab (What-If + Optimization), and Fit comparison/counterfactual
  sections on the stock detail page.
- **Testing & Security** (Phase 21): Vitest + React Testing Library (37
  frontend tests), a dependency-vulnerability audit (`docs/security-review.md`:
  42 findings down to 1, with the remainder explicitly deferred and why),
  and rate limiting on auth/assistant endpoints.
- **Deployment** (Phase 22): Docker Compose for the full stack -- see
  `docs/DEPLOYMENT.md` for exactly what has and hasn't been verified end-to-end.

## Known limitations (honestly, and extended every phase)

Every limitation below has its reasoning, and often a measured example,
in `docs/limitations.md` -- this is a summary, not the full account.

- **Market data and news are development-sample (synthetic) data in this
  development environment** -- no outbound network access here to Yahoo
  Finance / Hugging Face / RSS hosts (verified, not assumed). The
  architecture fully supports live data (`LiveYFinanceProvider`, real
  FinBERT, real RSS ingestion) behind the same interfaces; flip
  `USE_LIVE_MARKET_DATA` / `USE_FINBERT` / `USE_LIVE_NEWS` on a machine
  with internet access. No live data is ever mislabeled as real.
- **ML models trained on synthetic data score close to random** (test AUC
  ~0.545, honestly reported, not inflated) -- a random-walk has very
  little learnable signal by construction. The backtest (Phase 13) tells
  the same story as trading performance: the ML strategy underperforms
  buy-and-hold on this data, reported as the correct, expected result of
  training on synthetic data, not a bug.
- **The NIFTY 100 symbol list is unverified against a live/official
  source** and the backtest/optimization universe has survivorship bias
  -- both must be re-checked before any number computed over them is
  cited in a paper.
- **The Deflated Sharpe Ratio formula (Phase 13) was not independently
  verified against the original paper** -- no network access to fetch it
  here; cross-checked against three secondary sources instead.
- **Docker Compose (Phase 22) has not been run end-to-end from this
  project's own sandbox** -- containers here can't complete outbound
  HTTPS to package registries. See `docs/DEPLOYMENT.md` for what partial
  verification was possible and why.
- **No geopolitical intelligence, alerts, or multi-turn assistant memory**
  -- intentionally out of scope; see `docs/ROADMAP.md`.
