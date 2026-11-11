"""Populates live_cache from existing cached/synthetic data when there's no
real broker connection -- i.e. whenever ENABLE_REALTIME_FEED is false, or
it's true but credentials/instrument tokens aren't ready yet.

Deliberately does NOT fabricate intraday price movement: it exposes
exactly the same close price ``MarketDataService.get_quote()`` already
returns (DevSampleProvider's synthetic series, or LiveYFinanceProvider's
cached history), tagged ``TickStatus.FIXTURE``. That is a real, if
non-live, number honestly labeled -- never an invented live tick. This is
what satisfies "never simulate price movement and label it live" for the
offline/demo path the same way the live path satisfies it by only ever
writing to the cache from an actual provider tick.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from app.services.market_data.live_cache import LiveCache
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import from_fixture
from app.services.market_data.watchlist import WATCHLIST_SYMBOLS

logger = logging.getLogger("portfolioiq.market_data.fixture")


def refresh_once(db: Session, cache: LiveCache, symbols: list[str] | None = None) -> int:
    """Writes one FIXTURE tick per symbol into ``cache``. Returns count written."""
    market_data = MarketDataService(db)
    symbols = symbols if symbols is not None else WATCHLIST_SYMBOLS
    now = dt.datetime.now(tz=dt.timezone.utc)
    written = 0
    for symbol in symbols:
        try:
            stock = market_data.get_or_create_stock(symbol)
            latest, previous = market_data.get_quote(stock)
        except Exception as exc:  # noqa: BLE001 -- one bad symbol shouldn't block the rest
            logger.warning("fixture refresh: could not get a quote for %s: %s", symbol, exc)
            continue
        tick = from_fixture(
            symbol=symbol,
            exchange="NSE",
            price=latest.close,
            previous_close=previous.close if previous else None,
            as_of=now,
        )
        cache.put(tick)
        written += 1
    return written
