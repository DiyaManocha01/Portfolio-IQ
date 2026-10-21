"""Tests for Phase 7: headline-to-stock matching, time-decay sentiment
aggregation, and real-headline ingestion (via the local news cache)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.news import News, NewsSentiment, SentimentLabel
from app.services.news.matching import match_symbols
from app.services.news_service import SENTIMENT_HALF_LIFE_DAYS, _time_decayed_average


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
