"""Hand-calculated unit tests for the Phase 8 portfolio risk metrics.

Every expected value in this file is worked out by hand in the comment
above the assertion -- these test the formulas themselves, not just that
the code runs, per the project's working rules (never trust a metric that
isn't independently verifiable).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.portfolio.risk_service import (
    diversification_ratio,
    effective_number_of_bets,
    hhi,
    historical_var_cvar,
    shrunk_covariance,
)


# ---------- HHI / effective number of bets ----------

def test_hhi_three_unequal_weights():
    # 0.5^2 + 0.3^2 + 0.2^2 = 0.25 + 0.09 + 0.04 = 0.38
    assert hhi(np.array([0.5, 0.3, 0.2])) == pytest.approx(0.38, abs=1e-9)


def test_hhi_normalizes_unnormalized_weights():
    # Same proportions as above (50:30:20), just not pre-normalized -> same HHI.
    assert hhi(np.array([50.0, 30.0, 20.0])) == pytest.approx(0.38, abs=1e-9)


def test_hhi_equal_weights_four_holdings():
    # 4 * (0.25^2) = 4 * 0.0625 = 0.25
    assert hhi(np.array([0.25, 0.25, 0.25, 0.25])) == pytest.approx(0.25, abs=1e-9)


def test_hhi_single_holding_is_one():
    assert hhi(np.array([1.0])) == pytest.approx(1.0, abs=1e-9)


def test_hhi_empty_is_zero():
    assert hhi(np.array([])) == 0.0


def test_effective_number_of_bets_equal_weights_equals_n():
    # Equal weights across 4 holdings -> effective number of bets is exactly 4.
    assert effective_number_of_bets(np.array([0.25, 0.25, 0.25, 0.25])) == pytest.approx(4.0, abs=1e-9)


def test_effective_number_of_bets_concentrated_portfolio():
    # 1 / 0.38 = 2.6315789...
    assert effective_number_of_bets(np.array([0.5, 0.3, 0.2])) == pytest.approx(1 / 0.38, abs=1e-6)


def test_effective_number_of_bets_single_holding_is_one():
    assert effective_number_of_bets(np.array([1.0])) == pytest.approx(1.0, abs=1e-9)


# ---------- Historical VaR / CVaR ----------

def test_historical_var_cvar_hand_calculated():
    # 10 sorted returns, confidence=0.90 -> alpha=0.10.
    # pandas .quantile(0.10) with default linear interpolation on a 10-point
    # series: position = alpha * (n-1) = 0.1 * 9 = 0.9 -> interpolate between
    # index 0 (-0.05) and index 1 (-0.04): -0.05 + 0.9*(0.01) = -0.041.
    # VaR = -(-0.041) = 0.041.
    # Tail (returns <= -0.041) contains only -0.05 -> CVaR = -(-0.05) = 0.05.
    returns = pd.Series([-0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04])
    var, cvar = historical_var_cvar(returns, confidence=0.90)
    assert var == pytest.approx(0.041, abs=1e-6)
    assert cvar == pytest.approx(0.05, abs=1e-6)


def test_historical_var_cvar_cvar_never_milder_than_var():
    returns = pd.Series(np.random.default_rng(42).normal(0, 0.02, 200))
    var_95, cvar_95 = historical_var_cvar(returns, confidence=0.95)
    assert cvar_95 >= var_95


def test_historical_var_cvar_empty_series():
    assert historical_var_cvar(pd.Series([], dtype=float), confidence=0.95) == (0.0, 0.0)


def test_historical_var_cvar_all_positive_returns_floors_at_zero():
    # No losses at all in the sample -> VaR/CVaR should floor at 0, never go negative.
    returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
    var, cvar = historical_var_cvar(returns, confidence=0.95)
    assert var >= 0.0
    assert cvar >= 0.0


# ---------- Diversification ratio ----------

def test_diversification_ratio_textbook_two_asset_example():
    # Two equally-weighted assets with 20% and 30% standalone annualized vol.
    # Weighted average vol = 0.5*0.20 + 0.5*0.30 = 0.25.
    # If the portfolio's actual (diversified) vol is 0.20, ratio = 0.25/0.20 = 1.25.
    ratio = diversification_ratio(
        weights=np.array([0.5, 0.5]),
        standalone_vols=np.array([0.20, 0.30]),
        portfolio_vol=0.20,
    )
    assert ratio == pytest.approx(1.25, abs=1e-9)


def test_diversification_ratio_perfectly_correlated_assets_equals_one():
    # When portfolio_vol equals the weighted average vol exactly (the
    # perfectly-correlated-assets case), the ratio is exactly 1 -- the floor.
    ratio = diversification_ratio(
        weights=np.array([0.5, 0.5]),
        standalone_vols=np.array([0.20, 0.30]),
        portfolio_vol=0.25,
    )
    assert ratio == pytest.approx(1.0, abs=1e-9)


def test_diversification_ratio_zero_portfolio_vol_floors_at_one():
    ratio = diversification_ratio(
        weights=np.array([0.5, 0.5]),
        standalone_vols=np.array([0.20, 0.30]),
        portfolio_vol=0.0,
    )
    assert ratio == 1.0


# ---------- Ledoit-Wolf shrinkage covariance ----------

def test_shrunk_covariance_falls_back_to_sample_for_single_asset():
    returns_df = pd.DataFrame({"A": [0.01, -0.02, 0.015, -0.005, 0.02]})
    cov, shrinkage, method = shrunk_covariance(returns_df)
    assert method == "sample"
    assert shrinkage == 0.0
    expected_annualized_var = returns_df["A"].var() * 252
    assert cov[0, 0] == pytest.approx(expected_annualized_var, rel=1e-6)


def test_shrunk_covariance_uses_ledoit_wolf_with_enough_data():
    rng = np.random.default_rng(7)
    n_obs = 100
    market_factor = rng.normal(0, 0.01, n_obs)
    returns_df = pd.DataFrame(
        {
            "A": market_factor + rng.normal(0, 0.005, n_obs),
            "B": market_factor + rng.normal(0, 0.005, n_obs),
        }
    )
    cov, shrinkage, method = shrunk_covariance(returns_df)
    assert method == "ledoit_wolf"
    assert 0.0 <= shrinkage <= 1.0
    # Covariance matrix must be symmetric with a positive diagonal.
    assert cov.shape == (2, 2)
    assert cov[0, 1] == pytest.approx(cov[1, 0], rel=1e-9)
    assert cov[0, 0] > 0 and cov[1, 1] > 0


def test_shrunk_covariance_falls_back_when_fewer_observations_than_assets():
    # 2 observations, 3 assets -- LedoitWolf would be degenerate here.
    returns_df = pd.DataFrame({"A": [0.01, -0.01], "B": [0.02, -0.02], "C": [0.005, -0.005]})
    cov, shrinkage, method = shrunk_covariance(returns_df)
    assert method == "sample"
    assert shrinkage == 0.0
