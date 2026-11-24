"""Market movers: volume leaders, unusual volume, 52-week high/low proximity.

Real Indian Stock Market Intelligence upgrade, Phase E. Computed from the
application's own tracked watchlist (``WATCHLIST_SYMBOLS``, 20 NSE
symbols) and each symbol's own stored daily OHLCV history -- NEVER from
the full NSE/BSE exchange, which this project has no feed for. Every
response this feeds into says so explicitly (``universe_scope``), per the
project's standing rule to never let a derived figure imply a broader
scope than what it was actually computed over.
"""

from __future__ import annotations

from app.services import analytics
from app.services.market_data.service import MarketDataService
from app.services.market_data.tick_normalizer import NormalizedTick

LOOKBACK_DAYS = 252  # ~1 trading year, for the 52-week high/low window
MIN_HISTORY_DAYS = 20  # below this, a 20-day avg volume / high-low window isn't meaningful
UNUSUAL_VOLUME_RATIO = 2.0  # today's volume >= 2x the 20-day average
NEAR_52W_PCT = 2.0  # within 2% of the 252-day high/low


def _row_for_tick(market_data: MarketDataService, tick: NormalizedTick) -> dict | None:
    """Returns None only when there isn't enough stored daily history to
    compute a meaningful 52-week window -- NOT when today's tick has no
    volume. A FIXTURE tick (the default, no-live-feed mode) never carries
    volume (``from_fixture`` deliberately never fabricates it), so
    gainers/losers/52-week proximity -- all price-only -- must still work
    without it; only the genuinely volume-dependent fields (``volume_ratio``,
    and therefore the ``volume_leaders``/``unusual_volume`` categories)
    come back None/excluded in that case.
    """
    stock = market_data.get_or_create_stock(tick.symbol)
    history = market_data.get_history(stock, days=LOOKBACK_DAYS)
    if len(history) < MIN_HISTORY_DAYS:
        return None

    df = analytics.ohlcv_to_frame(history)
    avg_volume_20d = float(analytics.avg_volume(df["volume"], 20).iloc[-1])
    week52_high = float(df["high"].max())
    week52_low = float(df["low"].min())

    volume_ratio = (tick.volume / avg_volume_20d) if (tick.volume is not None and avg_volume_20d) else None
    pct_from_high = ((tick.price - week52_high) / week52_high * 100) if week52_high else None
    pct_from_low = ((tick.price - week52_low) / week52_low * 100) if week52_low else None

    return {
        "symbol": tick.symbol,
        "price": tick.price,
        "change_percent": tick.change_pct,
        "volume": tick.volume,
        "avg_volume_20d": round(avg_volume_20d, 1) if avg_volume_20d else None,
        "volume_ratio": round(volume_ratio, 3) if volume_ratio is not None else None,
        "week52_high": round(week52_high, 2),
        "week52_low": round(week52_low, 2),
        "pct_from_52w_high": round(pct_from_high, 3) if pct_from_high is not None else None,
        "pct_from_52w_low": round(pct_from_low, 3) if pct_from_low is not None else None,
    }


def compute_movers(market_data: MarketDataService, ticks: list[NormalizedTick], top_n: int = 5) -> dict:
    """Builds every mover category from the given live ticks. A symbol
    with fewer than ``MIN_HISTORY_DAYS`` of stored daily history is
    silently excluded from every category -- never backfilled or
    approximated with a shorter window. A symbol with no usable volume on
    its tick (always true for FIXTURE ticks, the no-live-feed default --
    see ``_row_for_tick``) still appears in the price-only categories
    (gainers/losers/52-week proximity); only the volume-dependent
    categories exclude it.
    """
    rows = [row for tick in ticks if (row := _row_for_tick(market_data, tick)) is not None]

    def _top(candidates: list[dict], key, reverse: bool) -> list[dict]:
        return sorted(candidates, key=key, reverse=reverse)[:top_n]

    gainers = _top([r for r in rows if r["change_percent"] is not None], key=lambda r: r["change_percent"], reverse=True)
    losers = _top([r for r in rows if r["change_percent"] is not None], key=lambda r: r["change_percent"], reverse=False)
    volume_leaders = _top([r for r in rows if r["volume"] is not None], key=lambda r: r["volume"], reverse=True)
    unusual_volume = _top(
        [r for r in rows if r["volume_ratio"] is not None and r["volume_ratio"] >= UNUSUAL_VOLUME_RATIO],
        key=lambda r: r["volume_ratio"],
        reverse=True,
    )
    near_52w_high = _top(
        [r for r in rows if r["pct_from_52w_high"] is not None and r["pct_from_52w_high"] >= -NEAR_52W_PCT],
        key=lambda r: r["pct_from_52w_high"],
        reverse=True,
    )
    near_52w_low = _top(
        [r for r in rows if r["pct_from_52w_low"] is not None and r["pct_from_52w_low"] <= NEAR_52W_PCT],
        key=lambda r: r["pct_from_52w_low"],
        reverse=False,
    )

    return {
        "gainers": gainers,
        "losers": losers,
        "volume_leaders": volume_leaders,
        "unusual_volume": unusual_volume,
        "near_52w_high": near_52w_high,
        "near_52w_low": near_52w_low,
        "universe_scope": "watchlist",
        "universe_size": len(rows),
    }
