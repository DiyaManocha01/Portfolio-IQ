import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.stock import DataSource


class SentimentLabel(str, enum.Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(150), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_source: Mapped[DataSource] = mapped_column(Enum(DataSource, name="data_source"), default=DataSource.DEV_SAMPLE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stock: Mapped["Stock"] = relationship(back_populates="news_items")
    sentiment: Mapped["NewsSentiment"] = relationship(
        back_populates="news", uselist=False, cascade="all, delete-orphan"
    )


class NewsSentiment(Base):
    __tablename__ = "news_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"), unique=True, nullable=False)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=True, index=True)
    sentiment_label: Mapped[SentimentLabel] = mapped_column(Enum(SentimentLabel, name="sentiment_label"), nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)  # -1 (negative) to +1 (positive)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "finbert" or "lexicon-v1"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    news: Mapped["News"] = relationship(back_populates="sentiment")
