from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.corporate_event import CorporateEvent, CorporateEventType
from app.models.stock import FinancialMetric, MarketData, Stock
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

    def get_fundamentals(self, stock: Stock) -> FinancialMetric:
        """Returns today's fundamentals snapshot, fetching+caching it if absent.

        One row per (stock, day), same granularity as daily OHLCV --
        fundamentals don't change intraday in any source this project
        uses, so refetching more than once a day would just be wasted
        provider calls.
        """
        today = date.today()
        existing = (
            self.db.query(FinancialMetric)
            .filter(FinancialMetric.stock_id == stock.id, FinancialMetric.date == today)
            .first()
        )
        if existing:
            return existing

        snapshot = self.provider.get_fundamentals(stock.symbol)
        metric = FinancialMetric(
            stock_id=stock.id,
            date=today,
            pe_ratio=snapshot.pe_ratio,
            market_cap=snapshot.market_cap,
            eps=snapshot.eps,
            dividend_yield=snapshot.dividend_yield,
            book_value=snapshot.book_value,
            revenue_growth_yoy=snapshot.revenue_growth_yoy,
            profit_growth_yoy=snapshot.profit_growth_yoy,
            roe=snapshot.roe,
            roce=snapshot.roce,
            debt_to_equity=snapshot.debt_to_equity,
            source=self.provider.source,
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_corporate_events(self, stock: Stock, refresh_after_hours: int = 24) -> list[CorporateEvent]:
        """Returns stored corporate events for `stock`, refreshing from the
        provider at most once per `refresh_after_hours` (events don't
        change intraday, same reasoning as Phase 26's fundamentals cache).
        Upserts via the table's own (stock_id, event_type, event_date)
        unique constraint -- re-running never duplicates a row; it's
        checked here first (not via catching an IntegrityError) so a
        provider returning the same event twice in one call doesn't
        abort the whole batch.
        """
        most_recent = (
            self.db.query(CorporateEvent)
            .filter(CorporateEvent.stock_id == stock.id)
            .order_by(CorporateEvent.created_at.desc())
            .first()
        )
        needs_refresh = (
            most_recent is None
            or (datetime.now(timezone.utc) - most_recent.created_at) > timedelta(hours=refresh_after_hours)
        )

        if needs_refresh:
            existing_keys = {
                (e.event_type.value, e.event_date)
                for e in self.db.query(CorporateEvent).filter(CorporateEvent.stock_id == stock.id).all()
            }
            for item in self.provider.get_corporate_events(stock.symbol):
                key = (item.event_type, item.event_date)
                if key in existing_keys:
                    continue
                self.db.add(
                    CorporateEvent(
                        stock_id=stock.id,
                        event_type=CorporateEventType(item.event_type),
                        event_date=item.event_date,
                        description=item.description,
                        source=self.provider.source,
                    )
                )
                existing_keys.add(key)
            self.db.commit()

        return (
            self.db.query(CorporateEvent)
            .filter(CorporateEvent.stock_id == stock.id)
            .order_by(CorporateEvent.event_date.asc())
            .all()
        )

    @property
    def data_source_label(self) -> str:
        return self.provider.source.value

    @property
    def adjusted(self) -> bool:
        """Whether this provider's OHLCV series is split/dividend-adjusted --
        see MarketDataProvider.adjusted and docs/limitations.md."""
        return self.provider.adjusted

    def get_index_history(self, internal_symbol: str, days: int = 365) -> list:
        """Returns raw OHLCVBar history for an index (real-data upgrade
        Phase E: NIFTY 50/BANK/IT overview tiles, benchmark comparisons).

        Deliberately NOT persisted through the Stock/MarketData DB tables --
        an index isn't a holding or a discoverable stock, it's only used as
        an input to beta/overview calculations, computed on demand. Goes
        straight to the provider (which is cache-first for
        LiveYFinanceProvider, same as every other symbol). ``internal_symbol``
        is the provider-level key (e.g. ``^NSEI``), not the display name --
        see ``app.services.market_data.providers.INDEX_SYMBOLS``.
        """
        return self.provider.get_history(internal_symbol, days=days)

    def get_benchmark_history(self, days: int = 365) -> list:
        """Returns raw OHLCVBar history for the NIFTY 50 benchmark (Phase 5, beta calc)."""
        from app.services.market_data.nifty100 import BENCHMARK_SYMBOL

        return self.get_index_history(BENCHMARK_SYMBOL, days=days)
