from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.screener import ScreenerOut, ScreenerResultOut
from app.services.screener_service import ScreenerFilters, run_screener

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("", response_model=ScreenerOut)
def get_screener(
    sector: str | None = None,
    market_cap_min: float | None = None,
    market_cap_max: float | None = None,
    pe_min: float | None = None,
    pe_max: float | None = None,
    roe_min: float | None = None,
    debt_to_equity_max: float | None = None,
    dividend_yield_min: float | None = None,
    revenue_growth_min: float | None = None,
    profit_growth_min: float | None = None,
    rsi_min: float | None = None,
    rsi_max: float | None = None,
    momentum_10d_min: float | None = None,
    db: Session = Depends(get_db),
):
    """Phase 26: filters the current stock universe by fundamentals and
    (optionally) technical indicators. Every filter param is optional and
    omitted ones are simply not applied -- an empty query returns the
    whole universe this environment has seeded.
    """
    filters = ScreenerFilters(
        sector=sector,
        market_cap_min=market_cap_min,
        market_cap_max=market_cap_max,
        pe_min=pe_min,
        pe_max=pe_max,
        roe_min=roe_min,
        debt_to_equity_max=debt_to_equity_max,
        dividend_yield_min=dividend_yield_min,
        revenue_growth_min=revenue_growth_min,
        profit_growth_min=profit_growth_min,
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        momentum_10d_min=momentum_10d_min,
    )
    results = run_screener(db, filters)
    return ScreenerOut(count=len(results), results=[ScreenerResultOut(**vars(r)) for r in results])
