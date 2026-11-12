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

import datetime as dt
import re

from sqlalchemy.orm import Session

from app.assistant.whatif_parser import parse_whatif_question
from app.ml import prediction_ledger
from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.discover_service import DiscoverService
from app.portfolio.fit_snapshot_service import get_fit_with_change
from app.portfolio.health_service import PortfolioHealthService
from app.portfolio.portfolio_performance_service import get_advanced_performance
from app.portfolio.risk_attribution_service import RiskAttributionService
from app.portfolio.risk_service import PortfolioRiskService
from app.portfolio.weakness_service import PortfolioWeaknessService
from app.portfolio.whatif_service import WhatIfService
from app.services import analytics, market_regime_service, portfolio_calc
from app.services.market_data.service import MarketDataService
from app.services.news_service import NewsService

RISK_KEYWORDS = ("risk", "volatil", "concentrat", "diversif", "exposure")
DISCOVER_KEYWORDS = ("new stock", "add to my portfolio", "candidate", "what fits", "discover")
TRACK_RECORD_KEYWORDS = ("track record", "accuracy", "how good", "how accurate", "model history", "ledger")
FIT_KEYWORDS = ("fit score", "portfolio fit", "fit engine", "good fit", "fits my portfolio", "how well would")
MARKET_KEYWORDS = (
    "market condition", "market regime", "market trend", "overall market", "broader market",
    "nifty", "bull market", "bear market", "market mood", "trending",
)
PERFORMANCE_KEYWORDS = (
    "performance", "how has my portfolio done", "how have i done", "returns", "drawdown",
    "benchmark", "historical return", "cumulative return",
)
WHATIF_KEYWORDS = (
    "what if", "hypothetical", "if i added", "if i add", "if i sold", "if i sell",
    "if i bought", "if i buy", "if i removed", "if i remove",
)

MAX_MENTIONED_SYMBOLS = 3  # cap context size for a single question

# Calendar days of history fetched for a regime classification -- matches
# GET /market/regime's own REGIME_HISTORY_DAYS (app/api/routes/market.py):
# enough to cover classify_regime's trend_window + lookback_days (60 + 252
# trading days) given dev-sample data is business-days-only.
REGIME_HISTORY_DAYS = 500


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
            try:
                bars = MarketDataService(db).get_history(stock, days=180)
                detail["technical_indicators"] = analytics.compute_indicators(analytics.ohlcv_to_frame(bars))
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

    if mentioned and any(k in lowered for k in FIT_KEYWORDS):
        fit_results = {}
        for symbol in mentioned:
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            try:
                fit_results[symbol] = _public_fields(get_fit_with_change(db, portfolio, stock))
            except Exception:
                pass
        if fit_results:
            context["fit_engine"] = fit_results
            sources_used.append(f"fit_engine:{','.join(fit_results)}")

    if any(k in lowered for k in MARKET_KEYWORDS):
        market_data = MarketDataService(db)
        regimes = {}
        try:
            bars = market_data.get_benchmark_history(days=REGIME_HISTORY_DAYS)
            regimes["NIFTY50"] = _public_fields(market_regime_service.classify_regime(bars))
        except Exception:
            pass
        for symbol in mentioned:
            try:
                stock = db.query(Stock).filter(Stock.symbol == symbol).first()
                bars = market_data.get_history(stock, days=REGIME_HISTORY_DAYS)
                regimes[symbol] = _public_fields(market_regime_service.classify_regime(bars))
            except Exception:
                pass
        if regimes:
            context["market_conditions"] = regimes
            sources_used.append("market_conditions")

    if any(k in lowered for k in PERFORMANCE_KEYWORDS):
        try:
            perf = get_advanced_performance(db, portfolio, days=180)
            context["historical_performance"] = {
                "unrealized_pnl": perf["unrealized_pnl"],
                "realized_pnl": perf["realized_pnl"],
                "total_pnl": perf["total_pnl"],
                "annualized_volatility_realized": perf["annualized_volatility_realized"],
                "data_source": perf["data_source"],
                "latest_cumulative_return_pct": (
                    perf["cumulative_returns"][-1]["cumulative_return_pct"] if perf["cumulative_returns"] else None
                ),
                "max_drawdown_pct": min((d["drawdown_pct"] for d in perf["drawdown"]), default=None),
                "holding_contributions": perf["holding_contributions"][:5],
                "sector_contributions": perf["sector_contributions"],
                "as_of": perf["points"][-1]["date"] if perf["points"] else None,
            }
            sources_used.append("historical_performance")
        except Exception:
            pass

    if any(k in lowered for k in WHATIF_KEYWORDS):
        unparsed_note = (
            "This looks like a hypothetical 'what if' question, but I couldn't confidently "
            "extract a single stock and an explicit share quantity to simulate from the question "
            "text (e.g. 'what if I added 10 shares of RELIANCE' or 'what if I sold all my TCS'). "
            "Ask again with one stock and a specific share count, or use the Portfolio Lab's "
            "What-If Simulator for anything more complex (percentage weights, multiple stocks)."
        )
        if len(mentioned) == 1:
            current_quantities = {h.stock.symbol: h.quantity for h in portfolio.holdings}
            parsed = parse_whatif_question(question, mentioned, current_quantities)
            if parsed:
                try:
                    sim = WhatIfService(db).simulate(
                        portfolio, [{"symbol": parsed["symbol"], "new_quantity": parsed["new_quantity"]}]
                    )
                    context["what_if_simulation"] = {**sim, "interpreted_as": parsed["note"]}
                    sources_used.append(f"what_if_simulation:{parsed['symbol']}")
                except ValueError as exc:
                    context["what_if_simulation"] = {"could_not_simulate": True, "reason": str(exc)}
                    sources_used.append("what_if_simulation:error")
            else:
                context["what_if_simulation"] = {"could_not_parse": True, "note": unparsed_note}
                sources_used.append("what_if_simulation:unparsed")
        else:
            context["what_if_simulation"] = {"could_not_parse": True, "note": unparsed_note}
            sources_used.append("what_if_simulation:unparsed")

    context["context_compiled_at"] = dt.datetime.now(tz=dt.timezone.utc).isoformat()

    return {"context": context, "sources_used": sources_used}
