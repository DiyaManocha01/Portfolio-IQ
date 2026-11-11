"""Phase 27: configurable alert rules + the events they trigger.

One generic `AlertRule` table covers all 8 requested alert types rather
than 8 separate tables -- they share the same shape (an optional stock
scope, an optional direction, a threshold, and dedup state), and a type
enum plus a dispatcher in `app/services/alert_service.py` is simpler than
eight near-identical tables.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class AlertRuleType(str, enum.Enum):
    PRICE_THRESHOLD = "PRICE_THRESHOLD"
    PRICE_PCT_MOVE = "PRICE_PCT_MOVE"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    RSI_THRESHOLD = "RSI_THRESHOLD"
    SENTIMENT_CHANGE = "SENTIMENT_CHANGE"
    PORTFOLIO_VOLATILITY_CHANGE = "PORTFOLIO_VOLATILITY_CHANGE"
    SECTOR_CONCENTRATION_CHANGE = "SECTOR_CONCENTRATION_CHANGE"
    FIT_RANKING_CHANGE = "FIT_RANKING_CHANGE"


class AlertDirection(str, enum.Enum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_type: Mapped[AlertRuleType] = mapped_column(Enum(AlertRuleType, name="alert_rule_type"), nullable=False)
    # Stock-scoped rule types (PRICE_*, VOLUME_SPIKE, RSI_THRESHOLD,
    # SENTIMENT_CHANGE, FIT_RANKING_CHANGE) set this; portfolio-level types
    # (PORTFOLIO_VOLATILITY_CHANGE, SECTOR_CONCENTRATION_CHANGE) leave it null.
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=True, index=True)
    # ABOVE/BELOW for PRICE_THRESHOLD and RSI_THRESHOLD; unused (null) for
    # every delta-based type, where a threshold is a magnitude, not a side.
    direction: Mapped[AlertDirection | None] = mapped_column(Enum(AlertDirection, name="alert_direction"), nullable=True)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Dedup state -- see app/services/alert_service.py's module docstring
    # for exactly how each rule type uses these to avoid re-firing on
    # every evaluation tick while a condition continues to hold.
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship()  # noqa: F821 -- resolved via SQLAlchemy's class registry
    events: Mapped[list["AlertEvent"]] = relationship(back_populates="rule", cascade="all, delete-orphan")


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    rule: Mapped["AlertRule"] = relationship(back_populates="events")
