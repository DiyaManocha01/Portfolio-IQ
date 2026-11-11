"""Angel One WebSocket 2.0 feed client -- connection + wire protocol.

NOT VERIFIED AGAINST A LIVE STREAM. This sandbox cannot reach
smartapisocket.angelone.in (same host-block as every other Angel One
endpoint -- see angelone_auth.py), so the binary tick layout below is
built from Angel One's publicly documented WS 2.0 "Quote" packet format,
never tested against real bytes. ``FIELD_OFFSETS`` is kept as named
constants specifically so it's a one-line fix if the real feed turns out
to disagree with the documented layout -- run
``backend/app/tests/test_angelone_ws_client.py`` after any offset change.
Before trusting this in a demo: connect once with real credentials, log a
handful of raw frames, and confirm ``parse_tick`` decodes them sensibly
(sane price magnitude, a token you recognize, a timestamp near "now").

Subscription/heartbeat contract (per public docs):
  - Handshake: wss://smartapisocket.angelone.in/smart-stream with headers
    Authorization: Bearer <jwtToken>, x-api-key, x-client-code, x-feed-token.
  - Subscribe: a JSON text frame {"correlationID", "action": 1, "params":
    {"mode": <1|2|3>, "tokenList": [{"exchangeType": 1, "tokens": [...]}]}}.
  - Heartbeat: client sends the text "ping" periodically; server replies
    "pong". No pong within HEARTBEAT_TIMEOUT means the connection is
    considered dead (see ws_connection_manager.py's watchdog).
  - Ticks arrive as individual binary frames, one instrument update per
    frame, in "Quote" mode (mode=2) layout below.
"""

from __future__ import annotations

import json
import struct

WS_URL = "wss://smartapisocket.angelone.in/smart-stream"
HEARTBEAT_INTERVAL_SECONDS = 20
HEARTBEAT_TIMEOUT_SECONDS = 45

MODE_LTP = 1
MODE_QUOTE = 2
MODE_SNAPQUOTE = 3

EXCHANGE_TYPE_NSE_CM = 1


class TickParseError(ValueError):
    pass


def connect_headers(jwt_token: str, api_key: str, client_code: str, feed_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {jwt_token}",
        "x-api-key": api_key,
        "x-client-code": client_code,
        "x-feed-token": feed_token,
    }


def build_subscribe_message(correlation_id: str, tokens: list[str], mode: int = MODE_QUOTE) -> str:
    return json.dumps(
        {
            "correlationID": correlation_id,
            "action": 1,
            "params": {
                "mode": mode,
                "tokenList": [{"exchangeType": EXCHANGE_TYPE_NSE_CM, "tokens": tokens}],
            },
        }
    )


def build_unsubscribe_message(correlation_id: str, tokens: list[str], mode: int = MODE_QUOTE) -> str:
    return json.dumps(
        {
            "correlationID": correlation_id,
            "action": 0,
            "params": {
                "mode": mode,
                "tokenList": [{"exchangeType": EXCHANGE_TYPE_NSE_CM, "tokens": tokens}],
            },
        }
    )


# Byte offsets for "Quote" mode (mode=2) binary ticks, per Angel One's
# publicly documented WS 2.0 payload structure. See module docstring --
# UNVERIFIED against a real frame.
_TOKEN_LEN = 25
_OFFSET_SUBSCRIPTION_MODE = 0
_OFFSET_EXCHANGE_TYPE = 1
_OFFSET_TOKEN = 2
_OFFSET_SEQUENCE_NUMBER = 27
_OFFSET_EXCHANGE_TIMESTAMP = 35
_OFFSET_LTP = 43
_OFFSET_LTQ = 51
_OFFSET_ATP = 59
_OFFSET_VOLUME = 67
_OFFSET_OPEN = 91
_OFFSET_HIGH = 99
_OFFSET_LOW = 107
_OFFSET_CLOSE = 115
_MIN_QUOTE_PACKET_LENGTH = 123


def parse_tick(raw: bytes) -> dict:
    """Parses one binary Quote-mode tick frame into provider-native fields.

    Prices are transmitted as integer paise (price * 100); divided back to
    rupees here. Raises TickParseError on a frame shorter than expected
    rather than silently returning a zeroed/garbage tick.
    """
    if len(raw) < _MIN_QUOTE_PACKET_LENGTH:
        raise TickParseError(f"tick frame too short: {len(raw)} bytes, expected >= {_MIN_QUOTE_PACKET_LENGTH}")

    token = raw[_OFFSET_TOKEN : _OFFSET_TOKEN + _TOKEN_LEN].split(b"\x00", 1)[0].decode("ascii", errors="replace")

    def _i64(offset: int) -> int:
        return struct.unpack_from("<q", raw, offset)[0]

    return {
        "subscription_mode": raw[_OFFSET_SUBSCRIPTION_MODE],
        "exchange_type": raw[_OFFSET_EXCHANGE_TYPE],
        "token": token,
        "sequence_number": _i64(_OFFSET_SEQUENCE_NUMBER),
        "exchange_timestamp": _i64(_OFFSET_EXCHANGE_TIMESTAMP),
        "last_traded_timestamp": _i64(_OFFSET_EXCHANGE_TIMESTAMP),
        "last_traded_price": _i64(_OFFSET_LTP) / 100,
        "last_traded_quantity": _i64(_OFFSET_LTQ),
        "average_traded_price": _i64(_OFFSET_ATP) / 100,
        "volume_trade_for_the_day": _i64(_OFFSET_VOLUME),
        "open_price_of_the_day": _i64(_OFFSET_OPEN) / 100,
        "high_price_of_the_day": _i64(_OFFSET_HIGH) / 100,
        "low_price_of_the_day": _i64(_OFFSET_LOW) / 100,
        "close_price": _i64(_OFFSET_CLOSE) / 100,
    }
