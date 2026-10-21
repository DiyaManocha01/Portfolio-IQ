"""Tests for Phase 14: risk attribution (marginal_contribution_to_risk in
risk_service.py, and app/portfolio/risk_attribution_service.py).

Hand-calculated test: a toy 2-asset covariance matrix where the component
risk contributions work out to an exact, clean 50/50 split despite
unequal money weights -- see the comment for the full by-hand derivation.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.models.portfolio import Portfolio
from app.portfolio.risk_attribution_service import RiskAttributionService
from app.portfolio.risk_service import marginal_contribution_to_risk


# ---------- hand-calculated: marginal_contribution_to_risk ----------

def test_marginal_contribution_hand_calculated_two_asset():
    # Sigma = [[0.04, 0.01], [0.01, 0.09]]  (vol1=20%, vol2=30%, cov12=0.01)
    # w = [0.6, 0.4]
    # Sigma @ w = [0.04*0.6 + 0.01*0.4, 0.01*0.6 + 0.09*0.4] = [0.028, 0.042]
    # portfolio_variance = w . (Sigma @ w) = 0.6*0.028 + 0.4*0.042 = 0.0168 + 0.0168 = 0.0336
    # portfolio_vol = sqrt(0.0336) = 0.18330303...
    # MCR = [0.028, 0.042] / 0.18330303 = [0.152753, 0.229129]
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    w = np.array([0.6, 0.4])
    portfolio_vol = float(np.sqrt(w @ cov @ w))
    assert portfolio_vol == pytest.approx(0.18330303, abs=1e-6)

    mcr = marginal_contribution_to_risk(cov, w, portfolio_vol)
    assert mcr[0] == pytest.approx(0.152753, abs=1e-5)
    assert mcr[1] == pytest.approx(0.229129, abs=1e-5)


def test_component_contributions_sum_exactly_to_portfolio_vol_eulers_theorem():
    # CC_i = w_i * MCR_i. By Euler's theorem (portfolio_vol is a degree-1
    # homogeneous function of w), sum(CC_i) == portfolio_vol EXACTLY.
    # With the same toy example: CC1 = 0.6*0.028/vol = 0.0168/vol,
    # CC2 = 0.4*0.042/vol = 0.0168/vol -- i.e. CC1 == CC2 EXACTLY (both
    # numerators are 0.0168), so despite 60/40 money weights, risk
    # contribution is an exact 50/50 split.
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    w = np.array([0.6, 0.4])
    portfolio_vol = float(np.sqrt(w @ cov @ w))
    mcr = marginal_contribution_to_risk(cov, w, portfolio_vol)
    cc = w * mcr

    assert cc.sum() == pytest.approx(portfolio_vol, abs=1e-9)
    assert cc[0] == pytest.approx(cc[1], abs=1e-9)  # exact 50/50 split by construction
    risk_contribution_pct = cc / portfolio_vol * 100
    assert risk_contribution_pct[0] == pytest.approx(50.0, abs=1e-6)
    assert risk_contribution_pct[1] == pytest.approx(50.0, abs=1e-6)


def test_marginal_contribution_zero_portfolio_vol_returns_zeros():
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    w = np.array([0.6, 0.4])
    mcr = marginal_contribution_to_risk(cov, w, 0.0)
    assert np.all(mcr == 0.0)


def test_marginal_contribution_three_asset_sanity():
    # Larger (random but fixed, positive-semi-definite by construction)
    # example -- just checks the sum-to-portfolio-vol property holds
    # beyond the clean hand-worked 2-asset case.
    A = np.array([[0.2, 0.05, 0.0], [0.1, 0.25, 0.05], [0.0, 0.05, 0.3]])
    cov = A @ A.T  # guarantees PSD
    w = np.array([0.5, 0.3, 0.2])
    portfolio_vol = float(np.sqrt(w @ cov @ w))
    mcr = marginal_contribution_to_risk(cov, w, portfolio_vol)
    cc = w * mcr
    assert cc.sum() == pytest.approx(portfolio_vol, abs=1e-9)


# ---------- integration: real seeded demo portfolio ----------

def test_risk_attribution_weight_and_risk_pcts_each_sum_to_100(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = RiskAttributionService(db_session).compute(portfolio)

    total_weight = sum(a["weight_pct"] for a in result["attributions"])
    total_risk = sum(a["risk_contribution_pct"] for a in result["attributions"])
    assert 99.0 <= total_weight <= 101.0
    assert 99.0 <= total_risk <= 101.0


def test_risk_attribution_concentration_ratio_matches_definition(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = RiskAttributionService(db_session).compute(portfolio)

    for item in result["attributions"]:
        expected_ratio = item["risk_contribution_pct"] / item["weight_pct"]
        assert item["risk_concentration_ratio"] == pytest.approx(expected_ratio, abs=1e-2)


def test_risk_attribution_sorted_descending_by_risk_contribution(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = RiskAttributionService(db_session).compute(portfolio)
    contributions = [a["risk_contribution_pct"] for a in result["attributions"]]
    assert contributions == sorted(contributions, reverse=True)


def test_risk_attribution_endpoint_shape(client, auth_headers):
    resp = client.get("/portfolio/risk-attribution", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolio_annualized_volatility"] >= 0
    assert len(body["attributions"]) > 0
    for item in body["attributions"]:
        assert item["weight_pct"] >= 0
        assert item["risk_concentration_ratio"] >= 0
