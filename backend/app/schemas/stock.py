from datetime import date, datetime

from pydantic import BaseModel


class StockOut(BaseModel):
    id: int
    symbol: str
    name: str
    sector: str
    industry: str
    exchange: str

    class Config:
        from_attributes = True


class StockQuote(BaseModel):
    symbol: str
    name: str
    sector: str
    current_price: float
    previous_close: float
    change: float
    change_percent: float
    volume: int
    data_source: str


class OHLCVPoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockHistory(BaseModel):
    symbol: str
    data_source: str
    points: list[OHLCVPoint]


class TechnicalIndicators(BaseModel):
    sma_20: float | None = None
    sma_50: float | None = None
    ema_20: float | None = None
    rsi_14: float | None = None
    volatility_annualized: float | None = None
    momentum_10d: float | None = None
    daily_return: float | None = None
    cumulative_return_30d: float | None = None
    avg_volume_20d: float | None = None


class StockDetail(BaseModel):
    quote: StockQuote
    indicators: TechnicalIndicators
    history: list[OHLCVPoint]


class PredictionOut(BaseModel):
    symbol: str
    direction: str
    probability: float
    confidence: str
    model_name: str
    prediction_date: date
    important_features: list[str]
    disclaimer: str = (
        "This is a model-generated estimate, not financial advice or a guaranteed outcome."
    )

    class Config:
        from_attributes = True


class NewsItemOut(BaseModel):
    id: int
    headline: str
    source: str
    url: str | None
    published_at: datetime
    sentiment_label: str | None = None
    sentiment_score: float | None = None

    class Config:
        from_attributes = True


class SentimentSummary(BaseModel):
    symbol: str
    positive_pct: float
    neutral_pct: float
    negative_pct: float
    average_score: float
    trend: str
    article_count: int
    model_used: str
