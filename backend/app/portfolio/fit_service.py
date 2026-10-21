"""PortfolioFitService: the Portfolio Fit Engine (PortfolioIQ's core USP).

Phase 10 rebuild -- see docs/adr/0005-fit-engine-rebuild.md for what this
supersedes and docs/methodology.md Section 7 for the full write-up.

Answers "how well does this stock fit into MY existing portfolio?" using
the z-scored, delta-based formula:

    Fit = w1*Outlook + w2*Sentiment - w3*dRisk + w4*dDiversification - w5*dConcentration

- Outlook: the Phase 6 ML model's probability, centered at 0 (raw = probability - 0.5).
- Sentiment: the Phase 7 time-decayed average news sentiment score.
- dRisk / dDiversification / dConcentration: what happens to the
  PORTFOLIO's annualized volatility / diversification ratio / holdings HHI
  if this stock were added at a modest weight (via
  ``app/portfolio/hypothetical.py``, which uses the exact same Ledoit-Wolf
  covariance machinery as Phase 8) -- these are properties of the
  portfolio-plus-candidate, not of the stock alone.

Each raw term is z-scored against the distribution of that term across the
full stock universe (so "how does this compare to other candidates" is a
real statistical standardization, not a hand-tuned clamp), then combined
with a preset's weights and squashed through a logistic sigmoid to a 0-100
display score. The per-factor "contribution" values are reported in
PRE-SIGMOID (additive/logit) units -- they sum exactly to the sigmoid's
input, not linearly to the displayed 0-100 fit_score, since that final
transform is nonlinear. Stating otherwise would misrepresent what the
number means.
"""

from __future__ import annotations

import math

import numpy as np
from sqlalchemy.orm import Session

from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.models.user import RiskTolerance
from app.portfolio import hypothetical
from app.services import analytics
from app.services.market_data.service import MarketDataService
from app.services.news_service import NewsService

# Each preset's weights sum to 1.0, so logit scale is comparable across presets.
PRESETS: dict[str, dict[str, float]] = {
    "balanced": {
        "outlook": 0.25,
        "sentiment": 0.15,
        "risk_delta": 0.20,
        "diversification_delta": 0.25,
        "concentration_delta": 0.15,
    },
    "risk_averse": {
        "outlook": 0.15,
        "sentiment": 0.10,
        "risk_delta": 0.35,
        "diversification_delta": 0.25,
        "concentration_delta": 0.15,
    },
    "growth_seeking": {
        "outlook": 0.40,
        "sentiment": 0.20,
        "risk_delta": 0.10,
        "diversification_delta": 0.15,
        "concentration_delta": 0.15,
    },
}
DEFAULT_PRESET = "balanced"

# +1: higher raw value is good for fit. -1: higher raw value is bad for fit
# (dRisk and dConcentration going UP is a worse outcome, hence the minus
# signs in the formula above).
TERM_SIGN: dict[str, int] = {
    "outlook": 1,
    "sentiment": 1,
    "risk_delta": -1,
    "diversification_delta": 1,
    "concentration_delta": -1,
}

TERM_DISPLAY_NAME = {
    "outlook": "ML Outlook",
    "sentiment": "News Sentiment",
    "risk_delta": "Risk Impact",
    "diversification_delta": "Diversification Impact",
    "concentration_delta": "Concentration Impact",
}

_PRESET_FROM_RISK_TOLERANCE = {
    RiskTolerance.CONSERVATIVE: "risk_averse",
    RiskTolerance.MODERATE: "balanced",
    RiskTolerance.AGGRESSIVE: "growth_seeking",
}


def default_preset_for(portfolio: Portfolio) -> str:
    if portfolio.user and portfolio.user.profile:
        return _PRESET_FROM_RISK_TOLERANCE.get(portfolio.user.profile.risk_tolerance, DEFAULT_PRESET)
    return DEFAULT_PRESET


def zscore(value: float, mean: float, std: float) -> float:
    """Standard z-score, with the degenerate std=0 case (every candidate
    in the batch has the identical raw value) mapped to 0 rather than
    dividing by zero -- 'no variation to standardize against' is itself
    informative, not an error."""
    return (value - mean) / std if std > 1e-12 else 0.0


