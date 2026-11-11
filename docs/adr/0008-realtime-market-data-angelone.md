# ADR 0008: Real-Time Market Data via Angel One SmartAPI (Phase 24)

**Status:** Accepted
**Date:** 2026-11-11

## Context

Phases 1-23 built the Portfolio Fit Engine, ML outlook, and analytics on
top of two existing providers (`DevSampleProvider`, synthetic;
`LiveYFinanceProvider`, real but cache-first, pull-based, daily OHLCV
only). Phase 24 is the first requirement for a genuine *real-time* feed:
live last-traded price, intraday OHLC, and volume during NSE trading
hours, pushed to the frontend, for an initial 20-symbol NSE watchlist.

### Provider selection

Four Indian broker APIs were evaluated: DhanHQ, Upstox (Market Data Feed
V3), Zerodha (Kite Connect), Angel One (SmartAPI). All four:
- require the integrator to hold their own trading/demat account with
  API access enabled (KYC, days to set up if not already held);
- license data to the account holder's own consumption, not
  redistribution to other end users of a built app -- confirmed most
  explicitly in Zerodha's terms, and consistent with NSE's own Data
  Sharing & Usage Policy, which makes NSE the sole owner of market data
  and requires separate written exchange approval for any multi-user
  commercial redistribution.
- Zerodha additionally charges ₹500/month for the Connect (live data)
  tier; DhanHQ charges ₹499+GST/month for its Data API; Upstox and Angel
  One's trading + market-data APIs are free.

**Decision: Angel One SmartAPI**, because the project owner already holds
an Angel One account with API access (the one genuinely blocking
constraint for a project on a deadline), and its terms match the other
free options on cost and technical shape (WebSocket 2.0, per-client-code
connection cap of 3, documented REST auth). This is **personal-use
integration**, not a licensed multi-tenant data redistribution service:
the running system pulls from the project owner's own Angel One account
and session credentials; it is not "any user can sign up and get live
broker data without their own account," and must not be presented or
demoed as such. This is a hard scope boundary, not a detail to relax
later without a new ADR.

### Why not the `smartapi-python` SDK

Angel One's official Python SDK (`smartapi-python` on PyPI) declares
**no license** -- no `License ::` classifier, no license field in its
PyPI metadata, and no `LICENSE` file found in its GitHub repo at the
paths checked. Per this project's rule 7 (check every dependency's
license before adding it), an unlicensed third-party package was not
added. Instead, this phase implements the REST auth flow
(`angelone_auth.py`) and the WebSocket 2.0 wire protocol
(`angelone_ws_client.py`) directly against Angel One's publicly
documented contract, using only cleanly-licensed dependencies:
`requests` (Apache-2.0, already an indirect dependency via `yfinance`,
now explicit), `websockets` (BSD-3-Clause), `pyotp` (MIT).

### Architecture

```
ws_connection_manager.py (asyncio background task, owns the ONE upstream
    connection; reconnect w/ backoff, heartbeat, dedup/out-of-order guard)
        |
        v
tick_normalizer.py (provider-native dict -> NormalizedTick, TickStatus)
        |
        v
live_cache.py (in-process, lock-guarded latest-tick-per-symbol store)
        |
        +---> /market/status (REST poll)         <- app/api/routes/market.py
        +---> /ws/market (per-client push loop)  <-'
        +---> snapshot_service.py -> intraday_candles table (periodic, market hours only)

fixture_replay_provider.py writes the SAME live_cache, tagged FIXTURE,
whenever the real feed isn't connected (no credentials, or
ENABLE_REALTIME_FEED=false) -- this is what lets /market/status and
/ws/market behave sensibly with zero setup.

instrument_registry.py resolves watchlist symbols -> Angel One tokens
from a locally-fetched scrip-master snapshot (scripts/fetch_angelone_instruments.py,
run by the project owner on a machine with real internet access -- this
sandbox cannot reach any Angel One host, verified).
```

Key decisions inside this shape:

