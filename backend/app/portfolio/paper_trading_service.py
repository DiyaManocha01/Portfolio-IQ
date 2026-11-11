"""Paper Trading (Phase 28): a hypothetical account, never the real portfolio.

Execution prices come from MarketDataService.get_quote -- the same real
(or dev-sample) price the rest of the app uses, never invented. Fees
reuse estimate_indian_trade_cost (app/portfolio/whatif_service.py,
Phase 11's illustrative, honesty-flagged NSE delivery-trade cost model)
rather than defining a second cost formula.

Every transaction is logged (buy or sell, with price and fees); sells
additionally record realized_pnl. Unlike the real Portfolio/Holding
tables, a paper account's avg_buy_price is a plain price-weighted
average across buys -- fees are tracked per-transaction, not blended
into the cost basis, so "what did I pay for this stock" and "what did
fees cost me" stay two separately inspectable numbers instead of one
opaque blended one.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from app.models.paper_trading import PaperAccount, PaperHolding, PaperTransaction
from app.models.portfolio import TransactionType
from app.models.user import User
from app.portfolio.whatif_service import estimate_indian_trade_cost
from app.services import analytics
from app.services.market_data.service import MarketDataService

DEFAULT_STARTING_CASH = 1_000_000.0  # Rs 10 lakh -- a round illustrative default, not a sourced figure


class InsufficientCashError(ValueError):
    pass


class InsufficientHoldingError(ValueError):
    pass


def get_or_create_account(db: Session, user: User, starting_cash: float = DEFAULT_STARTING_CASH) -> PaperAccount:
    account = db.query(PaperAccount).filter(PaperAccount.user_id == user.id).first()
    if account:
        return account
    account = PaperAccount(user_id=user.id, starting_cash=starting_cash, cash_balance=starting_cash)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def reset_account(db: Session, account: PaperAccount) -> PaperAccount:
    """Wipes holdings and transaction history, restores starting cash.

    Safe by design -- this is a hypothetical sandbox, never the real
    portfolio, so "start over" is an expected, harmless action.
    """
    for holding in list(account.holdings):
        db.delete(holding)
    for txn in list(account.transactions):
        db.delete(txn)
    account.cash_balance = account.starting_cash
    db.commit()
    db.refresh(account)
    return account


def _get_holding(db: Session, account: PaperAccount, stock_id: int) -> PaperHolding | None:
    return (
        db.query(PaperHolding)
        .filter(PaperHolding.paper_account_id == account.id, PaperHolding.stock_id == stock_id)
        .first()
    )


def buy(db: Session, account: PaperAccount, symbol: str, quantity: float) -> PaperTransaction:
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(symbol)
    latest, _ = market_data.get_quote(stock)
    price = latest.close

    trade_value = price * quantity
    fees = estimate_indian_trade_cost(trade_value, is_buy=True)["total"]
    total_debit = trade_value + fees
    if total_debit > account.cash_balance:
        raise InsufficientCashError(
            f"This buy needs ₹{total_debit:.2f} (including fees) but only ₹{account.cash_balance:.2f} is available"
        )

    holding = _get_holding(db, account, stock.id)
    if holding:
        new_quantity = holding.quantity + quantity
        holding.avg_buy_price = (holding.quantity * holding.avg_buy_price + quantity * price) / new_quantity
        holding.quantity = new_quantity
    else:
        holding = PaperHolding(paper_account_id=account.id, stock_id=stock.id, quantity=quantity, avg_buy_price=price)
        db.add(holding)

    account.cash_balance -= total_debit
    txn = PaperTransaction(
        paper_account_id=account.id,
        stock_id=stock.id,
        type=TransactionType.BUY,
        quantity=quantity,
        price=price,
        fees=fees,
        realized_pnl=None,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def sell(db: Session, account: PaperAccount, symbol: str, quantity: float) -> PaperTransaction:
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    market_data = MarketDataService(db)
    stock = market_data.get_or_create_stock(symbol)
    holding = _get_holding(db, account, stock.id)
    if holding is None or quantity > holding.quantity:
        held = holding.quantity if holding else 0.0
        raise InsufficientHoldingError(f"Cannot sell {quantity} shares of {symbol} -- only {held} are held")

    latest, _ = market_data.get_quote(stock)
    price = latest.close
    trade_value = price * quantity
    fees = estimate_indian_trade_cost(trade_value, is_buy=False)["total"]
    proceeds = trade_value - fees
    realized_pnl = (price - holding.avg_buy_price) * quantity - fees

    holding.quantity -= quantity
    if holding.quantity <= 1e-9:
        db.delete(holding)

    account.cash_balance += proceeds
    txn = PaperTransaction(
        paper_account_id=account.id,
        stock_id=stock.id,
        type=TransactionType.SELL,
        quantity=quantity,
        price=price,
        fees=fees,
        realized_pnl=round(realized_pnl, 2),
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def get_valuation(db: Session, account: PaperAccount) -> dict:
    market_data = MarketDataService(db)
    holdings_out = []
    holdings_value = 0.0
    unrealized_pnl = 0.0
    for h in account.holdings:
        latest, _ = market_data.get_quote(h.stock)
        current_value = h.quantity * latest.close
        invested_value = h.quantity * h.avg_buy_price
        pnl = current_value - invested_value
        holdings_value += current_value
        unrealized_pnl += pnl
        holdings_out.append(
            {
                "symbol": h.stock.symbol,
                "name": h.stock.name,
                "quantity": h.quantity,
                "avg_buy_price": round(h.avg_buy_price, 2),
                "current_price": round(latest.close, 2),
                "invested_value": round(invested_value, 2),
                "current_value": round(current_value, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl / invested_value * 100, 2) if invested_value else 0.0,
            }
        )

    realized_pnl = sum(t.realized_pnl for t in account.transactions if t.realized_pnl is not None)
    total_value = account.cash_balance + holdings_value
    # total_pnl is deliberately total_value - starting_cash (always correct
    # and includes every fee ever paid), NOT unrealized_pnl + realized_pnl:
    # that sum would silently exclude fees paid on positions still open
    # (a buy's fee reduces cash immediately but isn't folded into
    # invested_value/avg_buy_price, so it never shows up in
    # unrealized_pnl until the position is sold). unrealized_pnl and
    # realized_pnl are still reported separately, as price-only figures,
    # for transparency -- they will not exactly sum to total_pnl while
    # any fee-bearing position remains open, and that gap IS the unpaid
    # fee drag, not a bug.
    total_pnl = total_value - account.starting_cash
    total_return_pct = (total_pnl / account.starting_cash * 100) if account.starting_cash else 0.0

    return {
        "starting_cash": account.starting_cash,
        "cash_balance": round(account.cash_balance, 2),
        "holdings_value": round(holdings_value, 2),
        "total_value": round(total_value, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(total_return_pct, 2),
        "holdings": holdings_out,
        "data_source": market_data.data_source_label,
    }


def get_performance(db: Session, account: PaperAccount, days: int = 180) -> dict:
    """Account value over time vs. a NIFTY 50 buy-and-hold benchmark.

    Simplification (same one already documented for the real portfolio's
    performance series in app/services/portfolio_calc.py): current
    holding quantities are assumed constant across the lookback window --
    this shows "what my current holdings would be worth over time," not
    a full transaction-by-transaction historical reconstruction. The
    benchmark line answers Phase 28's "benchmark/strategy comparison"
    requirement: it's NIFTY 50 bought-and-held with the same starting
    cash over the same window, nothing more elaborate invented.
    """
    market_data = MarketDataService(db)
    holdings = list(account.holdings)

    points: list[dict] = []
    if holdings:
        price_frames = {}
        for h in holdings:
            bars = market_data.get_history(h.stock, days=days)
            df = analytics.ohlcv_to_frame(bars).set_index("date")["close"]
            price_frames[h.stock.symbol] = df * h.quantity
        combined = pd.DataFrame(price_frames).sort_index().ffill().bfill()
        combined["total_value"] = combined.sum(axis=1) + account.cash_balance
        points = [{"date": idx, "value": round(float(v), 2)} for idx, v in combined["total_value"].items()]

    benchmark_points: list[dict] = []
    bench_bars = market_data.get_benchmark_history(days=days)
    if bench_bars:
        bench_df = analytics.ohlcv_to_frame(bench_bars).set_index("date")["close"]
        bench_start = float(bench_df.iloc[0])
        if bench_start:
            benchmark_points = [
                {"date": idx, "value": round(account.starting_cash * float(price) / bench_start, 2)}
                for idx, price in bench_df.items()
            ]

    account_return_pct = (
        (points[-1]["value"] - account.starting_cash) / account.starting_cash * 100 if points and account.starting_cash else 0.0
    )
    benchmark_return_pct = (
        (benchmark_points[-1]["value"] - account.starting_cash) / account.starting_cash * 100
        if benchmark_points and account.starting_cash
        else 0.0
    )

    return {
        "points": points,
        "benchmark_points": benchmark_points,
        "account_return_pct": round(account_return_pct, 2),
        "benchmark_return_pct": round(benchmark_return_pct, 2),
        "data_source": market_data.data_source_label,
    }
