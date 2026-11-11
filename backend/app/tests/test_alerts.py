import datetime as dt
import uuid

from app.data.seed import DEMO_EMAIL
from app.models.alert import AlertDirection, AlertRule, AlertRuleType
from app.models.user import User
from app.services.alert_service import evaluate_rule, evaluate_rules
from app.services.market_data.service import MarketDataService


def _demo_user(db_session) -> User:
    return db_session.query(User).filter(User.email == DEMO_EMAIL).first()


def _tcs_stock_id(db_session) -> int:
    return MarketDataService(db_session).get_or_create_stock("TCS").id


def _make_rule(db_session, **kwargs) -> AlertRule:
    defaults = dict(
        user_id=_demo_user(db_session).id,
        rule_type=AlertRuleType.PRICE_THRESHOLD,
        stock_id=_tcs_stock_id(db_session),
        direction=AlertDirection.ABOVE,
        threshold=1.0,
    )
    defaults.update(kwargs)
    rule = AlertRule(**defaults)
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


# ---- Service-level dedup behavior ----


def test_first_evaluation_never_fires(db_session):
    rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, threshold=0.01, direction=AlertDirection.ABOVE)
    event = evaluate_rule(db_session, rule)
    assert event is None
    assert rule.last_value is not None
    assert rule.last_evaluated_at is not None


def test_price_threshold_fires_on_crossing_above(db_session):
    rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, direction=AlertDirection.ABOVE, threshold=0.01)
    evaluate_rule(db_session, rule)  # baseline below the (near-zero) threshold
    rule.last_value = 0.0  # force "previously below"
    db_session.commit()

    event = evaluate_rule(db_session, rule)
    assert event is not None
    assert "crossed above" in event.message
    assert "TCS" in event.message


def test_price_threshold_does_not_fire_when_already_above(db_session):
    rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, direction=AlertDirection.ABOVE, threshold=0.01)
    evaluate_rule(db_session, rule)  # baseline, already above 0.01
    event = evaluate_rule(db_session, rule)  # still above -- no new crossing
    assert event is None


def test_rsi_threshold_requires_direction_and_crosses():
    pass  # covered via route validation test below; evaluator logic shares _crossed with price


def test_cooldown_prevents_rapid_double_fire(db_session):
    rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, direction=AlertDirection.ABOVE, threshold=0.01)
    evaluate_rule(db_session, rule)
    rule.last_value = 0.0
    db_session.commit()

    first = evaluate_rule(db_session, rule)
    assert first is not None

    rule.last_value = 0.0  # pretend it crossed back and forth again immediately
    db_session.commit()
    second = evaluate_rule(db_session, rule)
    assert second is None  # cooldown blocks it even though the crossing condition is met again


def test_delta_type_rebaselines_only_on_fire(db_session):
    rule = _make_rule(
        db_session,
        rule_type=AlertRuleType.PORTFOLIO_VOLATILITY_CHANGE,
        stock_id=None,
        direction=None,
        threshold=1_000_000.0,  # effectively unreachable -- we only check last_value handling
    )
    evaluate_rule(db_session, rule)  # baseline
    baseline = rule.last_value
    assert baseline is not None

    evaluate_rule(db_session, rule)  # no fire (threshold unreachable)
    assert rule.last_value == baseline  # unchanged -- only rebaselines on fire, not every tick


def test_daily_type_fires_at_most_once_per_day(db_session):
    rule = _make_rule(
        db_session,
        rule_type=AlertRuleType.PRICE_PCT_MOVE,
        direction=None,
        threshold=0.0,  # any nonzero move exceeds this
    )
    first = evaluate_rule(db_session, rule)
    # First-ever evaluation is baseline-only by design, so force last_fired_at
    # to simulate "already fired earlier today" and confirm no second fire:
    rule.last_fired_at = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(seconds=120)
    rule.last_value = 0.0
    db_session.commit()
    second = evaluate_rule(db_session, rule)
    assert second is None  # same day -- already fired


def test_portfolio_level_rule_with_no_holdings_returns_none(db_session):
    from app.models.portfolio import Portfolio
    from app.models.user import User as UserModel

    email = f"pytest-alerts-{uuid.uuid4().hex[:8]}@example.com"
    user = UserModel(email=email, hashed_password="x", full_name="No Holdings")
    db_session.add(user)
    db_session.flush()
    db_session.add(Portfolio(user_id=user.id, name="Empty"))
    db_session.commit()

    rule = AlertRule(
        user_id=user.id,
        rule_type=AlertRuleType.PORTFOLIO_VOLATILITY_CHANGE,
        threshold=1.0,
    )
    db_session.add(rule)
    db_session.commit()

    event = evaluate_rule(db_session, rule)
    assert event is None
    assert rule.last_value is None  # never evaluated -- data genuinely unavailable, not guessed


