"""Resampling and gap detection over stored 1-minute intraday candles.

Real Indian Stock Market Intelligence upgrade, Phase C. Both functions are
pure (no DB/network access) and operate on whatever rows are already
in ``intraday_candles`` -- this module never fetches, backfills, or
fabricates a candle; it only aggregates/audits what ``snapshot_service.py``
has already written. A sparse or empty input simply produces a sparse or
empty output, never an invented bar.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

# Supported output intervals and their minute width. "1m" is a pass-through
# (no aggregation needed) but listed here so callers validate against one
# single source of truth rather than hardcoding the allowed set twice.
ALLOWED_INTERVALS: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
}

# NSE equity cash session, matching app.services.market_data.session_calendar.
SESSION_START = dt.time(9, 15)
SESSION_END = dt.time(15, 30)


class CandleLike(Protocol):
    timestamp: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    status: object  # an enum member; carried through untouched, never reinterpreted


def _bucket_start(ts: dt.datetime, interval_minutes: int) -> dt.datetime:
    """Floors ``ts`` to the start of its interval bucket, anchored to midnight.

    Session hours don't always divide evenly into every supported interval
    (9:15 is a multiple of 5 and 15 minutes, but not of 30 or 60) -- the
    first bucket of a trading day can legitimately be partial (e.g. a 1h
    bucket starting at 9:00 but only containing 9:15-9:59 data). This is
    standard resampling behavior, not a bug; see docs/limitations.md.
    """
    minute_of_day = ts.hour * 60 + ts.minute
    bucket_start_minute = (minute_of_day // interval_minutes) * interval_minutes
    return ts.replace(hour=bucket_start_minute // 60, minute=bucket_start_minute % 60, second=0, microsecond=0)


def resample_candles(rows: list[CandleLike], interval: str) -> list[dict]:
    """Aggregates 1-minute ``rows`` (sorted ascending by timestamp) into
    ``interval`` bars (open=first, high=max, low=min, close=last,
    volume=sum). Each output bar's ``status`` is the LAST input row's
    status within that bucket -- i.e. "how fresh/trustworthy was the most
    recent data contributing to this bar", not some aggregate of statuses
    that wouldn't mean anything.

    Raises ValueError for an unknown interval rather than silently falling
    back to one -- an unrecognized interval string is a caller bug, not a
    case to guess through.
    """
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"Unknown interval '{interval}' -- must be one of {sorted(ALLOWED_INTERVALS)}")
    width = ALLOWED_INTERVALS[interval]
    if width == 1 or not rows:
        return [
            {
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "status": r.status,
            }
            for r in rows
        ]

    buckets: dict[dt.datetime, list[CandleLike]] = {}
    order: list[dt.datetime] = []
    for r in rows:
        key = _bucket_start(r.timestamp, width)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)

    out = []
    for key in order:
        members = buckets[key]
        out.append(
            {
                "timestamp": key,
                "open": members[0].open,
                "high": max(m.high for m in members),
                "low": min(m.low for m in members),
                "close": members[-1].close,
                "volume": sum(m.volume for m in members),
                "status": members[-1].status,
            }
        )
    return out


def detect_gaps(rows: list[CandleLike], max_samples: int = 20) -> tuple[int, list[dt.datetime]]:
    """Finds 1-minute marks within NSE session hours, between the first and
    last row's own dates, that have no candle row.

    Returns (total_gap_count, first ``max_samples`` gap timestamps) --
    bounded so a badly-gapped symbol doesn't blow up the API response size.
    An empty or single-row input has nothing to compare against and
    reports 0 gaps, not an error.
    """
    if len(rows) < 2:
        return 0, []

    present = {r.timestamp for r in rows}
    start = rows[0].timestamp
    end = rows[-1].timestamp

    gaps: list[dt.datetime] = []
    total = 0
    one_minute = dt.timedelta(minutes=1)
    cursor = start
    while cursor <= end:
        # Only minutes within session hours on a weekday are "expected" to
        # have a candle -- walking strictly from the first to the last
        # observed row (not the whole calendar day) means a feed that
        # started mid-session, or hasn't reached market close yet, is
        # never scored against minutes that were never due in the first
        # place. A real NSE holiday falling inside this range would still
        # be wrongly counted as gaps -- see docs/limitations.md's existing
        # empty-holiday-calendar caveat, which this function inherits.
        if cursor.weekday() < 5 and SESSION_START <= cursor.time() <= SESSION_END:
            if cursor not in present:
                total += 1
                if len(gaps) < max_samples:
                    gaps.append(cursor)
        cursor += one_minute
    return total, gaps
