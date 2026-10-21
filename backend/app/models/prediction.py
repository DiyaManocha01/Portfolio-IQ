import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Direction(str, enum.Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class Confidence(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "xgboost", "random_forest"
    # Phase 6: content-hash fingerprint of the exact methodology (features,
    # split params, calibration method, model type) that produced this
    # prediction -- lets two predictions be compared only when they're
    # actually from the same training methodology. Nullable: rows created
    # before Phase 6 won't have one.
    model_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direction: Mapped[Direction] = mapped_column(Enum(Direction, name="prediction_direction"), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)  # model probability of positive class
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence, name="prediction_confidence"), nullable=False)
    important_features: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded list
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="predictions")
