from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.portfolio import paper_trading_service as service
from app.schemas.paper_trading import (
    PaperAccountOut,
    PaperHoldingOut,
    PaperPerformanceOut,
    PaperTransactionOut,
    TradeRequest,
)

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


def _account_out(valuation: dict) -> PaperAccountOut:
    return PaperAccountOut(
        starting_cash=valuation["starting_cash"],
        cash_balance=valuation["cash_balance"],
        holdings_value=valuation["holdings_value"],
        total_value=valuation["total_value"],
        unrealized_pnl=valuation["unrealized_pnl"],
        realized_pnl=valuation["realized_pnl"],
        total_pnl=valuation["total_pnl"],
        total_return_pct=valuation["total_return_pct"],
        holdings=[PaperHoldingOut(**h) for h in valuation["holdings"]],
        data_source=valuation["data_source"],
    )


def _transaction_out(txn) -> PaperTransactionOut:
    return PaperTransactionOut(
        id=txn.id,
        symbol=txn.stock.symbol,
        type=txn.type.value,
        quantity=txn.quantity,
        price=txn.price,
        fees=txn.fees,
        realized_pnl=txn.realized_pnl,
        executed_at=txn.executed_at,
    )


@router.get("/account", response_model=PaperAccountOut)
def get_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    return _account_out(service.get_valuation(db, account))


@router.post("/account/reset", response_model=PaperAccountOut)
def reset_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    service.reset_account(db, account)
    return _account_out(service.get_valuation(db, account))


@router.post("/buy", response_model=PaperTransactionOut)
def buy(payload: TradeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    try:
        txn = service.buy(db, account, payload.symbol, payload.quantity)
    except service.InsufficientCashError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _transaction_out(txn)


@router.post("/sell", response_model=PaperTransactionOut)
def sell(payload: TradeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    try:
        txn = service.sell(db, account, payload.symbol, payload.quantity)
    except service.InsufficientHoldingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _transaction_out(txn)


@router.get("/holdings", response_model=list[PaperHoldingOut])
def get_holdings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    valuation = service.get_valuation(db, account)
    return [PaperHoldingOut(**h) for h in valuation["holdings"]]


@router.get("/transactions", response_model=list[PaperTransactionOut])
def get_transactions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    return [_transaction_out(t) for t in reversed(account.transactions)]


@router.get("/performance", response_model=PaperPerformanceOut)
def get_performance(days: int = 180, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = service.get_or_create_account(db, current_user)
    result = service.get_performance(db, account, days=days)
    return PaperPerformanceOut(**result)
