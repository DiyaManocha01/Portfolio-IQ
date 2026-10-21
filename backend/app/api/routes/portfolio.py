from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_portfolio, get_current_user
from app.database.session import get_db
from app.models.portfolio import Holding, Portfolio
from app.models.user import User
from app.portfolio.health_service import PortfolioHealthService
from app.portfolio.optimization_service import VALID_METHODS, PortfolioOptimizationService
from app.portfolio.risk_attribution_service import RiskAttributionService
from app.portfolio.risk_service import PortfolioRiskService
from app.portfolio.scenario_parser import ScenarioParseError, parse_scenario_text
from app.portfolio.stress_test_service import SCENARIO_PRESETS, StressTestService
from app.portfolio.weakness_service import PortfolioWeaknessService
from app.portfolio.whatif_service import WhatIfService
from app.schemas.portfolio import (
    AllocationSlice,
    CorrelationPair,
    HoldingCreate,
    HoldingOut,
    OptimizationAllocation,
    PortfolioAllocation,
    PortfolioHealth,
    PortfolioOptimization,
    PortfolioPerformance,
    PortfolioRisk,
    PortfolioRiskAttribution,
    PortfolioSummary,
    PortfolioWeaknesses,
    RiskAttributionItem,
    RiskContribution,
    ScoreComponent,
    StressTestHoldingImpact,
    StressTestRequest,
    StressTestResult,
    WeaknessOut,
    PerformancePoint,
    TradeCost,
    WhatIfMetrics,
    WhatIfRequest,
    WhatIfResult,
    WhatIfTrade,
)
from app.services import portfolio_calc
from app.services.market_data.service import MarketDataService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _risk_label(annualized_volatility: float) -> str:
    if annualized_volatility >= 0.35:
        return "High"
    if annualized_volatility >= 0.20:
        return "Moderate"
    return "Low"


