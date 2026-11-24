"""Real Indian Stock Market Intelligence upgrade, Phase G: corporate
events (earnings, dividends, splits, bonuses, buybacks, announcements).

A genuinely new capability -- confirmed entirely absent from this
codebase's 20-table schema during the Phase A audit
(docs/gap-analysis-realtime-upgrade.md). Only EARNINGS dates are
synthesized for DEV_SAMPLE (a structural calendar fact -- a company
reports roughly quarterly); dividend/split/bonus/buyback AMOUNTS are not
fabricated for synthetic data, since this project has no basis for a
realistic per-symbol figure the way it does for an OHLCV random walk --
see app/services/market_data/providers.py's DevSampleProvider and
docs/limitations.md.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.stock import DataSource


class CorporateEventType(str, enum.Enum):
    EARNINGS = "EARNINGS"
    DIVIDEND = "DIVIDEND"
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    BUYBACK = "BUYBACK"
    ANNOUNCEMENT = "ANNOUNCEMENT"


class CorporateEvent(Base):
    __tablename__ = "corporate_events"
    __table_args__ = (
        UniqueConstraint("stock_id", "event_type", "event_date", name="uq_corporate_events_stock_type_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[CorporateEventType] = mapped_column(
        Enum(CorporateEventType, name="corporate_event_type"), nullable=False
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource, name="data_source"), default=DataSource.DEV_SAMPLE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship()  # noqa: F821 -- resolved via SQLAlchemy's class registry
