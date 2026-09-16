"""DiscoverService: ranks candidate stocks by Portfolio Fit Score.

Powers /discover ("Stocks That May Fit Your Portfolio"). The candidate
universe is every seeded stock the user does not already hold in full
(stocks already held are still scored, since partial-fit context can be
useful, but they naturally score low on diversification).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.fit_service import PortfolioFitService
from app.services.market_data.service import MarketDataService


class DiscoverService:
    def __init__(self, db: Session):
        self.db = db
        self.fit_service = PortfolioFitService(db)
        self.market_data = MarketDataService(db)

    def get_candidates(self, portfolio: Portfolio, limit: int = 20) -> list[dict]:
        held_symbols = {h.stock.symbol for h in portfolio.holdings}
        all_stocks = self.db.query(Stock).all()
        candidates = [s for s in all_stocks if s.symbol not in held_symbols] or all_stocks

        results = []
        for stock in candidates:
            fit = self.fit_service.compute_fit(stock, portfolio)
            latest, _ = self.market_data.get_quote(stock)

            try:
                prediction = PredictionService(self.db).predict_for_stock(stock)
                ml_outlook = prediction.direction.value
                probability = prediction.probability
            except (ModelNotTrainedError, ValueError):
                ml_outlook = "NEUTRAL"
                probability = 0.5

            avg_corr = fit.get("_avg_correlation")
            diversification_benefit = "High" if fit["fit_score"] >= 75 else "Moderate" if fit["fit_score"] >= 55 else "Low"

            results.append(
                {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "sector": stock.sector,
                    "current_price": latest.close,
                    "ml_outlook": ml_outlook,
                    "prediction_probability": round(probability, 3),
                    "volatility": round(fit["_stock_vol"], 4),
                    "portfolio_fit": fit["fit_score"],
                    "correlation_with_portfolio": round(avg_corr, 3) if avg_corr is not None else 0.0,
                    "diversification_benefit": diversification_benefit,
                }
            )

        results.sort(key=lambda r: -r["portfolio_fit"])
        return results[:limit]
