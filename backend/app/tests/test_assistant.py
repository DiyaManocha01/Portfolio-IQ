"""Tests for Phase 19: the AI portfolio assistant.

Everything deterministic is tested here -- the data router, the
guardrail filter, and the 503-when-unconfigured path. The actual live
Claude API call (app.assistant.assistant_service.ask's anthropic SDK
call) can only be exercised with a real ANTHROPIC_API_KEY set locally;
it is NOT tested here, consistent with how this project handles its
other network-dependent pieces (Phase 4/7's fetch scripts) -- see
docs/limitations.md."""

from __future__ import annotations

import pytest

from app.assistant.assistant_service import (
    STANDARD_DISCLAIMER,
    AssistantNotConfiguredError,
    ask,
    contains_advice_language,
)
from app.assistant.context_builder import build_context
from app.models.portfolio import Portfolio


# ---------- context_builder: deterministic data routing ----------

def test_core_bundle_always_included(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "hello")
    assert "portfolio_summary" in result["sources_used"]
    assert "portfolio_health" in result["sources_used"]
    assert "portfolio_weaknesses" in result["sources_used"]
    # Nothing else should be pulled in for an irrelevant question.
    assert "portfolio_risk" not in result["sources_used"]
    assert "stock_details" not in "".join(result["sources_used"])


def test_risk_keyword_triggers_risk_data(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "How risky and volatile is my portfolio?")
    assert "portfolio_risk" in result["sources_used"]
    assert "risk_attribution" in result["sources_used"]
    assert "portfolio_risk" in result["context"]
    assert "risk_attribution" in result["context"]


def test_symbol_mention_triggers_stock_details(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(db_session, portfolio, f"What's the outlook for {held_symbol}?")
    assert any(s.startswith("stock_details:") for s in result["sources_used"])
    assert held_symbol in result["context"]["stock_details"]


def test_track_record_keyword_triggers_ledger_stats(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "What is the model's track record and accuracy?")
    assert "model_track_record" in result["sources_used"]
    assert "model_track_record" in result["context"]


def test_discover_keyword_triggers_candidates(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "Is there a new stock candidate that would fit my portfolio?")
    assert "discover_candidates" in result["sources_used"]


def test_context_is_json_serializable(db_session):
    import json

    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(
        db_session, portfolio, f"How risky is my portfolio, what about {held_symbol}, and track record?"
    )
    # Must not raise -- every value in context must be JSON-safe (no raw
    # DataFrames, no un-stripped internal service keys).
    serialized = json.dumps(result["context"], default=str)
    assert len(serialized) > 0
    for key in result["context"]:
        assert not key.startswith("_")


def test_internal_service_keys_are_stripped(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "How risky is my portfolio?")
    risk_block = result["context"]["portfolio_risk"]
    assert all(not k.startswith("_") for k in risk_block)


# ---------- guardrail: deterministic keyword filter ----------

@pytest.mark.parametrize(
    "text,should_trip",
    [
        ("Your portfolio's annualized volatility is 19.75%.", False),
        ("The model estimates a 62% probability of a positive move, low confidence.", False),
        ("Based on the data, ICICIBANK contributes 19.87% of portfolio risk.", False),
        ("You should buy more TCS right now.", True),
        ("I recommend selling your ICICIBANK position.", True),
        ("This stock is going to rise sharply next week.", True),
        ("Strong buy on INFY.", True),
        ("You must sell before it crashes.", True),
        ("I recommend holding your current position.", True),
    ],
)
def test_guardrail_detection(text, should_trip):
    tripped, matched = contains_advice_language(text)
    assert tripped == should_trip
    if should_trip:
        assert matched is not None
    else:
        assert matched is None


def test_guardrail_is_case_insensitive():
    tripped, _ = contains_advice_language("YOU SHOULD BUY this immediately")
    assert tripped is True


# ---------- not-configured path ----------

def test_ask_raises_when_not_configured(db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    portfolio = db_session.query(Portfolio).first()
    with pytest.raises(AssistantNotConfiguredError):
        ask(db_session, portfolio, "How risky is my portfolio?")


def test_disclaimer_is_the_standard_project_disclaimer():
    assert "not guaranteed financial advice" in STANDARD_DISCLAIMER


# ---------- HTTP endpoint integration ----------

def test_assistant_endpoint_requires_auth(client):
    resp = client.post("/assistant/ask", json={"question": "How risky is my portfolio?"})
    assert resp.status_code == 401


def test_assistant_endpoint_returns_503_when_unconfigured(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    resp = client.post("/assistant/ask", json={"question": "How risky is my portfolio?"}, headers=auth_headers)
    assert resp.status_code == 503


def test_assistant_endpoint_rejects_empty_question(client, auth_headers):
    resp = client.post("/assistant/ask", json={"question": ""}, headers=auth_headers)
    assert resp.status_code == 422
