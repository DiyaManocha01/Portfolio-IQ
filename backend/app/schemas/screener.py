from pydantic import BaseModel


class ScreenerResultOut(BaseModel):
    symbol: str
    name: str
    sector: str
    industry: str
    data_source: str
    current_price: float | None
    market_cap: float | None
    pe_ratio: float | None
    eps: float | None
    dividend_yield: float | None
    roe: float | None
    roce: float | None
    debt_to_equity: float | None
    revenue_growth_yoy: float | None
    profit_growth_yoy: float | None
    rsi_14: float | None
    momentum_10d: float | None


class ScreenerOut(BaseModel):
    count: int
    results: list[ScreenerResultOut]
    disclaimer: str = (
        "Screener results are filtered from sourced fundamentals and technical "
        "indicators. This is not a recommendation to buy or sell any stock."
    )
