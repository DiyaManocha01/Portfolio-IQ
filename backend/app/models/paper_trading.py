"""Phase 28: Paper Trading -- a wholly separate, hypothetical account.

Deliberately NOT the same tables as the real Portfolio/Holding/Transaction
(app/models/portfolio.py) -- paper trading must never touch or be
conflated with a user's real tracked holdings, the same "never mutate
the real portfolio" principle the Phase 11 What-If Simulator already
established. One PaperAccount per user.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.portfolio import TransactionType


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    starting_cash: Mapped[float] = mapped_column(Float, nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    holdings: Mapped[list["PaperHolding"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    transactions: Mapped[list["PaperTransaction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", order_by="PaperTransaction.executed_at"
    )


class PaperHolding(Base):
    __tablename__ = "paper_holdings"
    __table_args__ = (UniqueConstraint("paper_account_id", "stock_id", name="uq_paper_holdings_account_stock"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped["PaperAccount"] = relationship(back_populates="holdings")
    stock: Mapped["Stock"] = relationship()  # noqa: F821 -- resolved via SQLAlchemy's class registry


class PaperTransaction(Base):
    __tablename__ = "paper_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType, name="transaction_type"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, nullable=False)
    # Only set for SELL transactions -- (price - avg_buy_price_at_sale) *
    # quantity, net of this transaction's own fees. Null for BUY, never 0
    # as a stand-in for "not applicable."
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped["PaperAccount"] = relationship(back_populates="transactions")
    stock: Mapped["Stock"] = relationship()  # noqa: F821
