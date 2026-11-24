import datetime as dt

from app.services.market_data.market_movers_service import compute_movers
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import TickStatus, from_fixture


def _tick(symbol, price, previous_close, volume=None, as_of=None):
    tick = from_fixture(
        symbol=symbol,
        exchange="NSE",
        price=price,
        previous_close=previous_close,
        as_of=as_of or dt.datetime.now(tz=dt.timezone.utc),
    )
    if volume is not None:
        from dataclasses import replace

        tick = replace(tick, volume=volume, status=TickStatus.LIVE)
    return tick


class _FakeMarketDataShortHistory:
    """DevSampleProvider auto-generates a full synthetic history for ANY
    symbol on first access (existing, correct behavior -- not something
    this test should fight), so the short-history guard in
    market_movers_service._row_for_tick can't be exercised through a real
    MarketDataService with a merely-unfamiliar symbol. Isolate it instead
    with a fake that reports too little history, directly."""

    def get_or_create_stock(self, symbol):
        return type("FakeStock", (), {"symbol": symbol})()

    def get_history(self, stock, days):
        return []  # fewer than MIN_HISTORY_DAYS


def test_movers_excludes_symbol_with_insufficient_history():
    from app.services.market_data.market_movers_service import _row_for_tick

    tick = _tick("ZZZNOTREAL", price=100.0, previous_close=99.0)
    assert _row_for_tick(_FakeMarketDataShortHistory(), tick) is None


def test_movers_gainers_losers_work_without_volume(db_session):
    # TCS is seeded with ~287 days of history (app/data/seed.py) -- enough
    # for the 52-week window regardless of today's tick having volume.
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("TCS")
    history = market_data.get_history(stock, days=5)
    assert len(history) >= 1, "expected seeded TCS history to exist"
    current_price = history[-1].close

    # A FIXTURE tick never carries volume -- the real bug this test guards
    # against (found during the real-data-upgrade Phase E audit): movers
    # must still populate from price alone in this, the default, mode.
    tick = _tick("TCS", price=current_price * 1.05, previous_close=current_price, volume=None)
    result = compute_movers(market_data, [tick])
    assert result["universe_size"] == 1
    assert result["gainers"][0]["symbol"] == "TCS"
    assert result["gainers"][0]["volume"] is None
    assert result["gainers"][0]["volume_ratio"] is None
    assert result["volume_leaders"] == []  # correctly excluded, not crashed


def test_movers_unusual_volume_and_volume_leaders_need_real_volume(db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("RELIANCE")
    history = market_data.get_history(stock, days=5)
    current_price = history[-1].close

    tick = _tick("RELIANCE", price=current_price, previous_close=current_price, volume=50_000_000)
    result = compute_movers(market_data, [tick])
    assert result["volume_leaders"][0]["symbol"] == "RELIANCE"
    assert result["volume_leaders"][0]["volume"] == 50_000_000
    # 50M is almost certainly >= 2x this symbol's own 20-day average on
    # seeded synthetic data (~2-3M/day) -- confirm it lands in unusual_volume.
    assert any(r["symbol"] == "RELIANCE" for r in result["unusual_volume"])


def test_movers_near_52w_high_and_low(db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("ITC")
    history = market_data.get_history(stock, days=252)
    highs = [b.high for b in history]
    week52_high = max(highs)

    # Price pinned exactly at the 252-day high -- must appear in near_52w_high.
    tick = _tick("ITC", price=week52_high, previous_close=week52_high)
    result = compute_movers(market_data, [tick])
    assert any(r["symbol"] == "ITC" for r in result["near_52w_high"])


def test_movers_top_n_is_respected(db_session):
    market_data = MarketDataService(db_session)
    symbols = ["TCS", "RELIANCE", "HDFCBANK", "INFY", "ICICIBANK", "LT", "ITC"]
    ticks = []
    for i, sym in enumerate(symbols):
        stock = market_data.get_or_create_stock(sym)
        price = market_data.get_history(stock, days=5)[-1].close
        ticks.append(_tick(sym, price=price * (1 + 0.01 * i), previous_close=price))

    result = compute_movers(market_data, ticks, top_n=3)
    assert len(result["gainers"]) <= 3
    assert len(result["losers"]) <= 3
    assert result["universe_scope"] == "watchlist"
    assert result["universe_size"] == len(symbols)
