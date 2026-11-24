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


# Real-data upgrade Phase F: benchmark-relative risk-adjusted stats.
RISK_FREE_RATE = 0.06  # same assumption as PortfolioRiskService's Sharpe ratio and optimization_service.py
MIN_OVERLAPPING_OBSERVATIONS = 20  # same floor as analytics.beta()


def _annualized_return(values: pd.Series) -> float | None:
    """CAGR using this codebase's existing 252-trading-day-per-year
    annualization convention (see analytics.volatility_from_returns's
    np.sqrt(252)), not calendar days -- a different, simpler convention
    than the arithmetic-mean-based annualized return _benchmark_risk_stats
    uses for alpha below; both are legitimate, commonly-used conventions
    for different purposes, not an inconsistency to reconcile. None if
    fewer than 2 observations exist.
    """
    if len(values) < 2:
        return None
    start, end = float(values.iloc[0]), float(values.iloc[-1])
    if start <= 0:
        return None
    n_periods = len(values) - 1
    return float((end / start) ** (252 / n_periods) - 1)


def _benchmark_risk_stats(portfolio_returns: pd.Series, benchmark_close: pd.Series) -> dict:
    """Beta, alpha (Jensen's, annualized), tracking error, and information
    ratio vs. a benchmark -- computed from the same aligned, inner-joined
    return series analytics.beta() already uses, with the same
    >=20-observation floor. Returns None for every field (not a
    misleadingly precise number from a handful of points) when there
    isn't enough overlapping history -- same discipline as beta() itself.
    """
    benchmark_returns = benchmark_close.pct_change()
    aligned = pd.concat([portfolio_returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(aligned) < MIN_OVERLAPPING_OBSERVATIONS:
        return {"beta": None, "alpha": None, "tracking_error": None, "information_ratio": None}

    port_r = aligned.iloc[:, 0]
    bench_r = aligned.iloc[:, 1]
    beta_value = analytics.beta(port_r, bench_r)

    excess = port_r - bench_r
    tracking_error = float(excess.std() * math.sqrt(252))
    information_ratio = (float(excess.mean() * 252) / tracking_error) if tracking_error else None

    alpha = None
    if beta_value is not None:
        port_annual_return = float(port_r.mean() * 252)
        bench_annual_return = float(bench_r.mean() * 252)
        alpha = port_annual_return - (RISK_FREE_RATE + beta_value * (bench_annual_return - RISK_FREE_RATE))

    return {
        "beta": round(beta_value, 3) if beta_value is not None else None,
        "alpha": round(alpha, 4) if alpha is not None else None,
        "tracking_error": round(tracking_error, 4),
        "information_ratio": round(information_ratio, 3) if information_ratio is not None else None,
    }


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
    sharpe_ratio_realized = None
    cagr = None
    benchmark_cagr = None
    beta = alpha = tracking_error = information_ratio = None

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
        cagr = _annualized_return(values)

        realized_daily_returns = pct_change.dropna()
        if len(realized_daily_returns) >= 2:
            annualized_volatility_realized = round(float(realized_daily_returns.std() * math.sqrt(252)), 4)
            sharpe_ratio_realized = round(analytics.sharpe_ratio(realized_daily_returns, RISK_FREE_RATE), 4)

        benchmark_bars = market_data.get_benchmark_history(days=days)
        if benchmark_bars:
            benchmark_close = analytics.ohlcv_to_frame(benchmark_bars).set_index("date")["close"]
            benchmark_cagr = _annualized_return(benchmark_close)
            stats = _benchmark_risk_stats(pct_change, benchmark_close)
            beta, alpha, tracking_error, information_ratio = (
                stats["beta"], stats["alpha"], stats["tracking_error"], stats["information_ratio"],
            )

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
        "sharpe_ratio_realized": sharpe_ratio_realized,
        "cagr": round(cagr, 4) if cagr is not None else None,
        "benchmark_cagr": round(benchmark_cagr, 4) if benchmark_cagr is not None else None,
        "beta": beta,
        "alpha": alpha,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "risk_free_rate_assumed": RISK_FREE_RATE,
        "data_source": data_source,
    }
