"""Tests for Phase 31: transaction logging for the real portfolio
(app/api/routes/portfolio.py's buy/sell/transactions) and the Advanced
Portfolio Performance service (app/portfolio/portfolio_performance_service.py).
See docs/adr/0014-portfolio-transaction-ledger.md."""

from __future__ import annotations

import uuid
from datetime import date

from app.models.portfolio import Portfolio, Transaction, TransactionType
from app.models.stock import Stock
from app.models.user import User
from app.portfolio import portfolio_performance_service as service
from app.services import portfolio_calc
from app.services.security import create_access_token


def _register(client, db_session) -> dict:
    """Creates a fresh user + portfolio directly via the DB and mints a
    token with create_access_token, rather than going through the
    rate-limited POST /auth/register (Phase 21: 10/min) -- this test file
    alone registers more than that limit across its route-level tests,
    and the rate limiter's state is shared for the whole session via the
    session-scoped `client` fixture."""
    email = f"pytest-perf-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, hashed_password="x", full_name="Perf Tester")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(Portfolio(user_id=user.id, name="My Portfolio"))
    db_session.commit()
    token = create_access_token(user.email)
    return {"Authorization": f"Bearer {token}"}


# ---- Transaction logging via routes ----


def test_buy_logs_a_transaction(client, db_session):
    headers = _register(client, db_session)
    resp = client.post("/portfolio/holdings", json={"symbol": "TCS", "quantity": 10, "avg_buy_price": 3500}, headers=headers)
    assert resp.status_code == 201

    txns = client.get("/portfolio/transactions", headers=headers)
    assert txns.status_code == 200
    body = txns.json()
    assert len(body) == 1
    assert body[0]["type"] == "BUY"
    assert body[0]["quantity"] == 10
    assert body[0]["price"] == 3500
    assert body[0]["realized_pnl"] is None


def test_sell_computes_realized_pnl_and_logs_transaction(client, db_session):
    headers = _register(client, db_session)
    buy = client.post("/portfolio/holdings", json={"symbol": "TCS", "quantity": 10, "avg_buy_price": 3500}, headers=headers)
    holding_id = buy.json()["id"]

    sell = client.post(f"/portfolio/holdings/{holding_id}/sell", json={"price": 3600, "quantity": 4}, headers=headers)
    assert sell.status_code == 200
    body = sell.json()
    assert body["type"] == "SELL"
    assert body["realized_pnl"] == (3600 - 3500) * 4  # 400

    remaining = client.get("/portfolio", headers=headers).json()
    assert remaining[0]["quantity"] == 6

    txns = client.get("/portfolio/transactions", headers=headers).json()
    assert len(txns) == 2
    assert txns[0]["type"] == "SELL"  # newest first


def test_selling_entire_position_removes_the_holding(client, db_session):
    headers = _register(client, db_session)
    buy = client.post("/portfolio/holdings", json={"symbol": "TCS", "quantity": 5, "avg_buy_price": 3500}, headers=headers)
    holding_id = buy.json()["id"]

    sell = client.post(f"/portfolio/holdings/{holding_id}/sell", json={"price": 3600}, headers=headers)  # no quantity = sell all
    assert sell.status_code == 200
    assert sell.json()["quantity"] == 5

    remaining = client.get("/portfolio", headers=headers).json()
    assert remaining == []


def test_selling_more_than_held_returns_400(client, db_session):
    headers = _register(client, db_session)
    buy = client.post("/portfolio/holdings", json={"symbol": "TCS", "quantity": 5, "avg_buy_price": 3500}, headers=headers)
    holding_id = buy.json()["id"]

    sell = client.post(f"/portfolio/holdings/{holding_id}/sell", json={"price": 3600, "quantity": 10}, headers=headers)
    assert sell.status_code == 400


def test_sell_on_unknown_holding_returns_404(client, db_session):
    headers = _register(client, db_session)
    sell = client.post("/portfolio/holdings/999999/sell", json={"price": 100}, headers=headers)
    assert sell.status_code == 404


def test_delete_still_removes_without_logging_a_transaction(client, db_session):
    """DELETE stays a plain removal (no price, no transaction) -- distinct
    from the new /sell endpoint, for correcting a mis-entered holding."""
    headers = _register(client, db_session)
    buy = client.post("/portfolio/holdings", json={"symbol": "TCS", "quantity": 5, "avg_buy_price": 3500}, headers=headers)
    holding_id = buy.json()["id"]

    resp = client.delete(f"/portfolio/holdings/{holding_id}", headers=headers)
    assert resp.status_code == 204

    txns = client.get("/portfolio/transactions", headers=headers).json()
    assert len(txns) == 1  # only the original BUY -- the delete logged nothing
    assert txns[0]["type"] == "BUY"


