"""In-process cache of the latest known tick per symbol.

Deliberately NOT Redis: this is a single-process FastAPI deployment (see
docs/adr/0008-realtime-market-data-angelone.md for the reasoning), so a
plain dict behind a lock is the simplest thing that's actually correct --
every writer and every reader are threads/tasks in the same process. If
this app is ever split across multiple worker processes, ticks would need
to be fanned out through something shared (Redis pub/sub or similar) --
that's a real limitation, documented rather than silently worked around.

Thread-safe (not just asyncio-safe): the upstream broker WebSocket client
runs in a background thread (see ws_connection_manager.py), so writes can
come from a non-asyncio thread while reads come from request-handling
coroutines.
"""

from __future__ import annotations

import datetime as dt
import threading

from app.services.market_data.tick_normalizer import NormalizedTick, TickStatus

_STALE_AFTER = dt.timedelta(seconds=15)


class LiveCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ticks: dict[str, NormalizedTick] = {}

    def put(self, tick: NormalizedTick) -> None:
        with self._lock:
            self._ticks[tick.symbol] = tick

    def get(self, symbol: str, now: dt.datetime | None = None) -> NormalizedTick | None:
        """Returns the latest tick for a symbol, demoting it to STALE if too old.

        Demotion happens here (at read time) rather than via a background
        timer, so "how stale is too stale" has one single definition used
        consistently by every caller, and nothing needs its own polling loop
        just to keep the cache honest.
        """
        with self._lock:
            tick = self._ticks.get(symbol)
        if tick is None:
            return None
        if tick.status != TickStatus.LIVE:
            return tick
        reference_time = tick.exchange_timestamp or tick.last_traded_time
        now = now or dt.datetime.now(tz=dt.timezone.utc)
        if reference_time is not None and (now - reference_time) > _STALE_AFTER:
            from dataclasses import replace

            return replace(tick, status=TickStatus.STALE)
        return tick

    def get_all(self, now: dt.datetime | None = None) -> dict[str, NormalizedTick]:
        with self._lock:
            symbols = list(self._ticks.keys())
        return {s: t for s in symbols if (t := self.get(s, now)) is not None}

    def clear(self) -> None:
        with self._lock:
            self._ticks.clear()


# Process-wide singleton -- every caller (the WS connection manager writing,
# the /market REST and WebSocket routes reading) shares exactly one cache.
live_cache = LiveCache()
