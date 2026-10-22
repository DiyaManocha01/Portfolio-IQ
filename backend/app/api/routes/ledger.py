"""Public prediction ledger endpoints (Phase 18).

DELIBERATELY UNAUTHENTICATED -- no Authorization header required. The
entire point of a "verified public track record" is that a third party
can check it WITHOUT an account or trusting this project's own UI. This
is the first genuinely public (no-auth) data surface in this app; see
docs/adr/0007-prediction-ledger.md for why.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.ml import prediction_ledger
from app.models.prediction_ledger import PredictionLedgerEntry
from app.schemas.ledger import LedgerEntryOut, LedgerVerification, PaperTradingSummary, TrackRecord

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("/entries", response_model=list[LedgerEntryOut])
def list_entries(
    symbol: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(PredictionLedgerEntry).order_by(PredictionLedgerEntry.id.asc())
    if symbol:
        query = query.filter(PredictionLedgerEntry.symbol == symbol.upper())
    entries = query.offset(offset).limit(limit).all()
    return [LedgerEntryOut.model_validate(e) for e in entries]


@router.get("/verify", response_model=LedgerVerification)
def verify(db: Session = Depends(get_db)):
    result = prediction_ledger.verify_chain(db)
    return LedgerVerification(**result)


@router.get("/track-record", response_model=TrackRecord)
def track_record(db: Session = Depends(get_db)):
    stats = prediction_ledger.compute_track_record_stats(db)
    return TrackRecord(
        total_predictions=stats["total_predictions"],
        resolved_count=stats["resolved_count"],
        pending_count=stats["pending_count"],
        directional_predictions_resolved=stats["directional_predictions_resolved"],
        directional_hit_rate=stats["directional_hit_rate"],
        paper_trading=PaperTradingSummary(**stats["paper_trading"]),
        note=stats["note"],
    )
