"""Phase 24: real-time market data surface.

``GET /market/status`` is a plain polling fallback; ``/ws/market`` is the
real push channel for the dashboard (Phase 25). Both read ONLY from
``live_cache`` -- never touch the upstream broker connection directly --
so N browser tabs share the one upstream Angel One connection this
process holds (see ws_connection_manager.py).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import get_db
from app.schemas.market import MarketStatusOut, TickOut
from app.services.market_data import session_calendar
from app.services.market_data.live_cache import live_cache
from app.services.market_data.tick_normalizer import TickStatus
from app.services.market_data.watchlist import WATCHLIST_SYMBOLS
from app.services.security import decode_access_token

logger = logging.getLogger("portfolioiq.market_data.route")

router = APIRouter(tags=["market"])

WS_PUSH_INTERVAL_SECONDS = 1.0


def _tick_to_out(tick) -> TickOut:
    return TickOut(
        symbol=tick.symbol,
        exchange=tick.exchange,
        price=tick.price,
        previous_close=tick.previous_close,
        change=tick.change,
        change_percent=tick.change_pct,
        open=tick.open,
        high=tick.high,
        low=tick.low,
        close=tick.close,
        volume=tick.volume,
        last_traded_time=tick.last_traded_time,
        status=tick.status.value,
        source=tick.source,
    )


def _feed_status() -> str:
    if not settings.ENABLE_REALTIME_FEED:
        return "DISABLED"
    from app.main import ws_manager  # local import: avoids a circular import at module load time

    return ws_manager.status if ws_manager is not None else "DISABLED"


def _current_snapshot() -> list[TickOut]:
    now = dt.datetime.now(tz=dt.timezone.utc)
    ticks = live_cache.get_all(now)
    out = []
    for symbol in WATCHLIST_SYMBOLS:
        tick = ticks.get(symbol)
        if tick is None:
            continue
        out.append(_tick_to_out(tick))
    return out


@router.get("/market/status", response_model=MarketStatusOut)
def get_market_status(db: Session = Depends(get_db)):
    return MarketStatusOut(
        market_status=session_calendar.market_status().value,
        feed_status=_feed_status(),
        server_time=dt.datetime.now(tz=dt.timezone.utc),
        ticks=_current_snapshot(),
    )


@router.websocket("/ws/market")
async def market_ws(websocket: WebSocket, token: str | None = None):
    """Pushes the shared live-cache snapshot to this client every ~1s.

    Auth matches the REST API's JWT scheme, carried as a query param
    (WebSocket handshakes can't send a Bearer header from a browser
    client) -- same token issued by POST /auth/login.
    """
    if token is None or decode_access_token(token) is None:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    try:
        while True:
            await websocket.send_json(
                {
                    "market_status": session_calendar.market_status().value,
                    "feed_status": _feed_status(),
                    "server_time": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
                    "ticks": [t.model_dump(mode="json") for t in _current_snapshot()],
                }
            )
            await asyncio.sleep(WS_PUSH_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        logger.debug("market_ws client disconnected")
