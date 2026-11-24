# Gap Analysis: Real Indian Stock Market Intelligence Upgrade

Written as Phase A ("Existing system audit and live data integration
verification") of the real-data upgrade requested on 2026-11-24. Everything
below was produced by actually reading the current code and docs and by
actually running the test suites in this session — not assumed from memory
of earlier phases. Every claim either cites a file/line or a command that
was actually run.

## 0. What was actually run (not assumed)

- `sudo service postgresql start`, created `portfolioiq` role/DB.
- `python3 -m venv venv && pip install -r requirements.txt` (clean, no
  torch/transformers in the base install — FinBERT stays opt-in).
- `alembic upgrade head` — 9 migrations apply cleanly, no drift.
- `python -m app.data.seed` — reproduces the documented AUC exactly:
  `logistic_regression` selected, held-out `auc_calibrated=0.545`,
  momentum baseline `auc=0.519`, majority-class `acc=0.496`.
- `python -m pytest app/tests/ -q` → **429 passed**, 0 failed.
- `npm test -- --run` (frontend) → **71 passed**, 0 failed.
- Attempted to fetch `upstox.com`'s developer docs from this session —
  **DNS resolution failed** (`getaddrinfo ENOTFOUND upstox.com`). This
  session's own sandbox cannot reach Upstox either, the same network
  restriction already documented for Yahoo Finance, Hugging Face, and
  every Angel One host (`docs/limitations.md`, ADR 0008). Upstox API
  research (auth flow, WS protocol, rate limits, licensing terms) has to
  be done by you on a machine with real internet access — I cannot verify
  any Upstox-specific claim from here, and won't guess one.

This is a materially cleaner starting point than the brief assumes: there
is no backlog of failing tests or broken migrations to fix first.

## 1. Already implemented (verified by reading the actual code, not just docs)

- **Full provider abstraction** (`app/services/market_data/providers.py`):
  `MarketDataProvider` ABC with `get_history`/`get_quote`/`get_fundamentals`,
  `DevSampleProvider` (synthetic) and `LiveYFinanceProvider` (real, cache-first)
  behind it. `get_provider(use_live: bool)` is the single swap point — adding
  a third provider means adding a class here and extending this function,
  **not** touching `MarketDataService` or anything upstream of it.
- **A separate, already-working real-time path** (Phase 24/25), fully
  distinct from the pull-based providers above:
  `ws_connection_manager.py` (owns the one upstream Angel One connection;
  asyncio task, exponential backoff 2s→60s, app-level ping/pong heartbeat
  with a 45s staleness watchdog, dedup via `exchange_timestamp` monotonic
  check) → `tick_normalizer.py` (provider dict → `NormalizedTick` +
  `TickStatus`) → `live_cache.py` (in-process, lock-guarded, demotes `LIVE`
  → `STALE` after 15s of silence) → fanned out via `GET /market/status`
  (poll) and `WS /ws/market` (~1s push, JWT-authenticated via query param,
  one upstream connection shared across all browser tabs) →
  `snapshot_service.py` persists at most one row/symbol/minute into
  `intraday_candles` during market hours only.
- **`TickStatus` already matches the brief's required enum exactly**:
  `LIVE | DELAYED | STALE | CLOSED | FIXTURE | UNAVAILABLE`
  (`tick_normalizer.py:19-30`). This did not need to be invented — it's
  already there, already wired into every response.
- **`fixture_replay_provider.py`** already gives a safe, honestly-labeled
  default (`FIXTURE`, never promoted to `LIVE`) when no broker feed is
  connected — `ENABLE_REALTIME_FEED=false` today, matching the brief's
  suggested config name exactly.
- **Session/market-hours calendar** (`session_calendar.py`): correct
  Asia/Kolkata, 9:15–15:30, Mon–Fri logic, `OPEN|CLOSED|HOLIDAY|WEEKEND`.
  Rejects naive datetimes outright rather than silently assuming IST.
- **Historical data**: `MarketDataService` + Parquet cache
  (`cache.py`) for daily OHLCV; `intraday_candles` table (separate from
  `market_data`, unique on `(stock_id, timestamp)`) for intraday. Duplicate
  prevention is a DB unique constraint, not app-level de-duping logic.
- **Fundamentals** (Phase 26): P/E, P/B(`book_value`), EPS, ROE, ROCE,
  debt/equity, dividend yield, revenue/profit growth — `FinancialMetric`
  model, provider-abstracted, `N/A`-not-fabricated discipline already
  followed (`roce` is hard-coded `None` from `LiveYFinanceProvider`, never
  guessed).
- **Screener** (`GET /screener`), filtering the tracked universe by any
  combination of the above + RSI/momentum.
- **Portfolio P&L**: invested value, current value, unrealized P&L,
  return %, realized P&L (Phase 31, from real sell transactions with
  cost-basis averaging), sector/holding allocation, risk-attribution
  (money-weight vs. risk-contribution per holding), benchmark comparison
  (NIFTY 50 buy-and-hold), drawdown series, daily/cumulative returns —
  all already implemented in `portfolio_calc.py` +
  `portfolio_performance_service.py` + `risk_attribution_service.py`.
- **Alerts** (8 types): `PRICE_THRESHOLD`, `PRICE_PCT_MOVE`,
  `VOLUME_SPIKE`, `RSI_THRESHOLD`, `SENTIMENT_CHANGE`,
  `PORTFOLIO_VOLATILITY_CHANGE`, `SECTOR_CONCENTRATION_CHANGE`,
  `FIT_RANKING_CHANGE` — evaluated every ~30s off the existing background
  loop, deduped three different ways, no new scheduler needed.
- **AI assistant** (Phase 19/32): retrieval-and-cite architecture already
  matches the brief's "must not invent, must cite data, must distinguish
  timestamps" requirements almost verbatim — it was explicitly designed
  this way from the start (`assistant_service.py:1-25`'s own docstring
  reads like a direct answer to brief section 11).
- **Market regime** (Phase 30): rule-based TRENDING_UP/DOWN/SIDEWAYS/
  HIGH_VOL/LOW_VOL classifier for NIFTY 50 or any stock.
- **Security/ops baseline** (Phase 21/34): JWT auth, bcrypt, rate limiting
  on every route (120/min default, tighter on auth/assistant), structured
  JSON logging + correlation IDs, real `/health` (DB, migrations, ML model,
  realtime feed), opt-in Sentry, `pg_dump` backup script verified
  restorable.

**Bottom line: almost everything in the brief's sections 3–11 has a real
implementation already.** The actual primary gap is narrower than the
brief assumes: it's "replace/extend one provider behind an abstraction
that already exists" and "fill in a handful of specific, identifiable
holes," not "build a real-time platform from scratch."

## 2. Implemented but not verified with genuine external data

Everything in this section runs correctly against synthetic/cached data
and is architecturally ready for real data — but no one has ever watched
it handle an actual external byte, because this sandbox (and, per §0,
this new session too) cannot reach any of these hosts.

- **`LiveYFinanceProvider`**: never executed against live Yahoo Finance
  from any sandbox session to date. Works today only against a
  pre-populated local Parquet cache.
- **Angel One SmartAPI** (ADR 0008): REST auth, WS handshake, and the
  binary tick byte-offset layout are all built from public docs, never
  tested against a real frame or a real login. Self-consistent (pack/unpack
  round-trips), not proven correct against the real wire.
- **FinBERT, real RSS news ingestion**: implemented, never executed here
  (no `transformers`/`torch` installed, no internet to Hugging Face/RSS
  hosts).
- **NSE holiday calendar**: `NSE_HOLIDAYS` is an empty set by design — see
  §4 below, this is a real functional gap, not just an unverified feature.
- **Docker Compose**: never run end-to-end from any dev sandbox to date.

## 3. A genuine bug found during this audit (not previously documented)

Reading `tick_normalizer.py` and `angelone_ws_client.py` side by side
surfaces a real mismatch that ADR 0008's "not verified against a live
frame" caveat does not by itself describe:

- `angelone_ws_client.parse_tick()` only implements **Quote mode (mode=2)**
  parsing. Angel One's own documented Quote-mode packet does **not**
  include best bid/ask price or quantity, or market depth — those require
  **SnapQuote mode (mode=3)**, which this codebase never subscribes to
  (`build_subscribe_message(..., mode=MODE_QUOTE)` is the only mode ever
  used, `ws_connection_manager.py:141`).
- But `tick_normalizer.from_angelone_ws()` reads `raw.get("best_bid_price")`
  and `raw.get("best_ask_price")` (`tick_normalizer.py:94-95`) — keys that
  `parse_tick()`'s Quote-mode dict **never contains** (confirmed: its
  return dict at `angelone_ws_client.py:117-132` has no such keys). This
  means **`bid`/`ask` on every `NormalizedTick` will always be `None`**,
  even once a real feed is connected and working perfectly — not a future
  integration risk, a logic bug that would silently under-deliver even
  after Angel One (or Upstox) is proven to work.
