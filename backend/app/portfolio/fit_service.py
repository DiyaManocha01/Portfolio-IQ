"""PortfolioFitService: the Portfolio Fit Engine (PortfolioIQ's core USP).

Answers "how well does this stock fit into MY existing portfolio?" rather
than "is this stock good?". The score combines six transparent, independently
computed components, each in [0, 100], combined with configurable weights
(``DEFAULT_WEIGHTS`` below -- these can be tuned without touching the scoring
logic itself).

Components:
- prediction:      ML model's estimated probability of positive movement.
- risk:             penalizes high standalone volatility.
- diversification: rewards stocks in sectors the portfolio doesn't already
                    hold, and stocks not already owned.
- correlation:      rewards low historical return correlation with current
                    holdings (the classic diversification benefit).
- sector_balance:   penalizes adding to an already sector-heavy portfolio.
- user_preference:  adjusts for the investor's stated risk tolerance.

The final score is a weighted sum, and every component is returned alongside
its contribution so the UI can show a full explanation, never just a number.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.models.user import RiskTolerance
from app.services import analytics
from app.services.market_data.service import MarketDataService

DEFAULT_WEIGHTS = {
    "prediction": 0.25,
    "risk": 0.15,
    "diversification": 0.20,
    "correlation": 0.20,
    "sector_balance": 0.10,
    "user_preference": 0.10,
}

RISK_TOLERANCE_VOL_PENALTY = {
    RiskTolerance.CONSERVATIVE: 2.0,
    RiskTolerance.MODERATE: 1.0,
    RiskTolerance.AGGRESSIVE: 0.5,
}


class PortfolioFitService:
    def __init__(self, db: Session, weights: dict[str, float] | None = None):
        self.db = db
        self.weights = weights or DEFAULT_WEIGHTS
        self.market_data = MarketDataService(db)

    def _stock_returns(self, stock: Stock, days: int = 180) -> pd.Series:
        bars = self.market_data.get_history(stock, days=days)
        df = analytics.ohlcv_to_frame(bars)
        close = df.set_index("date")["close"]
        return close.pct_change().dropna()

    def _prediction_component(self, stock: Stock) -> tuple[float, str]:
        try:
            prediction = PredictionService(self.db).predict_for_stock(stock)
            score = prediction.probability * 100
            explanation = (
                f"Model outlook is {prediction.direction.value.lower()} with "
                f"{prediction.probability * 100:.0f}% estimated probability ({prediction.confidence.value.lower()} confidence)."
            )
            return round(score, 1), explanation
        except (ModelNotTrainedError, ValueError):
            return 50.0, "No model prediction available yet; treated as neutral."

    def _risk_component(self, stock_vol: float) -> tuple[float, str]:
        score = max(0.0, 100 - min(100, stock_vol * 100 * 1.5))
        explanation = f"Standalone annualized volatility of {stock_vol * 100:.1f}%."
        return round(score, 1), explanation

    def _diversification_component(
        self, stock: Stock, portfolio: Portfolio, sector_weights: dict[str, float]
    ) -> tuple[float, str]:
        already_held = any(h.stock_id == stock.id for h in portfolio.holdings)
        if already_held:
            return 0.0, "You already hold this stock, so it adds no new diversification."
        sector_pct = sector_weights.get(stock.sector, 0.0)
        score = max(0.0, 100 - sector_pct)
        if sector_pct == 0:
            explanation = f"Your portfolio currently has no exposure to {stock.sector}, a new sector for you."
        else:
            explanation = f"{stock.sector} is already {sector_pct:.1f}% of your portfolio."
        return round(score, 1), explanation

    def _correlation_component(self, stock: Stock, portfolio: Portfolio) -> tuple[float, str]:
        holdings = list(portfolio.holdings)
        if not holdings:
            return 100.0, "No existing holdings to correlate against."

        stock_returns = self._stock_returns(stock)
        correlations = []
        for h in holdings:
            if h.stock_id == stock.id:
                continue
            other_returns = self._stock_returns(h.stock)
            aligned = pd.concat([stock_returns, other_returns], axis=1, join="inner")
            if len(aligned) < 10:
                continue
            corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
            if not np.isnan(corr):
                correlations.append(corr)

        if not correlations:
            return 100.0, "Not enough overlapping history to estimate correlation; treated as favorable."

        avg_corr = float(np.mean(correlations))
        score = 100 * (1 - max(0.0, avg_corr))
        explanation = f"Average historical correlation with current holdings is {avg_corr:.2f}."
        return round(score, 1), explanation

    def _sector_balance_component(self, stock: Stock, sector_weights: dict[str, float]) -> tuple[float, str]:
        sector_pct = sector_weights.get(stock.sector, 0.0)
        score = max(0.0, 100 - sector_pct * 1.5)
        explanation = f"Adding {stock.sector} exposure to a sector currently at {sector_pct:.1f}% of portfolio."
        return round(score, 1), explanation

    def _user_preference_component(self, stock_vol: float, risk_tolerance: RiskTolerance) -> tuple[float, str]:
        penalty_mult = RISK_TOLERANCE_VOL_PENALTY.get(risk_tolerance, 1.0)
        score = max(0.0, 100 - stock_vol * 100 * penalty_mult)
        explanation = f"Matched against your {risk_tolerance.value} risk profile."
        return round(score, 1), explanation

    def compute_fit(self, stock: Stock, portfolio: Portfolio) -> dict:
        holdings = list(portfolio.holdings)
        total_value = 0.0
        sector_values: dict[str, float] = {}
        for h in holdings:
            latest, _ = self.market_data.get_quote(h.stock)
            value = latest.close * h.quantity
            total_value += value
            sector_values[h.stock.sector] = sector_values.get(h.stock.sector, 0.0) + value
        sector_weights = (
            {sector: v / total_value * 100 for sector, v in sector_values.items()} if total_value > 0 else {}
        )

        stock_returns = self._stock_returns(stock)
        stock_vol = analytics.volatility_from_returns(stock_returns)

        risk_tolerance = RiskTolerance.MODERATE
        if portfolio.user and portfolio.user.profile:
            risk_tolerance = portfolio.user.profile.risk_tolerance

        pred_score, pred_expl = self._prediction_component(stock)
        risk_score, risk_expl = self._risk_component(stock_vol)
        div_score, div_expl = self._diversification_component(stock, portfolio, sector_weights)
        corr_score, corr_expl = self._correlation_component(stock, portfolio)
        sector_score, sector_expl = self._sector_balance_component(stock, sector_weights)
        pref_score, pref_expl = self._user_preference_component(stock_vol, risk_tolerance)

        component_scores = {
            "prediction": pred_score,
            "risk": risk_score,
            "diversification": div_score,
            "correlation": corr_score,
            "sector_balance": sector_score,
            "user_preference": pref_score,
        }
        component_explanations = {
            "prediction": pred_expl,
            "risk": risk_expl,
            "diversification": div_expl,
            "correlation": corr_expl,
            "sector_balance": sector_expl,
            "user_preference": pref_expl,
        }

        fit_score = sum(self.weights[c] * component_scores[c] for c in self.weights)
        fit_score = round(max(0.0, min(100.0, fit_score)), 1)

        factors = [
            {
                "key": name,
                "name": name.replace("_", " ").title(),
                "contribution": round(self.weights[name] * component_scores[name], 1),
                "explanation": component_explanations[name],
            }
            for name in self.weights
        ]
        factors.sort(key=lambda f: -f["contribution"])

        strengths = [f["explanation"] for f in factors if component_scores[f["key"]] >= 70]
        concerns = [f["explanation"] for f in factors if component_scores[f["key"]] <= 40]
        factors = [{k: v for k, v in f.items() if k != "key"} for f in factors]

        return {
            "symbol": stock.symbol,
            "name": stock.name,
            "fit_score": fit_score,
            "factors": factors,
            "strengths": strengths[:3],
            "concerns": concerns[:3],
            "weights_used": self.weights,
            "_stock_vol": stock_vol,
            "_prediction_probability": component_scores["prediction"] / 100,
            "_avg_correlation": 1 - (corr_score / 100) if corr_score is not None else None,
        }
