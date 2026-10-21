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
    """Chronological split (no shuffling) into train/val/test by row position.

    Superseded as the main training-pipeline split by
    purged_walk_forward_splits() as of Phase 6 (see docs/adr/0003-*.md) --
    kept here as a simple, still-correct utility (e.g. for quick scripts or
    comparison), not used by app.ml.train anymore.
    """
    n = len(df)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return df.iloc[:train_end], df.iloc[train_end:val_end], df.iloc[val_end:]


LABEL_HORIZON_DAYS = 1  # next-day direction; kept as a named constant so a
# future multi-day-horizon label could change one place, and so the
# embargo (which must equal the label horizon) stays obviously in sync.


def purged_walk_forward_splits(
    df: pd.DataFrame, n_splits: int = 5, embargo: int = LABEL_HORIZON_DAYS
):
    """Expanding-window walk-forward CV splits with a purge embargo.

    Standard technique for time-series ML (see e.g. Lopez de Prado,
    "Advances in Financial Machine Learning", ch. 7) to avoid label
    leakage: the label at row t depends on data up to t + label_horizon, so
    any training row whose label window overlaps the start of the test
    block must be dropped ("purged" / embargoed), or the model would be
    trained on information that was only knowable after the test period
    had already begun.

    `df` must be a single symbol's data, sorted ascending by date (do not
    pass pooled multi-symbol data in here -- call this once per symbol and
    combine same-fold-index results across symbols at the call site).

    Yields (train_df, test_df) for each of `n_splits` folds, chronologically
    increasing: fold 0 uses the earliest data, fold n_splits-1 uses the most
    recent -- so the LAST fold yielded is the one honest, most-recent-data
    held-out test, same role the old time_aware_split's "test" portion played.
    """
    n = len(df)
    block_size = n // (n_splits + 1)
    if block_size < 1:
        raise ValueError(
            f"Not enough rows ({n}) for {n_splits} walk-forward folds -- "
            "reduce n_splits or provide more history."
        )

    for fold in range(n_splits):
        train_end = block_size * (fold + 1)
        test_start = train_end
        test_end = block_size * (fold + 2) if fold < n_splits - 1 else n

        purge_start = max(0, train_end - embargo)
        train_df = df.iloc[:purge_start]
        test_df = df.iloc[test_start:test_end]
        if len(train_df) == 0 or len(test_df) == 0:
            continue
        yield train_df, test_df