- Separately: `parse_tick()` *does* parse `average_traded_price` from the
  real wire bytes (offset 59, `angelone_ws_client.py:93,126`), but
  `from_angelone_ws()` never reads it into `NormalizedTick` at all — the
  data is extracted and then silently dropped before it reaches the cache,
  the API schema, or the frontend. `NormalizedTick`/`TickOut` have no ATP
  field to put it in even if it were read.
- `NormalizedTick`/`TickOut` also have no fields at all for VWAP, bid/ask
  **quantity** (only price), or a separate "data received time" distinct
  from `last_traded_time`/`exchange_timestamp` — these aren't bugs, just
  not modeled yet (see §4).

This needs fixing regardless of which broker ends up primary — it affects
Angel One too, today, independent of the Upstox decision.

## 4. Missing features (real gaps against the brief, not already covered)

- **Upstox integration**: does not exist in any form yet. New provider
  class + REST auth + WS client + wire-format parser, same shape as
  Angel One's, would be net-new code (see §3 above for the shape).
- **NSE holiday calendar is empty** (`session_calendar.py:35`) — `/market/
  status` will incorrectly report `OPEN` on an NSE holiday that falls on a
  weekday. This is the single most concrete, independently-fixable gap in
  the brief's "market schedule" section, and doesn't require any broker
  decision to fix — it needs a real, sourced holiday list (NSE's official
  circular) populated once and then a yearly refresh process.
