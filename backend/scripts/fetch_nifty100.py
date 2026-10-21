#!/usr/bin/env python3
"""Fetch and cache real NIFTY 100 (+ benchmark) OHLCV history via yfinance.

Run this LOCALLY, on a machine with real internet access -- this sandbox's
egress proxy blocks query1.finance.yahoo.com, so this script cannot be run
here (verified; it will fail with a connection error if you try).

Usage:
    cd backend
    source venv/bin/activate
    python scripts/fetch_nifty100.py                  # all NIFTY 100 + benchmark, 3y history
    python scripts/fetch_nifty100.py --symbols TCS,INFY --days 365
    python scripts/fetch_nifty100.py --days 365 --out-fixture   # also writes a small
                                                                  # committed test fixture

What it does, honestly:
    - Pulls daily OHLCV from yfinance for every symbol in nifty100.SYMBOLS,
      plus the NIFTY 50 benchmark index, requesting *adjusted* prices
      (auto_adjust=True) so splits/dividends are reflected in the series.
    - Runs cache.validate_ohlcv() on each symbol and PRINTS warnings rather
      than silently caching bad data -- you decide whether to keep a symbol
      with warnings.
    - Writes one Parquet file per symbol to backend/app/data/cache/, plus
      cache_manifest.json summarizing what was fetched and when.
    - Never fabricates a row: a symbol yfinance returns nothing for is
      skipped and reported, not interpolated or filled in.

Known data-quality limits (see docs/limitations.md for the full list):
    - Survivorship bias: this only fetches symbols CURRENTLY in the
      (approximate, unverified -- see nifty100.py) NIFTY 100 list. Stocks
      that were in the index historically but have since been delisted,
      merged, or dropped are not included, which will bias any backtest
      that uses this cache toward the companies that happened to survive
      and remain large.
    - The yfinance "NSE" (.NS) listing history for some symbols may be
      shorter than the requested window (recent IPOs, ticker changes) --
      validate_ohlcv() does not treat a short series as an error by itself,
      only as fewer rows than requested; check cache_manifest.json's
      start_date per symbol before assuming full coverage.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.services.market_data import cache
from app.services.market_data.nifty100 import BENCHMARK_SYMBOL, SYMBOLS


def fetch_one(yf_symbol: str, days: int) -> pd.DataFrame:
    import yfinance as yf

    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period=f"{days}d", auto_adjust=True)
    if hist.empty:
        return pd.DataFrame(columns=cache.REQUIRED_COLUMNS)
    df = hist.reset_index()
    df = df.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    return df[cache.REQUIRED_COLUMNS]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", help="Comma-separated NSE symbols (default: full NIFTY 100 list)")
    parser.add_argument("--days", type=int, default=365 * 3, help="Calendar days of history to request (default: 3y)")
    parser.add_argument(
        "--out-fixture",
        action="store_true",
        help="Also write a small committed test fixture (3 symbols, 90 days) to "
        "backend/app/tests/fixtures/real_ohlcv_sample/ for offline/CI tests",
    )
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else list(SYMBOLS)
    targets = [(s, f"{s}.NS") for s in symbols] + [("NIFTY50", BENCHMARK_SYMBOL)]

    print(f"Fetching {len(targets)} symbols ({args.days} days each) from yfinance...\n")

    results = []
    for symbol, yf_symbol in targets:
        try:
            df = fetch_one(yf_symbol, args.days)
        except Exception as e:  # noqa: BLE001 -- report and continue, don't abort the whole batch
            print(f"  [FAIL]  {symbol:<14} {e}")
            results.append((symbol, "FAIL", str(e)))
            continue

        if df.empty:
            print(f"  [EMPTY] {symbol:<14} yfinance returned no rows -- skipped, not cached")
            results.append((symbol, "EMPTY", "no rows returned"))
            continue

        warnings = cache.validate_ohlcv(df, symbol)
        meta = cache.write_cache(symbol, df, source="yfinance", validation_warnings=warnings)
        status = "OK" if not warnings else "OK (with warnings)"
        print(f"  [{status:>18}] {symbol:<14} {meta.rows} rows, {meta.start_date} -> {meta.end_date}")
        for w in warnings:
            print(f"      warning: {w}")
        results.append((symbol, status, "; ".join(warnings)))

        time.sleep(0.3)  # be polite to the free yfinance/Yahoo endpoint

    ok = sum(1 for _, s, _ in results if s.startswith("OK"))
    print(f"\nDone: {ok}/{len(targets)} symbols cached. See app/data/cache/cache_manifest.json for details.")

    if args.out_fixture:
        _write_fixture(symbols[:3] if symbols else list(SYMBOLS)[:3])


def _write_fixture(symbols: list[str]) -> None:
    """Writes a tiny, real (not synthetic) OHLCV sample for the test suite.

    Unlike the full cache (gitignored -- it's large and regeneratable), this
    fixture is meant to be committed: a handful of symbols, ~90 days, real
    data, so tests can validate the cache/validation code against actual
    market data without needing network access in CI.
    """
    fixture_dir = Path(__file__).resolve().parent.parent / "app" / "tests" / "fixtures" / "real_ohlcv_sample"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        df = fetch_one(f"{symbol}.NS", days=90)
        if df.empty:
            print(f"  fixture: skipping {symbol}, no data")
            continue
        df.to_csv(fixture_dir / f"{symbol}.csv", index=False)
        print(f"  fixture: wrote {fixture_dir / f'{symbol}.csv'} ({len(df)} rows)")
    print(
        f"\nCommit {fixture_dir} to git -- it's real (small, ~90-day) OHLCV data, "
        "used by test_market_data_cache.py so the cache/validation logic is tested "
        "against actual market data, not just synthetic fixtures."
    )


if __name__ == "__main__":
    main()
