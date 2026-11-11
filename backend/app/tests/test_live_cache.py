import datetime as dt

from app.services.market_data.live_cache import LiveCache
from app.services.market_data.tick_normalizer import TickStatus, from_angelone_ws


def _tick(symbol="RELIANCE", exchange_timestamp_ms=None, status=TickStatus.LIVE):
    raw = {
        "last_traded_price": 100.0,
        "close_price": 99.0,
        "exchange_timestamp": exchange_timestamp_ms,
        "last_traded_timestamp": exchange_timestamp_ms,
    }
    tick = from_angelone_ws(raw, symbol=symbol, exchange="NSE", status=status)
    return tick


def test_put_and_get_roundtrip():
    cache = LiveCache()
    now_ms = int(dt.datetime.now(tz=dt.timezone.utc).timestamp() * 1000)
    cache.put(_tick(exchange_timestamp_ms=now_ms))
    fetched = cache.get("RELIANCE")
    assert fetched is not None
    assert fetched.status == TickStatus.LIVE


def test_get_unknown_symbol_returns_none():
    cache = LiveCache()
    assert cache.get("NOPE") is None


def test_live_tick_demoted_to_stale_after_timeout():
    cache = LiveCache()
    old_ms = int((dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(seconds=60)).timestamp() * 1000)
    cache.put(_tick(exchange_timestamp_ms=old_ms))
    fetched = cache.get("RELIANCE")
    assert fetched.status == TickStatus.STALE


def test_non_live_status_never_demoted():
    cache = LiveCache()
    old_ms = int((dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(seconds=60)).timestamp() * 1000)
    cache.put(_tick(exchange_timestamp_ms=old_ms, status=TickStatus.FIXTURE))
    fetched = cache.get("RELIANCE")
    assert fetched.status == TickStatus.FIXTURE


def test_get_all_returns_every_symbol():
    cache = LiveCache()
    now_ms = int(dt.datetime.now(tz=dt.timezone.utc).timestamp() * 1000)
    cache.put(_tick(symbol="RELIANCE", exchange_timestamp_ms=now_ms))
    cache.put(_tick(symbol="TCS", exchange_timestamp_ms=now_ms))
    all_ticks = cache.get_all()
    assert set(all_ticks.keys()) == {"RELIANCE", "TCS"}


def test_clear_empties_cache():
    cache = LiveCache()
    now_ms = int(dt.datetime.now(tz=dt.timezone.utc).timestamp() * 1000)
    cache.put(_tick(exchange_timestamp_ms=now_ms))
    cache.clear()
    assert cache.get("RELIANCE") is None
