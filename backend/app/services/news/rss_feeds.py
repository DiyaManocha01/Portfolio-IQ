"""RSS feed sources for real financial headline ingestion (Phase 7).

HONESTY NOTE (read before relying on this list):

These are public RSS feed URLs published by Economic Times and
Moneycontrol, compiled from general knowledge -- NOT verified live from
this sandbox, which cannot reach either host (same network restriction as
Yahoo Finance and Hugging Face, documented throughout this project). A
feed URL can change or be retired without notice; `scripts/fetch_news_rss.py`
(run locally, where real network access exists) will report any feed that
fails to fetch or parse rather than silently skipping it.

Chosen over a general-purpose news API (e.g. NewsAPI.org) per the project
owner's explicit decision: free, no API key, and genuinely India/NSE-focused
coverage, at the cost of being category-level feeds (not per-symbol) that
need headline-to-stock matching -- see matching.py.
"""

from __future__ import annotations

RSS_FEEDS: list[tuple[str, str]] = [
    # (source_name, feed_url)
    ("Economic Times - Markets", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Economic Times - Stocks", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/1977021501.cms"),
    ("Moneycontrol - Business", "https://www.moneycontrol.com/rss/business.xml"),
    ("Moneycontrol - Top News", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
]
