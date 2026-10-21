"""Tests for Phase 11: the What-If Simulator (app/portfolio/whatif_service.py).

Hand-calculated unit tests cover the Indian transaction cost estimate.
Integration tests exercise the real /portfolio/what-if endpoint against
the seeded demo portfolio, with an explicit non-mutation check."""

from __future__ import annotations

import pytest

from app.models.portfolio import Portfolio
from app.portfolio.whatif_service import (
    EXCHANGE_CHARGE_RATE,
    GST_RATE,
    SEBI_FEE_RATE,
    STAMP_DUTY_RATE,
    STT_RATE,
    WhatIfService,
    estimate_indian_trade_cost,
)


# ---------- hand-calculated: transaction cost estimate ----------

def test_trade_cost_buy_hand_calculated():
    # trade_value = 100,000, is_buy=True, brokerage_rate=0 (default)
    # stt = 100000 * 0.001 = 100.0
    # stamp_duty = 100000 * 0.00015 = 15.0
    # exchange_charges = 100000 * 0.00003 = 3.0
    # sebi_fee = 100000 * 0.000001 = 0.1
    # gst = (0 + 3.0) * 0.18 = 0.54
    # total = 0 + 100.0 + 15.0 + 3.0 + 0.1 + 0.54 = 118.64
    cost = estimate_indian_trade_cost(100_000.0, is_buy=True)
    assert cost["stt"] == pytest.approx(100.0, abs=1e-6)
    assert cost["stamp_duty"] == pytest.approx(15.0, abs=1e-6)
    assert cost["exchange_charges"] == pytest.approx(3.0, abs=1e-6)
    assert cost["sebi_fee"] == pytest.approx(0.1, abs=1e-6)
    assert cost["gst"] == pytest.approx(0.54, abs=1e-6)
    assert cost["total"] == pytest.approx(118.64, abs=1e-6)


def test_trade_cost_sell_has_no_stamp_duty():
    # Same trade value, is_buy=False -> stamp_duty must be exactly 0.
    cost = estimate_indian_trade_cost(100_000.0, is_buy=False)
    assert cost["stamp_duty"] == 0.0
    # stt + exchange + sebi + gst = 100.0 + 3.0 + 0.1 + 0.54 = 103.64
    assert cost["total"] == pytest.approx(103.64, abs=1e-6)


def test_trade_cost_with_nonzero_brokerage():
    # brokerage_rate=0.0003 (0.03%) on 100,000 -> brokerage = 30.0
    # gst now includes brokerage: (30.0 + 3.0) * 0.18 = 5.94
    cost = estimate_indian_trade_cost(100_000.0, is_buy=True, brokerage_rate=0.0003)
    assert cost["brokerage"] == pytest.approx(30.0, abs=1e-6)
    assert cost["gst"] == pytest.approx(5.94, abs=1e-6)


def test_trade_cost_zero_value_is_zero():
    cost = estimate_indian_trade_cost(0.0, is_buy=True)
    assert cost["total"] == 0.0


def test_rate_constants_are_small_fractions():
    # Sanity bounds -- these are rates (fractions of trade value), not
    # rupee amounts; catches an accidental order-of-magnitude error.
    for rate in (STT_RATE, STAMP_DUTY_RATE, EXCHANGE_CHARGE_RATE, SEBI_FEE_RATE):
        assert 0 < rate < 0.01
    assert 0 < GST_RATE < 1


# ---------- integration: real seeded demo portfolio ----------

def test_whatif_never_mutates_real_holdings(client, auth_headers):
    before = client.get("/portfolio", headers=auth_headers).json()
    resp = client.post(
        "/portfolio/what-if",
        headers=auth_headers,
        json={"changes": [{"symbol": "SUNPHARMA", "new_quantity": 15}]},
    )
    assert resp.status_code == 200
    after = client.get("/portfolio", headers=auth_headers).json()
    assert before == after


def test_whatif_selling_entire_position(client, auth_headers, db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol

    resp = client.post(
        "/portfolio/what-if",
        headers=auth_headers,
        json={"changes": [{"symbol": held_symbol, "new_quantity": 0}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["trades"][0]["action"] == "sell"
    assert body["trades"][0]["quantity_delta"] < 0


def test_whatif_multi_trade_swap(client, auth_headers, db_session):
    portfolio = db_session.query(Portfolio).first()
    held_symbol = portfolio.holdings[0].stock.symbol
    held_qty = portfolio.holdings[0].quantity

    resp = client.post(
        "/portfolio/what-if",
        headers=auth_headers,
        json={
            "changes": [
                {"symbol": held_symbol, "new_quantity": 0},
                {"symbol": "SUNPHARMA", "new_quantity": 20},
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["trades"]) == 2
    actions = {t["symbol"]: t["action"] for t in body["trades"]}
    assert actions[held_symbol] == "sell"
    assert actions["SUNPHARMA"] == "buy"
    assert body["total_estimated_cost"] > 0


def test_whatif_costs_can_be_disabled(client, auth_headers):
    resp = client.post(
        "/portfolio/what-if",
        headers=auth_headers,
        json={"changes": [{"symbol": "SUNPHARMA", "new_quantity": 15}], "include_costs": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_estimated_cost"] is None
    assert all(t["estimated_cost"] is None for t in body["trades"])


def test_whatif_rejects_empty_changes(client, auth_headers):
    resp = client.post("/portfolio/what-if", headers=auth_headers, json={"changes": []})
    assert resp.status_code == 422


def test_whatif_rejects_negative_quantity(client, auth_headers):
    resp = client.post(
        "/portfolio/what-if", headers=auth_headers, json={"changes": [{"symbol": "TCS", "new_quantity": -5}]}
    )
    assert resp.status_code == 422


def test_whatif_no_op_change_has_zero_deltas(client, auth_headers, db_session):
    portfolio = db_session.query(Portfolio).first()
    held = portfolio.holdings[0]

    resp = client.post(
        "/portfolio/what-if",
        headers=auth_headers,
        json={"changes": [{"symbol": held.stock.symbol, "new_quantity": held.quantity}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["trades"] == []  # no actual change in quantity -> no trade recorded
    for v in body["deltas"].values():
        assert v == pytest.approx(0.0, abs=1e-6)
