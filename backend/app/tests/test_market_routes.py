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
