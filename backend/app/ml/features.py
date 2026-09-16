"""Feature engineering for the stock direction classifier.

Every feature at row t is computed using only data available up to and
including day t (rolling windows, lagged returns). The label at row t is
whether close[t+1] > close[t] -- i.e. it looks one day into the future,
which is standard for supervised next-day-direction classification and is
NOT look-ahead bias in the features themselves.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services import analytics

FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "sma5_ratio",
    "sma20_ratio",
    "ema20_ratio",
    "rsi_14",
    "volatility_10d",
    "momentum_10d",
    "volume_ratio",
]


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """df must have columns: date, open, high, low, close, volume (sorted ascending)."""
    out = df.copy()
    close = out["close"]
    volume = out["volume"]

    out["return_1d"] = analytics.daily_returns(close)
    out["return_5d"] = close.pct_change(5)
    sma5 = analytics.sma(close, 5)
    sma20 = analytics.sma(close, 20)
    ema20 = analytics.ema(close, 20)
    out["sma5_ratio"] = close / sma5 - 1
    out["sma20_ratio"] = close / sma20 - 1
    out["ema20_ratio"] = close / ema20 - 1
    out["rsi_14"] = analytics.rsi(close, 14)
    out["volatility_10d"] = close.pct_change().rolling(10, min_periods=2).std()
    out["momentum_10d"] = analytics.momentum(close, 10)
    avg_vol20 = analytics.avg_volume(volume, 20)
    out["volume_ratio"] = volume / avg_vol20.replace(0, np.nan)

    # label: next-day direction (1 = up, 0 = down/flat)
    out["label"] = (close.shift(-1) > close).astype(float)

    return out


def time_aware_split(df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15):
    """Chronological split (no shuffling) into train/val/test by row position."""
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return df.iloc[:train_end], df.iloc[train_end:val_end], df.iloc[val_end:]
