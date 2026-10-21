"""Tests for Phase 13: the ML strategy backtest (app/ml/backtest.py).

Hand-calculated tests cover the parts of the PSR/DSR math that reduce to
clean, independently-verifiable special cases (Phi(0)=0.5 exactly; a
simple 3-point Sharpe ratio). The rest of the PSR/DSR formula is checked
against an independent re-derivation from its documented components
(scipy.stats.norm.ppf/cdf called directly in the test) rather than against
hand arithmetic -- this verifies the IMPLEMENTATION matches the documented
formula, not that the formula itself is correct; see the explicit
verification caveat in app/ml/backtest.py's module docstring and
docs/limitations.md (no network access in this sandbox to fetch the
original Bailey & Lopez de Prado paper and check against it directly).

The final test is a real end-to-end integration smoke test against the
seeded demo database -- slower, but it's the only thing that actually
exercises the full purged-walk-forward retraining loop."""

from __future__ import annotations

import math

import pandas as pd
import pytest
from scipy import stats

from app.ml import backtest
from app.ml.features import FEATURE_COLUMNS


# ---------- daily_sharpe: hand-calculated ----------

def test_daily_sharpe_hand_calculated():
    # returns = [0.02, 0.04, 0.06] -> mean=0.04, sample std (ddof=1)=0.02 -> sharpe=2.0
    returns = pd.Series([0.02, 0.04, 0.06])
    assert backtest.daily_sharpe(returns) == pytest.approx(2.0, abs=1e-9)


def test_daily_sharpe_hand_calculated_with_risk_free():
    # Same series, daily_risk_free=0.01 -> excess=[0.01,0.03,0.05], mean=0.03, std=0.02 -> sharpe=1.5
    returns = pd.Series([0.02, 0.04, 0.06])
    assert backtest.daily_sharpe(returns, daily_risk_free=0.01) == pytest.approx(1.5, abs=1e-9)


def test_daily_sharpe_zero_std_returns_zero():
    returns = pd.Series([0.01, 0.01, 0.01])
    assert backtest.daily_sharpe(returns) == 0.0


def test_daily_sharpe_too_few_observations_returns_zero():
    assert backtest.daily_sharpe(pd.Series([0.01])) == 0.0


# ---------- compute_probabilistic_sharpe_ratio: hand-calculated ----------

def test_psr_is_exactly_half_when_sharpe_equals_benchmark():
    # z = (sharpe_hat - benchmark) * sqrt(n-1) / denom = 0 whenever sharpe_hat == benchmark,
    # regardless of skew/kurtosis/n (since the numerator is exactly 0) -> PSR = Phi(0) = 0.5 exactly.
    for skew, kurt, n in [(0.0, 3.0, 50), (1.2, 8.0, 10), (-0.5, 5.0, 500)]:
        psr = backtest.compute_probabilistic_sharpe_ratio(
            sharpe_hat=0.1, benchmark_sharpe=0.1, n_obs=n, skew=skew, kurtosis=kurt
        )
        assert psr == pytest.approx(0.5, abs=1e-9)


def test_psr_matches_independent_formula_recomputation():
    # skew=0, kurtosis=3 (normal), sharpe_hat=0.1, benchmark=0, n_obs=101:
    # denom = sqrt(1 - 0*0.1 + ((3-1)/4)*0.1^2) = sqrt(1.005)
    # z = 0.1 * sqrt(100) / sqrt(1.005)
    sharpe_hat, benchmark, n_obs, skew, kurt = 0.1, 0.0, 101, 0.0, 3.0
    denom = math.sqrt(1 - skew * sharpe_hat + ((kurt - 1) / 4) * sharpe_hat**2)
    expected_z = (sharpe_hat - benchmark) * math.sqrt(n_obs - 1) / denom
    expected_psr = float(stats.norm.cdf(expected_z))

    actual = backtest.compute_probabilistic_sharpe_ratio(sharpe_hat, benchmark, n_obs, skew, kurt)
    assert actual == pytest.approx(expected_psr, abs=1e-9)
    assert actual == pytest.approx(0.8407, abs=1e-3)  # sanity: should be a high-0.8x probability


def test_psr_higher_sharpe_hat_gives_higher_psr():
    low = backtest.compute_probabilistic_sharpe_ratio(0.05, 0.0, 100, 0.0, 3.0)
    high = backtest.compute_probabilistic_sharpe_ratio(0.5, 0.0, 100, 0.0, 3.0)
    assert high > low


def test_psr_too_few_observations_returns_half():
    assert backtest.compute_probabilistic_sharpe_ratio(0.5, 0.0, 1, 0.0, 3.0) == 0.5


# ---------- compute_expected_max_sharpe_under_null ----------

