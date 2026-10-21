"""Local Parquet cache for OHLCV history.

Purpose: let LiveYFinanceProvider (and the offline test suite) work without
live network access, by reading/writing a per-symbol Parquet file under
app/data/cache/. This is a plain file cache, not a database table -- it's
meant to be populated by running scripts/fetch_nifty100.py locally on a
machine with internet access, then committed (or shared) so the rest of the
team/CI can use it offline.

Nothing in this module invents or fabricates price data: it only reads/
writes what a caller gives it, and raises rather than silently returning
partial or synthetic data when a request can't be satisfied from cache.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
MANIFEST_PATH = CACHE_DIR / "cache_manifest.json"

REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


@dataclass
class CacheEntryMeta:
    symbol: str
    rows: int
    start_date: str
    end_date: str
    fetched_at: str
    source: str  # e.g. "yfinance"
    validation_warnings: list[str]


def _sanitize_filename(symbol: str) -> str:
    # Index tickers like "^NSEI" carry a leading caret that's awkward (if
    # not outright invalid) in a filename on some filesystems -- store them
    # as "_NSEI.parquet" instead. The symbol value itself (used as the
    # manifest key, cache lookups, etc.) is untouched; only the on-disk
    # filename is sanitized.
    return symbol.upper().replace("^", "_")


def _symbol_path(symbol: str) -> Path:
    return CACHE_DIR / f"{_sanitize_filename(symbol)}.parquet"


def has_cache(symbol: str) -> bool:
    return _symbol_path(symbol).exists()


def read_cache(symbol: str) -> pd.DataFrame | None:
    """Returns the cached OHLCV DataFrame for a symbol, or None if no cache exists."""
    path = _symbol_path(symbol)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Cache file for {symbol} is missing columns: {missing}")
    return df.sort_values("date").reset_index(drop=True)


def write_cache(symbol: str, df: pd.DataFrame, source: str, validation_warnings: list[str]) -> CacheEntryMeta:
    """Writes a validated OHLCV DataFrame to the cache and updates the manifest.

    Does not validate -- call validate_ohlcv() first and decide what to do
    with its warnings/errors before writing.
    """
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Cannot cache {symbol}: DataFrame missing columns {missing}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df = df.sort_values("date").reset_index(drop=True)
    df.to_parquet(_symbol_path(symbol), index=False)

    meta = CacheEntryMeta(
        symbol=symbol.upper(),
        rows=len(df),
        start_date=str(df["date"].min()),
        end_date=str(df["date"].max()),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        validation_warnings=validation_warnings,
    )
    _update_manifest(meta)
    return meta


def _update_manifest(meta: CacheEntryMeta) -> None:
    manifest = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())
    manifest[meta.symbol] = asdict(meta)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text())


def validate_ohlcv(df: pd.DataFrame, symbol: str, max_gap_days: int = 10) -> list[str]:
    """Checks a raw OHLCV DataFrame for data-quality problems.

    Returns a list of human-readable warnings (empty list = clean). Does not
    raise -- callers decide whether warnings are acceptable for their use
    case (e.g. the fetch script surfaces them to the user instead of
    silently caching bad data).
    """
    warnings: list[str] = []
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        warnings.append(f"missing required columns: {sorted(missing)}")
        return warnings  # can't check further without the columns

    if df.empty:
        warnings.append("no rows returned")
        return warnings

    for col in ["open", "high", "low", "close"]:
        if (df[col] <= 0).any():
            warnings.append(f"{(df[col] <= 0).sum()} row(s) with non-positive {col}")

    if (df["volume"] < 0).any():
        warnings.append(f"{(df['volume'] < 0).sum()} row(s) with negative volume")

    bad_hl = df[df["high"] < df["low"]]
    if len(bad_hl):
        warnings.append(f"{len(bad_hl)} row(s) with high < low")

    dates = pd.to_datetime(df["date"]).sort_values()
    gaps = dates.diff().dt.days.dropna()
    big_gaps = gaps[gaps > max_gap_days]
    if len(big_gaps):
        warnings.append(
            f"{len(big_gaps)} gap(s) longer than {max_gap_days} calendar days "
            f"(largest: {int(big_gaps.max())} days) -- check for a trading halt, "
            "delisting, or a provider outage rather than assuming a holiday"
        )

    # Rough split/adjustment sanity check: a single-day >40% move is unusual
    # for a large-cap stock and often indicates an unadjusted split/bonus.
    daily_return = df.sort_values("date")["close"].pct_change().abs()
    extreme_moves = daily_return[daily_return > 0.40]
    if len(extreme_moves):
        warnings.append(
            f"{len(extreme_moves)} day(s) with >40% single-day move -- "
            f"verify prices are split/dividend-adjusted for {symbol}, this "
            "is a common sign they are not"
        )

    return warnings
