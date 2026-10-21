"""StressTestService: hypothetical market/sector shocks applied to the
real portfolio (Phase 15). Never writes to the database -- purely a
computation over current holdings and their betas vs. NIFTY 50.

Methodology:

- Each holding's shocked return is estimated via a CAPM-style beta
  scaling: `stock_shock_pct = market_shock_pct * beta_vs_nifty50`, UNLESS
  a sector-specific shock was given for that holding's sector, in which
  case the sector shock is applied directly (it overrides the beta
  scaling for that sector, since a sector-level shock already encodes a
  sector-specific assumption the single-factor market-beta model
  wouldn't capture).
- Beta uses a 400-day lookback (Phase 5's documented recommendation: beta
  on short windows is empirically noisy, and this is exactly the kind of
  decision where that noise matters). A holding with insufficient
  overlapping history to estimate beta (Phase 5: <20 overlapping trading
  days) falls back to beta=1.0 (the market-average assumption) with that
  fallback explicitly flagged per holding, never silently assumed.
- This is a SINGLE-FACTOR approximation. It does not model idiosyncratic
  stress (a holding-specific event uncorrelated with the market), nor
  correlation structure changes under stress (correlations are well known
  to spike during real crises, which this simple model does not capture).
  See docs/limitations.md.
- Named historical scenario presets (SCENARIO_PRESETS) use PUBLICLY
  WELL-KNOWN, illustrative approximate magnitude figures for how far
  broad Indian/global equity indices fell in well-documented past
  episodes. These are STYLIZED single-number shocks, not a literal
  replay of actual historical daily price paths (this project has no
  real historical price data for 2008/2020 cached in this sandbox to
  replay literally) -- applied through the exact same beta-scaling
  mechanism as any other hypothetical shock.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.services import analytics
from app.services.market_data.service import MarketDataService

DEFAULT_BETA_LOOKBACK_DAYS = 400  # Phase 5's recommended window when beta matters for a decision
FALLBACK_BETA = 1.0

SCENARIO_PRESETS: dict[str, dict] = {
    "covid_2020_crash": {
        "label": "COVID-19 Crash (Feb-Mar 2020)",
        "market_shock_pct": -0.38,
        "note": (
            "Illustrative approximate magnitude: broad Indian and global equity "
            "indices fell roughly 35-40% peak-to-trough over about a month in "
            "Feb-Mar 2020 -- a publicly well-known figure, not fetched from a "
            "primary data source in this sandbox. Applied as a single stylized "
            "shock, not a literal day-by-day replay of 2020's actual price path."
        ),
    },
    "gfc_2008": {
        "label": "Global Financial Crisis (2008)",
        "market_shock_pct": -0.50,
        "note": (
            "Illustrative approximate magnitude: broad equity indices globally, "
            "including Indian markets, fell roughly 50-60% peak-to-trough during "
            "2008 -- a publicly well-known figure, not independently verified "
            "against a primary source in this sandbox. Stylized single shock, "
            "not a literal historical replay."
        ),
    },
    "moderate_correction": {
        "label": "Moderate Market Correction",
        "market_shock_pct": -0.15,
        "note": "A generic, illustrative 15% broad-market decline -- not tied to any specific historical event.",
    },
}


def _holding_beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> tuple[float, bool]:
    """Returns (beta, used_fallback). used_fallback=True means the real
    beta couldn't be estimated (Phase 5: <20 overlapping trading days)
    and FALLBACK_BETA was substituted -- always reported, never silent."""
    beta_value = analytics.beta(stock_returns, benchmark_returns)
    if beta_value is None:
        return FALLBACK_BETA, True
    return beta_value, False


class StressTestService:
    def __init__(self, db: Session):
        self.db = db
        self.market_data = MarketDataService(db)

    def apply_shock(
        self,
        portfolio: Portfolio,
        market_shock_pct: float = 0.0,
        sector_shocks: dict[str, float] | None = None,
        lookback_days: int = DEFAULT_BETA_LOOKBACK_DAYS,
    ) -> dict:
        sector_shocks = sector_shocks or {}
        holdings = list(portfolio.holdings)
        if not holdings:
            return self._empty_result()

        benchmark_history = self.market_data.get_benchmark_history(days=lookback_days)
        benchmark_df = analytics.ohlcv_to_frame(benchmark_history)
        benchmark_returns = benchmark_df.set_index("date")["close"].pct_change()

        breakdown = []
        total_value_before = 0.0
        total_value_after = 0.0

        for h in holdings:
            latest, _ = self.market_data.get_quote(h.stock)
            value_before = latest.close * h.quantity

            sector = h.stock.sector
            if sector in sector_shocks:
                shock_pct = sector_shocks[sector]
                beta_used = None
                used_fallback_beta = False
            else:
                bars = self.market_data.get_history(h.stock, days=lookback_days)
                stock_df = analytics.ohlcv_to_frame(bars)
                stock_returns = stock_df.set_index("date")["close"].pct_change()
                beta_used, used_fallback_beta = _holding_beta(stock_returns, benchmark_returns)
                shock_pct = market_shock_pct * beta_used

            value_after = value_before * (1 + shock_pct)
            total_value_before += value_before
            total_value_after += value_after

            breakdown.append(
                {
                    "symbol": h.stock.symbol,
                    "name": h.stock.name,
                    "sector": sector,
                    "value_before": round(value_before, 2),
                    "value_after": round(value_after, 2),
                    "loss": round(value_after - value_before, 2),
                    "shock_applied_pct": round(shock_pct, 4),
                    "beta_used": round(beta_used, 3) if beta_used is not None else None,
                    "used_fallback_beta": used_fallback_beta,
                    "sector_shock_applied": sector in sector_shocks,
                }
            )

        breakdown.sort(key=lambda b: b["loss"])  # largest loss first (most negative)

        total_loss = total_value_after - total_value_before
        total_loss_pct = (total_loss / total_value_before * 100) if total_value_before > 0 else 0.0

        return {
            "market_shock_pct": market_shock_pct,
            "sector_shocks": sector_shocks,
            "total_value_before": round(total_value_before, 2),
            "total_value_after": round(total_value_after, 2),
            "total_loss": round(total_loss, 2),
            "total_loss_pct": round(total_loss_pct, 2),
            "breakdown": breakdown,
            "data_source": self.market_data.data_source_label,
            "disclaimer": (
                "This is a hypothetical, single-factor (CAPM beta) stress simulation, not a "
                "prediction or a literal historical replay. It never modifies your actual "
                "holdings. Real crises often involve correlation spikes and idiosyncratic "
                "effects this simple model does not capture -- see docs/limitations.md."
            ),
        }

    def apply_preset(self, portfolio: Portfolio, preset_name: str, lookback_days: int = DEFAULT_BETA_LOOKBACK_DAYS) -> dict:
        if preset_name not in SCENARIO_PRESETS:
            raise ValueError(f"Unknown scenario preset: {preset_name!r}. Must be one of {list(SCENARIO_PRESETS)}.")
        preset = SCENARIO_PRESETS[preset_name]
        result = self.apply_shock(portfolio, market_shock_pct=preset["market_shock_pct"], lookback_days=lookback_days)
        result["scenario_preset"] = preset_name
        result["scenario_label"] = preset["label"]
        result["scenario_note"] = preset["note"]
        return result

    def _empty_result(self) -> dict:
        return {
            "market_shock_pct": 0.0,
            "sector_shocks": {},
            "total_value_before": 0.0,
            "total_value_after": 0.0,
            "total_loss": 0.0,
            "total_loss_pct": 0.0,
            "breakdown": [],
            "data_source": self.market_data.data_source_label,
            "disclaimer": (
                "This is a hypothetical, single-factor (CAPM beta) stress simulation, not a "
                "prediction or a literal historical replay. It never modifies your actual "
                "holdings. Real crises often involve correlation spikes and idiosyncratic "
                "effects this simple model does not capture -- see docs/limitations.md."
            ),
        }
