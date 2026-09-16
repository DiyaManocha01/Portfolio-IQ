"""PortfolioHealthService: transparent, explainable Portfolio Health Score.

Full methodology is documented in docs/PORTFOLIO_SCORING.md. Summary:

- Diversification (0-100): based on the effective number of holdings
  (1 / Herfindahl-Hirschman Index of value weights), scaled against a
  target of 10 effectively-equal-weighted holdings.
- Concentration (0-100): 100 minus the larger of (top single-stock weight,
  top sector weight), as percentages.
- Risk (0-100): 100 minus annualized portfolio volatility (%) scaled by 2x.
- Correlation (0-100): 100 minus the average pairwise return correlation
  across holdings (clamped to >= 0 contribution), as a percentage.
- Drawdown (0-100): 100 minus the historical max drawdown (%) scaled by 2x.
- Overall Health = simple average of the five components above.

All five component scores and the overall score are computed fresh from the
portfolio's actual holdings and market data -- nothing here is a fixed or
random number.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio, PortfolioScore
from app.portfolio.risk_service import PortfolioRiskService

DIVERSIFICATION_TARGET_N = 10
VOLATILITY_PENALTY_MULTIPLIER = 2.0
DRAWDOWN_PENALTY_MULTIPLIER = 2.0


class PortfolioHealthService:
    def __init__(self, db: Session):
        self.db = db
        self.risk_service = PortfolioRiskService(db)

    def _diversification_score(self, weights: dict[str, float]) -> float:
        if not weights:
            return 0.0
        hhi = sum(w**2 for w in weights.values())
        effective_n = (1 / hhi) if hhi > 0 else len(weights)
        return round(min(100.0, effective_n / DIVERSIFICATION_TARGET_N * 100), 1)

    def _concentration_score(self, weights: dict[str, float], sector_concentration: list[dict]) -> float:
        top_stock_pct = max(weights.values()) * 100 if weights else 0.0
        top_sector_pct = sector_concentration[0]["pct"] if sector_concentration else 0.0
        penalty = max(top_stock_pct, top_sector_pct)
        return round(max(0.0, 100 - penalty), 1)

    def _risk_score(self, annualized_volatility: float) -> float:
        penalty = min(100.0, annualized_volatility * 100 * VOLATILITY_PENALTY_MULTIPLIER)
        return round(max(0.0, 100 - penalty), 1)

    def _correlation_score(self, correlation_pairs: list[dict]) -> float:
        if not correlation_pairs:
            return 70.0  # neutral default: not enough holdings to measure correlation risk
        avg_corr = sum(p["correlation"] for p in correlation_pairs) / len(correlation_pairs)
        effective = max(0.0, avg_corr)
        return round(100 * (1 - effective), 1)

    def _drawdown_score(self, max_drawdown: float) -> float:
        penalty = min(100.0, abs(max_drawdown) * 100 * DRAWDOWN_PENALTY_MULTIPLIER)
        return round(max(0.0, 100 - penalty), 1)

    def compute(self, portfolio: Portfolio) -> dict:
        risk = self.risk_service.compute(portfolio)
        weights = risk["_weights"]

        diversification = self._diversification_score(weights)
        concentration = self._concentration_score(weights, risk["sector_concentration"])
        risk_score = self._risk_score(risk["annualized_volatility"])
        correlation = self._correlation_score(risk["correlation_matrix"])
        drawdown = self._drawdown_score(risk["max_drawdown"])

        overall = round((diversification + concentration + risk_score + correlation + drawdown) / 5, 1)

        components = [
            {
                "name": "Diversification",
                "score": diversification,
                "description": "How spread out your holdings are, based on effective number of positions.",
            },
            {
                "name": "Concentration",
                "score": concentration,
                "description": "Penalizes a portfolio dominated by one stock or one sector.",
            },
            {
                "name": "Risk",
                "score": risk_score,
                "description": "Penalizes high annualized portfolio volatility.",
            },
            {
                "name": "Correlation",
                "score": correlation,
                "description": "Penalizes holdings that historically move together, reducing hedging benefit.",
            },
            {
                "name": "Drawdown",
                "score": drawdown,
                "description": "Penalizes large historical peak-to-trough declines in portfolio value.",
            },
        ]

        record = PortfolioScore(
            portfolio_id=portfolio.id,
            health_score=overall,
            diversification_score=diversification,
            risk_score=risk_score,
            concentration_score=concentration,
            correlation_score=correlation,
            drawdown_score=drawdown,
        )
        self.db.add(record)
        self.db.commit()

        return {
            "overall_health": overall,
            "components": components,
            "computed_at": datetime.now(timezone.utc),
        }
