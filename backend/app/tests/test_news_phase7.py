"""Tests for Phase 7: headline-to-stock matching, time-decay sentiment
aggregation, and real-headline ingestion (via the local news cache)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.news import News, NewsSentiment, SentimentLabel
from app.models.stock import DataSource
from app.services.news import cache as rss_cache
from app.services.news.cache import CachedHeadline
from app.services.news.matching import match_symbols
from app.services.news_service import (
    SENTIMENT_HALF_LIFE_DAYS,
    NewsService,
    _headline_words,
    _is_near_duplicate,
    _time_decayed_average,
)
from app.services.market_data.service import MarketDataService


# ---------- matching ----------

def test_match_symbols_finds_company_name():
    assert "TCS" in match_symbols("Tata Consultancy Services shares rise 3% on strong Q2 results")


def test_match_symbols_excludes_bare_ambiguous_ticker():
    # "LT" alone must NOT match -- see matching.py docstring on why
    assert "LT" not in match_symbols("The company reported a loss, down 5% LT basis")


def test_match_symbols_matches_full_name_for_lt():
    assert "LT" in match_symbols("Larsen & Toubro wins large infrastructure order")


def test_match_symbols_can_return_multiple_stocks():
    text = "Reliance Industries and Infosys both featured in today's top gainers"
    result = match_symbols(text)
    assert "RELIANCE" in result
    assert "INFY" in result


def test_match_symbols_returns_empty_for_unrelated_text():
    assert match_symbols("Local weather forecast predicts heavy rainfall this weekend") == []


# ---------- time-decayed sentiment aggregation ----------

def _news_with_sentiment(score: float, age_days: float) -> News:
    n = News(
        id=None,
        stock_id=1,
        headline="test",
        source="test",
        published_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )
    n.sentiment = NewsSentiment(sentiment_label=SentimentLabel.POSITIVE, sentiment_score=score, model_used="test")
    return n


def test_time_decayed_average_weighs_recent_more_than_old():
    # recent strongly positive, old strongly negative -> decayed average should lean positive
    items = [_news_with_sentiment(0.9, age_days=0), _news_with_sentiment(-0.9, age_days=30)]
    result = _time_decayed_average(items, half_life_days=7.0)
    assert result > 0


def test_time_decayed_average_equals_simple_average_at_zero_age():
    items = [_news_with_sentiment(0.5, age_days=0), _news_with_sentiment(-0.3, age_days=0)]
    result = _time_decayed_average(items)
    assert result == pytest.approx((0.5 - 0.3) / 2, abs=1e-6)


def test_time_decayed_average_at_exactly_one_half_life():
    # one article at age = half_life should have exactly half the weight of a brand-new one
    items = [_news_with_sentiment(1.0, age_days=0), _news_with_sentiment(0.0, age_days=SENTIMENT_HALF_LIFE_DAYS)]
    result = _time_decayed_average(items)
    # weight(new)=1, weight(old)=0.5 -> (1*1.0 + 0.5*0.0) / 1.5 = 0.6667
    assert result == pytest.approx(2 / 3, abs=1e-3)


def test_time_decayed_average_none_when_no_sentiment():
    items = [News(id=None, stock_id=1, headline="x", source="x", published_at=datetime.now(timezone.utc))]
    assert _time_decayed_average(items) is None


def test_time_decayed_average_empty_list():
    assert _time_decayed_average([]) is None


# ---------- real-data upgrade Phase H: cross-source near-duplicate detection ----------


def test_headline_words_normalizes_case_and_punctuation():
    assert _headline_words("TCS Shares Surge 5%!") == _headline_words("tcs shares surge 5")


def test_is_near_duplicate_true_for_reworded_same_story():
    now = datetime.now(timezone.utc)
    words = _headline_words("TCS shares surge after strong quarterly earnings beat estimates")
    candidates = [(now, _headline_words("TCS shares jump after strong quarterly earnings beat estimates"))]
    assert _is_near_duplicate(now, words, candidates) is True


def test_is_near_duplicate_false_for_unrelated_headline():
    now = datetime.now(timezone.utc)
    words = _headline_words("TCS shares surge after strong quarterly earnings beat estimates")
    candidates = [(now, _headline_words("Local weather forecast predicts heavy rainfall this weekend"))]
    assert _is_near_duplicate(now, words, candidates) is False


def test_is_near_duplicate_false_outside_time_window():
    base = datetime.now(timezone.utc)
    words = _headline_words("TCS shares surge after strong quarterly earnings beat estimates")
    far_away = base - timedelta(hours=72)  # beyond the default 48h window
    candidates = [(far_away, _headline_words("TCS shares surge after strong quarterly earnings beat estimates"))]
    assert _is_near_duplicate(base, words, candidates) is False


def test_is_near_duplicate_false_for_empty_words():
    assert _is_near_duplicate(datetime.now(timezone.utc), set(), [(datetime.now(timezone.utc), {"a", "b"})]) is False


def _headline(symbol: str, headline: str, source: str, hours_ago: float, summary: str | None = None) -> CachedHeadline:
    published = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return CachedHeadline(symbol=symbol, headline=headline, source=source, url=None, published_at=published.isoformat(), summary=summary)


def _reset_live_news(db_session, stock_id: int) -> None:
    """db_session (conftest.py) is a real session against the persistent
    dev DB with no transaction rollback between tests, so a test asserting
    an exact `written`/stored count must not depend on whatever LIVE rows
    a *previous* run of this same test already committed. Clears the
    slate so these tests are idempotent across repeated runs."""
    db_session.query(News).filter(News.stock_id == stock_id, News.data_source == DataSource.LIVE).delete()
    db_session.commit()


def test_ingest_live_news_skips_cross_source_near_duplicate(db_session, monkeypatch):
    stock = MarketDataService(db_session).get_or_create_stock("TCS")
    _reset_live_news(db_session, stock.id)
    cached = [
        _headline("TCS", "TCS shares surge after strong quarterly earnings beat estimates", "Economic Times", hours_ago=2),
        _headline("TCS", "TCS shares jump after strong quarterly earnings beat estimates", "Moneycontrol", hours_ago=1.5),
    ]
    monkeypatch.setattr(rss_cache, "read_cache_for_symbol", lambda symbol: cached)

    written = NewsService(db_session).ingest_live_news(stock)
    assert written == 1  # the second, near-identical headline was skipped as a duplicate

    stored = db_session.query(News).filter(News.stock_id == stock.id, News.data_source == DataSource.LIVE).all()
    assert len(stored) == 1


def test_ingest_live_news_keeps_genuinely_different_headlines(db_session, monkeypatch):
    stock = MarketDataService(db_session).get_or_create_stock("INFY")
    _reset_live_news(db_session, stock.id)
    cached = [
        _headline("INFY", "Infosys wins large new contract, boosting investor confidence", "Economic Times", hours_ago=2),
        _headline("INFY", "Infosys downgraded by brokerage citing valuation and demand risks", "Moneycontrol", hours_ago=1),
    ]
    monkeypatch.setattr(rss_cache, "read_cache_for_symbol", lambda symbol: cached)

    written = NewsService(db_session).ingest_live_news(stock)
    assert written == 2  # genuinely different stories, both kept


def test_ingest_live_news_does_not_reduplicate_against_already_stored_live_news(db_session, monkeypatch):
    stock = MarketDataService(db_session).get_or_create_stock("WIPRO")
    _reset_live_news(db_session, stock.id)
    first_batch = [
        _headline("WIPRO", "Wipro shares surge after strong quarterly earnings beat estimates", "Economic Times", hours_ago=2),
    ]
    monkeypatch.setattr(rss_cache, "read_cache_for_symbol", lambda symbol: first_batch)
    assert NewsService(db_session).ingest_live_news(stock) == 1

    second_batch = [
        _headline("WIPRO", "Wipro shares jump after strong quarterly earnings beat estimates", "Moneycontrol", hours_ago=1),
    ]
    monkeypatch.setattr(rss_cache, "read_cache_for_symbol", lambda symbol: second_batch)
    assert NewsService(db_session).ingest_live_news(stock) == 0  # near-duplicate of the already-stored article
