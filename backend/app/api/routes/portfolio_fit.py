from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.portfolio.fit_counterfactual_service import FitCounterfactualService
from app.portfolio.fit_service import PRESETS, PortfolioFitService, default_preset_for
from app.schemas.portfolio import (
    FitCounterfactual,
    FitRankingGap,
    FitTermDelta,
    FitTermScenario,
    PortfolioFitFactor,
    PortfolioFitOut,
)
from app.services.market_data.service import MarketDataService

router = APIRouter(tags=["portfolio-fit"])


@router.get("/portfolio-fit/{symbol}", response_model=PortfolioFitOut)
def portfolio_fit(
    symbol: str,
    preset: str | None = None,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    if preset is not None and preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset!r}. Must be one of {list(PRESETS)}.")

    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(symbol)
    market_data.get_history(stock)

    chosen_preset = preset or default_preset_for(portfolio)
    fit = PortfolioFitService(db, preset=chosen_preset).compute_fit(stock, portfolio)
    return PortfolioFitOut(
        symbol=fit["symbol"],
        name=fit["name"],
        fit_score=fit["fit_score"],
        preset=fit["preset"],
        factors=[PortfolioFitFactor(**f) for f in fit["factors"]],
        strengths=fit["strengths"],
        concerns=fit["concerns"],
        weights_used=fit["weights_used"],
    )


@router.get("/portfolio-fit/{symbol}/compare/{other_symbol}", response_model=FitRankingGap)
def portfolio_fit_compare(
    symbol: str,
    other_symbol: str,
    preset: str | None = None,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    if preset is not None and preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset!r}. Must be one of {list(PRESETS)}.")

    market_data = MarketDataService(db)
    stock_a = market_data.get_or_create_stock(symbol)
    stock_b = market_data.get_or_create_stock(other_symbol)
    market_data.get_history(stock_a)
    market_data.get_history(stock_b)

    gap = FitCounterfactualService(db, preset=preset).explain_ranking_gap(portfolio, stock_a, stock_b)
    return FitRankingGap(
        symbol_a=gap["symbol_a"],
        symbol_b=gap["symbol_b"],
        fit_score_a=gap["fit_score_a"],
        fit_score_b=gap["fit_score_b"],
        logit_gap=gap["logit_gap"],
        term_deltas=[FitTermDelta(**d) for d in gap["term_deltas"]],
        preset=gap["preset"],
        note=gap["note"],
    )


@router.get("/portfolio-fit/{symbol}/counterfactual", response_model=FitCounterfactual)
def portfolio_fit_counterfactual(
    symbol: str,
    target_symbol: str | None = None,
    target_score: float | None = None,
    preset: str | None = None,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    if preset is not None and preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset!r}. Must be one of {list(PRESETS)}.")
    if (target_symbol is None) == (target_score is None):
        raise HTTPException(status_code=400, detail="Provide exactly one of target_symbol or target_score.")

    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(symbol)
    market_data.get_history(stock)

    target_stock = None
    if target_symbol is not None:
        target_stock = market_data.get_or_create_stock(target_symbol)
        market_data.get_history(target_stock)

    try:
        cf = FitCounterfactualService(db, preset=preset).what_would_improve_rank(
            portfolio, stock, target_stock=target_stock, target_score=target_score
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FitCounterfactual(
        symbol=cf["symbol"],
        fit_score=cf["fit_score"],
        target=cf["target"],
        already_meets_target=cf["already_meets_target"],
        term_scenarios=[FitTermScenario(**s) for s in cf["term_scenarios"]],
        note=cf["note"],
    )
