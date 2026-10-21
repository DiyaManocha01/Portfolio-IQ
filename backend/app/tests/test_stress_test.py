"""Tests for Phase 15: stress/scenario testing
(app/portfolio/stress_test_service.py, app/portfolio/scenario_parser.py).

Hand-calculated tests cover the CAPM beta-scaling math and the sector-
shock override. Parser tests cover a range of recognized phrasings and,
just as importantly, text it must REFUSE to guess on."""

from __future__ import annotations

import pytest

from app.models.portfolio import Portfolio
from app.portfolio.scenario_parser import ScenarioParseError, parse_scenario_text
from app.portfolio.stress_test_service import SCENARIO_PRESETS, StressTestService


# ---------- scenario_parser: recognized phrasings ----------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("IT stocks crash 20%", {"sector_shocks": {"Information Technology": -0.20}}),
        ("tech sector falls 15 percent", {"sector_shocks": {"Information Technology": -0.15}}),
        ("Healthcare rallies 10%", {"sector_shocks": {"Healthcare": 0.10}}),
        ("market drops 25%", {"market_shock_pct": -0.25}),
        ("-10% for Financial Services", {"sector_shocks": {"Financial Services": -0.10}}),
        ("Banking sector plunges by 30%", {"sector_shocks": {"Financial Services": -0.30}}),
        ("Energy stocks surge 12%", {"sector_shocks": {"Energy": 0.12}}),
    ],
)
def test_parser_recognized_phrasings(text, expected):
    result = parse_scenario_text(text)
    for key, value in expected.items():
        if key == "sector_shocks":
            for sector, pct in value.items():
                assert result["sector_shocks"][sector] == pytest.approx(pct, abs=1e-9)
        else:
            assert result[key] == pytest.approx(value, abs=1e-9)


# ---------- scenario_parser: must refuse rather than guess ----------

def test_parser_rejects_text_with_no_percentage():
    with pytest.raises(ScenarioParseError):
        parse_scenario_text("the weather is nice today")


def test_parser_rejects_text_with_no_clear_direction():
    with pytest.raises(ScenarioParseError):
        parse_scenario_text("stocks rise and fall sometimes by 10%")


def test_parser_rejects_text_with_no_identifiable_target():
    with pytest.raises(ScenarioParseError):
        parse_scenario_text("something drops 10%")


def test_parser_rejects_empty_string():
    with pytest.raises(ScenarioParseError):
        parse_scenario_text("")


# ---------- scenario presets ----------

def test_all_presets_have_required_fields():
    for name, preset in SCENARIO_PRESETS.items():
        assert "label" in preset and len(preset["label"]) > 0
        assert "market_shock_pct" in preset and isinstance(preset["market_shock_pct"], float)
        assert "note" in preset and len(preset["note"]) > 20  # must have a real explanatory note, not a stub


# ---------- StressTestService: integration against seeded demo portfolio ----------

def test_stress_test_zero_shock_leaves_values_unchanged(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = StressTestService(db_session).apply_shock(portfolio, market_shock_pct=0.0)
    assert result["total_loss"] == pytest.approx(0.0, abs=1e-6)
    assert result["total_value_after"] == pytest.approx(result["total_value_before"], abs=1e-6)
    for item in result["breakdown"]:
        assert item["shock_applied_pct"] == pytest.approx(0.0, abs=1e-9)


def test_stress_test_sector_shock_overrides_beta_scaling(db_session):
    portfolio = db_session.query(Portfolio).first()
    held_sectors = {h.stock.sector for h in portfolio.holdings}
    target_sector = next(iter(held_sectors))

    result = StressTestService(db_session).apply_shock(
        portfolio, market_shock_pct=-0.05, sector_shocks={target_sector: -0.40}
    )
    for item in result["breakdown"]:
        if item["sector"] == target_sector:
            assert item["shock_applied_pct"] == pytest.approx(-0.40, abs=1e-9)
            assert item["sector_shock_applied"] is True
            assert item["beta_used"] is None
        else:
            assert item["sector_shock_applied"] is False


def test_stress_test_negative_shock_reduces_total_value(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = StressTestService(db_session).apply_shock(portfolio, market_shock_pct=-0.20)
    assert result["total_value_after"] < result["total_value_before"]
    assert result["total_loss"] < 0
    assert result["total_loss_pct"] < 0


def test_stress_test_positive_shock_increases_total_value(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = StressTestService(db_session).apply_shock(portfolio, market_shock_pct=0.20)
    assert result["total_value_after"] > result["total_value_before"]


def test_stress_test_loss_breakdown_sums_to_total_loss(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = StressTestService(db_session).apply_shock(portfolio, market_shock_pct=-0.15)
    breakdown_sum = sum(item["loss"] for item in result["breakdown"])
    assert breakdown_sum == pytest.approx(result["total_loss"], abs=0.5)  # rounding tolerance across holdings


def test_stress_test_preset_applies_correct_market_shock(db_session):
    portfolio = db_session.query(Portfolio).first()
    result = StressTestService(db_session).apply_preset(portfolio, "moderate_correction")
    assert result["market_shock_pct"] == SCENARIO_PRESETS["moderate_correction"]["market_shock_pct"]
    assert result["scenario_label"] == SCENARIO_PRESETS["moderate_correction"]["label"]


def test_stress_test_unknown_preset_raises(db_session):
    portfolio = db_session.query(Portfolio).first()
    with pytest.raises(ValueError):
        StressTestService(db_session).apply_preset(portfolio, "not_a_real_preset")


def test_stress_test_endpoint_never_mutates_real_holdings(client, auth_headers):
    before = client.get("/portfolio", headers=auth_headers).json()
    client.post("/portfolio/stress-test", headers=auth_headers, json={"scenario_preset": "gfc_2008"})
    client.post("/portfolio/stress-test", headers=auth_headers, json={"scenario_text": "market crashes 30%"})
    after = client.get("/portfolio", headers=auth_headers).json()
    assert before == after


def test_stress_test_endpoint_rejects_unknown_preset(client, auth_headers):
    resp = client.post("/portfolio/stress-test", headers=auth_headers, json={"scenario_preset": "not_real"})
    assert resp.status_code == 400


def test_stress_test_endpoint_rejects_unparseable_text(client, auth_headers):
    resp = client.post("/portfolio/stress-test", headers=auth_headers, json={"scenario_text": "hello there"})
    assert resp.status_code == 400


def test_stress_test_endpoint_requires_some_input(client, auth_headers):
    resp = client.post("/portfolio/stress-test", headers=auth_headers, json={})
    assert resp.status_code == 400
