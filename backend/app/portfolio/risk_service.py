"""PortfolioRiskService: portfolio-level risk analytics.

Methodology (documented here since it's used across the API + UI):

- Each holding's daily return series comes from its cached OHLCV history
  (last ``lookback_days`` trading days, aligned on common dates).
- Portfolio daily return = sum(current_weight_i * return_i) using each
  holding's *current* value weight (a simplification: weights are not
  re-based day by day, which keeps this transparent and fast for an MVP;
  documented as a limitation in docs/PORTFOLIO_SCORING.md).
- Volatility = std(daily returns) * sqrt(252) (annualized).
- Sharpe ratio = mean(excess daily return) / std(daily return) * sqrt(252),
  using a 6% annual risk-free rate assumption (approximate Indian T-bill).
- Max drawdown = largest peak-to-trough decline of the cumulative portfolio
  value series over the lookback window.
- Risk contribution: marginal contribution to variance, using the
  covariance matrix of holding returns: contrib_i = w_i * (Cov @ w)_i,
  normalized to sum to 100%. This tells you which holdings drive portfolio
  risk -- not just which ones are individually volatile.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.portfolio import Holding, Portfolio
from app.models.stock import MarketData
from app.services import analytics
from app.services.market_data.service import MarketDataService


class PortfolioRiskService:
    def __init__(self, db: Session):
        self.db = db
        self.market_data = MarketDataService(db)

    def _returns_frame(self, holdings: list[Holding], lookback_days: int = 180) -> pd.DataFrame:
        series = {}
        for h in holdings:
            bars = self.market_data.get_history(h.stock, days=lookback_days)
            df = analytics.ohlcv_to_frame(bars)
            df = df.set_index("date")["close"]
            series[h.stock.symbol] = df
        price_df = pd.DataFrame(series).dropna(how="any")
        return price_df.pct_change().dropna(how="any")

    def compute(self, portfolio: Portfolio, lookback_days: int = 180) -> dict:
        holdings = list(portfolio.holdings)
        if not holdings:
            return self._empty_result()

        quotes = {}
        values = {}
        for h in holdings:
            latest, _ = self.market_data.get_quote(h.stock)
            quotes[h.stock.symbol] = latest.close
            values[h.stock.symbol] = latest.close * h.quantity

        total_value = sum(values.values()) or 1.0
        weights = {sym: v / total_value for sym, v in values.items()}

        returns_df = self._returns_frame(holdings, lookback_days)
        if returns_df.empty or len(returns_df.columns) == 0:
            return self._empty_result()

        symbols = [s for s in returns_df.columns if s in weights]
        w = np.array([weights[s] for s in symbols])
        w = w / w.sum() if w.sum() > 0 else w

        portfolio_returns = returns_df[symbols].values @ w
        portfolio_returns_series = pd.Series(portfolio_returns, index=returns_df.index)

        annualized_vol = float(portfolio_returns_series.std() * np.sqrt(252))
        sharpe = analytics.sharpe_ratio(portfolio_returns_series)

        cumulative = (1 + portfolio_returns_series).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_dd = float(drawdown.min())

        cov = returns_df[symbols].cov().values * 252  # annualized covariance
        port_variance = float(w @ cov @ w) or 1e-9
        marginal_contrib = cov @ w
        raw_contrib = w * marginal_contrib
        risk_contrib_pct = raw_contrib / raw_contrib.sum() * 100 if raw_contrib.sum() != 0 else raw_contrib

        risk_contributions = [
            {"symbol": sym, "risk_contribution_pct": round(float(max(pct, 0)), 2)}
            for sym, pct in sorted(zip(symbols, risk_contrib_pct), key=lambda x: -x[1])
        ]

        corr = returns_df[symbols].corr()
        correlation_pairs = []
        for i, a in enumerate(symbols):
            for b in symbols[i + 1 :]:
                correlation_pairs.append(
                    {"symbol_a": a, "symbol_b": b, "correlation": round(float(corr.loc[a, b]), 3)}
                )

        sector_values: dict[str, float] = {}
        for h in holdings:
            sector_values[h.stock.sector] = sector_values.get(h.stock.sector, 0.0) + values[h.stock.symbol]
        sector_concentration = [
            {"label": sector, "value": round(v, 2), "pct": round(v / total_value * 100, 1)}
            for sector, v in sorted(sector_values.items(), key=lambda x: -x[1])
        ]

        top_stock_concentration = max(weights.values()) * 100 if weights else 0.0

        return {
            "annualized_volatility": round(annualized_vol, 4),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown": round(max_dd, 4),
            "risk_contributions": risk_contributions,
            "correlation_matrix": correlation_pairs,
            "sector_concentration": sector_concentration,
            "top_stock_concentration_pct": round(top_stock_concentration, 1),
            "data_source": self.market_data.data_source_label,
            "_weights": weights,
            "_returns_df": returns_df,
            "_portfolio_variance": port_variance,
        }

    def _empty_result(self) -> dict:
        return {
            "annualized_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "risk_contributions": [],
            "correlation_matrix": [],
            "sector_concentration": [],
            "top_stock_concentration_pct": 0.0,
            "data_source": self.market_data.data_source_label,
            "_weights": {},
            "_returns_df": pd.DataFrame(),
            "_portfolio_variance": 0.0,
        }
