import pandas as pd

from app.models.portfolio import Holding
from app.models.stock import Stock
from app.services import analytics, portfolio_calc


def _fake_holding(quantity, avg_buy_price, symbol="TCS", sector="Information Technology"):
    stock = Stock(symbol=symbol, name=symbol, sector=sector, industry="x", exchange="NSE")
    h = Holding(quantity=quantity, avg_buy_price=avg_buy_price)
    h.stock = stock
    return h


def test_holding_metrics_profit():
    h = _fake_holding(quantity=10, avg_buy_price=3200.0)
    metrics = portfolio_calc.holding_metrics(h, current_price=3450.0)
    assert metrics["invested_value"] == 32000.0
    assert metrics["current_value"] == 34500.0
    assert metrics["pnl"] == 2500.0
    assert round(metrics["return_pct"], 2) == 7.81


def test_holding_metrics_loss():
    h = _fake_holding(quantity=5, avg_buy_price=1000.0)
    metrics = portfolio_calc.holding_metrics(h, current_price=800.0)
    assert metrics["pnl"] == -1000.0
    assert metrics["return_pct"] == -20.0


def test_portfolio_totals_aggregates_holdings():
    holdings = [
        portfolio_calc.holding_metrics(_fake_holding(10, 100.0), 120.0),
        portfolio_calc.holding_metrics(_fake_holding(5, 200.0), 180.0),
    ]
    totals = portfolio_calc.portfolio_totals(holdings)
    assert totals["invested_amount"] == 2000.0
    assert totals["portfolio_value"] == 2100.0
    assert totals["total_pnl"] == 100.0
    assert round(totals["return_pct"], 2) == 5.0


def test_portfolio_totals_empty():
    totals = portfolio_calc.portfolio_totals([])
    assert totals["invested_amount"] == 0
    assert totals["return_pct"] == 0.0


def test_rsi_is_bounded_0_100():
    close = pd.Series([100, 102, 101, 105, 103, 108, 110, 107, 111, 115, 112, 118, 120, 117, 121])
    rsi = analytics.rsi(close, window=14)
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_sma_matches_simple_average():
    close = pd.Series([10.0, 20.0, 30.0])
    result = analytics.sma(close, window=3)
    assert round(result.iloc[-1], 4) == 20.0


def test_volatility_zero_for_constant_prices():
    close = pd.Series([100.0] * 30)
    vol = analytics.volatility_annualized(close)
    assert vol == 0.0


def test_max_drawdown_is_non_positive():
    close = pd.Series([100, 110, 90, 95, 80, 120])
    dd = analytics.max_drawdown(close)
    assert dd <= 0
