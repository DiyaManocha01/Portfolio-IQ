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
from app.models.intraday_candle import IntradayCandle
from app.models.stock import Stock
from app.schemas.market import CandleOut, CandlesOut, MarketStatusOut, RegimeFactorOut, RegimeOut, TickOut
from app.services import market_regime_service
from app.services.market_data import session_calendar
from app.services.market_data.live_cache import live_cache
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import TickStatus
from app.services.market_data.watchlist import WATCHLIST_SYMBOLS
from app.services.security import decode_access_token

# Enough CALENDAR days (not trading days -- dev-sample data is business-days
# only, ~5/7 of calendar days) to comfortably cover classify_regime's
# trend_window + lookback_days (60 + 252 = 312 trading days).
REGIME_HISTORY_DAYS = 500
_MARKET_ALIASES = {"NIFTY50", "NIFTY", "MARKET", "^NSEI"}

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


@router.get("/market/candles/{symbol}", response_model=CandlesOut)
def get_intraday_candles(symbol: str, limit: int = 390, db: Session = Depends(get_db)):
    """Returns whatever real intraday candles exist for ``symbol``.

    Deliberately returns an empty list rather than fabricating bars when
    nothing has been snapshotted yet (e.g. the real-time feed has never
    run) -- the frontend is expected to hide this timeframe rather than
    show a chart with invented data. ``limit`` defaults to 390, one
    trading day's worth of one-minute candles (9:15-15:30 IST).
    """
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if stock is None:
        return CandlesOut(symbol=symbol.upper(), candles=[])

    rows = (
        db.query(IntradayCandle)
        .filter(IntradayCandle.stock_id == stock.id)
        .order_by(IntradayCandle.timestamp.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return CandlesOut(
        symbol=symbol.upper(),
        candles=[
            CandleOut(
                timestamp=r.timestamp,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                status=r.status.value,
            )
            for r in rows
        ],
    )


@router.get("/market/regime", response_model=RegimeOut)
def get_market_regime(symbol: str | None = None, db: Session = Depends(get_db)):
    """Classifies the current regime for `symbol`, or the NIFTY 50 market
    benchmark if no symbol is given -- see app/services/market_regime_service.py
    for the (rule-based, not trained-ML) method and docs/adr/0013.
    """
    market_data = MarketDataService(db)
    is_market = symbol is None or symbol.upper() in _MARKET_ALIASES

    if is_market:
        bars = market_data.get_benchmark_history(days=REGIME_HISTORY_DAYS)
        out_symbol = "NIFTY50"
    else:
        stock = market_data.get_or_create_stock(symbol)
        bars = market_data.get_history(stock, days=REGIME_HISTORY_DAYS)
        out_symbol = stock.symbol

    result = market_regime_service.classify_regime(bars)
    return RegimeOut(
        symbol=out_symbol,
        regime=result["regime"],
        display_name=result["display_name"],
        confidence=result["confidence"],
        factors=[RegimeFactorOut(**f) for f in result["factors"]],
        as_of=result["as_of"],
        note=result["note"],
        data_source=market_data.data_source_label,
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
