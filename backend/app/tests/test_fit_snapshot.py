"""Tests for Phase 29: the Dynamic Portfolio Fit Engine -- caching a Fit
Engine result (app/portfolio/fit_snapshot_service.py) and explaining why a
score moved relative to the last time it was computed."""

from __future__ import annotations

from app.models.fit_snapshot import FitScoreSnapshot
from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio import fit_snapshot_service as service


def _clear_snapshots(db, portfolio, stock, preset=None) -> None:
    """db_session is a real session against the shared seeded dev DB (see
    conftest.py), not a per-test transaction -- so tests that need to know
    whether a given (portfolio, stock, preset) combo starts with NO prior
    snapshot must clear it first, rather than assuming a clean slate."""
    q = db.query(FitScoreSnapshot).filter(
        FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id
    )
    if preset is not None:
        q = q.filter(FitScoreSnapshot.preset == preset)
    q.delete()
    db.commit()


def test_fingerprint_is_stable_for_identical_inputs(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    a = service.compute_input_fingerprint(db_session, portfolio, stock)
    b = service.compute_input_fingerprint(db_session, portfolio, stock)
    assert a == b


def test_fingerprint_changes_when_holdings_change(db_session):
    from app.models.portfolio import Holding

    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    before = service.compute_input_fingerprint(db_session, portfolio, stock)

    held_symbols = {h.stock_id for h in portfolio.holdings}
    new_stock = db_session.query(Stock).filter(~Stock.id.in_(held_symbols)).first()
    holding = Holding(portfolio_id=portfolio.id, stock_id=new_stock.id, quantity=1, avg_buy_price=100.0)
    db_session.add(holding)
    db_session.commit()

    after = service.compute_input_fingerprint(db_session, portfolio, stock)
    assert after != before

    db_session.delete(holding)
    db_session.commit()


def test_first_call_creates_a_snapshot_with_no_change(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    _clear_snapshots(db_session, portfolio, stock)

    result = service.get_fit_with_change(db_session, portfolio, stock, preset="balanced")

    assert result["change"] is None
    assert result["cached"] is False
    after_count = db_session.query(FitScoreSnapshot).filter(
        FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id
    ).count()
    assert after_count == 1


def test_second_call_with_unchanged_inputs_is_served_from_cache(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    _clear_snapshots(db_session, portfolio, stock, preset="balanced")

    first = service.get_fit_with_change(db_session, portfolio, stock, preset="balanced")
    count_after_first = db_session.query(FitScoreSnapshot).filter(
        FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id, FitScoreSnapshot.preset == "balanced"
    ).count()

    second = service.get_fit_with_change(db_session, portfolio, stock, preset="balanced")
    count_after_second = db_session.query(FitScoreSnapshot).filter(
        FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id, FitScoreSnapshot.preset == "balanced"
    ).count()

    # No new row was written -- the second call was served from the cache,
    # not recomputed.
    assert count_after_second == count_after_first
    assert second["cached"] is True
    assert second["change"] is None
    assert second["fit_score"] == first["fit_score"]


def test_recompute_after_holdings_change_explains_the_move(db_session):
    from app.models.portfolio import Holding

    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock_id for h in portfolio.holdings}
    candidate = db_session.query(Stock).filter(~Stock.id.in_(held_symbols)).first()
    other_candidate = db_session.query(Stock).filter(~Stock.id.in_(held_symbols), Stock.id != candidate.id).first()
    _clear_snapshots(db_session, portfolio, candidate, preset="balanced")

    first = service.get_fit_with_change(db_session, portfolio, candidate, preset="balanced")
    assert first["change"] is None

    # Change a real input: add a new holding, which changes the
    # portfolio-composition component of the fingerprint and therefore the
    # risk/diversification/concentration delta terms for `candidate`.
    holding = Holding(portfolio_id=portfolio.id, stock_id=other_candidate.id, quantity=5, avg_buy_price=100.0)
    db_session.add(holding)
    db_session.commit()

    second = service.get_fit_with_change(db_session, portfolio, candidate, preset="balanced")

    db_session.delete(holding)
    db_session.commit()

    assert second["cached"] is False
    if second["fit_score"] != first["fit_score"]:
        assert second["change"] is not None
        assert second["change"]["score_delta"] == round(second["fit_score"] - first["fit_score"], 1)
        assert "Fit score" in second["change"]["message"]
    else:
        # Extremely unlikely but not impossible for a z-scored sigmoid to
        # round to the identical display value -- in that case there is
        # genuinely nothing to explain.
        assert second["change"] is None


def test_different_presets_are_cached_independently(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    _clear_snapshots(db_session, portfolio, stock)

    balanced = service.get_fit_with_change(db_session, portfolio, stock, preset="balanced")
    growth = service.get_fit_with_change(db_session, portfolio, stock, preset="growth_seeking")

    assert balanced["cached"] is False
    assert growth["cached"] is False  # different preset, not served from balanced's cache

    snapshots = (
        db_session.query(FitScoreSnapshot)
        .filter(FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id)
        .all()
    )
    presets_seen = {s.preset for s in snapshots}
    assert {"balanced", "growth_seeking"}.issubset(presets_seen)


def test_portfolio_fit_route_includes_cached_and_change_fields(client, auth_headers, db_session):
    from app.services.market_data.service import MarketDataService

    portfolio = db_session.query(Portfolio).first()
    stock = MarketDataService(db_session).get_or_create_stock("TCS")
    _clear_snapshots(db_session, portfolio, stock)

    first = client.get("/portfolio-fit/TCS", headers=auth_headers)
    assert first.status_code == 200
    body = first.json()
    assert "change" in body
    assert "cached" in body
    assert body["cached"] is False

    second = client.get("/portfolio-fit/TCS", headers=auth_headers)
    assert second.status_code == 200
    assert second.json()["cached"] is True


def test_fit_ranking_change_alert_uses_cached_path(db_session):
    """app/services/alert_service.py's FIT_RANKING_CHANGE evaluator should
    route through fit_snapshot_service, not call PortfolioFitService
    directly -- exercised end-to-end via evaluate_rules."""
    from app.models.alert import AlertRule, AlertRuleType
    from app.models.portfolio import Portfolio
    from app.services.alert_service import evaluate_rules

    portfolio = db_session.query(Portfolio).first()
    stock = portfolio.holdings[0].stock
    _clear_snapshots(db_session, portfolio, stock)

    rule = AlertRule(
        user_id=portfolio.user_id,
        rule_type=AlertRuleType.FIT_RANKING_CHANGE,
        stock_id=stock.id,
        threshold=1.0,
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    # First evaluation establishes a baseline (never fires on the very
    # first check) and, as a side effect, creates a FitScoreSnapshot.
    evaluate_rules(db_session, [rule])
    snapshot_count = (
        db_session.query(FitScoreSnapshot)
        .filter(FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id)
        .count()
    )
    assert snapshot_count == 1

    # A second evaluation with nothing changed must be served from cache,
    # not create a second snapshot.
    evaluate_rules(db_session, [rule])
    snapshot_count_after = (
        db_session.query(FitScoreSnapshot)
        .filter(FitScoreSnapshot.portfolio_id == portfolio.id, FitScoreSnapshot.stock_id == stock.id)
        .count()
    )
    assert snapshot_count_after == 1

    db_session.delete(rule)
    db_session.commit()
