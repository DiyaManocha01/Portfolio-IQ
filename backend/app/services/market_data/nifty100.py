"""NIFTY 100 constituent universe.

HONESTY NOTE (read before using this list for anything published):

This list was compiled from general knowledge of large, liquid NSE-listed
companies. It was NOT fetched from NSE's official index methodology page or
any live data source -- this sandbox has no outbound network access to
nseindia.com or any index-data vendor (verified earlier in this project).

Consequences:
  - NIFTY 100 constituents are reviewed and rebalanced by NSE Indices twice
    a year (semi-annually), based on free-float market capitalization. This
    list reflects a point-in-time approximation, not a verified, dated
    snapshot of the official index.
  - Using this list "as of today" for a backtest or research paper claim
    would be an unverified assumption. Before Phase 13 (backtesting) or any
    paper/IP write-up, re-verify this list against NSE's official published
    constituent list (https://www.niftyindices.com) and replace it with a
    dated, sourced snapshot. Track that change via a new ADR if you do.

Until then, treat SYMBOLS below as "a representative large-cap NSE
universe for development and testing", not as an authoritative NIFTY 100
snapshot.

Each symbol is the NSE ticker (without the ".NS" suffix yfinance expects);
MarketDataService appends the exchange suffix itself.
"""

from __future__ import annotations

# NOTE: approximate, unverified against a live/official source -- see module
# docstring. ~100 large, liquid NSE names across sectors, compiled from
# general knowledge, not a dated index snapshot.
SYMBOLS: list[str] = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL",
    "HINDUNILVR", "ITC", "SBIN", "LT", "BAJFINANCE", "HCLTECH",
    "KOTAKBANK", "AXISBANK", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO",
    "ASIANPAINT", "WIPRO", "NESTLEIND", "ADANIENT", "ADANIPORTS", "NTPC",
    "POWERGRID", "BAJAJFINSV", "M&M", "TATAMOTORS", "TATASTEEL", "JSWSTEEL",
    "COALINDIA", "HINDALCO", "TECHM", "INDUSINDBK", "GRASIM", "BRITANNIA",
    "DRREDDY", "CIPLA", "EICHERMOT", "APOLLOHOSP", "DIVISLAB", "HEROMOTOCO",
    "BPCL", "ONGC", "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "TATACONSUM",
    "UPL", "SHREECEM", "VEDANTA", "GAIL", "PIDILITIND", "DABUR", "GODREJCP",
    "MARICO", "SIEMENS", "HAVELLS", "DLF", "AMBUJACEM", "ACC", "BANKBARODA",
    "PNB", "CANBK", "IDFCFIRSTB", "AUBANK", "BANDHANBNK", "CHOLAFIN",
    "MUTHOOTFIN", "LICHSGFIN", "PFC", "RECLTD", "IRCTC", "INDIGO", "ZOMATO",
    "NYKAA", "PAYTM", "POLICYBZR", "TRENT", "NAUKRI", "DMART", "PIIND",
    "SRF", "AARTIIND", "BERGEPAINT", "COLPAL", "MCDOWELL-N", "BOSCHLTD",
    "MOTHERSON", "BHARATFORG", "TVSMOTOR", "ASHOKLEY", "ABB", "CUMMINSIND",
    "LTIM", "MPHASIS", "PERSISTENT", "COFORGE", "OFSS", "IOC", "HINDPETRO",
    "TORNTPHARM", "LUPIN", "ALKEM", "BIOCON",
]

# Lower-liquidity / Phase-4-development subset: the 6 "discover-only"
# symbols already seeded by app/data/seed.py (see providers.py BASE_PRICES)
# plus the 7 symbols the demo portfolio holds. Keeping these distinct from
# the NIFTY 100 universe above makes it explicit which symbols have
# hand-tuned synthetic data and which are meant to get *real* cached data
# once fetch_nifty100.py has been run locally.
DEMO_SEEDED_SYMBOLS: list[str] = [
    "TCS", "RELIANCE", "HDFCBANK", "INFY", "ICICIBANK", "LT", "ITC",
    "HINDUNILVR", "BHARTIARTL", "SBIN", "WIPRO", "MARUTI", "SUNPHARMA",
]

BENCHMARK_SYMBOL = "^NSEI"  # NIFTY 50 index, for beta calculations (Phase 5)
