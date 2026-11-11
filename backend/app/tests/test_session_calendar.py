import datetime as dt

import pytest

from app.services.market_data import session_calendar
from app.services.market_data.session_calendar import IST, MarketStatus, market_status


def _ist(y, m, d, h, mi):
    return dt.datetime(y, m, d, h, mi, tzinfo=IST)


def test_open_during_trading_hours():
    # Wednesday 2026-10-21, 11:00 IST
    assert market_status(_ist(2026, 10, 21, 11, 0)) == MarketStatus.OPEN


def test_open_at_exact_boundaries():
    assert market_status(_ist(2026, 10, 21, 9, 15)) == MarketStatus.OPEN
    assert market_status(_ist(2026, 10, 21, 15, 30)) == MarketStatus.OPEN


def test_closed_before_open():
    assert market_status(_ist(2026, 10, 21, 9, 14)) == MarketStatus.CLOSED


def test_closed_after_close():
    assert market_status(_ist(2026, 10, 21, 15, 31)) == MarketStatus.CLOSED


def test_weekend_saturday():
    # 2026-10-24 is a Saturday
    assert market_status(_ist(2026, 10, 24, 11, 0)) == MarketStatus.WEEKEND


def test_weekend_sunday():
    # 2026-10-25 is a Sunday
    assert market_status(_ist(2026, 10, 25, 11, 0)) == MarketStatus.WEEKEND


def test_holiday_overrides_weekday_open_hours(monkeypatch):
    holiday = dt.date(2026, 10, 21)
    monkeypatch.setattr(session_calendar, "NSE_HOLIDAYS", {holiday})
    assert market_status(_ist(2026, 10, 21, 11, 0)) == MarketStatus.HOLIDAY


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        market_status(dt.datetime(2026, 10, 21, 11, 0))


def test_is_market_open_wraps_status(monkeypatch):
    holiday = dt.date(2026, 10, 21)
    monkeypatch.setattr(session_calendar, "NSE_HOLIDAYS", set())
    assert session_calendar.is_market_open(_ist(2026, 10, 21, 11, 0)) is True
    monkeypatch.setattr(session_calendar, "NSE_HOLIDAYS", {holiday})
    assert session_calendar.is_market_open(_ist(2026, 10, 21, 11, 0)) is False


def test_timezone_conversion_from_utc():
    # 2026-10-21 05:00 UTC == 10:30 IST -- should be OPEN
    utc_time = dt.datetime(2026, 10, 21, 5, 0, tzinfo=dt.timezone.utc)
    assert market_status(utc_time) == MarketStatus.OPEN