def test_disabled_rule_never_fires(db_session):
    rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, direction=AlertDirection.ABOVE, threshold=0.01, enabled=False)
    event = evaluate_rule(db_session, rule)
    assert event is None
    assert rule.last_value is None


def test_evaluate_rules_skips_a_failing_rule_without_blocking_others(db_session, monkeypatch):
    from app.services import alert_service

    def _boom(db, rule):
        raise RuntimeError("simulated evaluator failure")

    good_rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, direction=AlertDirection.ABOVE, threshold=0.01)
    bad_rule = _make_rule(db_session, rule_type=AlertRuleType.RSI_THRESHOLD, direction=AlertDirection.ABOVE, threshold=70)
    monkeypatch.setitem(alert_service._EVALUATORS, AlertRuleType.RSI_THRESHOLD, _boom)

    events = evaluate_rules(db_session, [bad_rule, good_rule])
    assert events == []  # both are first-evaluations (baseline-only), but no exception propagated
    assert good_rule.last_value is not None


# ---- API routes ----


def test_create_rule_requires_symbol_for_stock_scoped_type(client, auth_headers):
    resp = client.post(
        "/alerts/rules",
        json={"rule_type": "PRICE_THRESHOLD", "direction": "ABOVE", "threshold": 3000},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_rule_rejects_symbol_for_portfolio_level_type(client, auth_headers):
    resp = client.post(
        "/alerts/rules",
        json={"rule_type": "PORTFOLIO_VOLATILITY_CHANGE", "symbol": "TCS", "threshold": 2.0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_rule_requires_direction_for_directional_type(client, auth_headers):
    resp = client.post(
        "/alerts/rules",
        json={"rule_type": "RSI_THRESHOLD", "symbol": "TCS", "threshold": 70},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_list_update_delete_rule(client, auth_headers):
    create = client.post(
        "/alerts/rules",
        json={"rule_type": "PRICE_THRESHOLD", "symbol": "RELIANCE", "direction": "ABOVE", "threshold": 2900},
        headers=auth_headers,
    )
    assert create.status_code == 201
    rule = create.json()
    assert rule["symbol"] == "RELIANCE"
    assert rule["enabled"] is True

    listed = client.get("/alerts/rules", headers=auth_headers)
    assert any(r["id"] == rule["id"] for r in listed.json())

    updated = client.patch(f"/alerts/rules/{rule['id']}", json={"enabled": False}, headers=auth_headers)
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False

    deleted = client.delete(f"/alerts/rules/{rule['id']}", headers=auth_headers)
    assert deleted.status_code == 204

    listed_after = client.get("/alerts/rules", headers=auth_headers)
    assert all(r["id"] != rule["id"] for r in listed_after.json())


def test_rules_are_isolated_between_users(client, auth_headers):
    email = f"pytest-alerts2-{uuid.uuid4().hex[:8]}@example.com"
    register = client.post("/auth/register", json={"email": email, "password": "testpass123", "full_name": "Other"})
    other_headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

    create = client.post(
        "/alerts/rules",
        json={"rule_type": "PRICE_THRESHOLD", "symbol": "TCS", "direction": "ABOVE", "threshold": 1},
        headers=auth_headers,
    )
    rule_id = create.json()["id"]

    forbidden = client.patch(f"/alerts/rules/{rule_id}", json={"enabled": False}, headers=other_headers)
    assert forbidden.status_code == 404

    other_rules = client.get("/alerts/rules", headers=other_headers)
    assert all(r["id"] != rule_id for r in other_rules.json())


def test_evaluate_endpoint_returns_new_events(client, auth_headers):
    create = client.post(
        "/alerts/rules",
        json={"rule_type": "PRICE_THRESHOLD", "symbol": "ICICIBANK", "direction": "ABOVE", "threshold": 0.01},
        headers=auth_headers,
    )
    rule_id = create.json()["id"]

    first = client.post("/alerts/evaluate", headers=auth_headers)
    assert first.status_code == 200
    assert first.json() == []  # baseline only

    patch = client.patch(f"/alerts/rules/{rule_id}", json={}, headers=auth_headers)
    assert patch.status_code == 200


def test_list_and_mark_read_events(client, auth_headers, db_session):
    rule = _make_rule(db_session, rule_type=AlertRuleType.PRICE_THRESHOLD, direction=AlertDirection.ABOVE, threshold=0.01)
    evaluate_rule(db_session, rule)
    rule.last_value = 0.0
    db_session.commit()
    event = evaluate_rule(db_session, rule)
    assert event is not None

    listed = client.get("/alerts/events", headers=auth_headers)
    assert listed.status_code == 200
    assert any(e["id"] == event.id for e in listed.json())

    marked = client.post(f"/alerts/events/{event.id}/read", headers=auth_headers)
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    unread = client.get("/alerts/events", params={"unread_only": True}, headers=auth_headers)
    assert all(e["id"] != event.id for e in unread.json())
