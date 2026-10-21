"""RiskAttributionService: per-holding risk attribution (Phase 14).

Answers a question Phase 8's `/portfolio/risk` doesn't directly surface:
for each holding, how does its share of portfolio RISK compare to its
share of portfolio MONEY? A holding that's 10% of your money but 25% of
your risk is a real finding -- this service puts the two side by side
and computes the ratio, rather than requiring a reader to compare two
separate numbers by eye.

Net-new (no ADR -- nothing existing is superseded; this is purely
additive, built entirely on PortfolioRiskService's already-computed,
already-correct risk_contribution_pct and the new
marginal_contribution_to_risk() pure function from Phase 8's module).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.portfolio.risk_service import PortfolioRiskService


class RiskAttributionService:
    def __init__(self, db: Session):
        self.db = db
        self.risk_service = PortfolioRiskService(db)

    def compute(self, portfolio: Portfolio, lookback_days: int = 180) -> dict:
        risk = self.risk_service.compute(portfolio, lookback_days)

        weights: dict[str, float] = risk["_weights"]
        mcr: dict[str, float] = risk["_marginal_contribution_to_vol"]
        risk_contrib_by_symbol = {rc["symbol"]: rc["risk_contribution_pct"] for rc in risk["risk_contributions"]}

        holdings_by_symbol = {h.stock.symbol: h.stock for h in portfolio.holdings}

        attributions = []
        for symbol, weight in weights.items():
            weight_pct = round(weight * 100, 2)
            risk_contribution_pct = risk_contrib_by_symbol.get(symbol, 0.0)
            # >1 means this holding contributes disproportionately MORE risk
            # than its money weight; <1 means less. Guard weight_pct==0 (a
            # degenerate case that shouldn't occur for a real holding, but
            # must not divide by zero if it ever did).
            risk_concentration_ratio = round(risk_contribution_pct / weight_pct, 3) if weight_pct > 1e-9 else 0.0

            stock = holdings_by_symbol.get(symbol)
            attributions.append(
                {
                    "symbol": symbol,
                    "name": stock.name if stock else symbol,
                    "sector": stock.sector if stock else "Unknown",
                    "weight_pct": weight_pct,
                    "risk_contribution_pct": risk_contribution_pct,
                    "marginal_contribution_to_vol": round(mcr.get(symbol, 0.0), 4),
                    "risk_concentration_ratio": risk_concentration_ratio,
                }
            )
        attributions.sort(key=lambda a: -a["risk_contribution_pct"])

        return {
            "portfolio_annualized_volatility": risk["annualized_volatility"],
            "attributions": attributions,
            "data_source": risk["data_source"],
        }
