import uuid

from app.models.user import User
from app.portfolio import paper_trading_service as service
from app.portfolio.whatif_service import estimate_indian_trade_cost
from app.services.market_data.service import MarketDataService


def _fresh_user(db_session) -> User:
    email = f"pytest-paper-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, hashed_password="x", full_name="Paper Tester")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _register(client) -> dict:
    email = f"pytest-paper-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post("/auth/register", json={"email": email, "password": "testpass123", "full_name": "Paper Tester"})
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---- Service level ----


def test_get_or_create_account_is_idempotent(db_session):
    user = _fresh_user(db_session)
    first = service.get_or_create_account(db_session, user)
    second = service.get_or_create_account(db_session, user)
    assert first.id == second.id
    assert first.cash_balance == service.DEFAULT_STARTING_CASH


def test_buy_deducts_cash_and_creates_holding(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    starting_cash = account.cash_balance

    txn = service.buy(db_session, account, "TCS", 10)

    assert txn.quantity == 10
    assert txn.fees > 0
    expected_debit = txn.price * 10 + txn.fees
    assert account.cash_balance == starting_cash - expected_debit
    assert len(account.holdings) == 1
    assert account.holdings[0].quantity == 10
    assert account.holdings[0].avg_buy_price == txn.price


def test_buy_twice_averages_cost_basis(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)

    first = service.buy(db_session, account, "TCS", 10)
    second = service.buy(db_session, account, "TCS", 10)

    holding = account.holdings[0]
    assert holding.quantity == 20
    expected_avg = (10 * first.price + 10 * second.price) / 20
    assert abs(holding.avg_buy_price - expected_avg) < 1e-6


def test_buy_rejects_when_cash_insufficient(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user, starting_cash=1.0)

    try:
        service.buy(db_session, account, "TCS", 10)
        assert False, "expected InsufficientCashError"
    except service.InsufficientCashError:
        pass

    assert len(account.holdings) == 0
    assert account.cash_balance == 1.0


def test_sell_without_holding_raises(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)

    try:
        service.sell(db_session, account, "TCS", 5)
        assert False, "expected InsufficientHoldingError"
    except service.InsufficientHoldingError:
        pass


def test_sell_more_than_held_raises(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    service.buy(db_session, account, "TCS", 5)

    try:
        service.sell(db_session, account, "TCS", 10)
        assert False, "expected InsufficientHoldingError"
    except service.InsufficientHoldingError:
        pass


def test_sell_computes_realized_pnl_and_credits_cash(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    buy_txn = service.buy(db_session, account, "TCS", 10)
    cash_after_buy = account.cash_balance

    sell_txn = service.sell(db_session, account, "TCS", 4)

    trade_value = sell_txn.price * 4
    expected_fees = estimate_indian_trade_cost(trade_value, is_buy=False)["total"]
    expected_realized = round((sell_txn.price - buy_txn.price) * 4 - expected_fees, 2)
    assert sell_txn.realized_pnl == expected_realized
    assert account.cash_balance == cash_after_buy + (trade_value - expected_fees)
    assert account.holdings[0].quantity == 6


def test_selling_entire_position_removes_holding(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    service.buy(db_session, account, "TCS", 5)
    service.sell(db_session, account, "TCS", 5)
    assert len(account.holdings) == 0


def test_reset_account_restores_starting_state(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    service.buy(db_session, account, "TCS", 5)
    assert len(account.holdings) == 1

    service.reset_account(db_session, account)
    assert account.cash_balance == account.starting_cash
    assert len(account.holdings) == 0
    assert len(account.transactions) == 0


def test_valuation_totals_are_consistent(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    service.buy(db_session, account, "TCS", 10)
    service.buy(db_session, account, "RELIANCE", 5)

    valuation = service.get_valuation(db_session, account)
    assert len(valuation["holdings"]) == 2
    assert valuation["total_value"] == round(valuation["cash_balance"] + valuation["holdings_value"], 2)
    # No price movement happened between buy and valuation (same dev-sample
    # quote), so the only thing total_pnl can reflect is the fees paid --
    # and total_pnl is defined as total_value - starting_cash precisely so
    # it captures that (see get_valuation's docstring note).
    total_fees = sum(t.fees for t in account.transactions)
    assert abs(valuation["total_pnl"] + total_fees) < 0.01
    assert valuation["unrealized_pnl"] == 0.0  # price-only, excludes fees by design


def test_performance_includes_benchmark_points(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    service.buy(db_session, account, "TCS", 10)

    perf = service.get_performance(db_session, account, days=60)
    assert len(perf["points"]) > 0
    assert len(perf["benchmark_points"]) > 0
    assert "account_return_pct" in perf
    assert "benchmark_return_pct" in perf


def test_performance_empty_when_no_holdings(db_session):
    user = _fresh_user(db_session)
    account = service.get_or_create_account(db_session, user)
    perf = service.get_performance(db_session, account, days=60)
    assert perf["points"] == []
    assert len(perf["benchmark_points"]) > 0  # benchmark doesn't depend on holdings


# ---- API routes ----


def test_account_route_creates_on_first_call(client):
    headers = _register(client)
    resp = client.get("/paper-trading/account", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cash_balance"] == service.DEFAULT_STARTING_CASH
    assert "disclaimer" in body
    assert "hypothetical" in body["disclaimer"].lower()


def test_buy_sell_flow_via_routes(client):
    headers = _register(client)

    buy_resp = client.post("/paper-trading/buy", json={"symbol": "TCS", "quantity": 10}, headers=headers)
    assert buy_resp.status_code == 200
    assert buy_resp.json()["type"] == "BUY"

    holdings_resp = client.get("/paper-trading/holdings", headers=headers)
    assert len(holdings_resp.json()) == 1
    assert holdings_resp.json()[0]["symbol"] == "TCS"

    sell_resp = client.post("/paper-trading/sell", json={"symbol": "TCS", "quantity": 4}, headers=headers)
    assert sell_resp.status_code == 200
    assert sell_resp.json()["realized_pnl"] is not None

    txns_resp = client.get("/paper-trading/transactions", headers=headers)
    assert len(txns_resp.json()) == 2
    assert txns_resp.json()[0]["type"] == "SELL"  # newest first


def test_buy_insufficient_cash_returns_400(client):
    headers = _register(client)
    resp = client.post("/paper-trading/buy", json={"symbol": "TCS", "quantity": 10_000_000}, headers=headers)
    assert resp.status_code == 400


def test_sell_without_holding_returns_400(client):
    headers = _register(client)
    resp = client.post("/paper-trading/sell", json={"symbol": "TCS", "quantity": 1}, headers=headers)
    assert resp.status_code == 400


def test_trade_request_rejects_non_positive_quantity(client):
    headers = _register(client)
    resp = client.post("/paper-trading/buy", json={"symbol": "TCS", "quantity": 0}, headers=headers)
    assert resp.status_code == 422


def test_account_reset_route(client):
    headers = _register(client)
    client.post("/paper-trading/buy", json={"symbol": "TCS", "quantity": 5}, headers=headers)
    reset_resp = client.post("/paper-trading/account/reset", headers=headers)
    assert reset_resp.status_code == 200
    assert reset_resp.json()["cash_balance"] == service.DEFAULT_STARTING_CASH
    assert reset_resp.json()["holdings"] == []


def test_performance_route(client):
    headers = _register(client)
    client.post("/paper-trading/buy", json={"symbol": "RELIANCE", "quantity": 5}, headers=headers)
    resp = client.get("/paper-trading/performance", params={"days": 60}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "points" in body and "benchmark_points" in body


def test_accounts_are_isolated_between_users(client):
    headers_a = _register(client)
    headers_b = _register(client)

    client.post("/paper-trading/buy", json={"symbol": "TCS", "quantity": 5}, headers=headers_a)

    holdings_b = client.get("/paper-trading/holdings", headers=headers_b)
    assert holdings_b.json() == []
