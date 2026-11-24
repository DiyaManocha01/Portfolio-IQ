# Acceptance Criteria Audit

Produced for the real-data upgrade brief's explicit acceptance criteria
(section 16): every capability below is classified against four tiers,
and the classification is never upgraded on hope or intent — only on
evidence that currently exists in this repository or was run in this
session. **A capability never gets marked VERIFIED WITH LIVE EXTERNAL
DATA until it has actually been exercised against real external data
with real credentials** — per the brief's own instruction, and
consistent with this project's CLAUDE.md rule 5 ("never invent data,
metrics, or results").

## The four tiers

1. **IMPLEMENTED** — the code exists, is wired into the API/UI, and runs
   without crashing (ad hoc exercise or by construction).
2. **UNIT TESTED** — a pytest/Vitest test exercises the underlying
   function/service/component directly (not through the HTTP API),
   asserting on its actual output.
3. **INTEGRATION TESTED** — a test exercises the feature through the real
   API layer (FastAPI `TestClient`) or a rendered page/component tree
   (React Testing Library), including request validation, auth, and
   response shape.
4. **VERIFIED WITH LIVE EXTERNAL DATA** — the feature has been run at
   least once against a real external data source or API (real market
   data, a real broker feed, a real LLM call, real RSS headlines, etc.),
   not `DEV_SAMPLE`/`FIXTURE` data, **with evidence of that run** (a log,
   a committed output, or a directly reported result).

A tier is only ever checked when a *lower* tier is also checked — there
is no "verified but untested" row in this project's actual state, though
the table marks tier 4 independently since in principle it could precede
automated tests for a one-off manual check (it never does here).

## How this was produced

Cross-referenced against:
- `app/tests/*.py` (42 files, 488 tests) and `frontend/src/**/*.test.tsx`
  (12 files, 78 tests) as of this audit — actually run, not assumed.
- `docs/limitations.md`, which already documents, phase by phase, exactly
  what has and hasn't been exercised against real external data — this
  audit's tier-4 column restates those facts in one place, it does not
  re-investigate them.
- `docs/gap-analysis-realtime-upgrade.md` (the Phase A audit) for the
  network-reachability facts (which hosts are blocked from this sandbox,
  verified directly, not assumed).

No new live-data runs were performed to produce this document. It is a
classification of existing evidence, not a new verification pass.

## Capability matrix

