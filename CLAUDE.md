# CLAUDE.md

Repo-specific instructions for working on this project. Read this before
making changes — it encodes working rules the project owner has set, not
suggestions.

## What this project is

An AI Portfolio Intelligence Platform (B.Tech AI & Data Science project).
**Not a broker, not financial advice.** Core contribution: the Portfolio
Fit Engine — ranking candidate stocks by how they change a specific user's
existing portfolio (risk, diversification, sector concentration), combined
with ML outlook and news sentiment — plus a What-If Simulator for
hypothetical changes that never mutate the real portfolio. Product story:
**explainable, honest, portfolio-aware.** Must be rigorous enough to
support a research paper and an IP/patent discussion, and strong enough to
be a defining CV project.

## Working rules (do not deviate without asking)

1. **Checkpoint rule.** Work in batches of two phases. Complete both fully
   (code, tests passing, docs updated, committed), then STOP — do not start
   the next phase. Report: what was built + how to run it, test results,
   anything incomplete/risky/assumed, the next two proposed phases, then
   ask "Shall I continue with Phases X and Y?" and wait.
2. Within a batch: write a short plan before each phase (files to touch,
   schema changes, tests). Wait for approval on the **first** phase of a
   batch; proceed without waiting on the **second**, unless something is
   unclear or risky.
3. Follow the existing architecture: `api -> services -> repositories ->
   models`; calculations in `backend/app/portfolio/`; ML training in `ml/`
   (training scripts), serving in `backend/app/ml/`.
4. Every phase ends with: passing tests, an Alembic migration if the schema
   changed, an updated `docs/` page or ADR, and a clear git commit.
5. **Never invent data, metrics, or results.** Every number in docs or a
   paper draft must come from code, with the script that produced it
   stored in the repo. Mark anything unverified as such.
6. Keep all outputs framed as probabilistic outlooks, simulations, and
   backtests. Keep the financial disclaimer visible. Never output "buy/sell"
   advice or guarantee returns.
7. Check the license of every new dependency; record it in
   `docs/open-source-inventory.md` in the same commit that adds it.
8. This sandbox may block market-data/HF hosts (verified: it does). Support
   a cached/fixture dataset so tests and demos run offline. Fetch/cache
   scripts that need real network access are written to be run by the
   project owner locally, not executed here.
9. **Do not silently change earlier decisions.** Propose changes and record
   an ADR (`docs/adr/000N-*.md`) before superseding existing behavior.

## Architecture

```
frontend (React + TS)  --Axios/JWT-->  FastAPI (api/routes/*)
                                             |
                                        services (thin routes, all logic here)
                                             |
                        +--------------------+--------------------+
                        |                    |                    |
                 app/portfolio/        app/ml/ (serving)     app/nlp/
                 (risk, health,        app/services/          (sentiment)
                  weakness, fit)        market_data/
                        |                    |                    |
                        +--------------------+--------------------+
                                             |
                                   PostgreSQL (Alembic-managed)
```

- Routes (`app/api/routes/*.py`) never contain business logic — they
  validate auth/input and call a service.
- `ml/` (repo-root-relative training scripts, currently `backend/app/ml/train.py`)
  trains and selects models; `backend/app/ml/predict.py` serves them.
  Model artifacts + metadata live in `backend/app/data/models/` (gitignored).
- Market data: provider abstraction (`DevSampleProvider` synthetic,
  `LiveYFinanceProvider` real+cached) behind `MarketDataService`.
- Schema changes go through Alembic (`backend/alembic/`) as of Phase 4 —
  `Base.metadata.create_all()` is no longer used.

## Commands

```bash
# Backend setup
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Database
sudo -u postgres psql -c "CREATE USER portfolioiq WITH PASSWORD 'portfolioiq_dev_pw';"
sudo -u postgres psql -c "CREATE DATABASE portfolioiq OWNER portfolioiq;"
cp .env.example .env
alembic upgrade head          # applies schema (Phase 4+; create_all is gone)
python -m app.data.seed       # demo user + synthetic data + trains ML model

# Run
uvicorn app.main:app --reload --port 8000

# Test
python -m pytest app/tests/ -v

# New migration after a model change
alembic revision --autogenerate -m "short description"
alembic upgrade head

# Fetch real NIFTY 100 data (run on a machine with real internet access —
# this sandbox cannot reach Yahoo Finance, verified)
python scripts/fetch_nifty100.py                 # full universe, 3y
python scripts/fetch_nifty100.py --out-fixture    # also writes committed test fixture

# Frontend
cd frontend
npm install
cp .env.example .env
npm run dev

# Or: full stack via Docker Compose (Phase 22) -- see docs/DEPLOYMENT.md
# for what's verified vs. not from this project's own sandbox
cp .env.example .env
cp backend/.env.example backend/.env
docker compose up --build
```

Demo login: `demo@portfolioiq.app` / `demo1234`.

## Docs map

- `docs/methodology.md` — every formula, evaluation protocol, extended each phase
- `docs/limitations.md` — known limitations, extended as found
- `docs/adr/` — architecture decision records, one per decision that changes or supersedes earlier behavior
- `docs/open-source-inventory.md` — dependency/license ledger (source of truth; `THIRD_PARTY_LICENSES.md` is the older narrative version)
- `docs/security-review.md` — Phase 21 dependency audit + auth rate limiting, what was fixed vs. deferred and why
- `docs/DEPLOYMENT.md` — Phase 22 Docker Compose setup, what's verified vs. not from this project's sandbox
- `docs/PORTFOLIO_SCORING.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACT.md`, `docs/ROADMAP.md` — pre-Phase-4 docs from the original MVP build; still accurate for what they describe, superseded incrementally as phases land
