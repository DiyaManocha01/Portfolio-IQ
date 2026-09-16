from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.portfolio.fit_service import PortfolioFitService
from app.schemas.portfolio import PortfolioFitFactor, PortfolioFitOut
from app.services.market_data.service import MarketDataService

router = APIRouter(tags=["portfolio-fit"])


@router.get("/portfolio-fit/{symbol}", response_model=PortfolioFitOut)
def portfolio_fit(
    symbol: str,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(symbol)
    market_data.get_history(stock)

    fit = PortfolioFitService(db).compute_fit(stock, portfolio)
    return PortfolioFitOut(
        symbol=fit["symbol"],
        name=fit["name"],
        fit_score=fit["fit_score"],
        factors=[PortfolioFitFactor(**f) for f in fit["factors"]],
        strengths=fit["strengths"],
        concerns=fit["concerns"],
        weights_used=fit["weights_used"],
    )
