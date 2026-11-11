"""Tests angelone_ws_client's parsing logic for internal self-consistency.

IMPORTANT: this only proves parse_tick() correctly inverts a packet built
with the SAME byte-offset layout documented in that module -- it does NOT
prove that layout matches Angel One's real wire format, which this
sandbox cannot verify (see that module's docstring). Treat this as a
regression test for the Python code, not a correctness proof of the
protocol.
"""

import json
import struct

from app.services.market_data import angelone_ws_client
from app.services.market_data.angelone_ws_client import (
    TickParseError,
    build_subscribe_message,
    build_unsubscribe_message,
    connect_headers,
    parse_tick,
)


def _build_quote_packet(token: str, ltp_rupees: float, open_rupees: float, high_rupees: float, low_rupees: float, close_rupees: float) -> bytes:
    buf = bytearray(angelone_ws_client._MIN_QUOTE_PACKET_LENGTH)
    buf[angelone_ws_client._OFFSET_SUBSCRIPTION_MODE] = 2
    buf[angelone_ws_client._OFFSET_EXCHANGE_TYPE] = 1
    token_bytes = token.encode("ascii")
    buf[angelone_ws_client._OFFSET_TOKEN : angelone_ws_client._OFFSET_TOKEN + len(token_bytes)] = token_bytes

    def _put_i64(offset: int, value: int) -> None:
        struct.pack_into("<q", buf, offset, value)

    _put_i64(angelone_ws_client._OFFSET_SEQUENCE_NUMBER, 1)
    _put_i64(angelone_ws_client._OFFSET_EXCHANGE_TIMESTAMP, 1_700_000_000_000)
    _put_i64(angelone_ws_client._OFFSET_LTP, round(ltp_rupees * 100))
    _put_i64(angelone_ws_client._OFFSET_LTQ, 10)
    _put_i64(angelone_ws_client._OFFSET_ATP, round(ltp_rupees * 100))
    _put_i64(angelone_ws_client._OFFSET_VOLUME, 500_000)
    _put_i64(angelone_ws_client._OFFSET_OPEN, round(open_rupees * 100))
    _put_i64(angelone_ws_client._OFFSET_HIGH, round(high_rupees * 100))
    _put_i64(angelone_ws_client._OFFSET_LOW, round(low_rupees * 100))
    _put_i64(angelone_ws_client._OFFSET_CLOSE, round(close_rupees * 100))
    return bytes(buf)


def test_parse_tick_roundtrip():
    packet = _build_quote_packet("2885", 2960.5, 2951.0, 2965.0, 2948.0, 2950.0)
    parsed = parse_tick(packet)
    assert parsed["token"] == "2885"
    assert parsed["last_traded_price"] == 2960.5
    assert parsed["open_price_of_the_day"] == 2951.0
    assert parsed["high_price_of_the_day"] == 2965.0
    assert parsed["low_price_of_the_day"] == 2948.0
    assert parsed["close_price"] == 2950.0
    assert parsed["volume_trade_for_the_day"] == 500_000


def test_parse_tick_too_short_raises():
    import pytest

    with pytest.raises(TickParseError):
        parse_tick(b"\x00" * 10)


def test_build_subscribe_message_shape():
    msg = json.loads(build_subscribe_message("corr-1", ["2885", "11536"]))
    assert msg["correlationID"] == "corr-1"
    assert msg["action"] == 1
    assert msg["params"]["mode"] == angelone_ws_client.MODE_QUOTE
    assert msg["params"]["tokenList"] == [{"exchangeType": 1, "tokens": ["2885", "11536"]}]


def test_build_unsubscribe_message_action_is_zero():
    msg = json.loads(build_unsubscribe_message("corr-2", ["2885"]))
    assert msg["action"] == 0


def test_connect_headers_contains_all_required_fields():
    headers = connect_headers("jwt", "apikey", "C123", "feed")
    assert headers["Authorization"] == "Bearer jwt"
    assert headers["x-api-key"] == "apikey"
    assert headers["x-client-code"] == "C123"
    assert headers["x-feed-token"] == "feed"