def test_expected_max_sharpe_term1_vanishes_at_n_equals_2():
    # Phi^-1(1 - 1/2) = Phi^-1(0.5) = 0 EXACTLY (standard normal median is 0),
    # so at n_trials=2 the first term of SR0 vanishes regardless of variance,
    # leaving SR0 = sqrt(V) * gamma * Phi^-1(1 - 1/(2e)) -- independently recomputed below.
    variance = 0.25
    gamma = backtest.EULER_MASCHERONI
    expected = math.sqrt(variance) * gamma * float(stats.norm.ppf(1 - 1 / (2 * math.e)))
    actual = backtest.compute_expected_max_sharpe_under_null(2, variance)
    assert actual == pytest.approx(expected, abs=1e-9)


def test_expected_max_sharpe_matches_independent_formula_recomputation():
    n_trials, variance = 5, 0.04
    gamma = backtest.EULER_MASCHERONI
    expected = math.sqrt(variance) * (
        (1 - gamma) * float(stats.norm.ppf(1 - 1 / n_trials))
        + gamma * float(stats.norm.ppf(1 - 1 / (n_trials * math.e)))
    )
    actual = backtest.compute_expected_max_sharpe_under_null(n_trials, variance)
    assert actual == pytest.approx(expected, abs=1e-9)


def test_expected_max_sharpe_zero_variance_is_zero():
    assert backtest.compute_expected_max_sharpe_under_null(5, 0.0) == 0.0


def test_expected_max_sharpe_too_few_trials_is_zero():
    assert backtest.compute_expected_max_sharpe_under_null(1, 1.0) == 0.0


def test_expected_max_sharpe_increases_with_more_trials():
    # More unskilled trials -> higher expected maximum by chance alone.
    low_n = backtest.compute_expected_max_sharpe_under_null(2, 0.01)
    high_n = backtest.compute_expected_max_sharpe_under_null(50, 0.01)
    assert high_n > low_n


# ---------- compute_deflated_sharpe_ratio: wiring ----------

def test_deflated_sharpe_ratio_returns_both_fields():
    result = backtest.compute_deflated_sharpe_ratio(
        sharpe_hat=0.05, n_trials=3, trial_sharpe_variance=0.001, n_obs=500, skew=0.2, kurtosis=4.0
    )
    assert "sr0_per_period" in result and "dsr" in result
    assert 0.0 <= result["dsr"] <= 1.0


# ---------- paired_bootstrap_test ----------

def test_paired_bootstrap_detects_consistently_better_strategy():
    # Strategy is baseline + a constant positive lift every single day --
    # unambiguously better, so the bootstrap should show a positive mean
    # diff and a low p(no improvement).
    rng_baseline = pd.Series([0.001 * i % 7 - 0.003 for i in range(200)])
    strategy = rng_baseline + 0.05
    result = backtest.paired_bootstrap_test(strategy, rng_baseline, n_resamples=500, seed=1)
    assert result["mean_sharpe_diff_per_period"] > 0
    assert result["p_value_no_improvement_one_sided"] < 0.1


def test_paired_bootstrap_identical_series_gives_zero_diff():
    returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02] * 20)
    result = backtest.paired_bootstrap_test(returns, returns, n_resamples=200, seed=1)
    assert result["mean_sharpe_diff_per_period"] == pytest.approx(0.0, abs=1e-9)


def test_paired_bootstrap_too_few_observations():
    result = backtest.paired_bootstrap_test(pd.Series([0.01, 0.02]), pd.Series([0.01, 0.02]))
    assert "note" in result


# ---------- feature groups / ablation structure ----------

def test_feature_groups_partition_all_feature_columns_exactly():
    grouped = [col for cols in backtest.FEATURE_GROUPS.values() for col in cols]
    assert sorted(grouped) == sorted(FEATURE_COLUMNS)
    assert len(grouped) == len(set(grouped))  # no column appears in two groups


# ---------- integration: real end-to-end backtest against seeded demo data ----------

def test_run_backtest_end_to_end_smoke(db_session):
    result = backtest.run_backtest(db_session, selected_model_name="logistic_regression")

    assert len(result["strategy_summaries"]) == 3
    strategy_names = {s["strategy"] for s in result["strategy_summaries"]}
    assert strategy_names == {"ml_strategy", "buy_and_hold", "momentum"}
    for summary in result["strategy_summaries"]:
        assert summary["n_observations"] > 0
        assert -1.0 <= summary["max_drawdown"] <= 0.0
        assert summary["var_95"] >= 0.0 and summary["cvar_95"] >= summary["var_95"]

    dsr = result["deflated_sharpe_ratio"]
    assert 0.0 <= dsr["dsr"] <= 1.0
    assert dsr["n_trials"] == 3

    bootstrap = result["paired_bootstrap_vs_buy_and_hold"]
    assert "mean_sharpe_diff_per_period" in bootstrap

    ablation = result["ablation"]
    assert ablation[0]["feature_group_removed"] is None
    assert ablation[0]["delta_vs_full"] == 0.0
    assert len(ablation) == 1 + len(backtest.FEATURE_GROUPS)