| Capability | Implemented | Unit Tested | Integration Tested | Verified w/ Live Data | Notes |
|---|:---:|:---:|:---:|:---:|---|
| **Auth** (register/login/JWT/bcrypt) | ✅ | ✅ | ✅ | N/A | No external dependency — "live" doesn't apply. |
| **Auth rate limiting** (login/register brute-force) | ✅ | — | ✅ | N/A | `test_rate_limit.py`, isolated-app mechanism tests. |
| **Portfolio CRUD** (holdings, buy/sell, transactions) | ✅ | ✅ | ✅ | N/A | Operates on this app's own DB; no external dependency. |
| **Today's P&L** (`day_pnl`/`day_pnl_pct`, real-data upgrade Phase D) | ✅ | ✅ | ✅ | ❌ | Correct against `DEV_SAMPLE`/cached data; never measured against a real previous-close from a live feed. |
| **Portfolio Risk** (Ledoit-Wolf, Sharpe, VaR/CVaR, HHI) | ✅ | ✅ | ✅ | ❌ | `test_portfolio_risk.py`. Covariance estimated from `DEV_SAMPLE`/cached history only. |
| **Portfolio Optimization** (min-variance/max-Sharpe/HRP) | ✅ | ✅ | ✅ | ❌ | `test_portfolio_optimization.py`. PyPortfolioOpt itself is a real, mature library — the *inputs* (expected returns, covariance) are synthetic here. |
| **Portfolio Fit Engine** (+ compare/counterfactual) | ✅ | ✅ | ✅ | ❌ | `test_fit_engine.py`, `test_fit_counterfactual.py`, `test_fit_snapshot.py`. Core differentiator; z-scored against the seeded universe, not the full NIFTY 100. |
| **Discover / Personalized Discovery** | ✅ | ✅ | ✅ | ❌ | `test_discovery_personalization.py`. Now rate-limited 30/minute (Phase J). |
| **What-If Simulator** | ✅ | ✅ | ✅ | ❌ | `test_whatif.py`. Transaction cost model is illustrative/unsourced (see `docs/limitations.md`), independent of the live-data question. Now rate-limited 30/minute (Phase J). |
| **Stress / Scenario Testing** | ✅ | ✅ | ✅ | ❌ | `test_stress_test.py`. Historical scenario magnitudes (e.g. "COVID 2020: ~-38%") are publicly known figures, not independently re-verified from this sandbox. Now rate-limited 30/minute (Phase J). |
| **Risk Attribution** | ✅ | ✅ | ✅ | ❌ | `test_risk_attribution.py`. Now rate-limited 30/minute (Phase J). |
| **Advanced Portfolio Performance** (benchmark, drawdown, sector/holding contribution) | ✅ | ✅ | ✅ | ❌ | `test_portfolio_performance.py`. |
| **Benchmark risk-adjusted stats** (CAGR/alpha/beta/tracking error/information ratio, real-data upgrade Phase F) | ✅ | ✅ | ✅ | ❌ | Covered inside `test_portfolio_performance.py`. Only NIFTY 50 supported as benchmark. |
| **Portfolio Heatmap** (real-data upgrade Phase E) | ✅ | ✅ | ✅ | ❌ | Reuses Phase D's `day_pnl` — same tier-4 status. |
| **Market Data provider abstraction** (`DevSampleProvider`/`LiveYFinanceProvider`) | ✅ | ✅ | ✅ | ❌ | `test_market_data_cache.py`. `LiveYFinanceProvider` has never reached `query1.finance.yahoo.com` from any sandbox session (verified blocked, not just untried). |
| **Historical Data Pipeline** (resampling, gap detection, adjusted-price labeling, real-data upgrade Phase C) | ✅ | ✅ | ✅ | ❌ | `test_candle_resample.py`. Pure functions over stored data; never run against real intraday history. |
| **Real-Time Feed** (Angel One WS client, tick normalization, session calendar, fixture replay) | ✅ | ✅ | ✅ | ❌ | `test_angelone_auth.py`, `test_angelone_ws_client.py`, `test_tick_normalizer.py`, `test_session_calendar.py`, `test_ws_connection_manager.py`, `test_fixture_replay_provider.py`, `test_live_cache.py`, `test_snapshot_service.py`, `test_instrument_registry.py`. Wire-format parsing is self-consistent (round-trips its own pack/unpack) but has **never decoded a real Angel One frame** — `ENABLE_REALTIME_FEED=false` by default; every demo runs on `FIXTURE` data. |
| **Market Dashboard** (status, movers, indices, regime) | ✅ | ✅ | ✅ | ❌ | `test_market_routes.py`, `test_market_movers.py`, `test_market_regime.py`. SENSEX explicitly unsupported (no BSE wiring). NIFTY IT's live ticker (`^CNXIT`) is an unverified guess. |
| **Fundamentals + retrieval metadata** (`retrieved_at`/`availability`, real-data upgrade Phase G) | ✅ | ✅ | ✅ | ❌ | `test_fundamentals.py`. `LiveYFinanceProvider`'s field coverage for NSE tickers has never been confirmed against a real response. |
| **Corporate Events** (earnings/dividend/split/bonus/buyback, real-data upgrade Phase G) | ✅ | ✅ | ✅ | ❌ | `test_corporate_events.py`. `DEV_SAMPLE` only ever synthesizes `EARNINGS`; dividend/split/bonus/buyback are never fabricated, only ever real or absent. `LiveYFinanceProvider`'s use of `Ticker.dividends`/`.splits`/`.calendar` is unverified against a live response. |
| **Screener** | ✅ | ✅ | ✅ | ❌ | `test_screener.py`. Operates on the seeded demo universe, not the full NIFTY 100. |
| **ML Prediction** (train/predict/SHAP) | ✅ | ✅ | ✅ | ❌ | `test_ml_train.py`, `test_shap_explain.py`. Validation AUC ~0.50-0.56 on synthetic data — expected, reported honestly, not yet re-measured on real NIFTY data. |
| **Backtesting** (purged walk-forward, DSR, bootstrap, ablation) | ✅ | ✅ | ✅ | ❌ | `test_backtest.py`. DSR formula cross-checked against 3 secondary sources, never against the primary Bailey & Lopez de Prado paper (no network access to fetch it). |
| **News & Sentiment** (lexicon/FinBERT, RSS ingestion, cross-source dedup, real-data upgrade Phase H) | ✅ | ✅ | ✅ | ❌ | `test_news_phase7.py` (unit-level: matching, time-decay, dedup) + `test_api_integration.py::test_stock_news_and_sentiment` (route-level, `GET /stocks/{symbol}/news`). FinBERT has never downloaded weights (HuggingFace blocked); all news in this sandbox is lexicon-scored. |
| **Alerts** (10 rule types incl. `EARNINGS_ANNOUNCEMENT`/`PORTFOLIO_DRAWDOWN`, real-data upgrade Phase G) | ✅ | ✅ | ✅ | ❌ | `test_alerts.py` (22 tests). Every evaluation runs against `DEV_SAMPLE` inputs — no alert has ever fired against a real market event. |
| **AI Portfolio Assistant** (backend, Phase 19/32) | ✅ | ✅ | ✅ | ⚠️ partial | `test_assistant.py`. `api.anthropic.com` reachability WAS verified directly (a real 401, not a connection error) — unlike every other external host this project has tried. But no `ANTHROPIC_API_KEY` is configured here, so the actual authenticated round-trip has never run. Tier 4 is "expected to work," not demonstrated. |
| **AI Assistant chat frontend** (real-data upgrade Phase H) | ✅ | — | ✅ | ❌ | `AssistantPage.test.tsx` (6 tests), mocked service responses — never exercised against a real backend response (which itself is only partially verified, above). |
| **Paper Trading** | ✅ | ✅ | ✅ | ❌ | `test_paper_trading.py`. Execution prices come from `MarketDataService.get_quote` — same `DEV_SAMPLE`/no-live-feed caveat as everything else. |
| **Prediction Ledger** (public track record) | ✅ | ✅ | ✅ | ❌ | `test_prediction_ledger.py`. Resolution uses cached (synthetic) OHLCV — confirms the resolution *mechanism* works, not a real market outcome. |
| **Market Regime Detection** | ✅ | ✅ | ✅ | ❌ | `test_market_regime.py`. No ground truth exists to validate classifications against, live or synthetic. |
| **Per-endpoint rate limiting** (optimize/what-if/stress-test/risk-attribution/discover, real-data upgrade Phase J) | ✅ | — | ✅ | N/A | `test_rate_limit.py`. Mechanism verified against an isolated throwaway `Limiter`; limit *values* (20-30/minute) are a judgment call, not load-tested. |
| **Health / readiness checks** | ✅ | ✅ | ✅ | ✅ | `test_health.py`. This one genuinely runs against this environment's real Postgres + real trained model — "live" here means this sandbox's own real infra, which it *can* reach. |
| **DB backup script** | ✅ | ✅ | — | ✅ | `test_backup_db.py` — a real `pg_dump` against this sandbox's real dev DB, confirmed restorable with `pg_restore --list`. Never run against a production-sized DB. |
| **Structured logging / correlation ID / Sentry** | ✅ | — | ✅ (logging); ❌ (Sentry) | ❌ (Sentry) | Logging confirmed via real log lines in this sandbox. Sentry has never reported a real exception to a real Sentry project (no DSN configured here). |
| **Docker Compose deployment** | ✅ | N/A | N/A | ⚠️ partial | Both Dockerfiles pass `docker build --check`; a full `docker compose up --build` has never completed in this sandbox (TLS interception + Docker Hub rate limits) — see `docs/DEPLOYMENT.md`. |
| **Upstox integration** | ❌ | ❌ | ❌ | ❌ | Explicitly deferred by the project owner's own choice (Phase B's `AskUserQuestion`) — "Skip Upstox for now, keep Angel One primary." No code exists. |
| **NSE holiday calendar** | ❌ | ❌ | ❌ | ❌ | `session_calendar.NSE_HOLIDAYS` ships empty — needs a real, sourced NSE circular, which no sandbox session can fetch. `/market/status` will report `OPEN` on an NSE holiday that falls on a weekday until this is populated. |

