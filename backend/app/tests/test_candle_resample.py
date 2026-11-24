import datetime as dt
from dataclasses import dataclass

import pytest

from app.services.market_data.candle_resample import ALLOWED_INTERVALS, detect_gaps, resample_candles


@dataclass
class _Candle:
    timestamp: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    status: str = "LIVE"


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _minute(hour: int, minute: int, day: int = 11) -> dt.datetime:
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=IST)


def test_resample_1m_is_passthrough():
    rows = [_Candle(_minute(9, 15), 100, 101, 99, 100.5, 1000)]
    out = resample_candles(rows, "1m")
    assert out == [
        {"timestamp": _minute(9, 15), "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "status": "LIVE"}
    ]


def test_resample_5m_aggregates_ohlcv_correctly():
    # Five consecutive 1-minute candles, 9:15-9:19, all in the same 5m bucket (9:15 is a multiple of 5).
    rows = [
        _Candle(_minute(9, 15), open=100, high=102, low=99, close=101, volume=100, status="LIVE"),
        _Candle(_minute(9, 16), open=101, high=103, low=100, close=102, volume=150, status="LIVE"),
        _Candle(_minute(9, 17), open=102, high=104, low=101, close=103, volume=200, status="LIVE"),
        _Candle(_minute(9, 18), open=103, high=103.5, low=98, close=99, volume=50, status="LIVE"),
        _Candle(_minute(9, 19), open=99, high=100, low=97, close=99.5, volume=300, status="STALE"),
    ]
    out = resample_candles(rows, "5m")
    assert len(out) == 1
    bar = out[0]
    assert bar["timestamp"] == _minute(9, 15)
    assert bar["open"] == 100       # first row's open
    assert bar["high"] == 104       # max high across all 5
    assert bar["low"] == 97         # min low across all 5
    assert bar["close"] == 99.5     # last row's close
    assert bar["volume"] == 100 + 150 + 200 + 50 + 300
    assert bar["status"] == "STALE"  # last row's own status, not an aggregate


def test_resample_splits_across_bucket_boundary():
    rows = [
        _Candle(_minute(9, 19), 10, 10, 10, 10, 1),  # last minute of the 9:15 5m bucket
        _Candle(_minute(9, 20), 20, 20, 20, 20, 2),  # first minute of the next 5m bucket
    ]
    out = resample_candles(rows, "5m")
    assert len(out) == 2
    assert out[0]["timestamp"] == _minute(9, 15)
    assert out[1]["timestamp"] == _minute(9, 20)


def test_resample_unknown_interval_raises():
    with pytest.raises(ValueError):
        resample_candles([_Candle(_minute(9, 15), 1, 1, 1, 1, 1)], "7m")


def test_resample_empty_input_returns_empty():
    assert resample_candles([], "5m") == []


def test_all_allowed_intervals_are_handled_without_error():
    rows = [_Candle(_minute(h, m), 1, 1, 1, 1, 1) for h in (9, 10) for m in (0, 15, 30, 45)]
    for interval in ALLOWED_INTERVALS:
        resample_candles(rows, interval)  # must not raise


def test_detect_gaps_finds_missing_minutes():
    rows = [
        _Candle(_minute(9, 15), 1, 1, 1, 1, 1),
        _Candle(_minute(9, 16), 1, 1, 1, 1, 1),
        # 9:17, 9:18 missing
        _Candle(_minute(9, 19), 1, 1, 1, 1, 1),
    ]
    count, samples = detect_gaps(rows)
    assert count == 2
    assert samples == [_minute(9, 17), _minute(9, 18)]


def test_detect_gaps_no_gaps_when_contiguous():
    rows = [_Candle(_minute(9, 15 + i), 1, 1, 1, 1, 1) for i in range(5)]
    count, samples = detect_gaps(rows)
    assert count == 0
    assert samples == []


def test_detect_gaps_single_row_reports_nothing():
    count, samples = detect_gaps([_Candle(_minute(9, 15), 1, 1, 1, 1, 1)])
    assert count == 0
    assert samples == []


def test_detect_gaps_is_bounded_by_max_samples():
    # Only the open+close minute present -- the whole session in between is "missing".
    rows = [_Candle(_minute(9, 15), 1, 1, 1, 1, 1), _Candle(_minute(15, 30), 1, 1, 1, 1, 1)]
    count, samples = detect_gaps(rows, max_samples=5)
    assert count > 5
    assert len(samples) == 5
