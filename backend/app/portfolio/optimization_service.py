"""PortfolioOptimizationService: hypothetical target-allocation suggestions.

Methodology (Phase 9 -- see docs/methodology.md Section 6 for the full
write-up, docs/limitations.md for caveats):

- Computes a *suggested* target weight for each currently-held stock under
  one of three methods, using PyPortfolioOpt:
  - ``min_variance``: the minimum-volatility portfolio on the efficient
    frontier (``EfficientFrontier.min_volatility``).
  - ``max_sharpe``: the maximum-Sharpe-ratio portfolio
    (``EfficientFrontier.max_sharpe``), same 6% annual risk-free rate
    assumption used elsewhere in this project (``risk_service.py``).
  - ``risk_parity``: Hierarchical Risk Parity (``HRPOpt``) -- note this is
    HRP specifically, a clustering-based allocation, NOT the simpler
    equal-risk-contribution ("naive risk parity") that the name might
    suggest. PyPortfolioOpt does not implement naive ERC, and conflating
    the two would misstate what was computed.
- Expected returns: ``pypfopt.expected_returns.mean_historical_return`` --
  i.e. each stock's own historical compound annual growth rate over the
  lookback window. This is NOT the ML outlook from Phase 6 and is not
  presented as a forecast; it is historical, and openly so.
- Covariance: PyPortfolioOpt's own Ledoit-Wolf shrinkage
  (``risk_models.CovarianceShrinkage(...).ledoit_wolf()``) -- consistent in
  spirit with Phase 8's choice, computed independently since PyPortfolioOpt
  needs it in its own internal format.
- Long-only, no leverage (``weight_bounds=(0, 1)``): this app holds real
  positions for a retail user, not a fund that can short or lever up, so
  suggesting either would be a meaningless hypothetical.
- This NEVER touches the real portfolio. It is a pure computation over
  current holdings' historical data, returned as a suggested allocation
  alongside the current one for comparison -- no trade is placed, no DB
  row is written. Framed as a simulation, per the project's working rules
  (never "you should rebalance to this", always "this is what the
  optimizer suggests under method X, here is why it may or may not be
  reasonable to act on").
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, HRPOpt, expected_returns, risk_models
from sqlalchemy.orm import Session

from app.models.portfolio import Holding, Portfolio
from app.portfolio.risk_service import PortfolioRiskService
from app.services import analytics
from app.services.market_data.service import MarketDataService

RISK_FREE_RATE = 0.06  # same assumption as PortfolioRiskService's Sharpe ratio
VALID_METHODS = ("min_variance", "max_sharpe", "risk_parity")


class PortfolioOptimizationService:
    def __init__(self, db: Session):
        self.db = db
        self.market_data = MarketDataService(db)
        self.risk_service = PortfolioRiskService(db)

    def _price_frame(self, holdings: list[Holding], lookback_days: int) -> pd.DataFrame:
        series = {}
        for h in holdings:
            bars = self.market_data.get_history(h.stock, days=lookback_days)
            df = analytics.ohlcv_to_frame(bars)
            df = df.set_index("date")["close"]
            series[h.stock.symbol] = df
        return pd.DataFrame(series).dropna(how="any")

    def compute(self, portfolio: Portfolio, method: str, lookback_days: int = 180) -> dict:
        if method not in VALID_METHODS:
            raise ValueError(f"Unknown optimization method: {method!r}. Must be one of {VALID_METHODS}.")

        holdings = list(portfolio.holdings)
        if len(holdings) < 2:
            return self._infeasible_result(
                method, "Optimization needs at least 2 holdings to suggest a reweighting; "
                "nothing to optimize over for a single-stock portfolio."
            )

        risk = self.risk_service.compute(portfolio, lookback_days)
        current_weights: dict[str, float] = risk["_weights"]

        price_df = self._price_frame(holdings, lookback_days)
        if price_df.empty or len(price_df.columns) < 2:
            return self._infeasible_result(method, "Not enough overlapping price history across holdings.")

        symbols = list(price_df.columns)
        mu = expected_returns.mean_historical_return(price_df, frequency=252)
        cov = risk_models.CovarianceShrinkage(price_df).ledoit_wolf()

        try:
            if method == "min_variance":
                ef = EfficientFrontier(mu, cov, weight_bounds=(0, 1))
                ef.min_volatility()
                weights = ef.clean_weights()
                exp_return, vol, sharpe = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE)
            elif method == "max_sharpe":
                ef = EfficientFrontier(mu, cov, weight_bounds=(0, 1))
                ef.max_sharpe(risk_free_rate=RISK_FREE_RATE)
                weights = ef.clean_weights()
                exp_return, vol, sharpe = ef.portfolio_performance(risk_free_rate=RISK_FREE_RATE)
            else:  # risk_parity -> Hierarchical Risk Parity
                returns_df = price_df.pct_change().dropna(how="any")
                hrp = HRPOpt(returns_df)
                hrp.optimize()
                weights = hrp.clean_weights()
                exp_return, vol, sharpe = hrp.portfolio_performance(risk_free_rate=RISK_FREE_RATE)
        except ValueError as e:
            # e.g. max_sharpe raises when no asset's expected return exceeds the risk-free rate
            return self._infeasible_result(method, str(e))

        allocations = []
        for sym in symbols:
            current_pct = round(current_weights.get(sym, 0.0) * 100, 2)
            suggested_pct = round(float(weights.get(sym, 0.0)) * 100, 2)
            allocations.append(
                {
                    "symbol": sym,
                    "current_weight_pct": current_pct,
                    "suggested_weight_pct": suggested_pct,
                    "delta_pct": round(suggested_pct - current_pct, 2),
                }
            )
        allocations.sort(key=lambda a: -a["suggested_weight_pct"])

        return {
            "method": method,
            "feasible": True,
            "note": None,
            "allocations": allocations,
            "expected_annual_return": round(float(exp_return), 4),
            "expected_annual_volatility": round(float(vol), 4),
            "expected_sharpe_ratio": round(float(sharpe), 3),
            "risk_free_rate_assumed": RISK_FREE_RATE,
            "lookback_days": lookback_days,
            "data_source": self.market_data.data_source_label,
            "disclaimer": (
                "This is a hypothetical target allocation from a portfolio-optimization "
                "model, computed over historical data. It is a simulation, not a trade "
                "instruction or a guarantee of future performance -- it never modifies "
                "your actual holdings."
            ),
        }

    def _infeasible_result(self, method: str, note: str) -> dict:
        return {
            "method": method,
            "feasible": False,
            "note": note,
            "allocations": [],
            "expected_annual_return": 0.0,
            "expected_annual_volatility": 0.0,
            "expected_sharpe_ratio": 0.0,
            "risk_free_rate_assumed": RISK_FREE_RATE,
            "lookback_days": 0,
            "data_source": self.market_data.data_source_label,
            "disclaimer": (
                "This is a hypothetical target allocation from a portfolio-optimization "
                "model, computed over historical data. It is a simulation, not a trade "
                "instruction or a guarantee of future performance -- it never modifies "
                "your actual holdings."
            ),
        }
