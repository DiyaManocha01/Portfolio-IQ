"""WhatIfService: the What-If Simulator (Phase 11).

Lets a user hypothesize arbitrary changes to their holdings (buy, sell,
add a new stock) and see the before/after impact on portfolio risk --
WITHOUT ever touching their real portfolio. No DB write happens anywhere
in this module; every function here takes a portfolio and a list of
*hypothetical* target quantities and returns a comparison dict.

This is a separate, self-contained sibling to Phase 10's
``app/portfolio/hypothetical.py``, not a reuse of it -- that module is
purpose-built for one fixed-weight single-stock addition (the Fit
Engine's need) and uses a covariance-matrix-implied volatility. This
module needs two things that module doesn't provide: arbitrary
multi-position rebalancing, and Value-at-Risk/CVaR, which fundamentally
requires an actual realized return series (an empirical quantile), not
just a covariance matrix. Rather than bend one tool to do both jobs, this
is its own tool -- internally self-consistent (before and after are
always computed by the exact same method), which is the property that
actually matters for a trustworthy delta.

Indian transaction cost estimates (``estimate_indian_trade_cost``) use
commonly-cited illustrative rates for NSE equity delivery trades (STT,
stamp duty, exchange transaction charges, SEBI turnover fee, GST on
brokerage+exchange charges). These are NOT sourced from any specific
broker's live rate card and must not be treated as accurate for real
cost planning -- see docs/limitations.md. Brokerage itself defaults to
zero, matching the now-common Indian discount-broker convention of zero
brokerage on equity delivery trades.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.portfolio.risk_service import (
    diversification_ratio,
    hhi,
    historical_var_cvar,
    shrunk_covariance,
)
from app.services import analytics
from app.services.market_data.service import MarketDataService

# Illustrative, approximate -- see module docstring and docs/limitations.md.
STT_RATE = 0.001  # 0.1%, both buy and sell, delivery equity
STAMP_DUTY_RATE = 0.00015  # 0.015%, buy side only
EXCHANGE_CHARGE_RATE = 0.00003  # ~0.003%, both sides
SEBI_FEE_RATE = 0.000001  # ~0.0001%, both sides
GST_RATE = 0.18  # on (brokerage + exchange charges)
DEFAULT_BROKERAGE_RATE = 0.0  # typical modern Indian discount-broker delivery rate
RISK_FREE_RATE = 0.06


def estimate_indian_trade_cost(trade_value: float, is_buy: bool, brokerage_rate: float = DEFAULT_BROKERAGE_RATE) -> dict:
    """Approximate transaction cost for one buy or sell leg of an NSE
    equity delivery trade of `trade_value` rupees. Illustrative only."""
    brokerage = trade_value * brokerage_rate
    stt = trade_value * STT_RATE
    stamp_duty = trade_value * STAMP_DUTY_RATE if is_buy else 0.0
    exchange_charges = trade_value * EXCHANGE_CHARGE_RATE
    sebi_fee = trade_value * SEBI_FEE_RATE
    gst = (brokerage + exchange_charges) * GST_RATE
    total = brokerage + stt + stamp_duty + exchange_charges + sebi_fee + gst
    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "stamp_duty": round(stamp_duty, 2),
        "exchange_charges": round(exchange_charges, 2),
        "sebi_fee": round(sebi_fee, 2),
        "gst": round(gst, 2),
        "total": round(total, 2),
    }


def _portfolio_metrics(returns_df: pd.DataFrame, weights: dict[str, float]) -> dict:
    symbols = list(returns_df.columns)
    w = np.array([weights.get(s, 0.0) for s in symbols])
    total_w = w.sum()
    w = w / total_w if total_w > 0 else w

    portfolio_returns = pd.Series(returns_df[symbols].values @ w, index=returns_df.index)
    annualized_vol = float(portfolio_returns.std() * np.sqrt(252))
    sharpe = analytics.sharpe_ratio(portfolio_returns)
    var_95, cvar_95 = historical_var_cvar(portfolio_returns, 0.95)
    var_99, cvar_99 = historical_var_cvar(portfolio_returns, 0.99)

    cov, _, _ = shrunk_covariance(returns_df[symbols])
    standalone_vols = returns_df[symbols].std().values * np.sqrt(252)
    div_ratio = diversification_ratio(w, standalone_vols, annualized_vol)
    hhi_holdings = hhi(w)

    return {
        "annualized_volatility": round(annualized_vol, 4),
        "sharpe_ratio": round(sharpe, 3),
        "var_95": var_95,
        "cvar_95": cvar_95,
        "var_99": var_99,
        "cvar_99": cvar_99,
        "diversification_ratio": round(div_ratio, 3),
        "hhi_holdings": round(hhi_holdings, 4),
    }


class WhatIfService:
    def __init__(self, db: Session):
        self.db = db
        self.market_data = MarketDataService(db)

    def simulate(
        self,
        portfolio: Portfolio,
        changes: list[dict],
        lookback_days: int = 180,
        include_costs: bool = True,
    ) -> dict:
        """`changes` is a list of {"symbol": str, "new_quantity": float}.
        `new_quantity` is an ABSOLUTE target, not a delta: 0 removes the
        position, a symbol not currently held with new_quantity > 0 is a
        hypothetical new buy. Never writes to the database."""
        current_quantities: dict[str, float] = {h.stock.symbol: h.quantity for h in portfolio.holdings}
        current_stocks = {h.stock.symbol: h.stock for h in portfolio.holdings}

        hypothetical_quantities = dict(current_quantities)
        stocks_by_symbol = dict(current_stocks)
        for change in changes:
            symbol = change["symbol"].upper()
            stock = stocks_by_symbol.get(symbol) or self.market_data.get_or_create_stock(symbol)
            self.market_data.get_history(stock, days=lookback_days)
            stocks_by_symbol[symbol] = stock
            hypothetical_quantities[symbol] = change["new_quantity"]

        all_symbols = set(current_quantities) | set(hypothetical_quantities)
        stocks = [stocks_by_symbol[s] for s in all_symbols]

        series: dict[str, pd.Series] = {}
        prices: dict[str, float] = {}
        for stock in stocks:
            bars = self.market_data.get_history(stock, days=lookback_days)
            df = analytics.ohlcv_to_frame(bars)
            series[stock.symbol] = df.set_index("date")["close"]
            latest, _ = self.market_data.get_quote(stock)
            prices[stock.symbol] = latest.close

        price_df = pd.DataFrame(series).dropna(how="any")
        returns_df = price_df.pct_change().dropna(how="any")
        if returns_df.empty or len(returns_df.columns) < 2:
            raise ValueError("Not enough overlapping price history across the before/after holdings to simulate.")

        before_values = {s: prices[s] * current_quantities.get(s, 0.0) for s in all_symbols}
        after_values = {s: prices[s] * hypothetical_quantities.get(s, 0.0) for s in all_symbols}

        before_metrics = _portfolio_metrics(returns_df, before_values)
        after_metrics = _portfolio_metrics(returns_df, after_values)

        deltas = {
            key: round(after_metrics[key] - before_metrics[key], 4)
            for key in before_metrics
        }

        trades = []
        total_cost = 0.0
        for symbol in sorted(all_symbols):
            qty_delta = hypothetical_quantities.get(symbol, 0.0) - current_quantities.get(symbol, 0.0)
            if abs(qty_delta) < 1e-9:
                continue
            trade_value = abs(qty_delta) * prices[symbol]
            cost = None
            if include_costs:
                cost = estimate_indian_trade_cost(trade_value, is_buy=qty_delta > 0)
                total_cost += cost["total"]
            trades.append(
                {
                    "symbol": symbol,
                    "quantity_delta": round(qty_delta, 4),
                    "trade_value": round(trade_value, 2),
                    "action": "buy" if qty_delta > 0 else "sell",
                    "estimated_cost": cost,
                }
            )

        return {
            "before": before_metrics,
            "after": after_metrics,
            "deltas": deltas,
            "trades": trades,
            "total_estimated_cost": round(total_cost, 2) if include_costs else None,
            "risk_free_rate_assumed": RISK_FREE_RATE,
            "lookback_days": lookback_days,
            "data_source": self.market_data.data_source_label,
            "disclaimer": (
                "This is a hypothetical simulation of portfolio changes computed over historical "
                "data. It never modifies your actual holdings, is not a trade instruction, and "
                "transaction cost estimates are illustrative approximate rates, not quotes from "
                "any specific broker."
            ),
        }
