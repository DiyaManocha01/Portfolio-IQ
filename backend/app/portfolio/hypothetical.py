"""Shared "what if we changed the portfolio" simulation core.

Phase 10 (the Fit Engine) needs a minimal slice of this: "what would the
portfolio's risk/diversification/concentration look like if we added this
one candidate stock at a modest weight?" Phase 11 (the What-If Simulator)
extends the same core into a general-purpose, multi-trade simulator with
cost modeling -- this module is written once and both build on it, rather
than duplicating the portfolio-reweighting math.

Nothing in this module writes to the database or mutates the real
`Portfolio`/`Holding` ORM objects it's given -- every function here is a
pure computation over returns/prices that returns a result dict.

Deliberate design point: `current_metrics()` and `hypothetical_metrics_after_adding()`
both go through the same `_metrics_from_weights()` covariance-quadratic-form
calculation. This matters for Phase 10's delta terms (dRisk etc.) -- they
must compare "current" and "hypothetical" computed the *same way*, not mix
`PortfolioRiskService`'s realized-historical-return-series volatility with
a covariance-model volatility for the hypothetical side. Comparing two
different estimators and calling the difference a "delta" would be exactly
the kind of silently-wrong number this project's working rules forbid.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.portfolio import Holding, Portfolio
from app.models.stock import Stock
from app.portfolio.risk_service import diversification_ratio, hhi, shrunk_covariance
from app.services import analytics
from app.services.market_data.service import MarketDataService


def _metrics_from_weights(returns_df: pd.DataFrame, weights: dict[str, float]) -> dict:
    symbols = list(returns_df.columns)
    w = np.array([weights.get(s, 0.0) for s in symbols])
    total_w = w.sum()
    w = w / total_w if total_w > 0 else w

    cov, _, _ = shrunk_covariance(returns_df[symbols])
    port_variance = float(w @ cov @ w)
    annualized_vol = float(np.sqrt(max(port_variance, 0.0)))

    standalone_vols = returns_df[symbols].std().values * np.sqrt(252)
    div_ratio = diversification_ratio(w, standalone_vols, annualized_vol)
    hhi_holdings = hhi(w)

    return {
        "annualized_volatility": annualized_vol,
        "diversification_ratio": div_ratio,
        "hhi_holdings": hhi_holdings,
        "weights": dict(zip(symbols, w.tolist())),
    }


def _returns_frame(market_data: MarketDataService, stocks: list[Stock], lookback_days: int) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for stock in stocks:
        bars = market_data.get_history(stock, days=lookback_days)
        df = analytics.ohlcv_to_frame(bars)
        series[stock.symbol] = df.set_index("date")["close"]
    price_df = pd.DataFrame(series).dropna(how="any")
    return price_df.pct_change().dropna(how="any")


def _current_weights(market_data: MarketDataService, holdings: list[Holding]) -> dict[str, float]:
    values: dict[str, float] = {}
    for h in holdings:
        latest, _ = market_data.get_quote(h.stock)
        values[h.stock.symbol] = latest.close * h.quantity
    total = sum(values.values())
    return {sym: v / total for sym, v in values.items()} if total > 0 else {}


def current_metrics(db: Session, portfolio: Portfolio, lookback_days: int = 180) -> dict | None:
    """Current portfolio's volatility/diversification-ratio/HHI, computed
    with the exact same covariance-quadratic-form method used by
    `hypothetical_metrics_after_adding()` -- see module docstring for why
    this must match rather than reusing `PortfolioRiskService`'s
    realized-return-series volatility."""
    market_data = MarketDataService(db)
    holdings = list(portfolio.holdings)
    if len(holdings) < 2:
        return None
    returns_df = _returns_frame(market_data, [h.stock for h in holdings], lookback_days)
    if returns_df.empty or len(returns_df.columns) < 2:
        return None
    weights = _current_weights(market_data, holdings)
    return _metrics_from_weights(returns_df, weights)


def hypothetical_metrics_after_adding(
    db: Session,
    portfolio: Portfolio,
    candidate_stock: Stock,
    target_weight: float = 0.10,
    lookback_days: int = 180,
) -> dict | None:
    """Simulate adding `candidate_stock` to the portfolio at `target_weight`
    (fraction of the new total, e.g. 0.10 = 10%), with every existing
    holding's weight scaled down proportionally to make room. Returns the
    hypothetical portfolio's annualized volatility, diversification ratio,
    and holdings HHI.

    Returns None if there isn't enough shared price history to compute a
    covariance matrix (e.g. a brand-new candidate with no overlapping
    trading days against the existing holdings).
    """
    market_data = MarketDataService(db)
    holdings: list[Holding] = list(portfolio.holdings)
    candidate_already_held = any(h.stock_id == candidate_stock.id for h in holdings)

    stocks = [h.stock for h in holdings]
    if not candidate_already_held:
        stocks = stocks + [candidate_stock]

    returns_df = _returns_frame(market_data, stocks, lookback_days)
    if returns_df.empty or len(returns_df.columns) < 2:
        return None

    current_weights = _current_weights(market_data, holdings)

    if candidate_already_held:
        hypothetical_weights = current_weights
    else:
        scale = 1.0 - target_weight
        hypothetical_weights = {s: w * scale for s, w in current_weights.items()}
        hypothetical_weights[candidate_stock.symbol] = target_weight

    return _metrics_from_weights(returns_df, hypothetical_weights)
