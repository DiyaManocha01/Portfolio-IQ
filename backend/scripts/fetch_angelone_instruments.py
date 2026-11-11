#!/usr/bin/env python3
"""Resolve the Phase 24 watchlist against Angel One's OFFICIAL scrip master.

Run this LOCALLY, on a machine with real internet access -- this sandbox's
egress proxy blocks every Angel One host (apiconnect.angelbroking.com,
smartapi.angelbroking.com, margincalculator.angelbroking.com; verified
during Phase 24 planning), so this script cannot be run here.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/fetch_angelone_instruments.py

What it does, honestly:
    - Downloads Angel One's full instrument/scrip master JSON (every
      instrument across every exchange/segment Angel One lists -- tens of
      thousands of rows) and filters it down to NSE cash-market ("EQ")
      entries matching WATCHLIST_SYMBOLS plus the NIFTY 50 index.
    - Never fabricates a token: a watchlist symbol the scrip master doesn't
      contain (wrong NSE ticker, delisted, renamed, etc.) is reported and
      skipped, not guessed.
    - Writes backend/app/data/angelone_instruments.json -- the file
      instrument_registry.py reads. This file is gitignored (regeneratable,
      and token IDs can change when Angel One re-issues its instrument
      list), so commit it only if your deployment needs a fixed snapshot;
      otherwise re-run this script periodically.

Source URL, honestly:
    The scrip master URL below (https://margincalculator.angelbroking.com/
    OpenAPI_File/files/OpenAPIScripMaster.json) comes from Angel One's own
    SmartAPI community forum, NOT a page in their official API reference --
    I could not find it published in official docs when researching Phase
    24. Forum threads also report this endpoint intermittently returning
    null or stalling after Angel One's nightly instrument-list rebuild; if
    it fails, wait a few minutes and retry, or check
    https://smartapi.angelone.in/docs for a current link before assuming
    this script is broken.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from app.services.market_data.watchlist import (
    BENCHMARK_INDEX_SYMBOL,
    WATCHLIST_EXCHANGE,
    WATCHLIST_SYMBOLS,
)

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "angelone_instruments.json"


def main() -> None:
    print(f"Fetching Angel One scrip master from {SCRIP_MASTER_URL} ...")
    resp = requests.get(SCRIP_MASTER_URL, timeout=60)
    resp.raise_for_status()
    full_list = resp.json()
    print(f"  downloaded {len(full_list)} total instruments across all exchanges/segments")

    wanted_trading_symbols = {f"{s}-EQ" for s in WATCHLIST_SYMBOLS}
    found_symbols: set[str] = set()
    resolved: dict[str, dict] = {}

    for entry in full_list:
        trading_symbol = entry.get("symbol", "")
        exch_seg = entry.get("exch_seg", "")
        name = trading_symbol.rsplit("-", 1)[0] if "-" in trading_symbol else trading_symbol

        if exch_seg == WATCHLIST_EXCHANGE and trading_symbol in wanted_trading_symbols:
            resolved[name] = {
                "exchange": WATCHLIST_EXCHANGE,
                "tradingsymbol": trading_symbol,
                "symboltoken": entry.get("token"),
            }
            found_symbols.add(name)
        elif exch_seg == WATCHLIST_EXCHANGE and entry.get("instrumenttype") == "AMXIDX" and name == "Nifty 50":
            resolved[BENCHMARK_INDEX_SYMBOL] = {
                "exchange": WATCHLIST_EXCHANGE,
                "tradingsymbol": trading_symbol,
                "symboltoken": entry.get("token"),
            }

    missing = [s for s in WATCHLIST_SYMBOLS if s not in found_symbols]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(resolved, indent=2, sort_keys=True))

    print(f"\nResolved {len(found_symbols)}/{len(WATCHLIST_SYMBOLS)} watchlist symbols.")
    if BENCHMARK_INDEX_SYMBOL in resolved:
        print(f"  also resolved benchmark index '{BENCHMARK_INDEX_SYMBOL}'")
    else:
        print(f"  WARNING: could not resolve benchmark index '{BENCHMARK_INDEX_SYMBOL}' -- check its exact name in the scrip master")
    if missing:
        print(f"  NOT resolved (check these symbols manually -- not written to the output file): {missing}")
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
