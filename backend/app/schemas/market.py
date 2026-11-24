from datetime import date, datetime

from pydantic import BaseModel


class TickOut(BaseModel):
    symbol: str
    exchange: str
    price: float
    previous_close: float | None
    change: float | None
    change_percent: float | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    average_traded_price: float | None
    vwap: float | None
    bid: float | None
    ask: float | None
    bid_qty: int | None
    ask_qty: int | None
    last_traded_time: datetime | None
    data_received_at: datetime
    status: str
    source: str


class MarketStatusOut(BaseModel):
    market_status: str  # OPEN | CLOSED | HOLIDAY | WEEKEND (session_calendar.MarketStatus)
    feed_status: str  # the WS connection manager's own status, or "DISABLED"/"FIXTURE_ONLY"
    server_time: datetime
    ticks: list[TickOut]


class CandleOut(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    status: str


class CandlesOut(BaseModel):
    symbol: str
    interval: str
    candles: list[CandleOut]
    gap_count: int
    sample_gaps: list[datetime]


class RegimeFactorOut(BaseModel):
    name: str
    raw_value: float
    z_score: float
    explanation: str


class RegimeOut(BaseModel):
    symbol: str
    regime: str  # TRENDING_UP | TRENDING_DOWN | SIDEWAYS | HIGH_VOLATILITY | LOW_VOLATILITY
    display_name: str
    confidence: float  # 0..1, NOT a probability -- see app/services/market_regime_service.py
    factors: list[RegimeFactorOut]
    as_of: date | None
    note: str | None
    data_source: str


# --- Real-data upgrade Phase E: market movers + index overview ---


class MoverItem(BaseModel):
    symbol: str
    price: float
    change_percent: float | None
    # None for a FIXTURE tick (the default, no-live-feed mode) -- see
    # market_movers_service._row_for_tick. Never fabricated.
    volume: int | None
    avg_volume_20d: float | None
    volume_ratio: float | None  # today's volume / avg_volume_20d
    week52_high: float | None
    week52_low: float | None
    pct_from_52w_high: float | None
    pct_from_52w_low: float | None


class MarketMoversOut(BaseModel):
    gainers: list[MoverItem]
    losers: list[MoverItem]
    volume_leaders: list[MoverItem]
    unusual_volume: list[MoverItem]
    near_52w_high: list[MoverItem]
    near_52w_low: list[MoverItem]
    universe_scope: str  # always "watchlist" today -- see docs/limitations.md
    universe_size: int
    data_source: str


class IndexQuote(BaseModel):
    name: str
    symbol: str
    price: float
    previous_close: float | None
    change: float | None
    change_percent: float | None
    data_source: str


class MarketIndicesOut(BaseModel):
    indices: list[IndexQuote]
    unsupported: list[str]  # e.g. ["SENSEX"] -- see docs/limitations.md for why
