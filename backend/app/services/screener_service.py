"""Stock screener (Phase 26): filters the current stock universe by
fundamentals and (optionally) technical indicators.

Operates only on stocks already present in the `stocks` table -- in this
development environment that's the seeded demo/discover universe (see
app/data/seed.py's ALL_SYMBOLS), not the full NIFTY 100 list, which
matches how GET /stocks already behaves. Fundamentals are fetched
cache-first via MarketDataService.get_fundamentals (no extra provider
calls beyond what that method already does); technical indicators are
computed only when a technical filter is actually requested, to avoid
pointless work on every screener call.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.services import analytics
from app.services.market_data.service import MarketDataService


@dataclass
class ScreenerFilters:
    sector: str | None = None
    market_cap_min: float | None = None
    market_cap_max: float | None = None
    pe_min: float | None = None
    pe_max: float | None = None
    roe_min: float | None = None
    debt_to_equity_max: float | None = None
    dividend_yield_min: float | None = None
    revenue_growth_min: float | None = None
    profit_growth_min: float | None = None
    rsi_min: float | None = None
    rsi_max: float | None = None
    momentum_10d_min: float | None = None

    def has_technical_filter(self) -> bool:
        return self.rsi_min is not None or self.rsi_max is not None or self.momentum_10d_min is not None


@dataclass
class ScreenerResultItem:
    symbol: str
    name: str
    sector: str
    industry: str
    data_source: str
    current_price: float | None
    market_cap: float | None
    pe_ratio: float | None
    eps: float | None
    dividend_yield: float | None
    roe: float | None
    roce: float | None
    debt_to_equity: float | None
    revenue_growth_yoy: float | None
    profit_growth_yoy: float | None
    rsi_14: float | None
    momentum_10d: float | None


def _passes_fundamental_filters(metric, filters: ScreenerFilters) -> bool:
    checks = [
        (filters.market_cap_min, metric.market_cap, lambda v, t: v is not None and v >= t),
        (filters.market_cap_max, metric.market_cap, lambda v, t: v is not None and v <= t),
        (filters.pe_min, metric.pe_ratio, lambda v, t: v is not None and v >= t),
        (filters.pe_max, metric.pe_ratio, lambda v, t: v is not None and v <= t),
        (filters.roe_min, metric.roe, lambda v, t: v is not None and v >= t),
        (filters.debt_to_equity_max, metric.debt_to_equity, lambda v, t: v is not None and v <= t),
        (filters.dividend_yield_min, metric.dividend_yield, lambda v, t: v is not None and v >= t),
        (filters.revenue_growth_min, metric.revenue_growth_yoy, lambda v, t: v is not None and v >= t),
        (filters.profit_growth_min, metric.profit_growth_yoy, lambda v, t: v is not None and v >= t),
    ]
    for threshold, value, predicate in checks:
        if threshold is not None and not predicate(value, threshold):
            return False
    return True


def run_screener(db: Session, filters: ScreenerFilters) -> list[ScreenerResultItem]:
    market_data = MarketDataService(db)

    query = db.query(Stock)
    if filters.sector:
        query = query.filter(Stock.sector == filters.sector)
    stocks = query.order_by(Stock.symbol.asc()).all()

    results: list[ScreenerResultItem] = []
    for stock in stocks:
        metric = market_data.get_fundamentals(stock)
        if not _passes_fundamental_filters(metric, filters):
            continue

        rsi_14 = momentum_10d = None
        if filters.has_technical_filter():
            history = market_data.get_history(stock, days=60)
            if len(history) >= 15:
                indicators = analytics.compute_indicators(analytics.ohlcv_to_frame(history))
                rsi_14 = indicators["rsi_14"]
                momentum_10d = indicators["momentum_10d"]

            if filters.rsi_min is not None and (rsi_14 is None or rsi_14 < filters.rsi_min):
                continue
            if filters.rsi_max is not None and (rsi_14 is None or rsi_14 > filters.rsi_max):
                continue
            if filters.momentum_10d_min is not None and (momentum_10d is None or momentum_10d < filters.momentum_10d_min):
                continue

        current_price = None
        try:
            latest, _ = market_data.get_quote(stock)
            current_price = latest.close
        except ValueError:
            pass  # no history yet -- price stays None, never guessed

        results.append(
            ScreenerResultItem(
                symbol=stock.symbol,
                name=stock.name,
                sector=stock.sector,
                industry=stock.industry,
                data_source=metric.source.value,
                current_price=current_price,
                market_cap=metric.market_cap,
                pe_ratio=metric.pe_ratio,
                eps=metric.eps,
                dividend_yield=metric.dividend_yield,
                roe=metric.roe,
                roce=metric.roce,
                debt_to_equity=metric.debt_to_equity,
                revenue_growth_yoy=metric.revenue_growth_yoy,
                profit_growth_yoy=metric.profit_growth_yoy,
                rsi_14=rsi_14,
                momentum_10d=momentum_10d,
            )
        )
    return results
