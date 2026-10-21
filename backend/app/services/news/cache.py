"""Local JSON cache for real (RSS-ingested) headlines, matched to stocks.

Same role as app/services/market_data/cache.py for price data: a plain
file cache populated by scripts/fetch_news_rss.py (run locally, where real
network access exists), read cache-first by NewsService so the app can
demo/test against real headlines without needing live network access at
request time.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "news_cache"
CACHE_PATH = CACHE_DIR / "rss_headlines.json"


@dataclass
class CachedHeadline:
    symbol: str
    headline: str
    source: str
    url: str | None
    published_at: str  # ISO 8601
    summary: str | None = None


def read_cache() -> list[CachedHeadline]:
    if not CACHE_PATH.exists():
        return []
    raw = json.loads(CACHE_PATH.read_text())
    return [CachedHeadline(**item) for item in raw]


def read_cache_for_symbol(symbol: str) -> list[CachedHeadline]:
    return [h for h in read_cache() if h.symbol == symbol.upper()]


def write_cache(headlines: list[CachedHeadline]) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps([asdict(h) for h in headlines], indent=2, default=str))
    by_symbol: dict[str, int] = {}
    for h in headlines:
        by_symbol[h.symbol] = by_symbol.get(h.symbol, 0) + 1
    return {
        "total_headlines": len(headlines),
        "by_symbol": by_symbol,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def has_cache() -> bool:
    return CACHE_PATH.exists()
