import datetime as dt

from app.models.intraday_candle import CandleStatus, IntradayCandle
from app.services.market_data.live_cache import LiveCache
from app.services.market_data.snapshot_service import snapshot_cache, snapshot_tick
from app.services.market_data.tick_normalizer import NormalizedTick, TickStatus


def _ohlc_tick(symbol="RELIANCE", minute=None):
    minute = minute or dt.datetime.now(tz=dt.timezone.utc).replace(second=0, microsecond=0)
    return NormalizedTick(
        symbol=symbol,
        exchange="NSE",
        price=100.0,
        previous_close=99.0,
        change=1.0,
        change_pct=1.01,
        open=99.5,
        high=101.0,
        low=99.0,
        close=99.0,
        volume=1000,
        last_traded_time=minute,
        exchange_timestamp=minute,
        bid=None,
        ask=None,
        status=TickStatus.LIVE,
        source="ANGELONE",
    )


def test_snapshot_tick_creates_row(db_session):
    tick = _ohlc_tick(symbol="RELIANCE")
    candle = snapshot_tick(db_session, tick)
    assert candle is not None
    assert candle.status == CandleStatus.LIVE
    assert candle.open == 99.5


def test_snapshot_tick_without_ohlc_returns_none(db_session):
    tick = _ohlc_tick(symbol="RELIANCE")
    bare_ltp_tick = tick.__class__(**{**tick.__dict__, "open": None, "high": None, "low": None})
    assert snapshot_tick(db_session, bare_ltp_tick) is None


def test_snapshot_tick_upserts_same_minute(db_session):
    minute = dt.datetime.now(tz=dt.timezone.utc).replace(second=0, microsecond=0)
    first = _ohlc_tick(symbol="TCS", minute=minute)
    second = first.__class__(**{**first.__dict__, "high": 105.0, "low": 95.0, "price": 102.0, "close": 102.0})

    snapshot_tick(db_session, first)
    snapshot_tick(db_session, second)

    rows = (
        db_session.query(IntradayCandle)
        .join(IntradayCandle.stock)
        .filter(IntradayCandle.timestamp == minute)
        .all()
    )
    matching = [r for r in rows if r.stock.symbol == "TCS"]
    assert len(matching) == 1
    assert matching[0].high == 105.0
    assert matching[0].low == 95.0
    assert matching[0].close == 102.0


def test_snapshot_cache_writes_all_symbols(db_session):
    cache = LiveCache()
    cache.put(_ohlc_tick(symbol="RELIANCE"))
    cache.put(_ohlc_tick(symbol="TCS"))
    written = snapshot_cache(db_session, cache)
    assert written == 2
