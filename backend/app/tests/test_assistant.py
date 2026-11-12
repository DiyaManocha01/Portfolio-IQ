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
from app.assistant.whatif_parser import parse_whatif_question
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


# ---------- context_builder: Phase 32 additions ----------

def test_fit_keyword_triggers_fit_engine(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(db_session, portfolio, f"What's the fit score for {held_symbol}?")
    assert any(s.startswith("fit_engine:") for s in result["sources_used"])
    assert held_symbol in result["context"]["fit_engine"]
    assert "fit_score" in result["context"]["fit_engine"][held_symbol]


def test_fit_keyword_without_a_symbol_does_not_trigger(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "Would a good fit score matter here?")
    assert "fit_engine" not in result["context"]


def test_market_keyword_triggers_market_conditions(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "What are the overall market conditions right now?")
    assert "market_conditions" in result["sources_used"]
    assert "NIFTY50" in result["context"]["market_conditions"]
    assert "regime" in result["context"]["market_conditions"]["NIFTY50"]


def test_market_keyword_with_symbol_includes_both(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(db_session, portfolio, f"Is {held_symbol} trending with the broader market?")
    regimes = result["context"]["market_conditions"]
    assert "NIFTY50" in regimes
    assert held_symbol in regimes


def test_performance_keyword_triggers_historical_performance(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "How has my portfolio's performance and returns been?")
    assert "historical_performance" in result["sources_used"]
    perf = result["context"]["historical_performance"]
    assert "unrealized_pnl" in perf
    assert "realized_pnl" in perf
    assert "total_pnl" in perf


def test_irrelevant_question_does_not_trigger_new_blocks(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "hello")
    assert "fit_engine" not in result["context"]
    assert "market_conditions" not in result["context"]
    assert "historical_performance" not in result["context"]
    assert "what_if_simulation" not in result["context"]


def test_context_always_carries_a_compiled_at_timestamp(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "hello")
    assert "context_compiled_at" in result["context"]


def test_stock_details_includes_technical_indicators(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(db_session, portfolio, f"What's the outlook for {held_symbol}?")
    detail = result["context"]["stock_details"][held_symbol]
    assert "technical_indicators" in detail


def test_whatif_keyword_with_parseable_question_runs_simulation(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(
        db_session, portfolio, f"What if I bought 5 shares of {held_symbol}?"
    )
    assert any(s.startswith("what_if_simulation:") for s in result["sources_used"])
    sim = result["context"]["what_if_simulation"]
    assert "before" in sim
    assert "after" in sim
    assert "interpreted_as" in sim


def test_whatif_keyword_with_unparseable_question_reports_could_not_parse(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    result = build_context(
        db_session, portfolio, f"What if I added {held_symbol} at 10% weight?"
    )
    sim = result["context"]["what_if_simulation"]
    assert sim["could_not_parse"] is True
    assert "note" in sim


def test_whatif_keyword_with_no_symbol_reports_could_not_parse(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = build_context(db_session, portfolio, "What if the market crashed?")
    sim = result["context"]["what_if_simulation"]
    assert sim["could_not_parse"] is True


# ---------- whatif_parser: deterministic regex parsing ----------

def test_parser_handles_explicit_add_quantity():
    parsed = parse_whatif_question(
        "What if I added 10 shares of RELIANCE?", ["RELIANCE"], {"RELIANCE": 5.0}
    )
    assert parsed == {
        "symbol": "RELIANCE",
        "new_quantity": 15.0,
        "note": "Interpreted as adding 10.0 shares of RELIANCE to the current 5.0.",
    }


def test_parser_handles_explicit_sell_quantity():
    parsed = parse_whatif_question(
        "What if I sold 3 shares of TCS?", ["TCS"], {"TCS": 10.0}
    )
    assert parsed["new_quantity"] == 7.0


def test_parser_floors_sell_at_zero():
    parsed = parse_whatif_question(
        "What if I sold 50 shares of TCS?", ["TCS"], {"TCS": 10.0}
    )
    assert parsed["new_quantity"] == 0.0


def test_parser_handles_full_exit_phrasing():
    parsed = parse_whatif_question(
        "What if I sold all my TCS?", ["TCS"], {"TCS": 10.0}
    )
    assert parsed["new_quantity"] == 0.0


def test_parser_handles_new_buy_with_no_current_holding():
    parsed = parse_whatif_question(
        "What if I bought 20 shares of INFY?", ["INFY"], {}
    )
    assert parsed["new_quantity"] == 20.0


@pytest.mark.parametrize(
    "question,symbols,quantities",
    [
        ("What if I added RELIANCE at 10% weight?", ["RELIANCE"], {}),  # weight-based, out of scope
        ("What if the market crashed 10%?", [], {}),  # no symbol
        ("What if I added RELIANCE and sold TCS?", ["RELIANCE", "TCS"], {}),  # multi-symbol
        ("What if RELIANCE happens?", ["RELIANCE"], {}),  # no add/remove verb
        ("What if I added and sold RELIANCE?", ["RELIANCE"], {}),  # ambiguous verbs
    ],
)
def test_parser_refuses_rather_than_guesses(question, symbols, quantities):
    assert parse_whatif_question(question, symbols, quantities) is None
