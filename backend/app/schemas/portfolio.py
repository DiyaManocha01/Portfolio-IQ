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
    var_95: float
    cvar_95: float
    var_99: float
    cvar_99: float
    hhi_holdings: float
    hhi_sector: float
    effective_number_of_bets: float
    diversification_ratio: float
    covariance_method: str
    shrinkage_intensity: float
    data_source: str


class RiskAttributionItem(BaseModel):
    symbol: str
    name: str
    sector: str
    weight_pct: float
    risk_contribution_pct: float
    marginal_contribution_to_vol: float
    risk_concentration_ratio: float


class PortfolioRiskAttribution(BaseModel):
    portfolio_annualized_volatility: float
    attributions: list[RiskAttributionItem]
    data_source: str


class OptimizationAllocation(BaseModel):
    symbol: str
    current_weight_pct: float
    suggested_weight_pct: float
    delta_pct: float


class PortfolioOptimization(BaseModel):
    method: str
    feasible: bool
    note: str | None
    allocations: list[OptimizationAllocation]
    expected_annual_return: float
    expected_annual_volatility: float
    expected_sharpe_ratio: float
    risk_free_rate_assumed: float
    lookback_days: int
    data_source: str
    disclaimer: str


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
    raw_value: float
    z_score: float


class PortfolioFitOut(BaseModel):
    symbol: str
    name: str
    fit_score: float
    preset: str
    factors: list[PortfolioFitFactor]
    strengths: list[str]
    concerns: list[str]
    weights_used: dict[str, float]


class FitTermDelta(BaseModel):
    term: str
    name: str
    contribution_a: float
    contribution_b: float
    delta: float


class FitRankingGap(BaseModel):
    symbol_a: str
    symbol_b: str
    fit_score_a: float
    fit_score_b: float
    logit_gap: float
    term_deltas: list[FitTermDelta]
    preset: str
    note: str


class FitTermScenario(BaseModel):
    term: str
    name: str
    current_raw_value: float
    required_z_delta: float
    required_raw_delta: float | None
    target_raw_value: float | None


class FitCounterfactual(BaseModel):
    symbol: str
    fit_score: float
    target: str
    already_meets_target: bool
    term_scenarios: list[FitTermScenario]
    note: str


class WhatIfChange(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    new_quantity: float = Field(ge=0)


class WhatIfRequest(BaseModel):
    changes: list[WhatIfChange] = Field(min_length=1)
    include_costs: bool = True


class WhatIfMetrics(BaseModel):
    annualized_volatility: float
    sharpe_ratio: float
    var_95: float
    cvar_95: float
    var_99: float
    cvar_99: float
    diversification_ratio: float
    hhi_holdings: float


class TradeCost(BaseModel):
    brokerage: float
    stt: float
    stamp_duty: float
    exchange_charges: float
    sebi_fee: float
    gst: float
    total: float


class WhatIfTrade(BaseModel):
    symbol: str
    quantity_delta: float
    trade_value: float
    action: str
    estimated_cost: TradeCost | None


class WhatIfResult(BaseModel):
    before: WhatIfMetrics
    after: WhatIfMetrics
    deltas: dict[str, float]
    trades: list[WhatIfTrade]
    total_estimated_cost: float | None
    risk_free_rate_assumed: float
    lookback_days: int
    data_source: str
    disclaimer: str


class StressTestRequest(BaseModel):
    scenario_preset: str | None = None
    market_shock_pct: float | None = None
    sector_shocks: dict[str, float] | None = None
    scenario_text: str | None = None


class StressTestHoldingImpact(BaseModel):
    symbol: str
    name: str
    sector: str
    value_before: float
    value_after: float
    loss: float
    shock_applied_pct: float
    beta_used: float | None
    used_fallback_beta: bool
    sector_shock_applied: bool


class StressTestResult(BaseModel):
    market_shock_pct: float
    sector_shocks: dict[str, float]
    total_value_before: float
    total_value_after: float
    total_loss: float
    total_loss_pct: float
    breakdown: list[StressTestHoldingImpact]
    data_source: str
    disclaimer: str
    scenario_preset: str | None = None
    scenario_label: str | None = None
    scenario_note: str | None = None


class TopFactor(BaseModel):
    name: str
    explanation: str


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
    top_factor: TopFactor
