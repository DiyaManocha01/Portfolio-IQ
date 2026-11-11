"""Dynamic Portfolio Fit Engine (Phase 29): caches a Fit Engine result and
explains why it moved relative to the last time it was computed, rather
than recomputing PortfolioFitService.compute_fit on every single request
regardless of whether anything it depends on actually changed. See
docs/adr/0012-dynamic-fit-engine.md.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.ml.predict import ModelNotTrainedError, PredictionService
from app.models.fit_snapshot import FitScoreSnapshot
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.fit_service import PortfolioFitService, default_preset_for
from app.services.market_data.service import MarketDataService
from app.services.news_service import NewsService


def _model_version(db: Session) -> str:
    try:
        return PredictionService(db).model_version
    except ModelNotTrainedError:
        return "untrained"


def compute_input_fingerprint(db: Session, portfolio: Portfolio, stock: Stock) -> str:
    """A short hash of everything compute_fit's result actually depends on:
    the stock's latest price date, the trained model's version, the
    stock's current time-decayed sentiment score, and the portfolio's full
    holdings composition (the risk/diversification/concentration delta
    terms depend on the WHOLE portfolio, not just this stock).

    Deliberately coarse, not a bit-for-bit hash of every float: price is
    keyed off its `date` (a new trading day's bar landed), not `close`,
    and sentiment is rounded to 2 decimals -- so a sub-cent difference
    that doesn't change what a user would see can't force a recompute.
    """
    market_data = MarketDataService(db)
    latest, _ = market_data.get_quote(stock)
    price_component = latest.date.isoformat() if latest else "no-price"

    summary = NewsService(db).get_sentiment_summary(stock)
    sentiment_score = round(summary.get("average_score_time_decayed", 0.0) or 0.0, 2)
    sentiment_component = f"{sentiment_score}:{summary.get('article_count', 0)}"

    holdings_component = "|".join(
        sorted(f"{h.stock_id}:{h.quantity}:{h.avg_buy_price}" for h in portfolio.holdings)
    )

    raw = f"{price_component}::{_model_version(db)}::{sentiment_component}::{holdings_component}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _latest_snapshot(db: Session, portfolio: Portfolio, stock: Stock, preset: str) -> FitScoreSnapshot | None:
    return (
        db.query(FitScoreSnapshot)
        .filter(
            FitScoreSnapshot.portfolio_id == portfolio.id,
            FitScoreSnapshot.stock_id == stock.id,
            FitScoreSnapshot.preset == preset,
        )
        .order_by(FitScoreSnapshot.computed_at.desc())
        .first()
    )


def _explain_change(previous_score: float, previous_result: dict, current_result: dict, previous_computed_at) -> dict | None:
    """Compares the newly computed result to the previous snapshot and
    explains, in plain language, why the fit score moved: the overall
    point change, plus the single factor whose contribution shifted the
    most (not every factor -- one clear reason reads better than five
    marginal ones). Returns None if the score is unchanged."""
    score_delta = round(current_result["fit_score"] - previous_score, 1)
    if score_delta == 0:
        return None

    prev_contribution_by_name = {f["name"]: f["contribution"] for f in previous_result["factors"]}
    biggest_term = None
    biggest_delta = 0.0
    for f in current_result["factors"]:
        delta = f["contribution"] - prev_contribution_by_name.get(f["name"], 0.0)
        if abs(delta) > abs(biggest_delta):
            biggest_delta = delta
            biggest_term = f["name"]

    direction = "improved" if score_delta > 0 else "fell"
    message = f"Fit score {direction} by {abs(score_delta):.1f} points since the last check"
    if biggest_term and abs(biggest_delta) > 1e-6:
        factor_direction = "more favorable" if biggest_delta > 0 else "less favorable"
        message += f", mainly because {biggest_term} became {factor_direction}."
    else:
        message += "."

    return {
        "score_delta": score_delta,
        "biggest_factor": biggest_term,
        "biggest_factor_delta": round(biggest_delta, 3),
        "message": message,
        "previous_computed_at": previous_computed_at,
    }


def _result_payload(result: dict) -> dict:
    """The subset of compute_fit's return value that's actually
    serialized/cached -- excludes the `_`-prefixed diagnostic-only keys
    (not part of the public API contract)."""
    return {
        "factors": result["factors"],
        "strengths": result["strengths"],
        "concerns": result["concerns"],
        "weights_used": result["weights_used"],
    }


def get_fit_with_change(db: Session, portfolio: Portfolio, stock: Stock, preset: str | None = None) -> dict:
    """Returns the same shape as PortfolioFitService.compute_fit, plus a
    `change` key: None if this is served from cache (nothing relevant has
    changed since the last computation) or if this is the very first
    snapshot ever taken (nothing to compare against), otherwise a plain-
    language explanation of why the score moved since the previous
    snapshot.
    """
    chosen_preset = preset if preset else default_preset_for(portfolio)
    fingerprint = compute_input_fingerprint(db, portfolio, stock)
    latest = _latest_snapshot(db, portfolio, stock, chosen_preset)

    if latest is not None and latest.input_fingerprint == fingerprint:
        payload = json.loads(latest.result_json)
        return {
            "symbol": stock.symbol,
            "name": stock.name,
            "fit_score": latest.fit_score,
            "preset": latest.preset,
            "factors": payload["factors"],
            "strengths": payload["strengths"],
            "concerns": payload["concerns"],
            "weights_used": payload["weights_used"],
            "change": None,
            "cached": True,
            "computed_at": latest.computed_at,
        }

    result = PortfolioFitService(db, preset=chosen_preset).compute_fit(stock, portfolio)

    change = None
    if latest is not None:
        previous_payload = json.loads(latest.result_json)
        change = _explain_change(latest.fit_score, previous_payload, result, latest.computed_at.isoformat())

    snapshot = FitScoreSnapshot(
        portfolio_id=portfolio.id,
        stock_id=stock.id,
        preset=chosen_preset,
        fit_score=result["fit_score"],
        result_json=json.dumps(_result_payload(result)),
        input_fingerprint=fingerprint,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return {
        "symbol": result["symbol"],
        "name": result["name"],
        "fit_score": result["fit_score"],
        "preset": result["preset"],
        "factors": result["factors"],
        "strengths": result["strengths"],
        "concerns": result["concerns"],
        "weights_used": result["weights_used"],
        "change": change,
        "cached": False,
        "computed_at": snapshot.computed_at,
    }
