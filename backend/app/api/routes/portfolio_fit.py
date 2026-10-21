from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.portfolio.fit_service import PRESETS, PortfolioFitService, default_preset_for
from app.schemas.portfolio import PortfolioFitFactor, PortfolioFitOut
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
