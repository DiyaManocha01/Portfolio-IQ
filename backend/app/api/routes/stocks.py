import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.stock import Stock
from app.schemas.stock import (
    AnalysisPoint,
    NewsItemOut,
    OHLCVPoint,
    PredictionOut,
    ReturnsSummary,
    SentimentSummary,
    StockAnalysis,
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


@router.get("/{symbol}/analysis", response_model=StockAnalysis)
def get_stock_analysis(symbol: str, days: int = 400, db: Session = Depends(get_db)):
    """Phase 5: returns, volatility, drawdown, moving averages, RSI, MACD, beta vs NIFTY 50.

    Returns a full time series (not just the latest value) so the frontend
    can chart RSI/MACD over time, unlike GET /{symbol} which only returns
    latest-value indicators for the stock-detail summary tab.
    """
    stock = _get_stock_or_404(symbol, db)
    market_data = MarketDataService(db)
    history = market_data.get_history(stock, days=days)
    if len(history) < 30:
        raise HTTPException(status_code=400, detail=f"Not enough history to analyze {symbol}")

    df = analytics.ohlcv_to_frame(history)
    close = df["close"]

    sma_20 = analytics.sma(close, 20)
    ema_20 = analytics.ema(close, 20)
    rsi_14 = analytics.rsi(close, 14)
    macd_df = analytics.macd(close)
    returns = analytics.daily_returns(close)
    cum_returns = analytics.cumulative_returns(close)

    def _cum_return(window: int) -> float | None:
        if len(cum_returns) < 2:
            return None
        tail = cum_returns.tail(window)
        if len(tail) < 2:
            return None
        return float(tail.iloc[-1] - tail.iloc[0])

    series = [
        AnalysisPoint(
            date=row["date"],
            close=float(row["close"]),
            sma_20=float(sma_20.iloc[i]) if not pd.isna(sma_20.iloc[i]) else None,
            ema_20=float(ema_20.iloc[i]) if not pd.isna(ema_20.iloc[i]) else None,
            rsi_14=float(rsi_14.iloc[i]) if not pd.isna(rsi_14.iloc[i]) else None,
            macd_line=float(macd_df["macd_line"].iloc[i]) if not pd.isna(macd_df["macd_line"].iloc[i]) else None,
            macd_signal=float(macd_df["signal_line"].iloc[i]) if not pd.isna(macd_df["signal_line"].iloc[i]) else None,
            macd_histogram=float(macd_df["histogram"].iloc[i]) if not pd.isna(macd_df["histogram"].iloc[i]) else None,
        )
        for i, row in df.iterrows()
    ]

    # Beta vs NIFTY 50: align the stock's own return series with the
    # benchmark's, over the same lookback window.
    benchmark_history = market_data.get_benchmark_history(days=days)
    benchmark_df = analytics.ohlcv_to_frame(benchmark_history)
    benchmark_returns = benchmark_df.set_index("date")["close"].pct_change()
    stock_returns_by_date = df.set_index("date")["close"].pct_change()
    beta_value = analytics.beta(stock_returns_by_date, benchmark_returns)

    return StockAnalysis(
        symbol=stock.symbol,
        data_source=market_data.data_source_label,
        returns=ReturnsSummary(
            daily_return=float(returns.iloc[-1]) if len(returns) and not pd.isna(returns.iloc[-1]) else None,
            cumulative_return_30d=_cum_return(30),
            cumulative_return_90d=_cum_return(90),
            cumulative_return_1y=_cum_return(252),
        ),
        volatility_annualized=analytics.volatility_annualized(close, window=30),
        max_drawdown=analytics.max_drawdown(close),
        beta_vs_nifty50=round(beta_value, 3) if beta_value is not None else None,
        benchmark_data_source=market_data.data_source_label,
        series=series,
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
        model_version=prediction.model_version,
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
