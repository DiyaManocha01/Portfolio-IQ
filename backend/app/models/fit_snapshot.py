"""FitScoreSnapshot (Phase 29): a point-in-time Fit Engine result, kept so a
later recompute can be skipped when nothing relevant has changed, and so a
new result can explain *why* it moved relative to the last one. See
docs/adr/0012-dynamic-fit-engine.md.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class FitScoreSnapshot(Base):
    __tablename__ = "fit_score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True)
    preset: Mapped[str] = mapped_column(String(32), nullable=False)
    fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    # JSON-encoded {"factors": [...], "strengths": [...], "concerns": [...], "weights_used": {...}}
    # -- the full serializable compute_fit() result besides fit_score itself,
    # so a cache hit never has to re-derive strengths/concerns from factors.
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    portfolio: Mapped["Portfolio"] = relationship()
    stock: Mapped["Stock"] = relationship()