def test_transactions_are_isolated_between_users(client, db_session):
    headers_a = _register(client, db_session)
    headers_b = _register(client, db_session)
    client.post("/portfolio/holdings", json={"symbol": "TCS", "quantity": 5, "avg_buy_price": 3500}, headers=headers_a)

    txns_b = client.get("/portfolio/transactions", headers=headers_b)
    assert txns_b.json() == []


# ---- portfolio_performance_service: integration against seeded demo portfolio ----


def test_advanced_performance_shape_on_seeded_portfolio(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = service.get_advanced_performance(db_session, portfolio, days=180)

    assert "points" in result and "daily_returns" in result and "benchmark" in result
    expected_unrealized = sum(h["pnl"] for h in portfolio_calc.get_holdings_with_metrics(db_session, portfolio))
    assert abs(result["unrealized_pnl"] - expected_unrealized) < 0.01


def test_holding_contributions_sum_to_roughly_total_pnl_pct(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = service.get_advanced_performance(db_session, portfolio, days=180)
    total_contribution_pct = sum(c["contribution_pct"] for c in result["holding_contributions"])
    assert abs(total_contribution_pct - 100.0) < 0.5  # rounding tolerance


def test_sector_contributions_sum_to_roughly_total_pnl_pct(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = service.get_advanced_performance(db_session, portfolio, days=180)
    total_contribution_pct = sum(c["contribution_pct"] for c in result["sector_contributions"])
    assert abs(total_contribution_pct - 100.0) < 0.5


def test_benchmark_series_starts_near_the_portfolios_own_starting_value(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = service.get_advanced_performance(db_session, portfolio, days=180)
    assert len(result["benchmark"]) > 0
    first_point_value = result["points"][0]["value"]
    first_benchmark_value = result["benchmark"][0]["value"]
    # Normalized to start at the same value as the portfolio's own series --
    # dates may not align exactly (benchmark/portfolio histories can start
    # on slightly different trading days), so allow a loose tolerance.
    assert abs(first_benchmark_value - first_point_value) / first_point_value < 0.1


def test_drawdown_is_never_positive(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = service.get_advanced_performance(db_session, portfolio, days=180)
    assert all(p["drawdown_pct"] <= 1e-6 for p in result["drawdown"])


def test_cumulative_return_first_point_is_zero(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = service.get_advanced_performance(db_session, portfolio, days=180)
    if result["cumulative_returns"]:
        assert abs(result["cumulative_returns"][0]["cumulative_return_pct"]) < 1e-6


def test_realized_pnl_reflects_only_sell_transactions(db_session):
    user = User(email=f"pytest-perf-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", full_name="Perf Tester")
    db_session.add(user)
    db_session.commit()
    portfolio = Portfolio(user_id=user.id, name="Test Portfolio")
    db_session.add(portfolio)
    db_session.commit()

    assert service._realized_pnl(db_session, portfolio) == 0.0

    stock = db_session.query(Stock).first()
    db_session.add(
        Transaction(
            portfolio_id=portfolio.id,
            stock_id=stock.id,
            type=TransactionType.SELL,
            quantity=5,
            price=100,
            realized_pnl=250.0,
            transaction_date=date.today(),
        )
    )
    db_session.commit()

    assert service._realized_pnl(db_session, portfolio) == 250.0


def test_empty_portfolio_returns_empty_series_without_crashing(db_session):
    user = User(email=f"pytest-perf-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", full_name="Perf Tester")
    db_session.add(user)
    db_session.commit()
    portfolio = Portfolio(user_id=user.id, name="Empty Portfolio")
    db_session.add(portfolio)
    db_session.commit()

    result = service.get_advanced_performance(db_session, portfolio, days=180)
    assert result["points"] == []
    assert result["holding_contributions"] == []
    assert result["unrealized_pnl"] == 0.0
    assert result["realized_pnl"] == 0.0


# ---- HTTP endpoint integration ----


def test_performance_advanced_route_shape(client, auth_headers):
    resp = client.get("/portfolio/performance/advanced", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in ("points", "daily_returns", "cumulative_returns", "drawdown", "benchmark", "holding_contributions", "sector_contributions"):
        assert key in body
    assert "unrealized_pnl" in body and "realized_pnl" in body and "total_pnl" in body
