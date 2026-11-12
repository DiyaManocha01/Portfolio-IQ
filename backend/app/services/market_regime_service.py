"""Market Regime Detection (Phase 30): a transparent, rule-based classifier
-- deterministic thresholds on z-scored trend and volatility features, not
a trained black-box model. See docs/adr/0013-market-regime-detection.md.

Why rule-based rather than trained ML: there is no ground-truth "this day
was actually a Trending/Sideways/High-Vol regime" label to train or
validate a classifier against -- any label would itself be a human
judgment call dressed up as data. A deterministic threshold on two
already-transparent features (a trend z-statistic, a rolling volatility
z-score) is directly explainable (the factors ARE the explanation) and
trivially avoids look-ahead bias: every feature at a given date is
computed only from bars up to and including that date.

The trend feature is deliberately NOT z-scored against its own trailing
history of trend values (unlike volatility, below) -- a market that has
been steadily trending for a long time would self-normalize to "nothing
unusual" under that scheme, since its own recent history IS that trend,
which defeats the purpose. Instead, trend_z is a standard statistical
z-statistic against a zero-drift null: the rolling N-day cumulative
return divided by the standard deviation that pure zero-drift noise at
the recently observed volatility would produce over that same N-day
window (daily_vol * sqrt(N)). This answers "is this move large relative
to what noise alone would produce," which correctly flags a sustained,
low-noise uptrend as significant.

Five regimes: TRENDING_UP, TRENDING_DOWN, SIDEWAYS, HIGH_VOLATILITY,
LOW_VOLATILITY. Volatility extremes take priority over trend -- a market
whose volatility has genuinely spiked or collapsed is more actionably
described by that fact than by whatever modest trend happens to
accompany it.

Confidence is NOT a probability (there is no ground truth to calibrate
against). It is a single, uniformly-applied, bounded (0..1) measure of
how far the decisive feature sits from the threshold that would have
flipped the classification: tanh(margin / 2), where `margin` is the
amount a crossed threshold was exceeded by (TRENDING_*/HIGH|LOW_VOLATILITY)
or the smallest remaining gap to either threshold not being crossed
(SIDEWAYS). Confidence is exactly 0 right at a boundary (the most
genuinely uncertain point) and approaches 1 far from it.
"""

from __future__ import annotations

import enum
import math

from app.portfolio.fit_service import zscore
from app.services import analytics

TREND_WINDOW_DAYS = 60  # trading days of cumulative return used as the trend feature
VOL_WINDOW_DAYS = 20  # trading days used for the rolling annualized volatility feature
LOOKBACK_DAYS = 252  # trailing window the z-score is computed against (~1 trading year)
MIN_HISTORY_FOR_ZSCORE = 20  # below this many historical points, a z-score is too noisy to trust

# Both thresholds are exactly one standard deviation -- a round, standard,
# easily-defensible cutoff, not tuned against any labeled ground truth
# (none exists to tune against). Using the SAME magnitude for both
# features, rather than two independently-chosen numbers, is itself part
# of the defensibility: there's no hidden asymmetry to justify.
TREND_Z_THRESHOLD = 1.0
VOL_Z_THRESHOLD = 1.0


