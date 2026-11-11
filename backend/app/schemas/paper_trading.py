from datetime import date, datetime

from pydantic import BaseModel, Field

DISCLAIMER = (
    "This is a hypothetical paper-trading account. No real money, real orders, "
    "or brokerage integration is involved -- prices are real (or dev-sample) "
    "market data, but every trade here is simulated."
)


class TradeRequest(BaseModel):
    symbol: str
    quantity: float = Field(gt=0)


class PaperTransactionOut(BaseModel):
    id: int
    symbol: str
    type: str
    quantity: float
    price: float
    fees: float
    realized_pnl: float | None
    executed_at: datetime


class PaperHoldingOut(BaseModel):
    symbol: str
    name: str
    quantity: float
    avg_buy_price: float
    current_price: float
    invested_value: float
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class PaperAccountOut(BaseModel):
    starting_cash: float
    cash_balance: float
    holdings_value: float
    total_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    total_return_pct: float
    holdings: list[PaperHoldingOut]
    data_source: str
    disclaimer: str = DISCLAIMER


class PerformancePoint(BaseModel):
    date: date
    value: float


class PaperPerformanceOut(BaseModel):
    points: list[PerformancePoint]
    benchmark_points: list[PerformancePoint]
    account_return_pct: float
    benchmark_return_pct: float
    data_source: str
    disclaimer: str = DISCLAIMER
