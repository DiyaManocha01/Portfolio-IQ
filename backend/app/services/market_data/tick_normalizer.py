"""Normalizes raw provider payloads into PortfolioIQ's internal tick schema.

Deliberately decoupled from any one provider's wire format: callers (e.g.
``angelone_ws_client``) parse their provider's raw bytes/JSON into a plain
dict with provider-native field names, and the ``from_*`` functions here do
the one normalization step. This is what keeps this module unit-testable
without a live WebSocket connection, and what would let a second broker be
added later (Phase 24's provider-abstraction goal) without touching the
connection-manager or cache code downstream.
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass


class TickStatus(str, enum.Enum):
    """How much to trust a price shown to the user -- see Phase 24 scope.

    A cached or fixture value must never be presented as LIVE.
    """

    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    CLOSED = "CLOSED"
    FIXTURE = "FIXTURE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class NormalizedTick:
    symbol: str
    exchange: str
    price: float
    previous_close: float | None
    change: float | None
    change_pct: float | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    last_traded_time: dt.datetime | None
    exchange_timestamp: dt.datetime | None
    bid: float | None
    ask: float | None
    status: TickStatus
    source: str


def _pct_change(price: float, previous_close: float | None) -> float | None:
    if not previous_close:
        return None
    return round((price - previous_close) / previous_close * 100, 4)


def from_angelone_ws(
    raw: dict,
    symbol: str,
    exchange: str,
    status: TickStatus = TickStatus.LIVE,
) -> NormalizedTick:
    """Normalizes a parsed Angel One WebSocket 2.0 tick dict.

    ``raw`` is expected to already be parsed out of the provider's binary
    frame (see ``angelone_ws_client.parse_tick``) into these provider-native
    keys -- this function does NOT touch raw bytes.
    """
    price = float(raw["last_traded_price"])
    previous_close = raw.get("close_price")
    previous_close = float(previous_close) if previous_close else None
    change = (price - previous_close) if previous_close is not None else None

    ltt = raw.get("last_traded_timestamp")
    exch_ts = raw.get("exchange_timestamp")

    return NormalizedTick(
        symbol=symbol,
        exchange=exchange,
        price=price,
        previous_close=previous_close,
        change=round(change, 2) if change is not None else None,
        change_pct=_pct_change(price, previous_close),
        open=_opt_float(raw.get("open_price_of_the_day")),
        high=_opt_float(raw.get("high_price_of_the_day")),
        low=_opt_float(raw.get("low_price_of_the_day")),
        close=previous_close,
        volume=_opt_int(raw.get("volume_trade_for_the_day")),
        last_traded_time=_from_epoch(ltt),
        exchange_timestamp=_from_epoch(exch_ts),
        bid=_opt_float(raw.get("best_bid_price")),
        ask=_opt_float(raw.get("best_ask_price")),
        status=status,
        source="ANGELONE",
    )


def from_fixture(
    symbol: str,
    exchange: str,
    price: float,
    previous_close: float | None,
    as_of: dt.datetime,
) -> NormalizedTick:
    """Normalizes a replayed/fixture bar -- always tagged FIXTURE, never LIVE."""
    return NormalizedTick(
        symbol=symbol,
        exchange=exchange,
        price=price,
        previous_close=previous_close,
        change=round(price - previous_close, 2) if previous_close else None,
        change_pct=_pct_change(price, previous_close),
        open=None,
        high=None,
        low=None,
        close=previous_close,
        volume=None,
        last_traded_time=as_of,
        exchange_timestamp=as_of,
        bid=None,
        ask=None,
        status=TickStatus.FIXTURE,
        source="FIXTURE",
    )


def _opt_float(value) -> float | None:
    return float(value) if value is not None else None


def _opt_int(value) -> int | None:
    return int(value) if value is not None else None


def _from_epoch(value) -> dt.datetime | None:
    """Angel One timestamps are epoch milliseconds in its WS 2.0 payloads."""
    if value is None:
        return None
    try:
        return dt.datetime.fromtimestamp(float(value) / 1000, tz=dt.timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None