def sigmoid_score(logit: float) -> float:
    """Logistic squash of a weighted-z-score sum to a 0-100 display
    score. Monotonic and bounded, replacing the old service's hand-tuned
    per-component clamps with one principled transform applied once, at
    the end."""
    return 100.0 / (1.0 + math.exp(-logit))


class PortfolioFitService:
    def __init__(self, db: Session, preset: str | None = None):
        self.db = db
        self.preset_name = preset if preset in PRESETS else DEFAULT_PRESET
        self.weights = PRESETS[self.preset_name]
        self.market_data = MarketDataService(db)
        self.news_service = NewsService(db)

    def _stock_returns(self, stock: Stock, days: int = 180):
        bars = self.market_data.get_history(stock, days=days)
        df = analytics.ohlcv_to_frame(bars)
        close = df.set_index("date")["close"]
        return close.pct_change().dropna()

    def _outlook_raw(self, stock: Stock) -> tuple[float, str]:
        try:
            prediction = PredictionService(self.db).predict_for_stock(stock)
            explanation = (
                f"Model outlook is {prediction.direction.value.lower()} with "
                f"{prediction.probability * 100:.0f}% estimated probability ({prediction.confidence.value.lower()} confidence)."
            )
            return prediction.probability - 0.5, explanation
        except (ModelNotTrainedError, ValueError):
            return 0.0, "No model prediction available yet; treated as neutral."

    def _sentiment_raw(self, stock: Stock) -> tuple[float, str]:
        summary = self.news_service.get_sentiment_summary(stock)
        score = summary.get("average_score_time_decayed", 0.0) or 0.0
        if summary.get("article_count", 0) == 0:
            explanation = "No recent news; treated as neutral sentiment."
        else:
            explanation = (
                f"Time-decayed average sentiment is {score:+.2f} across "
                f"{summary['article_count']} recent articles."
            )
        return score, explanation

    def _diagnostics(self, stock: Stock, portfolio: Portfolio) -> tuple[float, float | None]:
        """Standalone volatility and average correlation with current
        holdings -- descriptive context shown in the UI, not formula
        inputs (correlation's job moved into the portfolio-level
        dDiversification/dRisk deltas, which account for it properly via
        the covariance matrix rather than a naive pairwise average)."""
        stock_returns = self._stock_returns(stock)
        stock_vol = analytics.volatility_from_returns(stock_returns)

        holdings = [h for h in portfolio.holdings if h.stock_id != stock.id]
        if not holdings:
            return stock_vol, None
        correlations = []
        for h in holdings:
            other_returns = self._stock_returns(h.stock)
            aligned = stock_returns.to_frame("a").join(other_returns.to_frame("b"), how="inner")
            if len(aligned) < 10:
                continue
            corr = aligned["a"].corr(aligned["b"])
            if not np.isnan(corr):
                correlations.append(corr)
        avg_corr = float(np.mean(correlations)) if correlations else None
        return stock_vol, avg_corr

    def _raw_terms_for_stock(self, stock: Stock, portfolio: Portfolio, current: dict | None) -> dict[str, float]:
        outlook_raw, outlook_expl = self._outlook_raw(stock)
        sentiment_raw, sentiment_expl = self._sentiment_raw(stock)

        already_held = any(h.stock_id == stock.id for h in portfolio.holdings)
        hypo = hypothetical.hypothetical_metrics_after_adding(self.db, portfolio, stock)

        if already_held:
            risk_delta = div_delta = conc_delta = 0.0
            delta_expl = (
                "You already hold this stock, so 'adding more' has no raw effect on portfolio "
                "risk/diversification/concentration (delta = 0); its z-score/contribution below "
                "only reflects how a zero change compares to other candidates' typical impact."
            )
        elif current is None or hypo is None:
            risk_delta = div_delta = conc_delta = 0.0
            delta_expl = "Not enough overlapping price history to simulate adding this stock; deltas treated as neutral."
        else:
            risk_delta = hypo["annualized_volatility"] - current["annualized_volatility"]
            div_delta = hypo["diversification_ratio"] - current["diversification_ratio"]
            conc_delta = hypo["hhi_holdings"] - current["hhi_holdings"]
            delta_expl = None

        return {
            "raw": {
                "outlook": outlook_raw,
                "sentiment": sentiment_raw,
                "risk_delta": risk_delta,
                "diversification_delta": div_delta,
                "concentration_delta": conc_delta,
            },
            "explanations": {
                "outlook": outlook_expl,
                "sentiment": sentiment_expl,
                "risk_delta": delta_expl or f"Adding this stock would change portfolio volatility by {risk_delta * 100:+.2f} pts.",
                "diversification_delta": delta_expl or f"Adding this stock would change the diversification ratio by {div_delta:+.3f}.",
                "concentration_delta": delta_expl or f"Adding this stock would change holdings concentration (HHI) by {conc_delta:+.4f}.",
            },
        }

    def compute_fit_batch(self, portfolio: Portfolio, stocks: list[Stock]) -> dict[str, dict]:
        """Computes fit for every stock in `stocks`, z-scoring each raw
        term against this batch's distribution. Pass the full stock
        universe (not just a few candidates) for a statistically
        meaningful z-score -- a batch of 2-3 stocks makes 'standardized
        against the population' close to meaningless."""
        current = hypothetical.current_metrics(self.db, portfolio)

        per_stock_raw: dict[str, dict] = {}
        for stock in stocks:
            per_stock_raw[stock.symbol] = self._raw_terms_for_stock(stock, portfolio, current)

        term_names = list(self.weights.keys())
        term_matrix = {
            term: np.array([per_stock_raw[s.symbol]["raw"][term] for s in stocks]) for term in term_names
        }
        term_mean = {term: float(np.mean(vals)) for term, vals in term_matrix.items()}
        term_std = {term: float(np.std(vals)) for term, vals in term_matrix.items()}

        results: dict[str, dict] = {}
        for stock in stocks:
            raw = per_stock_raw[stock.symbol]["raw"]
            explanations = per_stock_raw[stock.symbol]["explanations"]

            z_scores = {term: zscore(raw[term], term_mean[term], term_std[term]) for term in term_names}

            logit = sum(TERM_SIGN[term] * self.weights[term] * z_scores[term] for term in term_names)
            fit_score = round(sigmoid_score(logit), 1)

            factors = []
            for term in term_names:
                contribution = TERM_SIGN[term] * self.weights[term] * z_scores[term]
                factors.append(
                    {
                        "name": TERM_DISPLAY_NAME[term],
                        "contribution": round(contribution, 3),
                        "explanation": explanations[term],
                        "raw_value": round(raw[term], 4),
                        "z_score": round(z_scores[term], 3),
                    }
                )
            factors.sort(key=lambda f: -f["contribution"])

            strengths = [f["explanation"] for f in factors if f["contribution"] > 0.03][:3]
            concerns = [f["explanation"] for f in factors if f["contribution"] < -0.03][:3]

            stock_vol, avg_corr = self._diagnostics(stock, portfolio)

            results[stock.symbol] = {
                "symbol": stock.symbol,
                "name": stock.name,
                "fit_score": fit_score,
                "preset": self.preset_name,
                "factors": factors,
                "strengths": strengths,
                "concerns": concerns,
                "weights_used": self.weights,
                "_stock_vol": stock_vol,
                "_avg_correlation": avg_corr,
                "_prediction_probability": raw["outlook"] + 0.5,
                "_logit": logit,
                "_raw": dict(raw),
                "_z_scores": dict(z_scores),
                "_term_std": dict(term_std),
            }
        return results

    def compute_fit(self, stock: Stock, portfolio: Portfolio) -> dict:
        """Single-stock entry point. Z-scores against the FULL stock
        universe (every seeded stock), since a single candidate has no
        batch of its own to standardize against."""
        universe = self.db.query(Stock).all()
        if stock not in universe:
            universe = universe + [stock]
        batch = self.compute_fit_batch(portfolio, universe)
        return batch[stock.symbol]
