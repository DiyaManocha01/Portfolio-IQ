import datetime as dt

from app.models.intraday_candle import CandleStatus, IntradayCandle
from app.services.market_data.live_cache import live_cache
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import from_fixture


def test_market_status_returns_200_shape(client):
    resp = client.get("/market/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["market_status"] in {"OPEN", "CLOSED", "HOLIDAY", "WEEKEND"}
    assert body["feed_status"] in {"DISABLED", "MISCONFIGURED", "CONNECTING", "CONNECTED", "RECONNECTING", "STOPPED"}
    assert "ticks" in body


def test_market_status_includes_cached_ticks(client):
    import datetime as dt

    live_cache.put(
        from_fixture(
            symbol="RELIANCE",
            exchange="NSE",
            price=2950.0,
            previous_close=2940.0,
            as_of=dt.datetime.now(tz=dt.timezone.utc),
        )
    )
    resp = client.get("/market/status")
    body = resp.json()
    symbols = [t["symbol"] for t in body["ticks"]]
    assert "RELIANCE" in symbols
    live_cache.clear()


def test_candles_empty_when_none_snapshotted(client, auth_headers):
    resp = client.get("/market/candles/WIPRO", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "WIPRO"
    assert body["candles"] == []


def test_candles_unknown_symbol_returns_empty_not_404(client, auth_headers):
    resp = client.get("/market/candles/NOTREAL", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["candles"] == []


def test_candles_returns_snapshotted_rows(client, auth_headers, db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("TATAMOTORS")
    minute = dt.datetime.now(tz=dt.timezone.utc).replace(second=0, microsecond=0)
    db_session.add(
        IntradayCandle(
            stock_id=stock.id,
            timestamp=minute,
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=5000,
            source="ANGELONE",
            status=CandleStatus.LIVE,
        )
    )
    db_session.commit()

    resp = client.get("/market/candles/TATAMOTORS", headers=auth_headers)
    body = resp.json()
    assert len(body["candles"]) >= 1
    assert body["candles"][-1]["close"] == 101.0
    assert body["candles"][-1]["status"] == "LIVE"
    assert body["interval"] == "1m"
    assert "gap_count" in body and "sample_gaps" in body


def test_candles_rejects_unknown_interval(client, auth_headers):
    resp = client.get("/market/candles/WIPRO?interval=7m", headers=auth_headers)
    assert resp.status_code == 400


def test_candles_resamples_to_requested_interval(client, auth_headers, db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("ADANIPORTS")
    # This test runs against the persistent dev DB (no per-test rollback --
    # see conftest.py's db_session fixture), so clear any rows a prior run
    # left behind before inserting -- otherwise a second run within the
    # same 5-minute bucket collides with the (stock_id, timestamp) unique
    # constraint.
    db_session.query(IntradayCandle).filter(IntradayCandle.stock_id == stock.id).delete()
    db_session.commit()
    now = dt.datetime.now(tz=dt.timezone.utc)
    base = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    for i in range(5):
        db_session.add(
            IntradayCandle(
                stock_id=stock.id,
                timestamp=base + dt.timedelta(minutes=i),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1000,
                source="ANGELONE",
                status=CandleStatus.LIVE,
            )
        )
    db_session.commit()

    resp = client.get("/market/candles/ADANIPORTS?interval=5m", headers=auth_headers)
    body = resp.json()
    assert body["interval"] == "5m"
    assert len(body["candles"]) == 1
    bar = body["candles"][0]
    assert bar["open"] == 100.0
    assert bar["close"] == 104.5
    assert bar["volume"] == 5000


def test_market_indices_returns_nifty_tiles(client):
    resp = client.get("/market/indices")
    assert resp.status_code == 200
    body = resp.json()
    names = [i["name"] for i in body["indices"]]
    assert "NIFTY 50" in names
    assert "NIFTY BANK" in names
    assert "NIFTY IT" in names
    assert body["unsupported"] == ["SENSEX"]


def test_market_indices_items_have_real_computed_prices(client):
    body = client.get("/market/indices").json()
    for item in body["indices"]:
        assert item["price"] > 0
        assert item["data_source"] in {"DEV_SAMPLE", "LIVE"}


def test_market_movers_shape(client, auth_headers):
    resp = client.get("/market/movers", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["universe_scope"] == "watchlist"
    for key in ("gainers", "losers", "volume_leaders", "unusual_volume", "near_52w_high", "near_52w_low"):
        assert key in body


def test_ws_market_rejects_missing_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    # The server closes immediately with the policy-violation code (1008);
    # the test client raises on connection entry itself when that happens.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/market"):
            pass


def test_ws_market_accepts_valid_token_and_streams(client, auth_token):
    with client.websocket_connect(f"/ws/market?token={auth_token}") as ws:
        message = ws.receive_json()
        assert "market_status" in message
        assert "ticks" in message
