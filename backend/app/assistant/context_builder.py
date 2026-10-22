"""Deterministic data router for the AI portfolio assistant (Phase 19).

Decides WHICH already-computed data to hand the LLM for a given question
-- via plain keyword/symbol matching (the same style as Phase 15's
scenario_parser.py), never by asking the LLM itself to decide what it
needs. This is what makes "never compute figures itself" actually
enforceable: the assistant_service only ever gets numbers that came from
this module's calls into the EXISTING service layer (risk_service,
health_service, predict.py, etc.) -- it has no other way to produce a
number.

Every data block included is also listed in `sources_used`, so exactly
what was fetched for a given question is always inspectable and testable
without needing a live LLM call at all.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.ml import prediction_ledger
from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.discover_service import DiscoverService
from app.portfolio.health_service import PortfolioHealthService
from app.portfolio.risk_attribution_service import RiskAttributionService
from app.portfolio.risk_service import PortfolioRiskService
from app.portfolio.weakness_service import PortfolioWeaknessService
from app.services import portfolio_calc
from app.services.news_service import NewsService

RISK_KEYWORDS = ("risk", "volatil", "concentrat", "diversif", "exposure")
DISCOVER_KEYWORDS = ("new stock", "add to my portfolio", "candidate", "what fits", "discover")
TRACK_RECORD_KEYWORDS = ("track record", "accuracy", "how good", "how accurate", "model history", "ledger")

MAX_MENTIONED_SYMBOLS = 3  # cap context size for a single question


def _public_fields(d: dict) -> dict:
    """Strips internal (leading-underscore) keys a service dict may carry
    for its own callers (e.g. risk_service's _weights/_returns_df) --
    never pass those to the LLM, both because some aren't JSON-safe
    (DataFrames) and because they're implementation detail, not data this
    question needs answered."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _find_mentioned_symbols(question: str, universe_symbols: list[str]) -> list[str]:
    upper = question.upper()
    return [sym for sym in universe_symbols if re.search(rf"\b{re.escape(sym)}\b", upper)]


def build_context(db: Session, portfolio: Portfolio, question: str) -> dict:
    """Returns {"context": {...plain, JSON-safe dicts...}, "sources_used": [...]}."""
    context: dict = {}
    sources_used: list[str] = []
    lowered = question.lower()

    holdings = portfolio_calc.get_holdings_with_metrics(db, portfolio)
    totals = portfolio_calc.portfolio_totals(holdings)
    context["portfolio_summary"] = {
        **totals,
        "holdings": [
            {"symbol": h["symbol"], "sector": h["sector"], "quantity": h["quantity"], "current_value": h["current_value"]}
            for h in holdings
        ],
    }
    sources_used.append("portfolio_summary")

    health = PortfolioHealthService(db).compute(portfolio)
    context["portfolio_health"] = _public_fields(health)
    sources_used.append("portfolio_health")

    weaknesses = PortfolioWeaknessService(db).detect(portfolio)
    context["portfolio_weaknesses"] = weaknesses
    sources_used.append("portfolio_weaknesses")

    universe_symbols = [s.symbol for s in db.query(Stock).all()]
    mentioned = _find_mentioned_symbols(question, universe_symbols)[:MAX_MENTIONED_SYMBOLS]
    if mentioned:
        stock_details = {}
        for symbol in mentioned:
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            detail: dict = {}
            try:
                prediction = PredictionService(db).predict_for_stock(stock)
                detail["prediction"] = {
                    "direction": prediction.direction.value,
                    "probability": prediction.probability,
                    "confidence": prediction.confidence.value,
                    "model_version": prediction.model_version,
                }
            except (ModelNotTrainedError, ValueError):
                pass
            try:
                sentiment = NewsService(db).get_sentiment_summary(stock)
                detail["sentiment"] = sentiment
            except Exception:
                pass
            stock_details[symbol] = detail
        context["stock_details"] = stock_details
        sources_used.append(f"stock_details:{','.join(mentioned)}")

    if any(k in lowered for k in RISK_KEYWORDS):
        risk = PortfolioRiskService(db).compute(portfolio)
        context["portfolio_risk"] = _public_fields(risk)
        sources_used.append("portfolio_risk")

        attribution = RiskAttributionService(db).compute(portfolio)
        context["risk_attribution"] = attribution
        sources_used.append("risk_attribution")

    if any(k in lowered for k in DISCOVER_KEYWORDS):
        candidates = DiscoverService(db).get_candidates(portfolio, limit=5)
        context["discover_candidates"] = candidates
        sources_used.append("discover_candidates")

    if any(k in lowered for k in TRACK_RECORD_KEYWORDS):
        stats = prediction_ledger.compute_track_record_stats(db)
        context["model_track_record"] = stats
        sources_used.append("model_track_record")

    return {"context": context, "sources_used": sources_used}
