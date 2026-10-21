import pandas as pd
import pytest

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


def test_macd_returns_expected_columns():
    close = pd.Series([100 + i + (i % 5) for i in range(60)], dtype=float)
    result = analytics.macd(close)
    assert list(result.columns) == ["macd_line", "signal_line", "histogram"]
    assert len(result) == len(close)
    # histogram is always macd_line - signal_line by construction
    diff = (result["macd_line"] - result["signal_line"] - result["histogram"]).abs()
    assert (diff < 1e-9).all()


def test_beta_of_series_with_itself_is_one():
    rng_series = pd.Series([0.01, -0.02, 0.015, 0.03, -0.01, 0.02, -0.015, 0.005, 0.01, -0.02] * 3)
    result = analytics.beta(rng_series, rng_series)
    assert result == pytest.approx(1.0, abs=1e-9)


def test_beta_returns_none_with_insufficient_overlap():
    short_a = pd.Series([0.01, 0.02, -0.01])
    short_b = pd.Series([0.01, 0.02, -0.01])
    assert analytics.beta(short_a, short_b) is None


def test_beta_returns_none_for_zero_variance_benchmark():
    stock = pd.Series([0.01, -0.02, 0.015, 0.03, -0.01] * 5)
    flat_benchmark = pd.Series([0.0] * 25)
    assert analytics.beta(stock, flat_benchmark) is None


def test_beta_known_linear_relationship():
    # benchmark moves, stock = 2x benchmark exactly -> beta should be ~2.0
    benchmark = pd.Series([0.01, -0.02, 0.015, 0.03, -0.01, 0.02, -0.015, 0.005] * 4)
    stock = benchmark * 2.0
    result = analytics.beta(stock, benchmark)
    assert result == pytest.approx(2.0, abs=1e-9)


def test_purged_walk_forward_splits_no_leakage():
    from app.ml.features import purged_walk_forward_splits

    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=120, freq="D"), "value": range(120)})
    folds = list(purged_walk_forward_splits(df, n_splits=5, embargo=3))
    assert len(folds) == 5
    for train_df, test_df in folds:
        assert len(train_df) > 0 and len(test_df) > 0
        # every train row must come strictly before every test row
        assert train_df["date"].max() < test_df["date"].min()
        # the embargo gap itself must be respected: at least `embargo` days
        # of calendar time between the end of train and the start of test
        gap_days = (test_df["date"].min() - train_df["date"].max()).days
        assert gap_days >= 3


def test_purged_walk_forward_splits_folds_are_chronologically_increasing():
    from app.ml.features import purged_walk_forward_splits

    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=100, freq="D"), "value": range(100)})
    folds = list(purged_walk_forward_splits(df, n_splits=4, embargo=1))
    test_starts = [test_df["date"].min() for _, test_df in folds]
    assert test_starts == sorted(test_starts)
    # last fold's test block should reach the end of the available data
    assert folds[-1][1]["date"].max() == df["date"].max()


def test_purged_walk_forward_splits_raises_with_too_little_data():
    from app.ml.features import purged_walk_forward_splits

    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3, freq="D"), "value": range(3)})
    with pytest.raises(ValueError):
        list(purged_walk_forward_splits(df, n_splits=10, embargo=1))
