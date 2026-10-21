#!/usr/bin/env python3
"""Fetch and cache real financial headlines from Economic Times / Moneycontrol RSS.

Run this LOCALLY, on a machine with real internet access -- this sandbox's
egress proxy blocks these hosts too (same restriction documented for
Yahoo Finance and Hugging Face throughout this project).

Usage:
    cd backend
    source venv/bin/activate
    python scripts/fetch_news_rss.py

What it does, honestly:
    - Fetches every feed in app/services/news/rss_feeds.py via feedparser.
    - Reports (does not silently swallow) any feed that fails to fetch or
      that feedparser flags as malformed (`bozo`).
    - Matches each entry's title+summary against every seeded stock's
      distinctive name fragments (app/services/news/matching.py) --
      headlines matching zero stocks are counted and dropped (not cached),
      since NewsService only needs per-stock headlines; a headline
      matching multiple stocks is cached once per matched stock.
    - Writes app/data/news_cache/rss_headlines.json (gitignored -- large,
      regeneratable) plus a console summary of how many headlines were
      found per stock.

Known precision/recall limitations (see docs/limitations.md):
    - Category-level feeds + keyword matching will both miss relevant
      headlines (recall) and occasionally mis-attribute an unrelated
      headline that happens to contain a matched term (precision). This
      has not been measured against a labeled ground-truth set.
    - RSS feed URLs can change or be retired without notice; a feed
      returning zero entries or a fetch error is reported, not assumed to
      mean "no news today".
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser

from app.services.news import cache
from app.services.news.matching import match_symbols
from app.services.news.rss_feeds import RSS_FEEDS


def _parse_published(entry) -> str:
    for key in ("published", "updated", "pubDate"):
        value = entry.get(key)
        if value:
            try:
                return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                continue
    return datetime.now(timezone.utc).isoformat()


def main():
    all_headlines: list[cache.CachedHeadline] = []
    unmatched_count = 0

    print(f"Fetching {len(RSS_FEEDS)} RSS feeds...\n")

    for source_name, url in RSS_FEEDS:
        parsed = feedparser.parse(url)
        if parsed.bozo:
            print(f"  [WARN] {source_name}: feed reported as malformed ({parsed.bozo_exception}) -- entries parsed anyway where possible")
        if not parsed.entries:
            print(f"  [EMPTY] {source_name}: 0 entries returned -- feed URL may be stale, check docs/limitations.md")
            continue

        matched_here = 0
        for entry in parsed.entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            symbols = match_symbols(f"{title} {summary}")
            if not symbols:
                unmatched_count += 1
                continue
            published_at = _parse_published(entry)
            for symbol in symbols:
                all_headlines.append(
                    cache.CachedHeadline(
                        symbol=symbol,
                        headline=title,
                        source=source_name,
                        url=entry.get("link"),
                        published_at=published_at,
                        summary=summary[:500] if summary else None,
                    )
                )
                matched_here += 1
        print(f"  [OK] {source_name}: {len(parsed.entries)} entries, {matched_here} matched to a seeded stock")

    manifest = cache.write_cache(all_headlines)
    print(f"\nCached {manifest['total_headlines']} headlines ({unmatched_count} unmatched headlines dropped).")
    print("By symbol:")
    for symbol, count in sorted(manifest["by_symbol"].items(), key=lambda x: -x[1]):
        print(f"  {symbol}: {count}")
    print(f"\nWrote {cache.CACHE_PATH}")
    print("Set USE_LIVE_NEWS=true in backend/.env to make NewsService prefer this cache over synthetic headlines.")


if __name__ == "__main__":
    main()
