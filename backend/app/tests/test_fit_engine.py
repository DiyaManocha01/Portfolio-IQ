"""Tests for Phase 10: the rebuilt, z-scored, delta-based Portfolio Fit
Engine (app/portfolio/fit_service.py) and the shared hypothetical-addition
simulation core (app/portfolio/hypothetical.py).

Hand-calculated unit tests cover the pure z-score/sigmoid math. Integration
tests exercise the real endpoints against the seeded demo portfolio."""

from __future__ import annotations

import math

import pytest

from app.portfolio.fit_service import (
    DEFAULT_PRESET,
    PRESETS,
    TERM_SIGN,
    PortfolioFitService,
    sigmoid_score,
    zscore,
)
from app.portfolio.hypothetical import current_metrics, hypothetical_metrics_after_adding
from app.models.portfolio import Portfolio
from app.models.stock import Stock


# ---------- hand-calculated: zscore ----------

def test_zscore_hand_calculated():
    # (10 - 5) / 2 = 2.5
    assert zscore(10.0, mean=5.0, std=2.0) == pytest.approx(2.5, abs=1e-9)


def test_zscore_at_the_mean_is_zero():
    assert zscore(5.0, mean=5.0, std=2.0) == pytest.approx(0.0, abs=1e-9)


def test_zscore_degenerate_std_returns_zero_not_inf():
    assert zscore(10.0, mean=5.0, std=0.0) == 0.0


# ---------- hand-calculated: sigmoid_score ----------

def test_sigmoid_score_zero_logit_is_fifty():
    # 100 / (1 + e^0) = 100 / 2 = 50.0
    assert sigmoid_score(0.0) == pytest.approx(50.0, abs=1e-9)


def test_sigmoid_score_hand_calculated_positive_logit():
    # logit = 1.0 -> 100 / (1 + e^-1) = 100 / (1 + 0.367879...) = 73.105857...
    expected = 100.0 / (1.0 + math.exp(-1.0))
    assert sigmoid_score(1.0) == pytest.approx(expected, abs=1e-9)
    assert sigmoid_score(1.0) == pytest.approx(73.105857, abs=1e-4)


def test_sigmoid_score_is_monotonic_and_bounded():
    values = [sigmoid_score(x) for x in [-10, -1, 0, 1, 10]]
    assert values == sorted(values)
    assert 0.0 < values[0] < 1.0
    assert 99.0 < values[-1] < 100.0


# ---------- presets ----------

def test_all_preset_weights_sum_to_one():
    for name, weights in PRESETS.items():
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9), f"preset {name!r} doesn't sum to 1.0"


def test_term_sign_covers_every_weighted_term():
    for name, weights in PRESETS.items():
        assert set(weights.keys()) == set(TERM_SIGN.keys()), f"preset {name!r} term mismatch"


def test_default_preset_is_a_real_preset():
    assert DEFAULT_PRESET in PRESETS


# ---------- hypothetical.py: current vs hypothetical consistency ----------

def test_current_metrics_and_hypothetical_use_same_method_for_already_held(db_session):
    portfolio = db_session.query(Portfolio).first()
    holdings = list(portfolio.holdings)
    assert len(holdings) >= 2, "seeded demo portfolio must have >=2 holdings for this test to be meaningful"

    current = current_metrics(db_session, portfolio)
    already_held_stock = holdings[0].stock
    hypo = hypothetical_metrics_after_adding(db_session, portfolio, already_held_stock)

    # "Adding more" of an already-held stock is a no-op scenario -- the
    # hypothetical and current metrics must come out IDENTICAL, not just
    # close, since both should take the exact same code path internally.
    assert hypo["annualized_volatility"] == current["annualized_volatility"]
    assert hypo["diversification_ratio"] == current["diversification_ratio"]
    assert hypo["hhi_holdings"] == current["hhi_holdings"]


def test_hypothetical_new_sector_stock_changes_metrics(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    candidate = (
        db_session.query(Stock)
        .filter(~Stock.symbol.in_(held_symbols))
        .first()
    )
    assert candidate is not None, "seeded universe must have at least one unheld stock"

    current = current_metrics(db_session, portfolio)
    hypo = hypothetical_metrics_after_adding(db_session, portfolio, candidate)
    assert hypo is not None and current is not None
    # Adding any real candidate at a nonzero weight must change SOME metric
    # -- if all three matched current exactly, the simulation silently did
    # nothing, which would be a bug.
    changed = (
        hypo["annualized_volatility"] != current["annualized_volatility"]
        or hypo["diversification_ratio"] != current["diversification_ratio"]
        or hypo["hhi_holdings"] != current["hhi_holdings"]
    )
    assert changed


# ---------- fit_service: integration against seeded demo portfolio ----------

def test_already_held_stock_has_zero_raw_deltas(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_stock = portfolio.holdings[0].stock
    svc = PortfolioFitService(db_session, preset="balanced")
    fit = svc.compute_fit(held_stock, portfolio)

    by_name = {f["name"]: f for f in fit["factors"]}
    assert by_name["Risk Impact"]["raw_value"] == 0.0
    assert by_name["Diversification Impact"]["raw_value"] == 0.0
    assert by_name["Concentration Impact"]["raw_value"] == 0.0


def test_fit_score_bounded_zero_to_hundred(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    fit = PortfolioFitService(db_session).compute_fit(stock, portfolio)
    assert 0.0 <= fit["fit_score"] <= 100.0


def test_factors_sorted_descending_by_contribution(db_session):
    portfolio = db_session.query(Portfolio).first()
    stock = db_session.query(Stock).first()
    fit = PortfolioFitService(db_session).compute_fit(stock, portfolio)
    contributions = [f["contribution"] for f in fit["factors"]]
    assert contributions == sorted(contributions, reverse=True)


def test_different_presets_can_produce_different_scores(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbols = {h.stock.symbol for h in portfolio.holdings}
    candidate = db_session.query(Stock).filter(~Stock.symbol.in_(held_symbols)).first()

    scores = {
        preset: PortfolioFitService(db_session, preset=preset).compute_fit(candidate, portfolio)["fit_score"]
        for preset in PRESETS
    }
    # Not every preset needs to differ, but they must not all be coincidentally
    # identical for a real candidate with nonzero deltas -- that would suggest
    # the weights aren't actually being applied.
    assert len(set(scores.values())) > 1


# ---------- HTTP endpoint integration ----------

def test_portfolio_fit_endpoint_includes_preset_and_zscore_fields(client, auth_headers):
    resp = client.get("/portfolio-fit/TCS", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] in PRESETS
    for factor in body["factors"]:
        assert "raw_value" in factor and "z_score" in factor


def test_portfolio_fit_endpoint_accepts_preset_param(client, auth_headers):
    resp = client.get("/portfolio-fit/TCS?preset=growth_seeking", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["preset"] == "growth_seeking"


def test_portfolio_fit_endpoint_rejects_unknown_preset(client, auth_headers):
    resp = client.get("/portfolio-fit/TCS?preset=nonsense", headers=auth_headers)
    assert resp.status_code == 400


def test_discover_endpoint_still_returns_expected_shape(client, auth_headers):
    resp = client.get("/discover?limit=10", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    for item in items:
        assert 0.0 <= item["portfolio_fit"] <= 100.0
        assert item["diversification_benefit"] in {"High", "Moderate", "Low"}
    fits = [item["portfolio_fit"] for item in items]
    assert fits == sorted(fits, reverse=True)
