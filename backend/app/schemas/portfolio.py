from datetime import date, datetime

from pydantic import BaseModel, Field


class HoldingCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    quantity: float = Field(gt=0)
    avg_buy_price: float = Field(gt=0)


class HoldingOut(BaseModel):
    id: int
    symbol: str
    name: str
    sector: str
    quantity: float
    avg_buy_price: float
    current_price: float
    invested_value: float
    current_value: float
    pnl: float
    return_pct: float

    class Config:
        from_attributes = True


class PortfolioSummary(BaseModel):
    portfolio_id: int
    portfolio_value: float
    invested_amount: float
    total_pnl: float
    return_pct: float
    holdings_count: int
    portfolio_risk: str
    health_score: float


class PerformancePoint(BaseModel):
    date: date
    value: float
    invested: float


class PortfolioPerformance(BaseModel):
    points: list[PerformancePoint]
    data_source: str


class AllocationSlice(BaseModel):
    label: str
    value: float
    pct: float


class PortfolioAllocation(BaseModel):
    by_stock: list[AllocationSlice]
    by_sector: list[AllocationSlice]


class RiskContribution(BaseModel):
    symbol: str
    risk_contribution_pct: float


class CorrelationPair(BaseModel):
    symbol_a: str
    symbol_b: str
    correlation: float


class PortfolioRisk(BaseModel):
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    risk_contributions: list[RiskContribution]
    correlation_matrix: list[CorrelationPair]
    sector_concentration: list[AllocationSlice]
    top_stock_concentration_pct: float
    data_source: str


class ScoreComponent(BaseModel):
    name: str
    score: float
    description: str


class PortfolioHealth(BaseModel):
    overall_health: float
    components: list[ScoreComponent]
    computed_at: datetime


class WeaknessOut(BaseModel):
    title: str
    severity: str
    explanation: str
    supporting_metric: str


class PortfolioWeaknesses(BaseModel):
    weaknesses: list[WeaknessOut]


class PortfolioFitFactor(BaseModel):
    name: str
    contribution: float
    explanation: str


class PortfolioFitOut(BaseModel):
    symbol: str
    name: str
    fit_score: float
    factors: list[PortfolioFitFactor]
    strengths: list[str]
    concerns: list[str]
    weights_used: dict[str, float]


class DiscoverItem(BaseModel):
    symbol: str
    name: str
    sector: str
    current_price: float
    ml_outlook: str
    prediction_probability: float
    volatility: float
    portfolio_fit: float
    correlation_with_portfolio: float
    diversification_benefit: str
