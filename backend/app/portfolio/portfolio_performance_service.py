"""Advanced Portfolio Performance (Phase 31).

Builds a richer performance picture on top of what already exists, rather
than recomputing it: `app/services/portfolio_calc.py::get_performance_series`
for the value-over-time series, `PortfolioRiskService.compute()` (Phase 8)
for annualized volatility / Sharpe / max drawdown. New here: daily and
cumulative returns derived from that same series, a NIFTY 50 buy-and-hold
benchmark comparison (same normalization approach as Paper Trading's
Phase 28 benchmark), a running drawdown series (not just the single final
number risk_service already reports), sector- and holding-level
contribution to total unrealized P&L, and the realized/unrealized P&L
split enabled by Phase 31's new transaction logging.

Corporate actions (splits/dividends): `LiveYFinanceProvider` fetches
history with `auto_adjust=True` (see app/services/market_data/providers.py),
so returned close prices are already split/dividend-adjusted by yfinance
itself -- no separate adjustment logic is needed or implemented here.
`DevSampleProvider`'s synthetic data has no corporate actions to adjust
for. See docs/adr/0014-portfolio-transaction-ledger.md.
"""

from __future__ import annotations

import math

import pandas as pd
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio, Transaction, TransactionType
from app.services import analytics, portfolio_calc
from app.services.market_data.service import MarketDataService


def _benchmark_series(market_data: MarketDataService, days: int, normalize_to: float) -> list[dict]:
    """NIFTY 50 bought-and-held with `normalize_to` rupees at the start of
    the window -- nothing more elaborate (not a backtested strategy, not
    risk-adjusted). Same approach as Paper Trading's Phase 28 benchmark."""
    bars = market_data.get_benchmark_history(days=days)
    if not bars:
        return []
    df = analytics.ohlcv_to_frame(bars).set_index("date")["close"]
    start_price = float(df.iloc[0])
    if not start_price:
        return []
    return [{"date": idx, "value": round(normalize_to * float(price) / start_price, 2)} for idx, price in df.items()]


def _drawdown_series(values: pd.Series) -> list[dict]:
    """Running drawdown at every point, not just the single worst value --
    `analytics.max_drawdown` already reports that one number; this exposes
    the whole path so it can be charted."""
    running_max = values.cummax()
    drawdown = (values - running_max) / running_max.replace(0, pd.NA)
    return [
        {"date": idx, "drawdown_pct": round(float(d) * 100, 3) if pd.notna(d) else 0.0}
        for idx, d in drawdown.items()
    ]


def _realized_pnl(db: Session, portfolio: Portfolio) -> float:
    total = (
        db.query(Transaction)
        .filter(
            Transaction.portfolio_id == portfolio.id,
            Transaction.type == TransactionType.SELL,
            Transaction.realized_pnl.isnot(None),
        )
        .all()
    )
    return round(sum(t.realized_pnl for t in total), 2)


def get_advanced_performance(db: Session, portfolio: Portfolio, days: int = 180) -> dict:
    market_data = MarketDataService(db)
    holdings_with_metrics = portfolio_calc.get_holdings_with_metrics(db, portfolio)
    totals = portfolio_calc.portfolio_totals(holdings_with_metrics)
    unrealized_pnl = totals["total_pnl"]
    realized_pnl = _realized_pnl(db, portfolio)

    points, data_source = portfolio_calc.get_performance_series(db, portfolio, days=days)

    daily_returns: list[dict] = []
    cumulative_returns: list[dict] = []
    drawdown: list[dict] = []
    benchmark: list[dict] = []
    annualized_volatility_realized = None

    if points:
        values = pd.Series(
            [p["value"] for p in points], index=pd.Index([p["date"] for p in points], name="date")
        )
        pct_change = values.pct_change()
        daily_returns = [
            {"date": idx, "return_pct": round(float(r) * 100, 3) if pd.notna(r) else 0.0}
            for idx, r in pct_change.items()
        ]
        start_value = float(values.iloc[0])
        cumulative_returns = [
            {"date": idx, "cumulative_return_pct": round((float(v) / start_value - 1) * 100, 3) if start_value else 0.0}
            for idx, v in values.items()
        ]
        drawdown = _drawdown_series(values)
        benchmark = _benchmark_series(market_data, days, normalize_to=start_value)

        realized_daily_returns = pct_change.dropna()
        if len(realized_daily_returns) >= 2:
            annualized_volatility_realized = round(float(realized_daily_returns.std() * math.sqrt(252)), 4)

    total_pnl_for_contribution = sum(h["pnl"] for h in holdings_with_metrics)

    holding_contributions = [
        {
            "symbol": h["symbol"],
            "name": h["name"],
            "pnl": h["pnl"],
            "contribution_pct": round(h["pnl"] / total_pnl_for_contribution * 100, 2)
            if total_pnl_for_contribution
            else 0.0,
        }
        for h in holdings_with_metrics
    ]
    holding_contributions.sort(key=lambda c: -abs(c["contribution_pct"]))

    sector_pnl: dict[str, float] = {}
    for h in holdings_with_metrics:
        sector_pnl[h["sector"]] = sector_pnl.get(h["sector"], 0.0) + h["pnl"]
    sector_contributions = [
        {
            "sector": sector,
            "pnl": round(pnl, 2),
            "contribution_pct": round(pnl / total_pnl_for_contribution * 100, 2) if total_pnl_for_contribution else 0.0,
        }
        for sector, pnl in sector_pnl.items()
    ]
    sector_contributions.sort(key=lambda c: -abs(c["contribution_pct"]))

    return {
        "points": points,
        "daily_returns": daily_returns,
        "cumulative_returns": cumulative_returns,
        "drawdown": drawdown,
        "benchmark": benchmark,
        "holding_contributions": holding_contributions,
        "sector_contributions": sector_contributions,
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": realized_pnl,
        "total_pnl": round(unrealized_pnl + realized_pnl, 2),
        "annualized_volatility_realized": annualized_volatility_realized,
        "data_source": data_source,
    }
