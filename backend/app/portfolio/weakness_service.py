"""PortfolioWeaknessService: rule-based weakness detection.

Each rule inspects the same risk metrics used by PortfolioHealthService and
emits a warning only when a documented threshold is crossed, with the
supporting metric shown so the explanation is never a black box.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.portfolio import Portfolio
from app.portfolio.risk_service import PortfolioRiskService

TOP_STOCK_HIGH = 50.0
TOP_STOCK_MEDIUM = 30.0
TOP_SECTOR_HIGH = 55.0
TOP_SECTOR_MEDIUM = 40.0
VOLATILITY_HIGH = 0.35
VOLATILITY_MEDIUM = 0.25
CORRELATION_HIGH = 0.75
CORRELATION_MEDIUM = 0.6
DRAWDOWN_HIGH = -0.30
DRAWDOWN_MEDIUM = -0.20
MIN_HOLDINGS_FOR_DIVERSIFICATION = 4


class PortfolioWeaknessService:
    def __init__(self, db: Session):
        self.db = db
        self.risk_service = PortfolioRiskService(db)

    def detect(self, portfolio: Portfolio) -> list[dict]:
        holdings = list(portfolio.holdings)
        weaknesses: list[dict] = []

        if not holdings:
            return weaknesses

        risk = self.risk_service.compute(portfolio)
        weights = risk["_weights"]

        if weights:
            top_symbol = max(weights, key=weights.get)
            top_pct = weights[top_symbol] * 100
            if top_pct >= TOP_STOCK_HIGH:
                weaknesses.append(
                    {
                        "title": f"High Concentration in {top_symbol}",
                        "severity": "HIGH",
                        "explanation": f"{top_symbol} makes up a very large share of your portfolio, so its "
                        "performance will dominate your overall returns and risk.",
                        "supporting_metric": f"{top_symbol} = {top_pct:.1f}% of portfolio value",
                    }
                )
            elif top_pct >= TOP_STOCK_MEDIUM:
                weaknesses.append(
                    {
                        "title": f"Moderate Concentration in {top_symbol}",
                        "severity": "MEDIUM",
                        "explanation": f"{top_symbol} represents a sizeable share of your portfolio value.",
                        "supporting_metric": f"{top_symbol} = {top_pct:.1f}% of portfolio value",
                    }
                )

        sector_concentration = risk["sector_concentration"]
        if sector_concentration:
            top_sector = sector_concentration[0]
            if top_sector["pct"] >= TOP_SECTOR_HIGH:
                weaknesses.append(
                    {
                        "title": f"High {top_sector['label']} Sector Concentration",
                        "severity": "HIGH",
                        "explanation": f"{top_sector['label']} represents a very large share of your portfolio, "
                        "leaving you exposed to sector-specific downturns.",
                        "supporting_metric": f"{top_sector['label']} = {top_sector['pct']:.1f}% of portfolio",
                    }
                )
            elif top_sector["pct"] >= TOP_SECTOR_MEDIUM:
                weaknesses.append(
                    {
                        "title": f"High {top_sector['label']} Sector Concentration",
                        "severity": "MEDIUM",
                        "explanation": f"{top_sector['label']} represents a significant share of your portfolio.",
                        "supporting_metric": f"{top_sector['label']} = {top_sector['pct']:.1f}% of portfolio",
                    }
                )

        vol = risk["annualized_volatility"]
        if vol >= VOLATILITY_HIGH:
            weaknesses.append(
                {
                    "title": "High Portfolio Volatility",
                    "severity": "HIGH",
                    "explanation": "Your portfolio's historical price swings are significantly larger than a "
                    "typical diversified portfolio.",
                    "supporting_metric": f"Annualized volatility = {vol * 100:.1f}%",
                }
            )
        elif vol >= VOLATILITY_MEDIUM:
            weaknesses.append(
                {
                    "title": "Elevated Portfolio Volatility",
                    "severity": "MEDIUM",
                    "explanation": "Your portfolio shows above-average historical volatility.",
                    "supporting_metric": f"Annualized volatility = {vol * 100:.1f}%",
                }
            )

        corr_pairs = risk["correlation_matrix"]
        if corr_pairs:
            avg_corr = sum(p["correlation"] for p in corr_pairs) / len(corr_pairs)
            if avg_corr >= CORRELATION_HIGH:
                weaknesses.append(
                    {
                        "title": "High Correlation Between Holdings",
                        "severity": "HIGH",
                        "explanation": "Several holdings historically move together, reducing the diversification "
                        "benefit of holding multiple stocks.",
                        "supporting_metric": f"Average pairwise correlation = {avg_corr:.2f}",
                    }
                )
            elif avg_corr >= CORRELATION_MEDIUM:
                weaknesses.append(
                    {
                        "title": "Moderate Correlation Between Holdings",
                        "severity": "MEDIUM",
                        "explanation": "Some holdings show meaningful historical correlation with each other.",
                        "supporting_metric": f"Average pairwise correlation = {avg_corr:.2f}",
                    }
                )

        max_dd = risk["max_drawdown"]
        if max_dd <= DRAWDOWN_HIGH:
            weaknesses.append(
                {
                    "title": "Large Historical Drawdown",
                    "severity": "HIGH",
                    "explanation": "Your portfolio has experienced a large peak-to-trough decline in the "
                    "lookback window, indicating higher downside risk.",
                    "supporting_metric": f"Max drawdown = {max_dd * 100:.1f}%",
                }
            )
        elif max_dd <= DRAWDOWN_MEDIUM:
            weaknesses.append(
                {
                    "title": "Notable Historical Drawdown",
                    "severity": "MEDIUM",
                    "explanation": "Your portfolio has experienced a moderate peak-to-trough decline.",
                    "supporting_metric": f"Max drawdown = {max_dd * 100:.1f}%",
                }
            )

        if len(holdings) < MIN_HOLDINGS_FOR_DIVERSIFICATION:
            weaknesses.append(
                {
                    "title": "Low Number of Holdings",
                    "severity": "MEDIUM",
                    "explanation": "Holding only a few stocks limits diversification and increases the impact "
                    "of any single stock's performance on your portfolio.",
                    "supporting_metric": f"{len(holdings)} holding(s) in portfolio "
                    f"(recommended minimum: {MIN_HOLDINGS_FOR_DIVERSIFICATION})",
                }
            )

        severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        weaknesses.sort(key=lambda w: severity_rank.get(w["severity"], 3))
        return weaknesses
