from app.services.market_data.live_cache import live_cache
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
