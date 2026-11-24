import datetime as dt

from app.services.market_data.tick_normalizer import TickStatus, from_angelone_ws, from_fixture


def test_from_angelone_ws_computes_change_and_pct():
    raw = {
        "last_traded_price": 2960.50,
        "close_price": 2950.0,
        "open_price_of_the_day": 2951.0,
        "high_price_of_the_day": 2965.0,
        "low_price_of_the_day": 2948.0,
        "volume_trade_for_the_day": 1_234_567,
        "average_traded_price": 2958.25,
        "last_traded_timestamp": 1_700_000_000_000,
        "exchange_timestamp": 1_700_000_000_500,
    }
    before = dt.datetime.now(tz=dt.timezone.utc)
    tick = from_angelone_ws(raw, symbol="RELIANCE", exchange="NSE")
    after = dt.datetime.now(tz=dt.timezone.utc)

    assert tick.symbol == "RELIANCE"
    assert tick.price == 2960.50
    assert tick.previous_close == 2950.0
    assert tick.change == 10.5
    assert tick.change_pct == round(10.5 / 2950.0 * 100, 4)
    assert tick.volume == 1_234_567
    assert tick.status == TickStatus.LIVE
    assert tick.source == "ANGELONE"
    assert tick.last_traded_time == dt.datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=dt.timezone.utc)
    # average_traded_price IS present in Angel One's Quote-mode packet and
    # must be wired through, not silently dropped (a real bug found and
    # fixed during the Phase B audit -- see docs/gap-analysis-realtime-upgrade.md).
    assert tick.average_traded_price == 2958.25
    # bid/ask/bid_qty/ask_qty/vwap are never present in Quote-mode (mode=2)
    # packets -- honestly None, never fabricated, until SnapQuote (mode=3)
    # support is added.
    assert tick.bid is None
    assert tick.ask is None
    assert tick.bid_qty is None
    assert tick.ask_qty is None
    assert tick.vwap is None
    # data_received_at is assigned at normalization time (not from the
    # provider payload) -- just assert it's a real, current timestamp.
    assert before <= tick.data_received_at <= after


def test_from_angelone_ws_missing_previous_close():
    raw = {"last_traded_price": 100.0, "close_price": None}
    tick = from_angelone_ws(raw, symbol="X", exchange="NSE")
    assert tick.previous_close is None
    assert tick.change is None
    assert tick.change_pct is None


def test_from_angelone_ws_bad_timestamp_returns_none():
    raw = {
        "last_traded_price": 100.0,
        "close_price": 100.0,
        "last_traded_timestamp": "not-a-number",
        "exchange_timestamp": "not-a-number",
    }
    tick = from_angelone_ws(raw, symbol="X", exchange="NSE")
    assert tick.last_traded_time is None
    assert tick.exchange_timestamp is None


def test_from_fixture_is_always_tagged_fixture():
    now = dt.datetime(2026, 10, 21, 10, 0, tzinfo=dt.timezone.utc)
    tick = from_fixture(symbol="TCS", exchange="NSE", price=3450.0, previous_close=3400.0, as_of=now)
    assert tick.status == TickStatus.FIXTURE
    assert tick.source == "FIXTURE"
    assert tick.change == 50.0
    assert tick.last_traded_time == now
    assert tick.average_traded_price is None
    assert tick.vwap is None
    assert tick.bid is None and tick.ask is None
    assert tick.bid_qty is None and tick.ask_qty is None
    assert tick.data_received_at is not None


def test_from_fixture_no_previous_close():
    now = dt.datetime(2026, 10, 21, 10, 0, tzinfo=dt.timezone.utc)
    tick = from_fixture(symbol="TCS", exchange="NSE", price=3450.0, previous_close=None, as_of=now)
    assert tick.change is None
    assert tick.change_pct is None
