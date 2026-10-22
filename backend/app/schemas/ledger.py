from datetime import date, datetime

from pydantic import BaseModel


class LedgerEntryOut(BaseModel):
    id: int
    entry_type: str
    previous_hash: str | None
    entry_hash: str
    created_at: datetime
    stock_id: int | None
    symbol: str | None
    model_name: str | None
    model_version: str | None
    direction: str | None
    probability: float | None
    confidence: str | None
    prediction_date: date | None
    resolves_entry_id: int | None
    realized_direction: str | None
    realized_return: float | None

    class Config:
        from_attributes = True


class LedgerVerification(BaseModel):
    valid: bool
    total_entries: int
    first_broken_entry_id: int | None
    reason: str | None


class PaperTradingSummary(BaseModel):
    n_resolved_positions: int
    cumulative_return: float | None
    sharpe_ratio_unannualized: float | None
    note: str


class TrackRecord(BaseModel):
    total_predictions: int
    resolved_count: int
    pending_count: int
    directional_predictions_resolved: int
    directional_hit_rate: float | None
    paper_trading: PaperTradingSummary
    note: str
    disclaimer: str = (
        "Historical track record only, computed from real recorded predictions. "
        "Not a guarantee of future performance and not financial advice."
    )
