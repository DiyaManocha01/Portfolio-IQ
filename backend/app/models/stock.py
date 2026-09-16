import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class DataSource(str, enum.Enum):
    LIVE = "LIVE"
    DEV_SAMPLE = "DEV_SAMPLE"


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False, default="Unknown")
    industry: Mapped[str] = mapped_column(String(150), nullable=False, default="Unknown")
    exchange: Mapped[str] = mapped_column(String(50), nullable=False, default="NSE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    market_data: Mapped[list["MarketData"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    financial_metrics: Mapped[list["FinancialMetric"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    news_items: Mapped[list["News"]] = relationship(back_populates="stock", cascade="all, delete-orphan")


class MarketData(Base):
    __tablename__ = "market_data"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_market_data_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource, name="data_source"), default=DataSource.DEV_SAMPLE)

    stock: Mapped["Stock"] = relationship(back_populates="market_data")


class FinancialMetric(Base):
    __tablename__ = "financial_metrics"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_financial_metrics_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    eps: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    book_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[DataSource] = mapped_column(Enum(DataSource, name="data_source"), default=DataSource.DEV_SAMPLE)

    stock: Mapped["Stock"] = relationship(back_populates="financial_metrics")
