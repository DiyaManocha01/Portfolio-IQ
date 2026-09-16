from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.stock import Stock
from app.schemas.stock import (
    NewsItemOut,
    OHLCVPoint,
    PredictionOut,
    SentimentSummary,
    StockDetail,
    StockHistory,
    StockOut,
    StockQuote,
    TechnicalIndicators,
)
from app.services import analytics
from app.services.market_data.service import MarketDataService
from app.services.news_service import NewsService

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _get_stock_or_404(symbol: str, db: Session) -> Stock:
    stock = db.query(Stock).filter(Stock.symbol == symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return stock


@router.get("", response_model=list[StockOut])
def list_stocks(db: Session = Depends(get_db)):
    return db.query(Stock).order_by(Stock.symbol.asc()).all()


@router.get("/{symbol}", response_model=StockDetail)
def get_stock_detail(symbol: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(symbol, db)
    market_data = MarketDataService(db)
    history = market_data.get_history(stock, days=200)
    latest, previous = market_data.get_quote(stock)

    df = analytics.ohlcv_to_frame(history)
    indicators = analytics.compute_indicators(df)

    change = latest.close - (previous.close if previous else latest.close)
    change_pct = (change / previous.close * 100) if previous and previous.close else 0.0

    quote = StockQuote(
        symbol=stock.symbol,
        name=stock.name,
        sector=stock.sector,
        current_price=latest.close,
        previous_close=previous.close if previous else latest.close,
        change=round(change, 2),
        change_percent=round(change_pct, 2),
        volume=latest.volume,
        data_source=market_data.data_source_label,
    )

    return StockDetail(
        quote=quote,
        indicators=TechnicalIndicators(**indicators),
        history=[OHLCVPoint(date=b.date, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume) for b in history],
    )


@router.get("/{symbol}/history", response_model=StockHistory)
def get_stock_history(symbol: str, days: int = 200, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(symbol, db)
    market_data = MarketDataService(db)
    history = market_data.get_history(stock, days=days)
    return StockHistory(
        symbol=stock.symbol,
        data_source=market_data.data_source_label,
        points=[OHLCVPoint(date=b.date, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume) for b in history],
    )


@router.get("/{symbol}/prediction", response_model=PredictionOut)
def get_stock_prediction(symbol: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(symbol, db)
    try:
        prediction = PredictionService(db).predict_for_stock(stock)
    except ModelNotTrainedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    import json

    return PredictionOut(
        symbol=stock.symbol,
        direction=prediction.direction.value,
        probability=prediction.probability,
        confidence=prediction.confidence.value,
        model_name=prediction.model_name,
        prediction_date=prediction.prediction_date,
        important_features=json.loads(prediction.important_features),
    )


@router.get("/{symbol}/news", response_model=list[NewsItemOut])
def get_stock_news(symbol: str, limit: int = 10, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(symbol, db)
    news_items = NewsService(db).get_recent_news(stock, limit=limit)
    return [
        NewsItemOut(
            id=n.id,
            headline=n.headline,
            source=n.source,
            url=n.url,
            published_at=n.published_at,
            sentiment_label=n.sentiment.sentiment_label.value if n.sentiment else None,
            sentiment_score=n.sentiment.sentiment_score if n.sentiment else None,
        )
        for n in news_items
    ]


@router.get("/{symbol}/sentiment", response_model=SentimentSummary)
def get_stock_sentiment(symbol: str, db: Session = Depends(get_db)):
    stock = _get_stock_or_404(symbol, db)
    summary = NewsService(db).get_sentiment_summary(stock)
    return SentimentSummary(symbol=stock.symbol, **summary)
