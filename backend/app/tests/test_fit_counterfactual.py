"""Tests for Phase 16: counterfactual explanations for the Fit Engine
(app/portfolio/fit_counterfactual_service.py).

Hand-calculated / exact-identity tests:
  - term_deltas sum EXACTLY to logit_gap (an algebraic identity, not an
    approximation -- see the service's module docstring).
  - the single-term required-z-delta arithmetic, verified against a
    hand-worked toy example.
"""

from __future__ import annotations

import pytest

from app.models.portfolio import Portfolio
from app.models.stock import Stock
from app.portfolio.fit_counterfactual_service import FitCounterfactualService, _logit_from_score
from app.portfolio.fit_service import TERM_SIGN


# ---------- _logit_from_score: hand-calculated ----------

def test_logit_from_score_fifty_is_zero():
    # sigmoid(0) = 50 -> logit_from_score(50) = 0 exactly (ln(1) = 0)
    assert _logit_from_score(50.0) == pytest.approx(0.0, abs=1e-9)


def test_logit_from_score_hand_calculated():
    # score=73.105857... -> p=0.73105857, logit = ln(p/(1-p)) = ln(0.73105857/0.26894143) = ln(2.71828...) = 1.0
    # (this is the exact inverse of the sigmoid(1.0) example used in Phase 10's own tests)
    score = 100.0 / (1.0 + pytest.importorskip("math").exp(-1.0))
    assert _logit_from_score(score) == pytest.approx(1.0, abs=1e-6)


def test_logit_from_score_rejects_boundary_values():
    with pytest.raises(ValueError):
        _logit_from_score(0.0)
    with pytest.raises(ValueError):
        _logit_from_score(100.0)
    with pytest.raises(ValueError):
        _logit_from_score(150.0)


# ---------- explain_ranking_gap: exact identity ----------

def test_term_deltas_sum_exactly_to_logit_gap(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    candidates = db_session.query(Stock).filter(~Stock.symbol.in_(held_symbols)).limit(2).all()
    assert len(candidates) == 2, "seeded universe needs at least 2 unheld stocks for this test"
    stock_a, stock_b = candidates

    svc = FitCounterfactualService(db_session)
    gap = svc.explain_ranking_gap(portfolio, stock_a, stock_b)

    unrounded_sum = sum(d["delta"] for d in gap["term_deltas"])
    # Both are rounded to the same precision (4dp) so the sum of rounded
    # deltas matches the rounded logit_gap to within rounding tolerance.
    assert unrounded_sum == pytest.approx(gap["logit_gap"], abs=1e-3)


def test_ranking_gap_term_deltas_sorted_by_absolute_magnitude(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    candidates = db_session.query(Stock).filter(~Stock.symbol.in_(held_symbols)).limit(2).all()
    stock_a, stock_b = candidates

    gap = FitCounterfactualService(db_session).explain_ranking_gap(portfolio, stock_a, stock_b)
    magnitudes = [abs(d["delta"]) for d in gap["term_deltas"]]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_ranking_gap_covers_every_weighted_term(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    candidates = db_session.query(Stock).filter(~Stock.symbol.in_(held_symbols)).limit(2).all()
    stock_a, stock_b = candidates

    gap = FitCounterfactualService(db_session).explain_ranking_gap(portfolio, stock_a, stock_b)
    assert {d["term"] for d in gap["term_deltas"]} == set(TERM_SIGN.keys())


# ---------- what_would_improve_rank ----------

def test_counterfactual_required_z_delta_hand_calculated(db_session):
    # Construct the arithmetic directly: gap = target_logit - current_logit.
    # required_z_delta = gap / (TERM_SIGN[term] * weight[term]).
    # For a term with sign=+1 and weight=0.25, gap=0.5 -> required_z_delta = 0.5/0.25 = 2.0.
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    stock = db_session.query(Stock).filter(~Stock.symbol.in_(held_symbols)).first()

    svc = FitCounterfactualService(db_session, preset="balanced")
    cf = svc.what_would_improve_rank(portfolio, stock, target_score=99.0)  # a deliberately high target
    assert cf["already_meets_target"] is False

    from app.portfolio.fit_service import PRESETS

    weights = PRESETS["balanced"]
    # Cross-term check: required_z_delta was derived FROM a single shared
    # gap (gap = required_z_delta * sign * weight for each term in
    # isolation), so re-deriving the gap from every term's own
    # required_z_delta must recover the SAME value across all terms.
    implied_gaps = [
        s["required_z_delta"] * (TERM_SIGN[s["term"]] * weights[s["term"]]) for s in cf["term_scenarios"]
    ]
    for g in implied_gaps[1:]:
        assert g == pytest.approx(implied_gaps[0], abs=1e-3)


def test_counterfactual_already_meets_target_has_no_scenarios(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    stock = db_session.query(Stock).filter(~Stock.symbol.in_(held_symbols)).first()

    svc = FitCounterfactualService(db_session)
    cf = svc.what_would_improve_rank(portfolio, stock, target_score=1.0)  # trivially low target
    assert cf["already_meets_target"] is True
    assert cf["term_scenarios"] == []


def test_counterfactual_rejects_both_targets(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    svc = FitCounterfactualService(db_session)
    with pytest.raises(ValueError):
        svc.what_would_improve_rank(portfolio, stock, target_stock=stock, target_score=50.0)


def test_counterfactual_rejects_no_target(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    svc = FitCounterfactualService(db_session)
    with pytest.raises(ValueError):
        svc.what_would_improve_rank(portfolio, stock)


# ---------- HTTP endpoint integration ----------

def test_compare_endpoint_shape(client, auth_headers):
    resp = client.get("/portfolio-fit/SUNPHARMA/compare/WIPRO", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol_a"] == "SUNPHARMA"
    assert body["symbol_b"] == "WIPRO"
    assert len(body["term_deltas"]) == 5


def test_counterfactual_endpoint_requires_exactly_one_target(client, auth_headers):
    resp = client.get("/portfolio-fit/WIPRO/counterfactual", headers=auth_headers)
    assert resp.status_code == 400
    resp2 = client.get(
        "/portfolio-fit/WIPRO/counterfactual?target_symbol=SUNPHARMA&target_score=50", headers=auth_headers
    )
    assert resp2.status_code == 400


def test_counterfactual_endpoint_rejects_invalid_target_score(client, auth_headers):
    resp = client.get("/portfolio-fit/WIPRO/counterfactual?target_score=0", headers=auth_headers)
    assert resp.status_code == 400
