"""Tests for Phase 9: PyPortfolioOpt-based optimization suggestions.

Integration tests hit the real `/portfolio/optimize` endpoint against the
seeded demo portfolio (real holdings, real cached synthetic price history)
for every method. Unit tests cover the early-exit/infeasibility paths that
don't need a real portfolio."""

from __future__ import annotations

import pytest

from app.portfolio.optimization_service import PortfolioOptimizationService, VALID_METHODS


class _StubPortfolio:
    """Duck-typed stand-in for a Portfolio ORM object -- compute()'s
    infeasibility paths only ever touch `.holdings` before returning."""

    def __init__(self, n_holdings: int):
        self.holdings = [object() for _ in range(n_holdings)]


# ---------- unit: infeasibility / validation paths (no DB) ----------

def test_unknown_method_raises(db_session):
    svc = PortfolioOptimizationService(db_session)
    with pytest.raises(ValueError):
        svc.compute(_StubPortfolio(5), method="not_a_real_method")


def test_single_holding_is_infeasible(db_session):
    svc = PortfolioOptimizationService(db_session)
    result = svc.compute(_StubPortfolio(1), method="min_variance")
    assert result["feasible"] is False
    assert result["allocations"] == []
    assert "at least 2 holdings" in result["note"]


def test_zero_holdings_is_infeasible(db_session):
    svc = PortfolioOptimizationService(db_session)
    result = svc.compute(_StubPortfolio(0), method="min_variance")
    assert result["feasible"] is False


# ---------- integration: real seeded demo portfolio, real endpoint ----------

@pytest.mark.parametrize("method", VALID_METHODS)
def test_optimize_endpoint_shape_for_each_method(client, auth_headers, method):
    resp = client.get(f"/portfolio/optimize?method={method}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == method
    assert "disclaimer" in body and len(body["disclaimer"]) > 0
    if body["feasible"]:
        total_suggested = sum(a["suggested_weight_pct"] for a in body["allocations"])
        assert 99 <= total_suggested <= 101  # weights must sum to ~100%
        for a in body["allocations"]:
            assert a["suggested_weight_pct"] >= -1e-6  # long-only: no negative/short weights
            assert a["delta_pct"] == pytest.approx(
                a["suggested_weight_pct"] - a["current_weight_pct"], abs=0.01
            )
        assert body["expected_annual_volatility"] >= 0


def test_optimize_endpoint_rejects_unknown_method(client, auth_headers):
    resp = client.get("/portfolio/optimize?method=bogus", headers=auth_headers)
    assert resp.status_code == 400


def test_optimize_endpoint_defaults_to_min_variance(client, auth_headers):
    resp = client.get("/portfolio/optimize", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["method"] == "min_variance"


def test_optimize_never_mutates_real_holdings(client, auth_headers):
    # Compare the real portfolio before and after calling every optimizer
    # method -- the endpoint must be read-only w.r.t. actual holdings.
    before = client.get("/portfolio", headers=auth_headers).json()
    for method in VALID_METHODS:
        client.get(f"/portfolio/optimize?method={method}", headers=auth_headers)
    after = client.get("/portfolio", headers=auth_headers).json()
    assert before == after
