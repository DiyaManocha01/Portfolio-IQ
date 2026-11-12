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
    last_traded_time: datetime | None
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
    candles: list[CandleOut]


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
