"""Headline-to-stock matching for category-level RSS feeds (Phase 7).

The RSS feeds in rss_feeds.py are category feeds (e.g. "Markets", "Business"),
not per-symbol -- a headline has to be matched to zero, one, or more of our
seeded stocks by looking for a distinctive company-name fragment in its
text. This is a precision/recall tradeoff, not a solved problem:

- Deliberately matches on company NAME fragments, not bare ticker symbols,
  for ambiguous short tickers (e.g. "LT" for Larsen & Toubro is excluded --
  matching on it would false-positive on "Lt." as an abbreviation, "LT" as
  a unit, etc. -- only "Larsen" is matched).
- Still has known false-positive/negative risk even on full names (e.g. a
  headline about "ITC" the company vs. an unrelated "ITC" acronym
  elsewhere) -- NOT validated against a labeled ground-truth set here; see
  docs/limitations.md.
"""

from __future__ import annotations

import re

from app.services.market_data.providers import STOCK_NAMES

# symbol -> list of distinctive text fragments that, if found (case-insensitive,
# word-boundary aware), count as a match. Deliberately excludes bare short/
# ambiguous tickers (see module docstring).
MATCH_TERMS: dict[str, list[str]] = {
    "TCS": ["Tata Consultancy", "TCS"],
    "RELIANCE": ["Reliance Industries"],
    "HDFCBANK": ["HDFC Bank"],
    "INFY": ["Infosys"],
    "ICICIBANK": ["ICICI Bank"],
    "LT": ["Larsen & Toubro", "Larsen and Toubro"],  # bare "LT" deliberately excluded
    "ITC": ["ITC Limited", "ITC Ltd"],  # bare "ITC" deliberately excluded (acronym collision risk)
    "HINDUNILVR": ["Hindustan Unilever", "HUL"],
    "BHARTIARTL": ["Bharti Airtel"],
    "SBIN": ["State Bank of India", "SBI"],
    "WIPRO": ["Wipro"],
    "MARUTI": ["Maruti Suzuki", "Maruti"],
    "SUNPHARMA": ["Sun Pharmaceutical", "Sun Pharma"],
}

assert set(MATCH_TERMS.keys()) == set(STOCK_NAMES.keys()), "MATCH_TERMS must cover every seeded symbol"


def match_symbols(text: str) -> list[str]:
    """Returns every seeded stock symbol whose match terms appear in `text`."""
    matched = []
    for symbol, terms in MATCH_TERMS.items():
        for term in terms:
            if re.search(r"\b" + re.escape(term) + r"\b", text, flags=re.IGNORECASE):
                matched.append(symbol)
                break
    return matched
