"""Owns the single upstream Angel One WebSocket connection.

Runs as one asyncio background task (started from app.main's lifespan).
Everything downstream -- the /market REST status endpoint, the /ws/market
fan-out endpoint, the periodic candle snapshot -- reads from
``live_cache`` rather than touching this connection directly; that's what
lets many browser tabs share one upstream feed and stay within Angel
One's per-client-code connection cap.

NOT VERIFIED end-to-end against the live feed (see angelone_ws_client.py);
this class's reconnect/heartbeat/parsing logic is exercised by
test_ws_connection_manager.py against a mocked WebSocket, not a real one.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import uuid

import websockets
from websockets.exceptions import ConnectionClosed

from app.services.market_data import angelone_auth, angelone_ws_client
from app.services.market_data.instrument_registry import InstrumentRegistry
from app.services.market_data.live_cache import LiveCache
from app.services.market_data.tick_normalizer import TickStatus, from_angelone_ws

logger = logging.getLogger("portfolioiq.market_data.ws")

MAX_BACKOFF_SECONDS = 60
INITIAL_BACKOFF_SECONDS = 2


class ConnectionManagerStatus:
    STOPPED = "STOPPED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    MISCONFIGURED = "MISCONFIGURED"


class WSConnectionManager:
    def __init__(
        self,
        registry: InstrumentRegistry,
        cache: LiveCache,
        api_key: str,
        client_code: str,
        password: str,
        totp_secret: str,
    ) -> None:
        self._registry = registry
        self._cache = cache
        self._api_key = api_key
        self._client_code = client_code
        self._password = password
        self._totp_secret = totp_secret

        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self.status = ConnectionManagerStatus.STOPPED
        self._last_message_at: dt.datetime | None = None
        self._last_exchange_timestamp: dict[str, int] = {}

    def is_configured(self) -> bool:
        return bool(self._api_key and self._client_code and self._password and self._totp_secret)

    def start(self) -> None:
        if not self.is_configured():
            self.status = ConnectionManagerStatus.MISCONFIGURED
            logger.warning(
                "Real-time feed enabled but ANGELONE_* credentials are incomplete -- "
                "staying disconnected. Set them in backend/.env (never commit real values)."
            )
            return
        if not self._registry.is_ready():
            self.status = ConnectionManagerStatus.MISCONFIGURED
            logger.warning(
                "Real-time feed enabled but app/data/angelone_instruments.json is missing -- "
                "run scripts/fetch_angelone_instruments.py locally first."
            )
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="angelone-ws-connection-manager")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await asyncio.wait([self._task], timeout=5)
            self._task = None
        self.status = ConnectionManagerStatus.STOPPED
        logger.info("WS connection manager stopped.")

    async def _run_loop(self) -> None:
        backoff = INITIAL_BACKOFF_SECONDS
        while not self._stop_event.is_set():
            self.status = ConnectionManagerStatus.CONNECTING
            try:
                await self._connect_and_stream()
                backoff = INITIAL_BACKOFF_SECONDS  # a clean exit resets backoff
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- reconnect on anything, log it, never crash the app
                logger.warning("Angel One WS connection dropped: %s", exc)

            if self._stop_event.is_set():
                break
            self.status = ConnectionManagerStatus.RECONNECTING
            logger.info("Reconnecting to Angel One WS in %ss...", backoff)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _connect_and_stream(self) -> None:
        resolved, missing = self._registry.resolve_all(self._watchlist_symbols())
        if missing:
            logger.warning("Instrument registry missing tokens for: %s", missing)
        if not resolved:
            raise RuntimeError("No resolved instruments to subscribe to")

        session = angelone_auth.login(self._api_key, self._client_code, self._password, self._totp_secret)
        headers = angelone_ws_client.connect_headers(
            session.jwt_token, self._api_key, self._client_code, session.feed_token
        )
        token_to_symbol = {instr.token: symbol for symbol, instr in resolved.items()}
        tokens = list(token_to_symbol.keys())

        async with websockets.connect(
            angelone_ws_client.WS_URL,
            additional_headers=headers,
            ping_interval=None,  # Angel One expects app-level "ping" text, not protocol pings
            open_timeout=15,
        ) as ws:
            self.status = ConnectionManagerStatus.CONNECTED
            self._last_message_at = dt.datetime.now(tz=dt.timezone.utc)
            logger.info("Connected to Angel One WS, subscribing to %d instruments", len(tokens))
            await ws.send(angelone_ws_client.build_subscribe_message(str(uuid.uuid4()), tokens))

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for message in ws:
                    self._last_message_at = dt.datetime.now(tz=dt.timezone.utc)
                    if isinstance(message, str):
                        continue  # "pong" or other control text, nothing to normalize
                    self._handle_binary_tick(message, token_to_symbol)
            finally:
                heartbeat_task.cancel()

    async def _heartbeat_loop(self, ws) -> None:
        while True:
            await asyncio.sleep(angelone_ws_client.HEARTBEAT_INTERVAL_SECONDS)
            now = dt.datetime.now(tz=dt.timezone.utc)
            if self._last_message_at and (now - self._last_message_at).total_seconds() > angelone_ws_client.HEARTBEAT_TIMEOUT_SECONDS:
                logger.warning("No message from Angel One WS in >%ss -- closing as stale", angelone_ws_client.HEARTBEAT_TIMEOUT_SECONDS)
                await ws.close()
                return
            try:
                await ws.send("ping")
            except ConnectionClosed:
                return

    def _handle_binary_tick(self, raw: bytes, token_to_symbol: dict[str, str]) -> None:
        try:
            parsed = angelone_ws_client.parse_tick(raw)
        except angelone_ws_client.TickParseError as exc:
            logger.warning("Dropping unparseable tick frame: %s", exc)
            return

        symbol = token_to_symbol.get(parsed["token"])
        if symbol is None:
            return  # a tick for a token we didn't ask for -- ignore, don't guess

        exchange_ts = parsed.get("exchange_timestamp")
        last_seen = self._last_exchange_timestamp.get(symbol)
        if last_seen is not None and exchange_ts is not None and exchange_ts <= last_seen:
            return  # duplicate or out-of-order -- never let a stale tick overwrite a newer one
        if exchange_ts is not None:
            self._last_exchange_timestamp[symbol] = exchange_ts

        tick = from_angelone_ws(parsed, symbol=symbol, exchange="NSE", status=TickStatus.LIVE)
        self._cache.put(tick)

    def _watchlist_symbols(self) -> list[str]:
        from app.services.market_data.watchlist import WATCHLIST_SYMBOLS

        return list(WATCHLIST_SYMBOLS)
