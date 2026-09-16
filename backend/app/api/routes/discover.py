from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.portfolio.discover_service import DiscoverService
from app.schemas.portfolio import DiscoverItem

router = APIRouter(tags=["discover"])


@router.get("/discover", response_model=list[DiscoverItem])
def discover(
    limit: int = 20,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    results = DiscoverService(db).get_candidates(portfolio, limit=limit)
    return [DiscoverItem(**r) for r in results]
