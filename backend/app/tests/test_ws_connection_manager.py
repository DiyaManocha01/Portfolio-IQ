import asyncio
from pathlib import Path

from app.services.market_data import ws_connection_manager
from app.services.market_data.instrument_registry import InstrumentRegistry
from app.services.market_data.live_cache import LiveCache
from app.services.market_data.tick_normalizer import TickStatus
from app.services.market_data.ws_connection_manager import ConnectionManagerStatus, WSConnectionManager

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "angelone_instruments_sample.json"


def _manager(**overrides) -> WSConnectionManager:
    defaults = dict(
        registry=InstrumentRegistry(source_path=FIXTURE_PATH),
        cache=LiveCache(),
        api_key="key",
        client_code="code",
        password="pw",
        totp_secret="secret",
    )
    defaults.update(overrides)
    return WSConnectionManager(**defaults)


def test_is_configured_false_when_missing_fields():
    mgr = _manager(api_key="")
    assert mgr.is_configured() is False


def test_is_configured_true_when_all_present():
    mgr = _manager()
    assert mgr.is_configured() is True


def test_start_misconfigured_without_credentials():
    async def scenario():
        mgr = _manager(api_key="")
        mgr.start()
        assert mgr.status == ConnectionManagerStatus.MISCONFIGURED
        await mgr.stop()

    asyncio.run(scenario())


def test_start_misconfigured_without_instrument_file():
    async def scenario():
        mgr = _manager(registry=InstrumentRegistry(source_path=Path("/nonexistent/instruments.json")))
        mgr.start()
        assert mgr.status == ConnectionManagerStatus.MISCONFIGURED
        await mgr.stop()

    asyncio.run(scenario())


def _pack(token, ltp, open_, high, low, close, exch_ts):
    import struct

    buf = bytearray(ws_connection_manager.angelone_ws_client._MIN_QUOTE_PACKET_LENGTH)
    buf[ws_connection_manager.angelone_ws_client._OFFSET_SUBSCRIPTION_MODE] = 2
    buf[ws_connection_manager.angelone_ws_client._OFFSET_EXCHANGE_TYPE] = 1
    token_bytes = token.encode("ascii")
    buf[ws_connection_manager.angelone_ws_client._OFFSET_TOKEN : ws_connection_manager.angelone_ws_client._OFFSET_TOKEN + len(token_bytes)] = token_bytes

    def put(offset, value):
        struct.pack_into("<q", buf, offset, value)

    put(ws_connection_manager.angelone_ws_client._OFFSET_SEQUENCE_NUMBER, 1)
    put(ws_connection_manager.angelone_ws_client._OFFSET_EXCHANGE_TIMESTAMP, exch_ts)
    put(ws_connection_manager.angelone_ws_client._OFFSET_LTP, round(ltp * 100))
    put(ws_connection_manager.angelone_ws_client._OFFSET_LTQ, 1)
    put(ws_connection_manager.angelone_ws_client._OFFSET_ATP, round(ltp * 100))
    put(ws_connection_manager.angelone_ws_client._OFFSET_VOLUME, 1000)
    put(ws_connection_manager.angelone_ws_client._OFFSET_OPEN, round(open_ * 100))
    put(ws_connection_manager.angelone_ws_client._OFFSET_HIGH, round(high * 100))
    put(ws_connection_manager.angelone_ws_client._OFFSET_LOW, round(low * 100))
    put(ws_connection_manager.angelone_ws_client._OFFSET_CLOSE, round(close * 100))
    return bytes(buf)


def test_handle_binary_tick_writes_to_cache():
    import datetime as dt

    mgr = _manager()
    token_map = {"TEST-0001": "RELIANCE"}
    now_ms = int(dt.datetime.now(tz=dt.timezone.utc).timestamp() * 1000)
    raw = _pack("TEST-0001", 2960.5, 2951.0, 2965.0, 2948.0, 2950.0, now_ms)

    mgr._handle_binary_tick(raw, token_map)

    tick = mgr._cache.get("RELIANCE")
    assert tick is not None
    assert tick.price == 2960.5
    assert tick.status == TickStatus.LIVE


def test_handle_binary_tick_unknown_token_ignored():
    mgr = _manager()
    raw = _pack("UNKNOWN-TOKEN", 100.0, 99.0, 101.0, 98.0, 99.0, 1_700_000_000_000)
    mgr._handle_binary_tick(raw, {"TEST-0001": "RELIANCE"})
    assert mgr._cache.get("RELIANCE") is None


def test_handle_binary_tick_rejects_out_of_order_timestamp():
    mgr = _manager()
    token_map = {"TEST-0001": "RELIANCE"}

    newer = _pack("TEST-0001", 2960.5, 2951.0, 2965.0, 2948.0, 2950.0, 1_700_000_001_000)
    older = _pack("TEST-0001", 9999.0, 9999.0, 9999.0, 9999.0, 9999.0, 1_700_000_000_000)

    mgr._handle_binary_tick(newer, token_map)
    mgr._handle_binary_tick(older, token_map)  # must be dropped, not overwrite

    tick = mgr._cache.get("RELIANCE")
    assert tick.price == 2960.5


def test_handle_binary_tick_rejects_exact_duplicate():
    mgr = _manager()
    token_map = {"TEST-0001": "RELIANCE"}
    frame = _pack("TEST-0001", 2960.5, 2951.0, 2965.0, 2948.0, 2950.0, 1_700_000_000_000)
    duplicate = _pack("TEST-0001", 1111.0, 1111.0, 1111.0, 1111.0, 1111.0, 1_700_000_000_000)

    mgr._handle_binary_tick(frame, token_map)
    mgr._handle_binary_tick(duplicate, token_map)

    assert mgr._cache.get("RELIANCE").price == 2960.5


def test_handle_binary_tick_unparseable_frame_dropped(caplog):
    mgr = _manager()
    mgr._handle_binary_tick(b"\x00" * 5, {"TEST-0001": "RELIANCE"})
    assert mgr._cache.get("RELIANCE") is None


def test_run_loop_backoff_increases_then_stops(monkeypatch):
    monkeypatch.setattr(ws_connection_manager, "INITIAL_BACKOFF_SECONDS", 0.01)
    monkeypatch.setattr(ws_connection_manager, "MAX_BACKOFF_SECONDS", 0.02)

    attempts = []

    async def scenario():
        mgr = _manager()

        async def fake_connect_and_stream():
            attempts.append(1)
            if len(attempts) >= 3:
                mgr._stop_event.set()
            raise RuntimeError("simulated drop")

        mgr._connect_and_stream = fake_connect_and_stream
        await mgr._run_loop()

    asyncio.run(scenario())
    assert len(attempts) == 3
