"""GET /health (Phase 34) -- a real readiness check, not a trivial
{"status": "ok"}. Deliberately unauthenticated and unrate-limited: a load
balancer or container orchestrator polling this needs it to always be
reachable, and it reveals no portfolio data, only this process's own
dependency status. See app/services/health_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.health_service import check_health
from app.services.rate_limit import limiter

router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.exempt
def health(db: Session = Depends(get_db)):
    return check_health(db)
