from datetime import date

from sqlalchemy.orm import Session

from app.config import settings
from app.models.stock import MarketData, Stock
from app.services.market_data.providers import (
    SECTORS,
    STOCK_NAMES,
    OHLCVBar,
    get_provider,
)


class MarketDataService:
    """Fetches, normalizes, and caches OHLCV market data.

    Callers should always go through this service rather than talking to a
    provider directly -- it handles provider selection (live vs dev sample),
    DB caching, and normalization to the internal MarketData model.
    """

    def __init__(self, db: Session):
        self.db = db
        self.provider = get_provider(settings.USE_LIVE_MARKET_DATA)

    def get_or_create_stock(self, symbol: str) -> Stock:
        symbol = symbol.upper()
        stock = self.db.query(Stock).filter(Stock.symbol == symbol).first()
        if stock:
            return stock
        sector, industry = SECTORS.get(symbol, ("Unknown", "Unknown"))
        stock = Stock(
            symbol=symbol,
            name=STOCK_NAMES.get(symbol, symbol),
            sector=sector,
            industry=industry,
            exchange="NSE",
        )
        self.db.add(stock)
        self.db.commit()
        self.db.refresh(stock)
        return stock

    def sync_history(self, stock: Stock, days: int = 400) -> int:
        """Fetch history from the provider and upsert into market_data. Returns rows written."""
        bars = self.provider.get_history(stock.symbol, days=days)
        existing_dates = {
            md.date for md in self.db.query(MarketData).filter(MarketData.stock_id == stock.id).all()
        }
        written = 0
        for bar in bars:
            if bar.date in existing_dates:
                continue
            self.db.add(
                MarketData(
                    stock_id=stock.id,
                    date=bar.date,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    source=self.provider.source,
                )
            )
            written += 1
        self.db.commit()
        return written

    def get_history(self, stock: Stock, days: int = 365) -> list[MarketData]:
        rows = (
            self.db.query(MarketData)
            .filter(MarketData.stock_id == stock.id)
            .order_by(MarketData.date.asc())
            .all()
        )
        if not rows:
            self.sync_history(stock, days=days)
            rows = (
                self.db.query(MarketData)
                .filter(MarketData.stock_id == stock.id)
                .order_by(MarketData.date.asc())
                .all()
            )
        return rows[-days:]

    def get_quote(self, stock: Stock) -> tuple[MarketData, MarketData | None]:
        """Returns (latest_bar, previous_bar)."""
        history = self.get_history(stock, days=5)
        if not history:
            raise ValueError(f"No market data available for {stock.symbol}")
        latest = history[-1]
        previous = history[-2] if len(history) > 1 else None
        return latest, previous

    @property
    def data_source_label(self) -> str:
        return self.provider.source.value
