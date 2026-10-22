"""The prediction ledger (Phase 18): an append-only, hash-chained record
of every genuinely new prediction the deployed model makes, plus a
"resolution" entry once each prediction's real outcome becomes knowable.

See app/ml/prediction_ledger.py for the hash-chain logic and
docs/adr/0007-prediction-ledger.md for why this table has two entry
"kinds" in one chain instead of mutating a prediction row in place once
its outcome is known -- the short version: mutating a row to attach its
outcome would not be append-only. A Postgres trigger (added in the
Alembic migration that creates this table) rejects any UPDATE or DELETE
against this table at the database level, not just by application
convention.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class LedgerEntryType(str, enum.Enum):
    PREDICTION = "prediction"
    RESOLUTION = "resolution"


class PredictionLedgerEntry(Base):
    __tablename__ = "prediction_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_type: Mapped[LedgerEntryType] = mapped_column(Enum(LedgerEntryType, name="ledger_entry_type"), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # Set explicitly in Python at append time (not a server_default) --
    # it is part of the hashed payload, so it must be fixed before the
    # hash is computed, not assigned by the database after insert.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- "prediction" entry fields (null on "resolution" entries) ---
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prediction_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # --- "resolution" entry fields (null on "prediction" entries) ---
    resolves_entry_id: Mapped[int | None] = mapped_column(ForeignKey("prediction_ledger.id"), nullable=True)
    realized_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "UP" | "DOWN" | "FLAT"
    realized_return: Mapped[float | None] = mapped_column(Float, nullable=True)