class Regime(str, enum.Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


REGIME_DISPLAY_NAME: dict[Regime, str] = {
    Regime.TRENDING_UP: "Trending Upward",
    Regime.TRENDING_DOWN: "Trending Downward",
    Regime.SIDEWAYS: "Sideways",
    Regime.HIGH_VOLATILITY: "High Volatility",
    Regime.LOW_VOLATILITY: "Low Volatility",
}


def _confidence_from_margin(margin: float) -> float:
    return float(math.tanh(max(margin, 0.0) / 2))


def classify_regime(
    bars: list,
    trend_window: int = TREND_WINDOW_DAYS,
    vol_window: int = VOL_WINDOW_DAYS,
    lookback_days: int = LOOKBACK_DAYS,
) -> dict:
    """Classifies the regime as of the LAST bar in `bars`.

    No look-ahead by construction: every feature used is computed purely
    from `bars`, which the caller must already have truncated to "as of"
    the date being classified -- this function never receives, and so
    cannot peek at, anything beyond that last bar.
    """
    if len(bars) < trend_window + MIN_HISTORY_FOR_ZSCORE:
        as_of = max(b.date for b in bars) if bars else None
        return {
            "regime": Regime.SIDEWAYS.value,
            "display_name": REGIME_DISPLAY_NAME[Regime.SIDEWAYS],
            "confidence": 0.0,
            "factors": [],
            "as_of": as_of,
            "note": "Not enough price history to classify a regime; defaulted to Sideways with zero confidence.",
        }

    df = analytics.ohlcv_to_frame(bars)
    close = df.set_index("date")["close"]
    as_of = df["date"].iloc[-1]

    trend_series = close / close.shift(trend_window) - 1  # rolling N-day cumulative return
    returns = analytics.daily_returns(close)
    daily_vol_series = returns.rolling(vol_window).std()  # NOT annualized -- used for the trend null below
    vol_series = daily_vol_series * math.sqrt(252)  # rolling annualized volatility, the Volatility factor itself

    vol_hist = vol_series.dropna().tail(lookback_days)

    trend_raw = float(trend_series.iloc[-1])
    vol_raw = float(vol_series.iloc[-1]) if not math.isnan(vol_series.iloc[-1]) else 0.0
    daily_vol_raw = float(daily_vol_series.iloc[-1]) if not math.isnan(daily_vol_series.iloc[-1]) else 0.0

    # trend_z: a z-statistic against a zero-drift null, NOT a z-score
    # against the trend's own trailing history (see module docstring for
    # why) -- "is this N-day move large relative to what zero-drift noise
    # at the recently observed daily volatility would produce over N days".
    expected_noise_std = daily_vol_raw * math.sqrt(trend_window)
    trend_z = trend_raw / expected_noise_std if expected_noise_std > 1e-12 else 0.0
    vol_z = (
        zscore(vol_raw, float(vol_hist.mean()), float(vol_hist.std()))
        if len(vol_hist) >= MIN_HISTORY_FOR_ZSCORE
        else 0.0
    )

    factors = [
        {
            "name": "Trend",
            "raw_value": round(trend_raw, 4),
            "z_score": round(trend_z, 3),
            "explanation": (
                f"{trend_window}-day cumulative return is {trend_raw * 100:+.2f}%, "
                f"{abs(trend_z):.2f} standard deviations {'above' if trend_z >= 0 else 'below'} "
                f"zero given recent volatility."
            ),
        },
        {
            "name": "Volatility",
            "raw_value": round(vol_raw, 4),
            "z_score": round(vol_z, 3),
            "explanation": (
                f"{vol_window}-day annualized volatility is {vol_raw * 100:.2f}%, "
                f"{abs(vol_z):.2f} standard deviations {'above' if vol_z >= 0 else 'below'} "
                f"its trailing {len(vol_hist)}-day average."
            ),
        },
    ]

    if abs(vol_z) >= VOL_Z_THRESHOLD:
        regime = Regime.HIGH_VOLATILITY if vol_z > 0 else Regime.LOW_VOLATILITY
        margin = abs(vol_z) - VOL_Z_THRESHOLD
    elif trend_z >= TREND_Z_THRESHOLD:
        regime = Regime.TRENDING_UP
        margin = trend_z - TREND_Z_THRESHOLD
    elif trend_z <= -TREND_Z_THRESHOLD:
        regime = Regime.TRENDING_DOWN
        margin = -trend_z - TREND_Z_THRESHOLD
    else:
        regime = Regime.SIDEWAYS
        margin = min(TREND_Z_THRESHOLD - abs(trend_z), VOL_Z_THRESHOLD - abs(vol_z))

    confidence = _confidence_from_margin(margin)

    return {
        "regime": regime.value,
        "display_name": REGIME_DISPLAY_NAME[regime],
        "confidence": round(confidence, 3),
        "factors": factors,
        "as_of": as_of,
        "note": None,
    }
