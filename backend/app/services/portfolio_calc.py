"""Holding-level P&L and portfolio-level aggregate calculations."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.models.portfolio import Holding, Portfolio
from app.services import analytics
from app.services.market_data.service import MarketDataService


def holding_metrics(holding: Holding, current_price: float) -> dict:
    invested_value = holding.quantity * holding.avg_buy_price
    current_value = holding.quantity * current_price
    pnl = current_value - invested_value
    return_pct = (pnl / invested_value * 100) if invested_value > 0 else 0.0
    return {
        "id": holding.id,
        "symbol": holding.stock.symbol,
        "name": holding.stock.name,
        "sector": holding.stock.sector,
        "quantity": holding.quantity,
        "avg_buy_price": holding.avg_buy_price,
        "current_price": current_price,
        "invested_value": round(invested_value, 2),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "return_pct": round(return_pct, 2),
    }


def get_holdings_with_metrics(db: Session, portfolio: Portfolio) -> list[dict]:
    market_data = MarketDataService(db)
    results = []
    for h in portfolio.holdings:
        latest, _ = market_data.get_quote(h.stock)
        results.append(holding_metrics(h, latest.close))
    return results


def portfolio_totals(holdings_with_metrics: list[dict]) -> dict:
    invested = sum(h["invested_value"] for h in holdings_with_metrics)
    current = sum(h["current_value"] for h in holdings_with_metrics)
    pnl = current - invested
    return_pct = (pnl / invested * 100) if invested > 0 else 0.0
    return {
        "invested_amount": round(invested, 2),
        "portfolio_value": round(current, 2),
        "total_pnl": round(pnl, 2),
        "return_pct": round(return_pct, 2),
    }


def get_performance_series(db: Session, portfolio: Portfolio, days: int = 180) -> tuple[list[dict], str]:
    """Reconstructs portfolio value over time.

    Simplification (documented for the MVP): current holding quantities are
    assumed constant across the lookback window -- i.e. this shows "what my
    current holdings would have been worth over time", not a full
    transaction-by-transaction historical reconstruction.
    """
    market_data = MarketDataService(db)
    holdings = list(portfolio.holdings)
    if not holdings:
        return [], market_data.data_source_label

    price_frames = {}
    invested_total = 0.0
    for h in holdings:
        bars = market_data.get_history(h.stock, days=days)
        df = analytics.ohlcv_to_frame(bars).set_index("date")["close"]
        price_frames[h.stock.symbol] = df * h.quantity
        invested_total += h.quantity * h.avg_buy_price

    combined = pd.DataFrame(price_frames).sort_index().ffill().bfill()
    combined["total_value"] = combined.sum(axis=1)

    points = [
        {"date": idx, "value": round(float(row["total_value"]), 2), "invested": round(invested_total, 2)}
        for idx, row in combined.iterrows()
    ]
    return points, market_data.data_source_label
