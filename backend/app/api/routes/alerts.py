from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.alert import AlertEvent, AlertRule
from app.models.user import User
from app.schemas.alert import AlertEventOut, AlertRuleCreate, AlertRuleOut, AlertRuleUpdate
from app.services.alert_service import evaluate_rules
from app.services.market_data.service import MarketDataService

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _to_rule_out(rule: AlertRule) -> AlertRuleOut:
    return AlertRuleOut(
        id=rule.id,
        rule_type=rule.rule_type,
        symbol=rule.stock.symbol if rule.stock else None,
        direction=rule.direction,
        threshold=rule.threshold,
        enabled=rule.enabled,
        last_value=rule.last_value,
        last_evaluated_at=rule.last_evaluated_at,
        last_fired_at=rule.last_fired_at,
        created_at=rule.created_at,
    )


def _to_event_out(event: AlertEvent) -> AlertEventOut:
    rule = event.rule
    return AlertEventOut(
        id=event.id,
        rule_id=event.rule_id,
        rule_type=rule.rule_type,
        symbol=rule.stock.symbol if rule.stock else None,
        triggered_at=event.triggered_at,
        value=event.value,
        message=event.message,
        is_read=event.is_read,
    )


def _get_owned_rule(db: Session, rule_id: int, user_id: int) -> AlertRule:
    rule = db.query(AlertRule).filter(AlertRule.id == rule_id, AlertRule.user_id == user_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return rule


@router.post("/rules", response_model=AlertRuleOut, status_code=201)
def create_rule(payload: AlertRuleCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stock_id = None
    if payload.symbol:
        stock = MarketDataService(db).get_or_create_stock(payload.symbol)
        stock_id = stock.id

    rule = AlertRule(
        user_id=current_user.id,
        rule_type=payload.rule_type,
        stock_id=stock_id,
        direction=payload.direction,
        threshold=payload.threshold,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _to_rule_out(rule)


@router.get("/rules", response_model=list[AlertRuleOut])
def list_rules(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = db.query(AlertRule).filter(AlertRule.user_id == current_user.id).order_by(AlertRule.created_at.desc()).all()
    return [_to_rule_out(r) for r in rules]


@router.patch("/rules/{rule_id}", response_model=AlertRuleOut)
def update_rule(
    rule_id: int,
    payload: AlertRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = _get_owned_rule(db, rule_id, current_user.id)
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.threshold is not None:
        rule.threshold = payload.threshold
    db.commit()
    db.refresh(rule)
    return _to_rule_out(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = _get_owned_rule(db, rule_id, current_user.id)
    db.delete(rule)
    db.commit()


@router.post("/evaluate", response_model=list[AlertEventOut])
def evaluate(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Evaluates every enabled rule the current user owns right now.

    This is the on-demand path; the same evaluation also runs
    periodically from the Phase 24 background loop while the server is
    up (no new scheduler added -- see docs/adr/0010-alerts-and-notifications.md).
    """
    rules = db.query(AlertRule).filter(AlertRule.user_id == current_user.id, AlertRule.enabled.is_(True)).all()
    events = evaluate_rules(db, rules)
    return [_to_event_out(e) for e in events]


@router.get("/events", response_model=list[AlertEventOut])
def list_events(
    unread_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(AlertEvent).join(AlertRule).filter(AlertRule.user_id == current_user.id)
    if unread_only:
        query = query.filter(AlertEvent.is_read.is_(False))
    events = query.order_by(AlertEvent.triggered_at.desc()).limit(limit).all()
    return [_to_event_out(e) for e in events]


@router.post("/events/{event_id}/read", response_model=AlertEventOut)
def mark_event_read(event_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    event = (
        db.query(AlertEvent)
        .join(AlertRule)
        .filter(AlertEvent.id == event_id, AlertRule.user_id == current_user.id)
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Alert event not found")
    event.is_read = True
    db.commit()
    db.refresh(event)
    return _to_event_out(event)
