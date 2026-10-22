"""The AI portfolio assistant endpoint (Phase 19). Authenticated (unlike
Phase 18's deliberately public ledger) -- this answers questions about
the CURRENT USER's own portfolio data."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio
from app.assistant.assistant_service import AssistantNotConfiguredError, ask
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.schemas.assistant import AssistantAnswer, AssistantQuestion
from app.services.rate_limit import limiter

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAnswer)
@limiter.limit("20/minute")
def ask_assistant(
    request: Request,
    payload: AssistantQuestion,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    try:
        result = ask(db, portfolio, payload.question)
    except AssistantNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return AssistantAnswer(**result)
