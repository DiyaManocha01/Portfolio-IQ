# PortfolioIQ -- AI Portfolio Intelligence

> PortfolioIQ doesn't just analyze stocks -- it understands an investor's
> existing portfolio and evaluates stocks based on how they may fit into
> that portfolio.

BTech final-year/minor project MVP. This milestone implements the
foundation through the **Portfolio Fit Engine**: auth, portfolio
management, market data, stock analytics, ML stock direction prediction,
financial news + sentiment, portfolio risk analytics, Portfolio Health
Score, Portfolio Weakness Detector, and the Portfolio Fit Engine +
Discover page. See `docs/ROADMAP.md` for what's intentionally deferred.

**Disclaimer**: PortfolioIQ is an educational and analytical
decision-support system. Its predictions and portfolio analytics are
model-based estimates and are not guaranteed financial advice.

## Tech stack

- **Frontend**: React, TypeScript, Tailwind CSS, Recharts, React Router, Axios
- **Backend**: Python, FastAPI, SQLAlchemy, Pydantic
- **Database**: PostgreSQL
- **ML**: pandas, NumPy, scikit-learn, XGBoost
- **NLP**: Hugging Face Transformers / FinBERT (optional, see below), with a
  lexicon-based sentiment provider as the offline default
- **Testing**: pytest

## Project structure

```
backend/app/   api/ models/ schemas/ services/ ml/ nlp/ portfolio/ database/ data/ tests/
frontend/src/  components/ pages/ layouts/ services/ hooks/ types/ charts/ utils/
docs/          ARCHITECTURE.md  ROADMAP.md  API_CONTRACT.md  PORTFOLIO_SCORING.md  THIRD_PARTY_LICENSES.md
```

## Prerequisites

- Python 3.11+
- Node.js 18+ (this project was built/tested on Node 22)
- PostgreSQL 14+ running locally

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
python -m pytest app/tests/ -v
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

- **Auth**: register/login/JWT, protected portfolio APIs, current-user endpoint.
- **Portfolio management**: add/remove holdings, live P&L/return calculation.
- **Dashboard**: summary cards, performance chart, stock/sector allocation,
  top holdings table, AI market outlook per holding, portfolio intelligence
  summary, recent news.
- **Stock analysis**: price history, SMA/EMA/RSI/volatility/momentum,
  AI stock outlook (direction/probability/confidence/important factors),
  news + sentiment.
- **ML prediction**: Logistic Regression, Random Forest, and XGBoost trained
  on a strictly time-aware (non-shuffled) split; the best model by
  validation ROC-AUC is selected and reported honestly (see
  `backend/app/data/models/model_metadata.json` after seeding -- no
  fabricated accuracy numbers).
- **Portfolio risk**: volatility, Sharpe ratio, max drawdown, correlation
  matrix, sector concentration, per-holding risk contribution.
- **Portfolio Health Score**: five transparent components, methodology in
  `docs/PORTFOLIO_SCORING.md`.
- **Portfolio Weakness Detector**: rule-based warnings with severity,
  explanation, and supporting metric.
- **Portfolio Fit Engine + Discover**: the core USP -- see
  `docs/API_CONTRACT.md` for the exact scoring breakdown returned by
  `GET /portfolio-fit/{symbol}`.

## Known limitations (by design, for this milestone)

- Market data and news are development-sample data in this environment
  (no outbound network access here) -- architecture supports live data,
  see above.
- ML models are trained on ~1 year of synthetic per-stock history; reported
  validation/test AUC is near 0.5-0.56 (close to random), which is honestly
  reported rather than inflated -- synthetic random-walk data has limited
  learnable signal by construction. Predictions are explicitly labeled as
  model estimates, not guarantees.
- Portfolio performance history assumes current holding quantities were
  held constant across the lookback window (documented in
  `docs/PORTFOLIO_SCORING.md`), rather than a full transaction-by-transaction
  reconstruction.
- Geopolitical intelligence, What-If simulation, stress testing, full
  backtesting, alerts, and the AI assistant are intentionally out of scope
  for this milestone -- see `docs/ROADMAP.md`.
