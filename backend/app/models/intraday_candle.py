"""Phase 24: persisted intraday (minute) candles from the real-time feed.

Kept as its own table rather than widening ``market_data`` (Phase 4's
daily-OHLCV table, unique on (stock_id, date)) -- intraday granularity is
a different concept with a different natural key (stock_id, timestamp),
and reusing a Date-keyed unique constraint for minute data would either
break it or silently collapse a day's candles into one row. See
docs/adr/0008-realtime-market-data-angelone.md.

Per the Phase 24 instruction not to persist every tick: rows here are
written by a periodic snapshot of the live cache (one row per symbol per
minute during market hours), not one row per WebSocket message.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class CandleStatus(str, enum.Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    CLOSED = "CLOSED"
    FIXTURE = "FIXTURE"
    UNAVAILABLE = "UNAVAILABLE"


class IntradayCandle(Base):
    __tablename__ = "intraday_candles"
    __table_args__ = (UniqueConstraint("stock_id", "timestamp", name="uq_intraday_candles_stock_timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="ANGELONE")
    status: Mapped[CandleStatus] = mapped_column(
        Enum(CandleStatus, name="intraday_candle_status"), default=CandleStatus.UNAVAILABLE
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821 -- Stock imported via app.models package init