- **"Today's P&L" is not a distinct field anywhere.** Grepped the whole
  backend for `today|day_pnl|daily_pnl` — no such concept exists.
  `holding_metrics()`/`portfolio_totals()` only ever compute **total**
  unrealized P&L (`current_value - invested_value`), never "P&L since
  yesterday's close" / "P&L since market open." The brief explicitly
  requires this be a distinct figure from total/unrealized/realized P&L
  — today it genuinely is not computed anywhere. This needs a new
  calculation (holding quantity × (current_price − previous_close), summed
  across holdings), not just relabeling an existing number.
- **Market movers beyond gainers/losers**: `MarketPage.tsx` only derives
  top 3 gainers/losers from the 20-symbol watchlist tick cache
  (`MarketPage.tsx:31-35`). No "volume leaders," no "unusual volume
  activity," no "approaching 52-week high/low" anywhere in the codebase.
- **No NIFTY BANK / NIFTY IT / SENSEX overview tiles.** Only a single NIFTY
  50 regime card exists on the Market page. No multi-index summary row.
- **No mini intraday sparkline on watchlist cards** — `TickCard` (referenced
  but not yet read in full) shows price/change/volume only, per
  `MarketPage.tsx`'s rendering; confirm exact fields in Phase B/E scoping,
  but no chart library call for a per-card sparkline was found.
- **Fundamentals metadata is row-level, not per-field.** `FinancialMetric`
  (`models/stock.py:51-79`) has one `date` and one `source` column for the
  *entire* snapshot row — the brief wants per-metric reporting period,
  source, retrieval timestamp, freshness, and availability status
  individually. Today you cannot express "P/E is fresh as of today but
  ROE is 3 months stale" — it's all-or-nothing per row.
- **No corporate events / earnings calendar at all.** Confirmed against
  the full 20-table schema in `ARCHITECTURE.md` — there is no
  `corporate_events`/`earnings` table, model, service, or route anywhere.
  Dividends/splits/bonuses/buybacks/earnings dates are entirely absent,
  not just unverified.
- **News deduplication**: `services/news/matching.py` does headline→stock
  regex matching; no explicit duplicate-article detection logic was found
  (this needs a direct code read in Phase B/G to confirm, not assumed from
  absence in docs alone).
