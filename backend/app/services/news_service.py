"""NewsService: fetches/generates headlines and links them to stocks.

Like MarketDataService, this follows a provider-abstraction pattern:
``USE_LIVE_NEWS=true`` would route through a real news API (not implemented
here, since this environment has no outbound network access to news
vendors), while the default DEV_SAMPLE path generates clearly-labeled,
realistic-looking sample headlines so the news + sentiment pipeline is
fully demonstrable offline.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.news import News, NewsSentiment, SentimentLabel
from app.models.stock import DataSource, Stock
from app.nlp.sentiment_service import SentimentService

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

    def get_recent_news(self, stock: Stock, limit: int = 10) -> list[News]:
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
                "trend": "STABLE",
                "article_count": 0,
                "model_used": self.sentiment_service.model_name,
            }

        total = len(sentiments)
        pos = sum(1 for s in sentiments if s.sentiment_label == SentimentLabel.POSITIVE)
        neu = sum(1 for s in sentiments if s.sentiment_label == SentimentLabel.NEUTRAL)
        neg = sum(1 for s in sentiments if s.sentiment_label == SentimentLabel.NEGATIVE)
        avg_score = sum(s.sentiment_score for s in sentiments) / total

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
            "trend": trend,
            "article_count": total,
            "model_used": self.sentiment_service.model_name,
        }
