"""Phase 24 real-time watchlist: the initial 20-symbol NSE universe.

This list is the project owner's explicit choice for the real-time feed
(a deliberately small, liquid set -- not the full, unverified NIFTY 100
approximation in ``nifty100.py``, which was compiled from general knowledge
and is a separate, pre-existing concern -- see that module's docstring).

7 of these 20 (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, BHARTIARTL,
ITC, LT -- actually 9; see nifty100.DEMO_SEEDED_SYMBOLS) already have
hand-tuned DevSampleProvider synthetic data. The remaining symbols below
currently fall back to DevSampleProvider's generic base price -- that's a
pre-existing Phase 4/5 gap, not something Phase 24 fixes (Phase 24 is about
the real-time broker feed, not DevSampleProvider's synthetic calibration).
"""

from __future__ import annotations

WATCHLIST_SYMBOLS: list[str] = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "BHARTIARTL",
    "ITC",
    "LT",
    "AXISBANK",
    "KOTAKBANK",
    "HINDUNILVR",
    "MARUTI",
    "TATAMOTORS",
    "SUNPHARMA",
    "TITAN",
    "WIPRO",
    "BAJFINANCE",
    "ADANIPORTS",
    "ASIANPAINT",
]

# NSE exchange segment code Angel One's instrument/scrip master uses for
# cash-market equities; see docs/adr/0008-realtime-market-data-angelone.md.
WATCHLIST_EXCHANGE = "NSE"

# NIFTY 50 index, included for a market-summary tile (Phase 25), resolved
# against the scrip master the same way as any other instrument -- never a
# hardcoded token.
BENCHMARK_INDEX_SYMBOL = "NIFTY 50"