- **Two alert types the brief wants don't exist yet**: an
  earnings-announcement alert (no earnings data to key off, see above) and
  a portfolio-drawdown-threshold alert (today's 8 types cover volatility
  and sector concentration, but not "drawdown exceeded X%" specifically).
- **No AI assistant frontend at all** — already flagged honestly in
  `docs/limitations.md`'s Phase 33 section: the backend endpoint
  (`POST /assistant/ask`) has no chat page calling it anywhere in
  `frontend/src/pages/`. The brief's section 11 sample questions assume a
  conversational UI that does not exist yet.
- **Per-endpoint rate limiting**: today it's one flat 120/min default
  across every route (already documented as a known gap in
  `docs/limitations.md`'s Phase 34 section) — an expensive endpoint like
  `/portfolio/optimize` has no tighter limit of its own.

## 5. Architectural limitations worth flagging before Phase B starts

- **In-process `live_cache`, not Redis/shared state** — correct for this
  project's single-process deployment today; would need to change if the
  app is ever split across multiple backend workers. Not a blocker for
  adding Upstox, just a ceiling noted in ADR 0008 that still applies.
- **One upstream connection per broker, chosen at startup from
  `ENABLE_REALTIME_FEED`/`ANGELONE_*`** — there's no existing concept of
  "provider A is primary, provider B is fallback" or runtime provider
  switching; `ws_connection_manager.py` is hard-wired to Angel One's auth
  and wire format specifically. Making `MARKET_DATA_PROVIDER=upstox|angelone`
  actually switch the *real-time* path (not just the pull-based
  history/quote path, which already swaps cleanly via `get_provider()`)
  means generalizing `WSConnectionManager` into something that takes a
  pluggable auth/wire-format adapter — a real design task for Phase B, not
  a trivial config flip.
- **`fit_score_snapshots` grows unboundedly** (already documented) — worth
  keeping in mind if alert evaluation frequency increases.
- **The existing rate limiter is in-memory, single-replica only** — fine
  today, a real gap the moment this is horizontally scaled.

## 6. What this means for the brief's suggested phase order

Section 15's suggested order (A: audit → B: Upstox+feed → C: historical →
D: portfolio recalc → E: charts/movers → F: benchmarks → G: fundamentals/
events → H: news/assistant → I: alerts/perf/testing) is sound and matches
how every previous phase in this project was actually run (small,
checkpointed, test-gated). Two adjustments worth agreeing on before
starting Phase B, given what this audit found:

1. **Phase B should start with the §3 bug fix** (bid/ask/ATP field
   plumbing) and the §4 holiday-calendar gap, *before* any Upstox-specific
   code — both affect the existing Angel One path today, independent of
   which broker ends up primary, and are small, well-scoped, testable
   units of work in their own right.
2. **Upstox API research (auth/WS protocol/limits/licensing) cannot be
   done from any sandbox session** (§0) — it needs to happen on your own
   machine with real internet access, the same way Angel One's scrip
   master and ADR 0008's four-broker comparison were originally done. I
   can draft the `WSConnectionManager` generalization and an Upstox
   provider class against whatever you find and report back, but I cannot
   independently verify Upstox's documented wire format, rate limits, or
   redistribution terms from here — same honesty constraint this project
   has applied to every other external host throughout its history.

## Proposed Phase A completion

Given the above, Phase A's own deliverables (per the brief's own
description: "Existing system audit and live data integration
verification") are:

1. This document.
2. The actual, fresh 429/71 passing-test baseline recorded in §0 (not
   assumed from README's prior count).
3. A short ADR (`docs/adr/0016-provider-abstraction-generalization.md`,
   written in Phase B once the Upstox facts in §0/§6.2 are in hand) laying
   out how `WSConnectionManager` generalizes to a pluggable broker
   adapter — deliberately not written yet, since it would need real
   Upstox facts to be honest rather than speculative.
4. No application code changes in Phase A — consistent with the brief's
   own instruction not to jump into modifying the project, and with
   `CLAUDE.md`'s checkpoint rule (plan, then wait for approval, before
   code).

**Phase A is otherwise complete.** Awaiting your go-ahead (and, ideally,
the Upstox facts from §0.2/§6.2 gathered on a machine with real internet
access) before Phase B begins.
