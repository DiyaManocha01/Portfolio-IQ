"""PortfolioRiskService: portfolio-level risk analytics.

Methodology (Phase 8 rebuild -- see docs/adr/0004-portfolio-risk-rebuild.md
for what this supersedes and docs/methodology.md Section 5 for the full
write-up):

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
- Covariance matrix: Ledoit-Wolf shrinkage (``sklearn.covariance.LedoitWolf``)
  of daily holding returns, annualized (* 252). Shrinkage pulls the noisy
  sample covariance toward a structured target, which matters here because
  the number of holdings can be comparable to the lookback window length --
  exactly the regime where the raw sample covariance is known to be poorly
  conditioned. The chosen shrinkage intensity is reported, not hidden.
- Risk contribution: marginal contribution to variance using the shrunk
  covariance matrix: contrib_i = w_i * (Cov @ w)_i, normalized to sum to
  100%. Tells you which holdings drive portfolio risk, not just which are
  individually volatile.
- VaR / CVaR: historical simulation (no distributional assumption) on the
  realized portfolio daily-return series over the same lookback window, at
  95% and 99% confidence. VaR is the loss threshold not expected to be
  exceeded with that confidence on a single day; CVaR (expected shortfall)
  is the average loss *given* that the VaR threshold is breached.
- HHI (Herfindahl-Hirschman Index) = sum(w_i^2) over holding weights and,
  separately, over sector weights. Ranges from 1/n (perfectly spread) to 1
  (single holding/sector). A standard concentration measure.
- Effective number of bets = 1 / HHI(holding weights). This is the
  *weight-concentration* definition -- it answers "how many equally-weighted
  positions would produce this much concentration", not the PCA/eigenvalue
  based "effective number of independent bets" (Meucci-style) that accounts
  for correlation between holdings. The two are different numbers; this
  service only computes the former. See docs/limitations.md.
- Diversification ratio (Choueifaty & Coignard) = weighted average of
  holdings' standalone annualized volatility / portfolio annualized
  volatility. A ratio > 1 means diversification is reducing portfolio risk
  below what any single holding's volatility would suggest; a ratio of
  exactly 1 is only possible with a single holding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from sqlalchemy.orm import Session

from app.models.portfolio import Holding, Portfolio
from app.services import analytics
from app.services.market_data.service import MarketDataService

VAR_CONFIDENCE_LEVELS = (0.95, 0.99)


def hhi(weights: np.ndarray) -> float:
    """Herfindahl-Hirschman Index: sum(w_i^2). Weights need not be
    pre-normalized -- this normalizes them first so the result is always
    comparable regardless of whether the caller passed fractions summing to
    1 or raw values summing to something else."""
    w = np.asarray(weights, dtype=float)
    total = w.sum()
    if total <= 0:
        return 0.0
    w = w / total
    return float(np.sum(w**2))


def effective_number_of_bets(weights: np.ndarray) -> float:
    """1 / HHI(weights) -- the weight-concentration definition of
    'effective number of bets', not the PCA/correlation-aware one. See the
    module docstring."""
    h = hhi(weights)
    return float(1.0 / h) if h > 0 else 0.0


def historical_var_cvar(returns: pd.Series, confidence: float) -> tuple[float, float]:
    """Historical-simulation VaR and CVaR (expected shortfall) at the given
    confidence level, as positive loss fractions (e.g. 0.032 = a 3.2% daily
    loss). Returns (0.0, 0.0) for an empty or all-NaN series."""
    clean = returns.dropna()
    if clean.empty:
        return 0.0, 0.0
    alpha = 1.0 - confidence
    var_quantile = float(clean.quantile(alpha))
    var = -var_quantile
    tail = clean[clean <= var_quantile]
    cvar = -float(tail.mean()) if not tail.empty else var
    return round(max(var, 0.0), 4), round(max(cvar, 0.0), 4)


def diversification_ratio(weights: np.ndarray, standalone_vols: np.ndarray, portfolio_vol: float) -> float:
    """Choueifaty-Coignard diversification ratio: weighted-average
    standalone volatility / portfolio volatility. Returns 1.0 (the
    single-asset floor) if portfolio_vol is ~0 to avoid division blow-up."""
    if portfolio_vol <= 1e-9:
        return 1.0
    weighted_avg_vol = float(np.asarray(weights) @ np.asarray(standalone_vols))
    return float(weighted_avg_vol / portfolio_vol)


def shrunk_covariance(returns_df: pd.DataFrame) -> tuple[np.ndarray, float, str]:
    """Annualized covariance matrix via Ledoit-Wolf shrinkage, plus the
    estimator's chosen shrinkage intensity and a label for which method was
    actually used. Falls back to the raw sample covariance (shrinkage=0.0,
    method='sample') when there are fewer than 2 holdings or fewer
    observations than holdings, since LedoitWolf needs more than one
    feature/sample to do anything meaningful."""
    n_obs, n_assets = returns_df.shape
    if n_assets < 2 or n_obs <= n_assets:
        cov_daily = returns_df.cov().values
        return cov_daily * 252, 0.0, "sample"
    lw = LedoitWolf().fit(returns_df.values)
    return lw.covariance_ * 252, float(lw.shrinkage_), "ledoit_wolf"


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

        cov, shrinkage_intensity, covariance_method = shrunk_covariance(returns_df[symbols])
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

        var_95, cvar_95 = historical_var_cvar(portfolio_returns_series, 0.95)
        var_99, cvar_99 = historical_var_cvar(portfolio_returns_series, 0.99)

        sector_weights_arr = np.array(list(sector_values.values()))
        hhi_holdings = hhi(w)
        hhi_sector = hhi(sector_weights_arr)
        enb = effective_number_of_bets(w)

        standalone_vols = returns_df[symbols].std().values * np.sqrt(252)
        div_ratio = diversification_ratio(w, standalone_vols, annualized_vol)

        return {
            "annualized_volatility": round(annualized_vol, 4),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown": round(max_dd, 4),
            "risk_contributions": risk_contributions,
            "correlation_matrix": correlation_pairs,
            "sector_concentration": sector_concentration,
            "top_stock_concentration_pct": round(top_stock_concentration, 1),
            "var_95": var_95,
            "cvar_95": cvar_95,
            "var_99": var_99,
            "cvar_99": cvar_99,
            "hhi_holdings": round(hhi_holdings, 4),
            "hhi_sector": round(hhi_sector, 4),
            "effective_number_of_bets": round(enb, 2),
            "diversification_ratio": round(div_ratio, 3),
            "covariance_method": covariance_method,
            "shrinkage_intensity": round(shrinkage_intensity, 4),
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
            "var_95": 0.0,
            "cvar_95": 0.0,
            "var_99": 0.0,
            "cvar_99": 0.0,
            "hhi_holdings": 0.0,
            "hhi_sector": 0.0,
            "effective_number_of_bets": 0.0,
            "diversification_ratio": 1.0,
            "covariance_method": "sample",
            "shrinkage_intensity": 0.0,
            "data_source": self.market_data.data_source_label,
            "_weights": {},
            "_returns_df": pd.DataFrame(),
            "_portfolio_variance": 0.0,
        }
