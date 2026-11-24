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

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import get_db
from app.models.intraday_candle import IntradayCandle
from app.models.stock import Stock
from app.schemas.market import (
    CandleOut,
    CandlesOut,
    IndexQuote,
    MarketIndicesOut,
    MarketMoversOut,
    MarketStatusOut,
    RegimeFactorOut,
    RegimeOut,
    TickOut,
)
from app.services import market_regime_service
from app.services.market_data import session_calendar
from app.services.market_data.candle_resample import ALLOWED_INTERVALS, detect_gaps, resample_candles
from app.services.market_data.live_cache import live_cache
from app.services.market_data.market_movers_service import compute_movers
from app.services.market_data.providers import INDEX_SYMBOLS
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import TickStatus
from app.services.market_data.watchlist import WATCHLIST_SYMBOLS
from app.services.security import decode_access_token

# Indices named in the real-data upgrade brief that this project cannot
# supply: SENSEX is a BSE index, and the real-time feed only ever
# subscribes via Angel One's NSE cash-market exchange type -- no BSE
# exchange wiring exists. Reported explicitly in GET /market/indices'
# `unsupported` field rather than silently omitted.
UNSUPPORTED_INDICES = ["SENSEX"]

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
        average_traded_price=tick.average_traded_price,
        vwap=tick.vwap,
        bid=tick.bid,
        ask=tick.ask,
        bid_qty=tick.bid_qty,
        ask_qty=tick.ask_qty,
        last_traded_time=tick.last_traded_time,
        data_received_at=tick.data_received_at,
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
def get_intraday_candles(symbol: str, limit: int = 390, interval: str = "1m", db: Session = Depends(get_db)):
    """Returns whatever real intraday candles exist for ``symbol``, at the
    requested interval.

    Deliberately returns an empty list rather than fabricating bars when
    nothing has been snapshotted yet (e.g. the real-time feed has never
    run) -- the frontend is expected to hide this timeframe rather than
    show a chart with invented data. ``limit`` is the number of OUTPUT
    bars at the requested interval, not raw 1-minute rows -- the raw
    lookback window is widened accordingly so resampling has enough
    source data. Gap detection (``gap_count``/``sample_gaps``) always runs
    on the underlying 1-minute rows, independent of ``interval`` --
    "missing 1-minute candles" is the meaningful question regardless of
    what interval the caller is viewing.
    """
    symbol = symbol.upper()
    if interval not in ALLOWED_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown interval '{interval}' -- must be one of {sorted(ALLOWED_INTERVALS)}",
        )
    stock = db.query(Stock).filter(Stock.symbol == symbol).first()
    if stock is None:
        return CandlesOut(symbol=symbol, interval=interval, candles=[], gap_count=0, sample_gaps=[])

    raw_limit = limit * ALLOWED_INTERVALS[interval]
    rows = (
        db.query(IntradayCandle)
        .filter(IntradayCandle.stock_id == stock.id)
        .order_by(IntradayCandle.timestamp.desc())
        .limit(raw_limit)
        .all()
    )
    rows.reverse()

    gap_count, sample_gaps = detect_gaps(rows)
    resampled = resample_candles(rows, interval)[-limit:]

    return CandlesOut(
        symbol=symbol,
        interval=interval,
        candles=[
            CandleOut(
                timestamp=bar["timestamp"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
                status=bar["status"].value,
            )
            for bar in resampled
        ],
        gap_count=gap_count,
        sample_gaps=sample_gaps,
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


@router.get("/market/movers", response_model=MarketMoversOut)
def get_market_movers(top_n: int = 5, db: Session = Depends(get_db)):
    """Real-data upgrade Phase E: gainers/losers/volume leaders/unusual
    volume/52-week high-low proximity, computed from the application's own
    tracked watchlist (never the full NSE/BSE exchange, which this project
    has no feed for -- see ``universe_scope`` and docs/limitations.md).
    Symbols with fewer than 20 days of stored daily history are silently
    excluded from every category, not backfilled or approximated.
    """
    market_data = MarketDataService(db)
    now = dt.datetime.now(tz=dt.timezone.utc)
    ticks = [t for symbol in WATCHLIST_SYMBOLS if (t := live_cache.get(symbol, now)) is not None]
    result = compute_movers(market_data, ticks, top_n=top_n)
    return MarketMoversOut(**result, data_source=market_data.data_source_label)


@router.get("/market/indices", response_model=MarketIndicesOut)
def get_market_indices(db: Session = Depends(get_db)):
    """Real-data upgrade Phase E: NIFTY 50 / NIFTY BANK / NIFTY IT overview
    tiles, computed from each index's own daily history (not the live
    tick feed, which only covers the Phase 24 stock watchlist, not
    indices). SENSEX is reported in ``unsupported`` -- see
    docs/limitations.md for why (a BSE index; no BSE exchange wiring).
    """
    market_data = MarketDataService(db)
    indices = []
    for name, internal_symbol in INDEX_SYMBOLS.items():
        bars = market_data.get_index_history(internal_symbol, days=5)
        if not bars:
            continue
        latest = bars[-1]
        previous = bars[-2] if len(bars) > 1 else None
        change = latest.close - previous.close if previous else None
        change_pct = (change / previous.close * 100) if previous and previous.close else None
        indices.append(
            IndexQuote(
                name=name,
                symbol=internal_symbol,
                price=latest.close,
                previous_close=previous.close if previous else None,
                change=round(change, 2) if change is not None else None,
                change_percent=round(change_pct, 2) if change_pct is not None else None,
                data_source=market_data.data_source_label,
            )
        )
    return MarketIndicesOut(indices=indices, unsupported=UNSUPPORTED_INDICES)


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
