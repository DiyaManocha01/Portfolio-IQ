"""NSE equity market session calendar.

HONESTY NOTE (read before trusting this for a demo claim):

Weekday + trading-hours logic below (9:15-3:30 IST, Monday-Friday) is the
well-established NSE equity cash-market schedule and is not in dispute.
The exchange HOLIDAY list is a different matter: this sandbox cannot reach
nseindia.com (same network constraint as nifty100.py -- verified), and a
web search for "NSE holidays 2026" turned up only third-party sites that
disagree with each other on several dates. Rather than hardcode a
holiday list that might be wrong -- which would make this module silently
claim a holiday is a trading day, or vice versa -- ``NSE_HOLIDAYS`` below
ships EMPTY. Populate it yourself from NSE's official published circular
(https://www.nseindia.com/resources/exchange-communication-holidays)
before relying on holiday-awareness for anything real; track that change
with a note in docs/limitations.md. Until then, ``is_market_open()`` is
correct for ordinary trading weekdays but will incorrectly report "open"
on an NSE holiday that falls on a weekday.
"""

from __future__ import annotations

import datetime as dt
import enum
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = dt.time(9, 15)
MARKET_CLOSE = dt.time(15, 30)

# Deliberately empty -- see module docstring. A set of `datetime.date`
# objects (IST calendar dates) on which NSE equity cash trading is closed
# despite being a weekday.
NSE_HOLIDAYS: set[dt.date] = set()


class MarketStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"
    WEEKEND = "WEEKEND"


def now_ist() -> dt.datetime:
    return dt.datetime.now(tz=IST)


def market_status(at: dt.datetime | None = None) -> MarketStatus:
    """Classifies a moment in time against the NSE equity cash-market schedule.

    ``at`` must be timezone-aware; naive datetimes are rejected rather than
    silently assumed to be IST, since that assumption has previously bitten
    this project (see docs/limitations.md network/environment notes).
    """
    moment = at if at is not None else now_ist()
    if moment.tzinfo is None:
        raise ValueError("market_status() requires a timezone-aware datetime")
    moment = moment.astimezone(IST)

    if moment.weekday() >= 5:  # Saturday=5, Sunday=6
        return MarketStatus.WEEKEND
    if moment.date() in NSE_HOLIDAYS:
        return MarketStatus.HOLIDAY
    if MARKET_OPEN <= moment.time() <= MARKET_CLOSE:
        return MarketStatus.OPEN
    return MarketStatus.CLOSED


def is_market_open(at: dt.datetime | None = None) -> bool:
    return market_status(at) == MarketStatus.OPEN
