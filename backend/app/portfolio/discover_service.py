"""DiscoverService: ranks candidate stocks by Portfolio Fit Score.

Powers /discover ("Stocks That May Fit Your Portfolio"). The candidate
universe is every seeded stock the user does not already hold in full
(stocks already held are still scored, since partial-fit context can be
useful, but they naturally score low on diversification-related terms),
minus any sector the user has explicitly excluded via their discovery
preferences (Phase 12 -- see docs/methodology.md Section 9).

Uses PortfolioFitService.compute_fit_batch() (Phase 10) rather than calling
compute_fit() once per stock -- the Fit Engine's z-scoring is only
statistically meaningful against a real batch, and computing the whole
candidate set in one pass avoids redundant portfolio-level work.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.fit_service import PortfolioFitService, default_preset_for
from app.services.market_data.service import MarketDataService


def _excluded_sectors(portfolio: Portfolio) -> set[str]:
    profile = portfolio.user.profile if portfolio.user else None
    if not profile or not profile.preferences:
        return set()
    try:
        data = json.loads(profile.preferences)
    except (json.JSONDecodeError, TypeError):
        return set()
    return set(data.get("excluded_sectors", []))


class DiscoverService:
    def __init__(self, db: Session):
        self.db = db
        self.market_data = MarketDataService(db)

    def get_candidates(
        self,
        portfolio: Portfolio,
        limit: int = 20,
        preset: str | None = None,
        sector: str | None = None,
    ) -> list[dict]:
        held_symbols = {h.stock.symbol for h in portfolio.holdings}
        all_stocks = self.db.query(Stock).all()
        candidates = [s for s in all_stocks if s.symbol not in held_symbols] or all_stocks

        excluded = _excluded_sectors(portfolio)
        if excluded:
            filtered = [s for s in candidates if s.sector not in excluded]
            # If excluding every sector would empty the list, that's a
            # degenerate preference setup -- fall back to the unfiltered
            # set rather than silently returning nothing.
            candidates = filtered or candidates

        if sector:
            candidates = [s for s in candidates if s.sector.lower() == sector.lower()]

        if not candidates:
            return []

        chosen_preset = preset or default_preset_for(portfolio)
        fit_service = PortfolioFitService(self.db, preset=chosen_preset)
        fits = fit_service.compute_fit_batch(portfolio, candidates)

        results = []
        for stock in candidates:
            fit = fits[stock.symbol]
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
            top_factor = fit["factors"][0]

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
                    "top_factor": {"name": top_factor["name"], "explanation": top_factor["explanation"]},
                }
            )

        results.sort(key=lambda r: -r["portfolio_fit"])
        return results[:limit]
