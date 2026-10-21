"""NewsService: fetches/generates headlines and links them to stocks.

Like MarketDataService, this follows a provider-abstraction pattern.
``USE_LIVE_NEWS=true`` (Phase 7) makes this cache-first against real
headlines ingested by ``scripts/fetch_news_rss.py`` (Economic Times /
Moneycontrol RSS, run locally -- this sandbox has no outbound network
access to either host). When the flag is off (default) or no real
headlines are cached for a stock, this falls back to the original
DEV_SAMPLE path: deterministic, clearly-labeled synthetic headlines, so
the news + sentiment pipeline is always demonstrable offline.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.news import News, NewsSentiment, SentimentLabel
from app.models.stock import DataSource, Stock
from app.nlp.sentiment_service import SentimentService
from app.services.news import cache as rss_cache

HEADLINE_TEMPLATES = [
    ("{name} shares surge after strong quarterly earnings beat estimates", "positive"),
    ("{name} announces robust revenue growth, analysts upgrade outlook", "positive"),
    ("{name} wins large new contract, boosting investor confidence", "positive"),
    ("Brokerages turn bullish on {name} citing strong sector tailwinds", "positive"),
    ("{name} reports record profit margins for the quarter", "positive"),
    ("{name} stock rallies on positive management guidance", "positive"),
    ("{name} maintains steady performance amid mixed market conditions", "neutral"),
    ("Analysts remain neutral on {name} ahead of upcoming earnings", "neutral"),
    ("{name} announces routine board meeting to discuss quarterly results", "neutral"),
    ("{name} trades sideways as investors await clarity on demand outlook", "neutral"),
    ("{name} shares decline after weaker-than-expected quarterly results", "negative"),
    ("{name} faces margin pressure amid rising input costs, analysts warn", "negative"),
    ("Concerns grow over {name}'s slowing growth in key markets", "negative"),
    ("{name} downgraded by brokerage citing valuation and demand risks", "negative"),
    ("{name} stock slips on broader sector volatility and weak sentiment", "negative"),
]

SOURCES = ["Economic Times", "Moneycontrol", "Business Standard", "LiveMint", "Reuters"]

# Phase 7: half-life (in days) for the exponentially time-decayed sentiment
# aggregate -- an article this many days old contributes half the weight of
# a brand-new one. 7 days is a documented, chosen default (not derived from
# data), reasoning: short enough that week-old news stops dominating the
# "current sentiment" read, long enough that a single day's headline count
# fluctuations don't whipsaw it. Revisit once real headline volume/cadence
# (Phase 7's RSS ingestion) gives a basis to tune this empirically.
SENTIMENT_HALF_LIFE_DAYS = 7.0


def _time_decayed_average(news_items: list["News"], half_life_days: float = SENTIMENT_HALF_LIFE_DAYS) -> float | None:
    """Exponentially time-weighted mean sentiment score: weight = 0.5 ** (age_days / half_life_days).

    Returns None (not 0.0) when there's nothing to average, so callers
    don't confuse "no data" with "neutral sentiment".
    """
    now = datetime.now(timezone.utc)
    weighted_sum = 0.0
    weight_total = 0.0
    for n in news_items:
        if n.sentiment is None:
            continue
        published = n.published_at if n.published_at.tzinfo else n.published_at.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - published).total_seconds() / 86400)
        weight = 0.5 ** (age_days / half_life_days)
        weighted_sum += weight * n.sentiment.sentiment_score
        weight_total += weight
    if weight_total == 0:
        return None
    return weighted_sum / weight_total


class NewsService:
    def __init__(self, db: Session):
        self.db = db
        self.sentiment_service = SentimentService()

    def generate_sample_news(self, stock: Stock, count: int = 10) -> int:
        """Deterministically generates `count` sample headlines for a stock if none exist yet."""
        existing_count = self.db.query(News).filter(News.stock_id == stock.id).count()
        if existing_count >= count:
            return 0

        seed = int(hashlib.sha256(stock.symbol.encode()).hexdigest(), 16) % (2**31)
        rng = random.Random(seed)
        templates = rng.sample(HEADLINE_TEMPLATES, k=min(count, len(HEADLINE_TEMPLATES)))

        written = 0
        now = datetime.now(timezone.utc)
        for i, (template, _bias) in enumerate(templates):
            headline = template.format(name=stock.name)
            published_at = now - timedelta(days=i, hours=rng.randint(0, 20))
            source = rng.choice(SOURCES)

            news = News(
                stock_id=stock.id,
                headline=headline,
                source=source,
                url=None,
                content_snippet=headline,
                published_at=published_at,
                data_source=DataSource.DEV_SAMPLE,
            )
            self.db.add(news)
            self.db.flush()

            label, score = self.sentiment_service.analyze(headline)
            self.db.add(
                NewsSentiment(
                    news_id=news.id,
                    stock_id=stock.id,
                    sentiment_label=SentimentLabel(label),
                    sentiment_score=score,
                    model_used=self.sentiment_service.model_name,
                )
            )
            written += 1
        self.db.commit()
        return written

    def ingest_live_news(self, stock: Stock) -> int:
        """Upserts real, RSS-ingested headlines for a stock from the local
        cache (app/services/news/cache.py) into the News/NewsSentiment
        tables, tagged DataSource.LIVE. Idempotent: re-running does not
        duplicate a headline already stored (matched by headline text +
        published_at). Does nothing if no real cache entry exists for this
        symbol -- callers decide whether to fall back to synthetic data.
        """
        cached = rss_cache.read_cache_for_symbol(stock.symbol)
        if not cached:
            return 0

        existing_keys = {
            (n.headline, n.published_at)
            for n in self.db.query(News).filter(News.stock_id == stock.id, News.data_source == DataSource.LIVE).all()
        }

        written = 0
        for item in cached:
            published_at = datetime.fromisoformat(item.published_at)
            if (item.headline, published_at) in existing_keys:
                continue

            news = News(
                stock_id=stock.id,
                headline=item.headline,
                source=item.source,
                url=item.url,
                content_snippet=item.summary or item.headline,
                published_at=published_at,
                data_source=DataSource.LIVE,
            )
            self.db.add(news)
            self.db.flush()

            label, score = self.sentiment_service.analyze(item.headline)
            self.db.add(
                NewsSentiment(
                    news_id=news.id,
                    stock_id=stock.id,
                    sentiment_label=SentimentLabel(label),
                    sentiment_score=score,
                    model_used=self.sentiment_service.model_name,
                )
            )
            written += 1
        self.db.commit()
        return written

    def get_recent_news(self, stock: Stock, limit: int = 10) -> list[News]:
        if settings.USE_LIVE_NEWS:
            self.ingest_live_news(stock)
            live = (
                self.db.query(News)
                .filter(News.stock_id == stock.id, News.data_source == DataSource.LIVE)
                .order_by(News.published_at.desc())
                .limit(limit)
                .all()
            )
            if live:
                return live
            # USE_LIVE_NEWS is on but no real headlines are cached for this
            # symbol (e.g. fetch_news_rss.py hasn't been run, or no recent
            # article matched it) -- fall back rather than show nothing.

        self.generate_sample_news(stock)
        return (
            self.db.query(News)
            .filter(News.stock_id == stock.id)
            .order_by(News.published_at.desc())
            .limit(limit)
            .all()
        )

    def get_sentiment_summary(self, stock: Stock) -> dict:
        news_items = self.get_recent_news(stock, limit=50)
        sentiments = [n.sentiment for n in news_items if n.sentiment is not None]
        if not sentiments:
            return {
                "positive_pct": 0.0,
                "neutral_pct": 0.0,
                "negative_pct": 0.0,
                "average_score": 0.0,
                "average_score_time_decayed": 0.0,
                "sentiment_half_life_days": SENTIMENT_HALF_LIFE_DAYS,
                "trend": "STABLE",
                "article_count": 0,
                "model_used": self.sentiment_service.model_name,
            }

        total = len(sentiments)
        pos = sum(1 for s in sentiments if s.sentiment_label == SentimentLabel.POSITIVE)
        neu = sum(1 for s in sentiments if s.sentiment_label == SentimentLabel.NEUTRAL)
        neg = sum(1 for s in sentiments if s.sentiment_label == SentimentLabel.NEGATIVE)
        avg_score = sum(s.sentiment_score for s in sentiments) / total
        decayed_avg = _time_decayed_average(news_items)

        ordered = sorted(news_items, key=lambda n: n.published_at)
        half = max(1, total // 2)
        older_avg = sum(n.sentiment.sentiment_score for n in ordered[:half]) / half
        recent_avg = sum(n.sentiment.sentiment_score for n in ordered[half:]) / max(1, total - half)
        if recent_avg - older_avg > 0.1:
            trend = "IMPROVING"
        elif older_avg - recent_avg > 0.1:
            trend = "DECLINING"
        else:
            trend = "STABLE"

        return {
            "positive_pct": round(100 * pos / total, 1),
            "neutral_pct": round(100 * neu / total, 1),
            "negative_pct": round(100 * neg / total, 1),
            "average_score": round(avg_score, 3),
            "average_score_time_decayed": round(decayed_avg, 3) if decayed_avg is not None else 0.0,
            "sentiment_half_life_days": SENTIMENT_HALF_LIFE_DAYS,
            "trend": trend,
            "article_count": total,
            "model_used": self.sentiment_service.model_name,
        }
