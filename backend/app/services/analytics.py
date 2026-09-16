"""Reusable stock analytics functions.

All functions operate on pandas Series/DataFrames so they can be shared
between the API layer and the ML feature-engineering pipeline. Nothing here
talks to the database directly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ohlcv_to_frame(bars: list) -> pd.DataFrame:
    """Convert a list of MarketData ORM rows (or OHLCVBar) into a sorted DataFrame."""
    df = pd.DataFrame(
        [
            {
                "date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )
    df = df.sort_values("date").reset_index(drop=True)
    return df


def daily_returns(close: pd.Series) -> pd.Series:
    return close.pct_change()


def cumulative_returns(close: pd.Series) -> pd.Series:
    returns = daily_returns(close).fillna(0)
    return (1 + returns).cumprod() - 1


def volatility_annualized(close: pd.Series, window: int | None = None) -> float:
    returns = daily_returns(close).dropna()
    if window:
        returns = returns.tail(window)
    return volatility_from_returns(returns)


def volatility_from_returns(returns: pd.Series, window: int | None = None) -> float:
    returns = returns.dropna()
    if window:
        returns = returns.tail(window)
    if len(returns) < 2:
        return 0.0
    return float(returns.std() * np.sqrt(252))


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=1).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series.fillna(50.0)


def momentum(close: pd.Series, window: int = 10) -> pd.Series:
    return close.diff(window)


def avg_volume(volume: pd.Series, window: int = 20) -> pd.Series:
    return volume.rolling(window=window, min_periods=1).mean()


def max_drawdown(close: pd.Series) -> float:
    cumulative = (1 + daily_returns(close).fillna(0)).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return float(drawdown.min())


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.06) -> float:
    """Annualized Sharpe ratio. risk_free_rate is an annual rate (default ~ Indian T-bill)."""
    if len(returns.dropna()) < 2:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess = returns.dropna() - daily_rf
    if excess.std() == 0:
        return 0.0
    return float((excess.mean() / excess.std()) * np.sqrt(252))


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute the full indicator set used on the stock detail page."""
    close = df["close"]
    volume = df["volume"]
    returns = daily_returns(close)
    cum_returns = cumulative_returns(close)

    return {
        "sma_20": float(sma(close, 20).iloc[-1]) if len(close) else None,
        "sma_50": float(sma(close, 50).iloc[-1]) if len(close) else None,
        "ema_20": float(ema(close, 20).iloc[-1]) if len(close) else None,
        "rsi_14": float(rsi(close, 14).iloc[-1]) if len(close) else None,
        "volatility_annualized": volatility_annualized(close, window=30),
        "momentum_10d": float(momentum(close, 10).iloc[-1]) if len(close) >= 11 else None,
        "daily_return": float(returns.iloc[-1]) if len(returns) and not pd.isna(returns.iloc[-1]) else None,
        "cumulative_return_30d": float(cum_returns.tail(30).iloc[-1] - cum_returns.tail(30).iloc[0])
        if len(cum_returns) >= 2
        else None,
        "avg_volume_20d": float(avg_volume(volume, 20).iloc[-1]) if len(volume) else None,
    }