1. **One upstream connection, fanned out server-side.** Every browser tab
   reads `live_cache` via `/ws/market`'s own per-client push loop; none of
   them touch the broker connection directly. This respects Angel One's
   3-connections-per-client-code cap regardless of how many users/tabs
   are open, and keeps broker credentials entirely server-side (never
   sent to the frontend).
2. **In-process cache, not Redis.** This is a single-process FastAPI
   deployment (see `docs/DEPLOYMENT.md`); a thread-safe dict is the
   simplest correct thing. Documented limitation: this would need to
   become something shared (Redis pub/sub or similar) if the app is ever
   split across multiple worker processes -- not done now because nothing
   requires it yet (rule: don't add infrastructure the current
   architecture doesn't need).
3. **A new `intraday_candles` table, not a widened `market_data`.**
   `market_data` (Phase 4) is unique on `(stock_id, date)` -- daily
   granularity is baked into its schema. Minute candles need
   `(stock_id, timestamp)`; reusing the daily table would either break
   that constraint or silently collapse a day's candles into one row.
4. **Explicit `TickStatus`/`CandleStatus`: `LIVE | DELAYED | STALE |
   CLOSED | FIXTURE | UNAVAILABLE`.** `live_cache.get()` itself demotes a
   `LIVE` tick to `STALE` after 15 seconds of silence -- one single
   definition of staleness, used everywhere, rather than each caller
   guessing. A `FIXTURE` tick (from `fixture_replay_provider`) is never
   promoted to `LIVE`; that's the mechanism that satisfies "never
   simulate price movement and label it live."
5. **Never persist every tick.** `snapshot_service.py` writes at most one
   row per symbol per minute, only during market hours, from whatever is
   currently in `live_cache` -- not from the WebSocket handler directly.
6. **Holiday calendar ships empty.** `session_calendar.py`'s weekday +
   9:15-15:30 IST logic is correct and uncontested; the NSE holiday list
   (`NSE_HOLIDAYS`) is deliberately left empty because this sandbox
   cannot reach nseindia.com and a web search for "NSE holidays 2026"
   turned up only disagreeing third-party sites -- hardcoding a possibly
   wrong date would be worse than an honestly-documented gap. See
   `docs/limitations.md`.

## What is verified vs. not

**Verified in this sandbox:**
- `session_calendar`, `tick_normalizer`, `live_cache`,
  `instrument_registry`, `snapshot_service`, `fixture_replay_provider`:
  unit-tested directly.
- `angelone_ws_client.parse_tick`: tested for internal self-consistency
  against a packet built with the same documented byte offsets -- this
  does **not** prove the offsets match Angel One's real wire format.
- `angelone_auth`: tested against mocked HTTP responses matching the
  documented REST contract shape -- never a real request.
- `ws_connection_manager`: reconnect/backoff/heartbeat-timeout/dedup logic
  tested with a mocked binary frame and a faked `_connect_and_stream`;
  never a real WebSocket.
- `/market/status`, `/ws/market`: tested end-to-end through FastAPI's
  `TestClient`, including JWT auth rejection.
- Full existing test suite (291 tests) still green after this phase; 2
  pre-existing `test_stress_test.py` failures are unrelated and present
  on the base branch before this phase too (not caused by Phase 24).

**NOT verified -- cannot be, from this sandbox (egress proxy rejects
every Angel One host: apiconnect.angelbroking.com,
smartapi.angelbroking.com, margincalculator.angelbroking.com,
smartapisocket.angelone.in):**
- A real login exchange.
- The real WebSocket handshake and subscription acknowledgement.
- Whether `angelone_ws_client`'s documented byte-offset layout actually
  matches a live tick frame.
- The scrip-master URL in `scripts/fetch_angelone_instruments.py`
  (community-forum-sourced, not found in official docs).
- End-to-end real-time price flow into `/ws/market`.

Running this against the real feed requires the project owner's Angel
One credentials in a local `.env` (never committed) and running
`scripts/fetch_angelone_instruments.py` once on a machine with internet
access. Until then, `ENABLE_REALTIME_FEED=false` (the default) keeps the
app exactly as it behaved before this phase, and `/market/status` /
`/ws/market` serve honestly-labeled `FIXTURE` data instead of erroring.
