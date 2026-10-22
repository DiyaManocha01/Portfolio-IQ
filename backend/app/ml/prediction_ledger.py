"""The prediction ledger's hash-chain logic (Phase 18): appending new
prediction entries, resolving their outcomes once knowable, verifying
chain integrity, and computing the public track record.

See docs/adr/0007-prediction-ledger.md for the design and
docs/methodology.md Section 15 for the full write-up. Short version:

- Every entry's hash = sha256(previous_entry_hash + canonical_json(payload)).
  Recomputing every hash and comparing to what's stored (verify_chain)
  detects ANY alteration of ANY past entry or payload field -- that's
  what "tamper-evident" means here. A Postgres trigger (added in the
  table's Alembic migration) additionally rejects UPDATE/DELETE against
  this table at the database level.
- A prediction's outcome is recorded as a NEW "resolution" entry chained
  onto the end, never by editing the original "prediction" entry -- that
  is what keeps the whole table genuinely append-only.
- This is tamper-EVIDENT, not tamper-PROOF: someone with direct database
  admin access could still truncate the table and start a new chain from
  scratch, and nothing here would detect that from outside the database.
  A fully tamper-proof public record would need external anchoring (e.g.
  periodically publishing the latest hash somewhere outside this
  project's own control) -- explicitly out of scope here, not hidden.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prediction import Prediction
from app.models.prediction_ledger import LedgerEntryType, PredictionLedgerEntry
from app.models.stock import MarketData, Stock

RISK_FREE_RATE = 0.06  # same assumption used elsewhere in this project


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(previous_hash: str | None, payload: dict) -> str:
    material = (previous_hash or "GENESIS") + _canonical_json(payload)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _latest_entry(db: Session) -> PredictionLedgerEntry | None:
    return db.execute(
        select(PredictionLedgerEntry).order_by(PredictionLedgerEntry.id.desc()).limit(1)
    ).scalar_one_or_none()


def _prediction_payload(entry_type: str, created_at: datetime, **fields) -> dict:
    payload = {"entry_type": entry_type, "created_at": created_at.isoformat()}
    payload.update(fields)
    return payload


def append_prediction_entry(db: Session, stock: Stock, prediction: Prediction) -> PredictionLedgerEntry | None:
    """Appends a new 'prediction' entry -- but ONLY if one doesn't already
    exist for this (stock, model_name, prediction_date): predict_for_stock()
    can be called many times for the same stock on the same day (cached
    reads), and the ledger's job is to record that a prediction was MADE,
    once, not every time it was subsequently read. Returns None if an
    entry already exists (no duplicate append, not an error)."""
    existing = db.execute(
        select(PredictionLedgerEntry).where(
            PredictionLedgerEntry.entry_type == LedgerEntryType.PREDICTION,
            PredictionLedgerEntry.stock_id == stock.id,
            PredictionLedgerEntry.model_name == prediction.model_name,
            PredictionLedgerEntry.prediction_date == prediction.prediction_date,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None

    previous = _latest_entry(db)
    previous_hash = previous.entry_hash if previous else None
    created_at = datetime.now(timezone.utc)

    payload = _prediction_payload(
        LedgerEntryType.PREDICTION.value,
        created_at,
        stock_id=stock.id,
        symbol=stock.symbol,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        direction=prediction.direction.value,
        probability=prediction.probability,
        confidence=prediction.confidence.value,
        prediction_date=prediction.prediction_date.isoformat(),
    )
    entry_hash = _compute_hash(previous_hash, payload)

    entry = PredictionLedgerEntry(
        entry_type=LedgerEntryType.PREDICTION,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        created_at=created_at,
        stock_id=stock.id,
        symbol=stock.symbol,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        direction=prediction.direction.value,
        probability=prediction.probability,
        confidence=prediction.confidence.value,
        prediction_date=prediction.prediction_date,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _next_close_after(db: Session, stock_id: int, after_date) -> float | None:
    row = db.execute(
        select(MarketData.close)
        .where(MarketData.stock_id == stock_id, MarketData.date > after_date)
        .order_by(MarketData.date.asc())
        .limit(1)
    ).scalar_one_or_none()
    return row


def _close_on(db: Session, stock_id: int, on_date) -> float | None:
    row = db.execute(
        select(MarketData.close).where(MarketData.stock_id == stock_id, MarketData.date == on_date)
    ).scalar_one_or_none()
    return row


def resolve_due_entries(db: Session) -> list[PredictionLedgerEntry]:
    """Finds every 'prediction' entry with no 'resolution' entry yet, and
    resolves it IF the next trading day's close is already in the cache
    (i.e. the outcome is genuinely knowable now, not guessed). Appends
    one 'resolution' entry per newly-resolved prediction, processed in
    order so each one chains onto the TRUE current tail (which moves
    after every append within this same call)."""
    resolved_ids_subq = select(PredictionLedgerEntry.resolves_entry_id).where(
        PredictionLedgerEntry.entry_type == LedgerEntryType.RESOLUTION,
        PredictionLedgerEntry.resolves_entry_id.is_not(None),
    )
    unresolved = db.execute(
        select(PredictionLedgerEntry)
        .where(
            PredictionLedgerEntry.entry_type == LedgerEntryType.PREDICTION,
            PredictionLedgerEntry.id.not_in(resolved_ids_subq),
        )
        .order_by(PredictionLedgerEntry.id.asc())
    ).scalars().all()

    newly_resolved = []
    for pred_entry in unresolved:
        close_on_pred_date = _close_on(db, pred_entry.stock_id, pred_entry.prediction_date)
        close_next = _next_close_after(db, pred_entry.stock_id, pred_entry.prediction_date)
        if close_on_pred_date is None or close_next is None:
            continue  # outcome not knowable yet -- stays pending, not guessed

        realized_return = (close_next / close_on_pred_date) - 1.0
        if realized_return > 0:
            realized_direction = "UP"
        elif realized_return < 0:
            realized_direction = "DOWN"
        else:
            realized_direction = "FLAT"

        previous = _latest_entry(db)
        previous_hash = previous.entry_hash if previous else None
        created_at = datetime.now(timezone.utc)

        payload = _prediction_payload(
            LedgerEntryType.RESOLUTION.value,
            created_at,
            resolves_entry_id=pred_entry.id,
            realized_direction=realized_direction,
            realized_return=round(realized_return, 6),
        )
        entry_hash = _compute_hash(previous_hash, payload)

        resolution = PredictionLedgerEntry(
            entry_type=LedgerEntryType.RESOLUTION,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            created_at=created_at,
            resolves_entry_id=pred_entry.id,
            realized_direction=realized_direction,
            realized_return=round(realized_return, 6),
        )
        db.add(resolution)
        db.commit()
        db.refresh(resolution)
        newly_resolved.append(resolution)

    return newly_resolved


def verify_chain(db: Session) -> dict:
    """Walks every entry in insertion order and recomputes its hash from
    its own stored payload + previous_hash, comparing to the stored
    entry_hash, AND checks that each entry's previous_hash actually
    equals the preceding entry's entry_hash. Either check failing at any
    entry means the chain has been tampered with (or corrupted) at or
    before that point."""
    entries = db.execute(select(PredictionLedgerEntry).order_by(PredictionLedgerEntry.id.asc())).scalars().all()

    expected_previous_hash = None
    for entry in entries:
        if entry.previous_hash != expected_previous_hash:
            return {
                "valid": False,
                "total_entries": len(entries),
                "first_broken_entry_id": entry.id,
                "reason": "previous_hash does not match the preceding entry's hash",
            }

        if entry.entry_type == LedgerEntryType.PREDICTION:
            payload = _prediction_payload(
                LedgerEntryType.PREDICTION.value,
                entry.created_at,
                stock_id=entry.stock_id,
                symbol=entry.symbol,
                model_name=entry.model_name,
                model_version=entry.model_version,
                direction=entry.direction,
                probability=entry.probability,
                confidence=entry.confidence,
                prediction_date=entry.prediction_date.isoformat() if entry.prediction_date else None,
            )
        else:
            payload = _prediction_payload(
                LedgerEntryType.RESOLUTION.value,
                entry.created_at,
                resolves_entry_id=entry.resolves_entry_id,
                realized_direction=entry.realized_direction,
                realized_return=entry.realized_return,
            )

        recomputed_hash = _compute_hash(entry.previous_hash, payload)
        if recomputed_hash != entry.entry_hash:
            return {
                "valid": False,
                "total_entries": len(entries),
                "first_broken_entry_id": entry.id,
                "reason": "stored entry_hash does not match the recomputed hash of this entry's own payload",
            }

        expected_previous_hash = entry.entry_hash

    return {"valid": True, "total_entries": len(entries), "first_broken_entry_id": None, "reason": None}


def compute_track_record_stats(db: Session) -> dict:
    """Catches up on resolution first, then computes the public track
    record: directional hit rate (POSITIVE/NEGATIVE predictions only --
    NEUTRAL isn't a directional bet) and a genuine FORWARD paper-trading
    summary (long when POSITIVE, flat otherwise -- same strategy
    definition as Phase 13's backtest, but computed here from real,
    already-made, immutable predictions rather than a retrospective
    simulation)."""
    resolve_due_entries(db)

    predictions = db.execute(
        select(PredictionLedgerEntry)
        .where(PredictionLedgerEntry.entry_type == LedgerEntryType.PREDICTION)
        .order_by(PredictionLedgerEntry.prediction_date.asc(), PredictionLedgerEntry.id.asc())
    ).scalars().all()
    resolutions_by_pred_id = {
        r.resolves_entry_id: r
        for r in db.execute(
            select(PredictionLedgerEntry).where(PredictionLedgerEntry.entry_type == LedgerEntryType.RESOLUTION)
        ).scalars()
    }

    total = len(predictions)
    resolved = [(p, resolutions_by_pred_id[p.id]) for p in predictions if p.id in resolutions_by_pred_id]
    pending_count = total - len(resolved)

    directional = [(p, r) for p, r in resolved if p.direction in ("POSITIVE", "NEGATIVE")]
    hits = sum(
        1
        for p, r in directional
        if (p.direction == "POSITIVE" and r.realized_direction == "UP")
        or (p.direction == "NEGATIVE" and r.realized_direction == "DOWN")
    )
    hit_rate = round(hits / len(directional), 4) if directional else None

    paper_returns = [r.realized_return if p.direction == "POSITIVE" else 0.0 for p, r in resolved]
    if paper_returns:
        cumulative_return = 1.0
        for ret in paper_returns:
            cumulative_return *= 1 + ret
        cumulative_return -= 1.0
        n = len(paper_returns)
        mean_r = sum(paper_returns) / n
        if n > 1:
            variance = sum((r - mean_r) ** 2 for r in paper_returns) / (n - 1)
            std_r = variance**0.5
        else:
            std_r = 0.0
        sharpe = (mean_r / std_r) if std_r > 1e-12 else None
    else:
        cumulative_return = None
        sharpe = None

    return {
        "total_predictions": total,
        "resolved_count": len(resolved),
        "pending_count": pending_count,
        "directional_predictions_resolved": len(directional),
        "directional_hit_rate": hit_rate,
        "paper_trading": {
            "n_resolved_positions": len(paper_returns),
            "cumulative_return": round(cumulative_return, 4) if cumulative_return is not None else None,
            "sharpe_ratio_unannualized": round(sharpe, 3) if sharpe is not None else None,
            "note": (
                "Long when the prediction was POSITIVE, flat otherwise -- same strategy "
                "definition as Phase 13's backtest, but computed here from real, already-made, "
                "append-only predictions rather than a retrospective walk-forward simulation."
            ),
        },
        "note": (
            "This track record grows only from genuinely new predictions made since Phase 18 "
            "shipped -- no history has been backdated or fabricated. A thin or empty record "
            "reflects how new this ledger is, not a data gap."
        ),
    }
