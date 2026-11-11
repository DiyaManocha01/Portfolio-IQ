"""Periodically persists the live cache into intraday_candles.

Deliberately NOT one row per WebSocket tick -- that would grow the table
unboundedly for no real benefit (Phase 24 explicitly calls out avoiding
this). Called on a fixed interval (see `main.py`'s background task) and
writes at most one row per symbol per call; callers decide the interval
(the running system uses 60s, during market hours only).
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from app.models.intraday_candle import CandleStatus, IntradayCandle
from app.services.market_data.live_cache import LiveCache
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import NormalizedTick, TickStatus

logger = logging.getLogger("portfolioiq.market_data.snapshot")

_STATUS_MAP = {
    TickStatus.LIVE: CandleStatus.LIVE,
    TickStatus.DELAYED: CandleStatus.DELAYED,
    TickStatus.STALE: CandleStatus.STALE,
    TickStatus.CLOSED: CandleStatus.CLOSED,
    TickStatus.FIXTURE: CandleStatus.FIXTURE,
    TickStatus.UNAVAILABLE: CandleStatus.UNAVAILABLE,
}


def snapshot_tick(db: Session, tick: NormalizedTick) -> IntradayCandle | None:
    """Upserts one candle row for ``tick``'s symbol at the current minute.

    Returns None (and writes nothing) for a tick with no usable OHLC --
    a bare LTP-only tick isn't a candle, it's a point price, and faking
    open=high=low=close=price would misrepresent intraday range data that
    was never actually observed.
    """
    if tick.open is None or tick.high is None or tick.low is None:
        return None

    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(tick.symbol)

    minute = (tick.exchange_timestamp or tick.last_traded_time or dt.datetime.now(tz=dt.timezone.utc)).replace(
        second=0, microsecond=0
    )

    existing = (
        db.query(IntradayCandle)
        .filter(IntradayCandle.stock_id == stock.id, IntradayCandle.timestamp == minute)
        .first()
    )
    close_price = tick.close if tick.close is not None else tick.price
    if existing:
        existing.close = close_price
        existing.high = max(existing.high, tick.high)
        existing.low = min(existing.low, tick.low)
        existing.volume = tick.volume or existing.volume
        existing.status = _STATUS_MAP[tick.status]
        candle = existing
    else:
        candle = IntradayCandle(
            stock_id=stock.id,
            timestamp=minute,
            open=tick.open,
            high=tick.high,
            low=tick.low,
            close=close_price,
            volume=tick.volume or 0,
            source=tick.source,
            status=_STATUS_MAP[tick.status],
        )
        db.add(candle)
    db.commit()
    return candle


def snapshot_cache(db: Session, cache: LiveCache) -> int:
    """Snapshots every symbol currently in ``cache``. Returns rows written/updated."""
    written = 0
    for tick in cache.get_all().values():
        try:
            if snapshot_tick(db, tick) is not None:
                written += 1
        except Exception as exc:  # noqa: BLE001 -- one bad symbol shouldn't abort the batch
            logger.warning("snapshot failed for %s: %s", tick.symbol, exc)
            db.rollback()
    return written
