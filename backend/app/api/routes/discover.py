from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.portfolio.discover_service import DiscoverService
from app.portfolio.fit_service import PRESETS
from app.schemas.portfolio import DiscoverItem

router = APIRouter(tags=["discover"])


@router.get("/discover", response_model=list[DiscoverItem])
def discover(
    limit: int = 20,
    preset: str | None = None,
    sector: str | None = None,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    if preset is not None and preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset: {preset!r}. Must be one of {list(PRESETS)}.")

    results = DiscoverService(db).get_candidates(portfolio, limit=limit, preset=preset, sector=sector)
    return [DiscoverItem(**r) for r in results]