## Known testing gaps (found while producing this audit, not previously flagged)

- **`AssistantPage`'s frontend tests mock the service layer**, so there is
  no frontend test that exercises a real `axios` call against even this
  app's own backend (every other page's tests follow this same
  established pattern, so this isn't a Phase-H-specific gap — just worth
  stating plainly since the assistant's backend verification is itself
  only partial, per the table above).

## What would move rows from "Integration Tested" to "Verified with Live External Data"

None of this requires new code — it requires the project owner, on their
own machine with real internet access, to:

1. `python scripts/fetch_nifty100.py --out-fixture` — real NIFTY 100 OHLCV,
   moves Market Data / Historical Pipeline / ML / Backtesting / Screener
   rows toward tier 4 once the backend is pointed at that cache
   (`USE_LIVE_MARKET_DATA=true`).
2. Set a real `ANTHROPIC_API_KEY` in `backend/.env` and ask the Assistant
   a real question — moves the Assistant backend row from "expected to
   work" to actually demonstrated (the frontend row follows once it's
   pointed at that backend).
3. Set real `ANGELONE_*` credentials, run
   `scripts/fetch_angelone_instruments.py`, and set
   `ENABLE_REALTIME_FEED=true` — moves Real-Time Feed from "self-consistent
   wire-format parsing" to "proven against a real frame." Log a few raw
   frames and sanity-check the decoded price/token/timestamp first, per
   `docs/limitations.md`.
4. Run `scripts/fetch_news_rss.py` with real internet access and set
   `USE_LIVE_NEWS=true` — moves News ingestion/dedup to tier 4 (the
   cross-source near-duplicate detection added in Phase H has specifically
   never been exercised against two *real* same-story headlines from
   different outlets).
5. Set `USE_FINBERT=true` with real HuggingFace access — moves FinBERT
   sentiment from "never downloaded" to actually running, and makes
   `scripts/evaluate_finbert.py`'s agreement-rate figure meaningful for
   real headlines rather than only runnable in principle.
6. Fetch NSE's official published holiday circular and populate
   `session_calendar.NSE_HOLIDAYS` — the one gap on this list that doesn't
   need a broker/API credential, just a sourced list of dates.
7. Research Upstox's real auth/WS protocol, rate limits, and
   redistribution terms on a machine with real internet access (per
   `docs/gap-analysis-realtime-upgrade.md` §6) before any Upstox provider
   code is written — this one needs new code too, not just
   credentials.

Until each of these is actually done and the result reported back
(a log, a re-run test suite, a committed fixture), no corresponding row
above should be changed to tier 4 — including by a future phase of this
same project.