@router.get("", response_model=list[HoldingOut])
def list_holdings(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    return portfolio_calc.get_holdings_with_metrics(db, portfolio)


@router.post("/holdings", response_model=HoldingOut, status_code=201)
def add_holding(
    payload: HoldingCreate,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(payload.symbol)
    market_data.get_history(stock)  # ensure data exists

    existing = (
        db.query(Holding).filter(Holding.portfolio_id == portfolio.id, Holding.stock_id == stock.id).first()
    )
    if existing:
        total_qty = existing.quantity + payload.quantity
        existing.avg_buy_price = (
            existing.quantity * existing.avg_buy_price + payload.quantity * payload.avg_buy_price
        ) / total_qty
        existing.quantity = total_qty
        holding = existing
    else:
        holding = Holding(
            portfolio_id=portfolio.id,
            stock_id=stock.id,
            quantity=payload.quantity,
            avg_buy_price=payload.avg_buy_price,
        )
        db.add(holding)
    db.commit()
    db.refresh(holding)

    latest, _ = market_data.get_quote(stock)
    return portfolio_calc.holding_metrics(holding, latest.close)


@router.delete("/holdings/{holding_id}", status_code=204)
def remove_holding(
    holding_id: int,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    holding = (
        db.query(Holding).filter(Holding.id == holding_id, Holding.portfolio_id == portfolio.id).first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    db.delete(holding)
    db.commit()
    return None


@router.get("/summary", response_model=PortfolioSummary)
def summary(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    holdings = portfolio_calc.get_holdings_with_metrics(db, portfolio)
    totals = portfolio_calc.portfolio_totals(holdings)
    risk = PortfolioRiskService(db).compute(portfolio)
    health = PortfolioHealthService(db).compute(portfolio)

    return PortfolioSummary(
        portfolio_id=portfolio.id,
        portfolio_value=totals["portfolio_value"],
        invested_amount=totals["invested_amount"],
        total_pnl=totals["total_pnl"],
        return_pct=totals["return_pct"],
        holdings_count=len(holdings),
        portfolio_risk=_risk_label(risk["annualized_volatility"]),
        health_score=health["overall_health"],
    )


@router.get("/performance", response_model=PortfolioPerformance)
def performance(
    days: int = 180,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    points, source = portfolio_calc.get_performance_series(db, portfolio, days=days)
    return PortfolioPerformance(points=[PerformancePoint(**p) for p in points], data_source=source)


@router.get("/allocation", response_model=PortfolioAllocation)
def allocation(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    holdings = portfolio_calc.get_holdings_with_metrics(db, portfolio)
    total = sum(h["current_value"] for h in holdings) or 1.0

    by_stock = [
        AllocationSlice(label=h["symbol"], value=h["current_value"], pct=round(h["current_value"] / total * 100, 1))
        for h in sorted(holdings, key=lambda x: -x["current_value"])
    ]

    sector_values: dict[str, float] = {}
    for h in holdings:
        sector_values[h["sector"]] = sector_values.get(h["sector"], 0.0) + h["current_value"]
    by_sector = [
        AllocationSlice(label=sector, value=round(v, 2), pct=round(v / total * 100, 1))
        for sector, v in sorted(sector_values.items(), key=lambda x: -x[1])
    ]

    return PortfolioAllocation(by_stock=by_stock, by_sector=by_sector)


@router.get("/risk", response_model=PortfolioRisk)
def risk(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    r = PortfolioRiskService(db).compute(portfolio)
    return PortfolioRisk(
        annualized_volatility=r["annualized_volatility"],
        sharpe_ratio=r["sharpe_ratio"],
        max_drawdown=r["max_drawdown"],
        risk_contributions=[RiskContribution(**rc) for rc in r["risk_contributions"]],
        correlation_matrix=[CorrelationPair(**cp) for cp in r["correlation_matrix"]],
        sector_concentration=[AllocationSlice(**sc) for sc in r["sector_concentration"]],
        top_stock_concentration_pct=r["top_stock_concentration_pct"],
        var_95=r["var_95"],
        cvar_95=r["cvar_95"],
        var_99=r["var_99"],
        cvar_99=r["cvar_99"],
        hhi_holdings=r["hhi_holdings"],
        hhi_sector=r["hhi_sector"],
        effective_number_of_bets=r["effective_number_of_bets"],
        diversification_ratio=r["diversification_ratio"],
        covariance_method=r["covariance_method"],
        shrinkage_intensity=r["shrinkage_intensity"],
        data_source=r["data_source"],
    )


@router.get("/risk-attribution", response_model=PortfolioRiskAttribution)
def risk_attribution(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    r = RiskAttributionService(db).compute(portfolio)
    return PortfolioRiskAttribution(
        portfolio_annualized_volatility=r["portfolio_annualized_volatility"],
        attributions=[RiskAttributionItem(**a) for a in r["attributions"]],
        data_source=r["data_source"],
    )


@router.post("/stress-test", response_model=StressTestResult)
def stress_test(
    request: StressTestRequest,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    service = StressTestService(db)

    if request.scenario_preset is not None:
        if request.scenario_preset not in SCENARIO_PRESETS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown scenario_preset: {request.scenario_preset!r}. Must be one of {list(SCENARIO_PRESETS)}.",
            )
        r = service.apply_preset(portfolio, request.scenario_preset)
    elif request.scenario_text is not None:
        try:
            parsed = parse_scenario_text(request.scenario_text)
        except ScenarioParseError as e:
            raise HTTPException(status_code=400, detail=str(e))
        r = service.apply_shock(
            portfolio,
            market_shock_pct=parsed.get("market_shock_pct", 0.0),
            sector_shocks=parsed.get("sector_shocks"),
        )
    elif request.market_shock_pct is not None or request.sector_shocks is not None:
        r = service.apply_shock(
            portfolio,
            market_shock_pct=request.market_shock_pct or 0.0,
            sector_shocks=request.sector_shocks,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide one of: scenario_preset, scenario_text, market_shock_pct, or sector_shocks.",
        )

    return StressTestResult(
        market_shock_pct=r["market_shock_pct"],
        sector_shocks=r["sector_shocks"],
        total_value_before=r["total_value_before"],
        total_value_after=r["total_value_after"],
        total_loss=r["total_loss"],
        total_loss_pct=r["total_loss_pct"],
        breakdown=[StressTestHoldingImpact(**b) for b in r["breakdown"]],
        data_source=r["data_source"],
        disclaimer=r["disclaimer"],
        scenario_preset=r.get("scenario_preset"),
        scenario_label=r.get("scenario_label"),
        scenario_note=r.get("scenario_note"),
    )


@router.get("/optimize", response_model=PortfolioOptimization)
def optimize(
    method: str = "min_variance",
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    if method not in VALID_METHODS:
        raise HTTPException(
            status_code=400, detail=f"Unknown optimization method: {method!r}. Must be one of {VALID_METHODS}."
        )
    r = PortfolioOptimizationService(db).compute(portfolio, method=method)
    return PortfolioOptimization(
        method=r["method"],
        feasible=r["feasible"],
        note=r["note"],
        allocations=[OptimizationAllocation(**a) for a in r["allocations"]],
        expected_annual_return=r["expected_annual_return"],
        expected_annual_volatility=r["expected_annual_volatility"],
        expected_sharpe_ratio=r["expected_sharpe_ratio"],
        risk_free_rate_assumed=r["risk_free_rate_assumed"],
        lookback_days=r["lookback_days"],
        data_source=r["data_source"],
        disclaimer=r["disclaimer"],
    )


@router.get("/health", response_model=PortfolioHealth)
def health(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    h = PortfolioHealthService(db).compute(portfolio)
    return PortfolioHealth(
        overall_health=h["overall_health"],
        components=[ScoreComponent(**c) for c in h["components"]],
        computed_at=h["computed_at"],
    )


@router.get("/weaknesses", response_model=PortfolioWeaknesses)
def weaknesses(
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    w = PortfolioWeaknessService(db).detect(portfolio)
    return PortfolioWeaknesses(weaknesses=[WeaknessOut(**item) for item in w])


@router.post("/what-if", response_model=WhatIfResult)
def what_if(
    request: WhatIfRequest,
    portfolio: Portfolio = Depends(get_current_portfolio),
    db: Session = Depends(get_db),
):
    try:
        r = WhatIfService(db).simulate(
            portfolio,
            changes=[c.model_dump() for c in request.changes],
            include_costs=request.include_costs,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return WhatIfResult(
        before=WhatIfMetrics(**r["before"]),
        after=WhatIfMetrics(**r["after"]),
        deltas=r["deltas"],
        trades=[
            WhatIfTrade(
                symbol=t["symbol"],
                quantity_delta=t["quantity_delta"],
                trade_value=t["trade_value"],
                action=t["action"],
                estimated_cost=TradeCost(**t["estimated_cost"]) if t["estimated_cost"] else None,
            )
            for t in r["trades"]
        ],
        total_estimated_cost=r["total_estimated_cost"],
        risk_free_rate_assumed=r["risk_free_rate_assumed"],
        lookback_days=r["lookback_days"],
        data_source=r["data_source"],
        disclaimer=r["disclaimer"],
    )
