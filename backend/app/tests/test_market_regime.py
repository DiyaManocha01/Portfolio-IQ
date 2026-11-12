"""Tests for Phase 30: Market Regime Detection
(app/services/market_regime_service.py) -- a transparent, rule-based
classifier, not a trained model. See docs/adr/0013-market-regime-detection.md."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from app.services.market_data.providers import OHLCVBar
from app.services.market_regime_service import (
    TREND_Z_THRESHOLD,
    VOL_Z_THRESHOLD,
    Regime,
    _confidence_from_margin,
    classify_regime,
)


def _bars(prices: list[float], start: date = date(2024, 1, 1)) -> list[OHLCVBar]:
    bars = []
    d = start
    for p in prices:
        bars.append(OHLCVBar(date=d, open=p, high=p, low=p, close=p, volume=1_000_000))
        d += timedelta(days=1)
    return bars


def _noisy_series(drift: float, sigma: float, n: int = 400, seed: int = 0, vol_spike_last: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    prices = [100.0]
    for i in range(n):
        s = sigma * 6 if vol_spike_last and i >= n - vol_spike_last else sigma
        prices.append(prices[-1] * (1 + drift + rng.normal(0, s)))
    return prices[1:]


# ---------- hand-calculated: confidence ----------


def test_confidence_zero_exactly_at_a_boundary():
    assert _confidence_from_margin(0.0) == 0.0


def test_confidence_is_tanh_half_margin_hand_calculated():
    # tanh(1.0 / 2) = tanh(0.5)
    assert _confidence_from_margin(1.0) == pytest.approx(math.tanh(0.5), abs=1e-9)


def test_confidence_is_monotonic_and_bounded():
    values = [_confidence_from_margin(m) for m in [0, 0.5, 1, 2, 10]]
    assert values == sorted(values)
    assert all(0.0 <= v < 1.0 for v in values)


def test_confidence_never_negative_for_negative_margin():
    # Shouldn't occur in practice (branch conditions guarantee margin >= 0),
    # but the function itself must not return a negative or undefined value.
    assert _confidence_from_margin(-5.0) == 0.0


# ---------- insufficient history ----------


def test_insufficient_history_defaults_to_sideways_zero_confidence():
    result = classify_regime(_bars([100.0] * 10))
    assert result["regime"] == Regime.SIDEWAYS.value
    assert result["confidence"] == 0.0
    assert result["factors"] == []
    assert result["note"] is not None


def test_empty_bars_does_not_crash():
    result = classify_regime([])
    assert result["regime"] == Regime.SIDEWAYS.value
    assert result["as_of"] is None


# ---------- no look-ahead ----------


def test_no_look_ahead_result_unaffected_by_data_beyond_the_as_of_date():
    """classify_regime receives only `bars`, with no other input -- so the
    only way future data COULD leak in is if the caller passed it. This
    guards the practical failure mode: classifying "as of" some date must
    give the same answer whether or not more recent bars exist elsewhere,
    as long as they are not included in the list passed in."""
    full_prices = _noisy_series(drift=0.002, sigma=0.01, n=400, seed=3)
    bars = _bars(full_prices)

    as_of_300 = bars[:300]
    result_now = classify_regime(as_of_300)
    result_again = classify_regime(bars[:300])  # re-sliced from the same longer list
    assert result_now == result_again

    # Extending the list with 50 more days of (different, future) data and
    # re-slicing back down to the same cutoff must reproduce the identical
    # result -- nothing about calling classify_regime on the longer list
    # elsewhere can taint this call.
    classify_regime(bars[:350])  # exercise the "future" computation path first
    result_after_future_exists = classify_regime(bars[:300])
    assert result_after_future_exists == result_now


# ---------- scenario / "defensible evaluation" tests ----------
# Single random seeds can occasionally land on a different regime (e.g. a
# strong trend whose recent volatility also happens to be extreme, which
# this classifier deliberately lets volatility override -- see the module
# docstring). So these assert the MODAL (most common) regime across many
# seeds, which is what "defensible evaluation" can mean for a feature with
# no ground-truth labels: it behaves in the expected direction on average,
# not that every single draw matches.


def _modal_regime(drift: float, sigma: float, seeds: int = 25, **kwargs) -> str:
    from collections import Counter

    counts = Counter()
    for seed in range(seeds):
        bars = _bars(_noisy_series(drift, sigma, seed=seed, **kwargs))
        counts[classify_regime(bars)["regime"]] += 1
    return counts.most_common(1)[0][0]


def test_sustained_positive_drift_is_modally_trending_up():
    assert _modal_regime(drift=0.003, sigma=0.01) == Regime.TRENDING_UP.value


def test_sustained_negative_drift_is_modally_trending_down():
    assert _modal_regime(drift=-0.003, sigma=0.01) == Regime.TRENDING_DOWN.value


def test_zero_drift_is_modally_sideways():
    assert _modal_regime(drift=0.0, sigma=0.01) == Regime.SIDEWAYS.value


def test_recent_volatility_spike_is_always_high_volatility():
    # Unlike the trend scenarios, a genuine recent vol spike should be
    # detected essentially every time, not just modally -- it directly IS
    # the feature being measured, with no competing signal to override it.
    for seed in range(15):
        bars = _bars(_noisy_series(drift=0.0, sigma=0.01, seed=seed, vol_spike_last=20))
        assert classify_regime(bars)["regime"] == Regime.HIGH_VOLATILITY.value


def test_recent_volatility_collapse_is_always_low_volatility():
    rng = np.random.default_rng(0)

    def low_vol_series(seed):
        r = np.random.default_rng(seed)
        prices = [100.0]
        for _ in range(380):
            prices.append(prices[-1] * (1 + r.normal(0, 0.025)))
        for _ in range(20):
            prices.append(prices[-1] * (1 + r.normal(0, 0.003)))
        return prices[1:]

    for seed in range(15):
        bars = _bars(low_vol_series(seed))
        assert classify_regime(bars)["regime"] == Regime.LOW_VOLATILITY.value


# ---------- factor/structure checks ----------


def test_factors_present_and_well_formed_when_history_is_sufficient():
    bars = _bars(_noisy_series(drift=0.001, sigma=0.01, seed=5))
    result = classify_regime(bars)
    assert len(result["factors"]) == 2
    names = {f["name"] for f in result["factors"]}
    assert names == {"Trend", "Volatility"}
    for f in result["factors"]:
        assert isinstance(f["raw_value"], float)
        assert isinstance(f["z_score"], float)
        assert f["explanation"]


def test_confidence_is_bounded_zero_to_one():
    for seed in range(10):
        bars = _bars(_noisy_series(drift=0.002, sigma=0.01, seed=seed))
        result = classify_regime(bars)
        assert 0.0 <= result["confidence"] < 1.0


def test_thresholds_are_equal_in_magnitude_by_design():
    assert TREND_Z_THRESHOLD == VOL_Z_THRESHOLD


# ---------- HTTP endpoint integration ----------


def test_market_regime_endpoint_defaults_to_nifty50(client):
    resp = client.get("/market/regime")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "NIFTY50"
    assert body["regime"] in [r.value for r in Regime]
    assert 0.0 <= body["confidence"] < 1.0
    assert "data_source" in body


def test_market_regime_endpoint_accepts_symbol_param(client):
    resp = client.get("/market/regime", params={"symbol": "TCS"})
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "TCS"


def test_market_regime_endpoint_requires_no_auth(client):
    # Not user-scoped data -- same reasoning as /stocks and /screener (ADR 0009).
    resp = client.get("/market/regime")
    assert resp.status_code == 200
