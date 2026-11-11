#!/usr/bin/env python3
"""Fetch and cache real fundamentals (P/E, EPS, ROE, growth, etc.) via yfinance.

Run this LOCALLY, on a machine with real internet access -- this sandbox's
egress proxy blocks query1.finance.yahoo.com (same constraint as
fetch_nifty100.py, verified).

Usage:
    cd backend
    source venv/bin/activate
    python scripts/fetch_fundamentals.py                  # full NIFTY 100 + watchlist
    python scripts/fetch_fundamentals.py --symbols TCS,INFY
    python scripts/fetch_fundamentals.py --out-fixture      # also writes a committed test fixture

What it does, honestly:
    - Pulls yfinance's Ticker.info dict for each symbol and maps it onto
      PortfolioIQ's fundamentals schema (see providers.py's
      FundamentalSnapshot). A field yfinance doesn't return for a given
      ticker is cached as null -- never guessed or interpolated.
    - `roce` has no yfinance equivalent and is always cached as null here.
    - Reports, per symbol, exactly which fields came back null, so you can
      see real coverage gaps for NSE-listed tickers (unverified from this
      sandbox -- see docs/limitations.md) rather than assuming the schema
      is fully populated.
    - Writes one JSON file per symbol to backend/app/data/fundamentals_cache/,
      plus fundamentals_manifest.json summarizing what was fetched and when.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.market_data import cache
from app.services.market_data.nifty100 import SYMBOLS
from app.services.market_data.watchlist import WATCHLIST_SYMBOLS

# yfinance Ticker.info key -> PortfolioIQ FundamentalSnapshot field
FIELD_MAP = {
    "trailingPE": "pe_ratio",
    "marketCap": "market_cap",
    "trailingEps": "eps",
    "dividendYield": "dividend_yield",
    "bookValue": "book_value",
    "revenueGrowth": "revenue_growth_yoy",
    "earningsGrowth": "profit_growth_yoy",
    "returnOnEquity": "roe",
    "debtToEquity": "debt_to_equity",
}


def fetch_one(symbol: str) -> dict:
    import yfinance as yf

    yf_symbol = f"{symbol}.NS"
    info = yf.Ticker(yf_symbol).info
    data = {field: None for field in cache.FUNDAMENTAL_FIELDS}
    for yf_key, field in FIELD_MAP.items():
        data[field] = info.get(yf_key)
    data["roce"] = None  # no yfinance equivalent -- never fabricated
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", help="Comma-separated NSE symbols (default: NIFTY 100 + watchlist union)")
    parser.add_argument(
        "--out-fixture",
        action="store_true",
        help="Also write a small committed test fixture (3 symbols) to "
        "backend/app/tests/fixtures/fundamentals_sample/ for offline/CI tests",
    )
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else sorted(set(SYMBOLS) | set(WATCHLIST_SYMBOLS))
    print(f"Fetching fundamentals for {len(symbols)} symbols from yfinance...\n")

    results = []
    for symbol in symbols:
        try:
            data = fetch_one(symbol)
        except Exception as e:  # noqa: BLE001 -- report and continue, don't abort the whole batch
            print(f"  [FAIL]  {symbol:<14} {e}")
            results.append((symbol, "FAIL"))
            continue

        cache.write_fundamentals_cache(symbol, data, source="yfinance")
        null_fields = [f for f, v in data.items() if v is None]
        status = "OK" if not null_fields else f"OK (null: {', '.join(null_fields)})"
        print(f"  [{status:>60}] {symbol}")
        results.append((symbol, status))
        time.sleep(0.3)  # be polite to the free yfinance/Yahoo endpoint

    ok = sum(1 for _, s in results if s.startswith("OK"))
    print(f"\nDone: {ok}/{len(symbols)} symbols cached. See app/data/fundamentals_cache/fundamentals_manifest.json for details.")

    if args.out_fixture:
        _write_fixture(symbols[:3] if symbols else [])


def _write_fixture(symbols: list[str]) -> None:
    fixture_dir = Path(__file__).resolve().parent.parent / "app" / "tests" / "fixtures" / "fundamentals_sample"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        data = fetch_one(symbol)
        (fixture_dir / f"{symbol}.json").write_text(json.dumps(data, indent=2, sort_keys=True))
        print(f"  fixture: wrote {fixture_dir / f'{symbol}.json'}")
    print(f"\nCommit {fixture_dir} to git -- it's real (if sparse) fundamentals data for offline tests.")


if __name__ == "__main__":
    main()
