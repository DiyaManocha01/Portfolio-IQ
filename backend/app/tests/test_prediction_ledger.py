"""Tests for Phase 18: the append-only, hash-chained prediction ledger
(app/ml/prediction_ledger.py, app/models/prediction_ledger.py).

Since the whole point of this table is that it CANNOT be deleted from
(enforced by a DB trigger -- see test_db_trigger_blocks_delete), and
these tests run against the real persistent dev database (not a fresh
per-test database), every test uses a freshly RANDOMIZED base date (via
_random_base_date()) rather than a hardcoded one -- a hardcoded date
would collide with the exact same test's own data from a previous run
(both the ledger's duplicate-prediction guard and MarketData's
(stock_id, date) unique constraint would reject a repeat). Running this
suite leaves a few harmless entries behind in prediction_ledger -- that
is the expected, correct behavior of an append-only ledger, not a
test-hygiene bug.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError

from app.ml import prediction_ledger
from app.models.prediction import Confidence, Direction, Prediction
from app.models.stock import MarketData, Stock


def _random_base_date() -> date:
    """A date far from any real seeded data and extremely unlikely to
    collide with a previous run of this same test."""
    return date(1990, 1, 1) + timedelta(days=random.randint(0, 10_000))


def _make_prediction(db, stock, prediction_date, direction=Direction.POSITIVE, probability=0.6):
    pred = Prediction(
        stock_id=stock.id,
        model_name="test_model",
        model_version="test_version",
        direction=direction,
        probability=probability,
        confidence=Confidence.MEDIUM,
        important_features="[]",
        prediction_date=prediction_date,
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


# ---------- hash chain: append + verify ----------

def test_append_creates_chained_hash(db_session):
    stock = db_session.query(Stock).first()
    base = _random_base_date()
    pred1 = _make_prediction(db_session, stock, base)
    pred2 = _make_prediction(db_session, stock, base + timedelta(days=1))

    e1 = prediction_ledger.append_prediction_entry(db_session, stock, pred1)
    e2 = prediction_ledger.append_prediction_entry(db_session, stock, pred2)

    assert e1 is not None and e2 is not None
    assert e2.previous_hash == e1.entry_hash
    assert e1.entry_hash != e2.entry_hash


def test_append_is_idempotent_for_same_stock_model_day(db_session):
    stock = db_session.query(Stock).first()
    pred = _make_prediction(db_session, stock, _random_base_date())

    first = prediction_ledger.append_prediction_entry(db_session, stock, pred)
    second = prediction_ledger.append_prediction_entry(db_session, stock, pred)

    assert first is not None
    assert second is None  # no duplicate append


def test_verify_chain_valid_after_normal_appends(db_session):
    stock = db_session.query(Stock).first()
    pred = _make_prediction(db_session, stock, _random_base_date())
    prediction_ledger.append_prediction_entry(db_session, stock, pred)

    result = prediction_ledger.verify_chain(db_session)
    assert result["valid"] is True
    assert result["first_broken_entry_id"] is None


def test_verify_chain_detects_tampered_payload(db_session):
    stock = db_session.query(Stock).first()
    pred = _make_prediction(db_session, stock, _random_base_date())
    entry = prediction_ledger.append_prediction_entry(db_session, stock, pred)
    assert entry is not None

    # Simulate a privileged tamper that bypasses the normal ORM path AND
    # the trigger (disabled here on purpose, to isolate what the HASH
    # check alone catches -- see test_db_trigger_blocks_update for the
    # trigger's own, separate protection). Deliberately NEVER COMMITTED:
    # the ledger is append-only with no way to undo a persisted change
    # (that's the point), so this verifies the tamper is detected within
    # the same uncommitted transaction (read-your-own-writes) and then
    # rolls back -- the real, persisted chain is never actually corrupted.
    try:
        db_session.execute(text("ALTER TABLE prediction_ledger DISABLE TRIGGER prediction_ledger_no_update"))
        db_session.execute(
            text("UPDATE prediction_ledger SET probability = 0.999 WHERE id = :id"), {"id": entry.id}
        )
        db_session.flush()
        # The raw UPDATE above bypasses the ORM, so the session's identity
        # map still holds the pre-tamper in-memory object for this row --
        # without expiring it, a subsequent ORM query would return that
        # stale cached object instead of reflecting the row's new state.
        db_session.expire_all()

        result = prediction_ledger.verify_chain(db_session)
        assert result["valid"] is False
        assert result["first_broken_entry_id"] == entry.id
    finally:
        db_session.rollback()


# ---------- DB-level append-only enforcement ----------

def test_db_trigger_blocks_update(db_session):
    stock = db_session.query(Stock).first()
    pred = _make_prediction(db_session, stock, _random_base_date())
    entry = prediction_ledger.append_prediction_entry(db_session, stock, pred)
    assert entry is not None

    entry.probability = 0.123
    with pytest.raises(InternalError):
        db_session.commit()
    db_session.rollback()


def test_db_trigger_blocks_delete(db_session):
    stock = db_session.query(Stock).first()
    pred = _make_prediction(db_session, stock, _random_base_date())
    entry = prediction_ledger.append_prediction_entry(db_session, stock, pred)
    assert entry is not None

    db_session.delete(entry)
    with pytest.raises(InternalError):
        db_session.commit()
    db_session.rollback()


# ---------- resolution ----------

def test_resolve_computes_realized_return_hand_calculated(db_session):
    stock = db_session.query(Stock).first()
    pred_date = _random_base_date()
    next_date = pred_date + timedelta(days=1)

    # Two consecutive days of known close prices for a clean hand-calculation:
    # close goes from 100.0 to 105.0 -> realized_return = 105/100 - 1 = 0.05 exactly.
    db_session.add(MarketData(stock_id=stock.id, date=pred_date, open=100, high=101, low=99, close=100.0, volume=1000))
    db_session.add(MarketData(stock_id=stock.id, date=next_date, open=105, high=106, low=104, close=105.0, volume=1000))
    db_session.commit()

    pred = _make_prediction(db_session, stock, pred_date, direction=Direction.POSITIVE)
    entry = prediction_ledger.append_prediction_entry(db_session, stock, pred)
    assert entry is not None

    resolved = prediction_ledger.resolve_due_entries(db_session)
    matching = [r for r in resolved if r.resolves_entry_id == entry.id]
    assert len(matching) == 1
    resolution = matching[0]
    assert resolution.realized_return == pytest.approx(0.05, abs=1e-9)
    assert resolution.realized_direction == "UP"


def test_resolve_skips_entries_without_known_outcome(db_session):
    stock = db_session.query(Stock).first()
    far_future_date = date(2099, 1, 1) + timedelta(days=random.randint(0, 300))  # nothing exists after this
    pred = _make_prediction(db_session, stock, far_future_date)
    entry = prediction_ledger.append_prediction_entry(db_session, stock, pred)
    assert entry is not None

    resolved = prediction_ledger.resolve_due_entries(db_session)
    matching = [r for r in resolved if r.resolves_entry_id == entry.id]
    assert matching == []  # correctly stays pending, not guessed


def test_resolve_is_idempotent(db_session):
    stock = db_session.query(Stock).first()
    pred_date = _random_base_date()
    next_date = pred_date + timedelta(days=1)
    db_session.add(MarketData(stock_id=stock.id, date=pred_date, open=50, high=51, low=49, close=50.0, volume=500))
    db_session.add(MarketData(stock_id=stock.id, date=next_date, open=48, high=49, low=47, close=48.0, volume=500))
    db_session.commit()

    pred = _make_prediction(db_session, stock, pred_date, direction=Direction.NEGATIVE)
    entry = prediction_ledger.append_prediction_entry(db_session, stock, pred)

    first_pass = prediction_ledger.resolve_due_entries(db_session)
    second_pass = prediction_ledger.resolve_due_entries(db_session)

    assert any(r.resolves_entry_id == entry.id for r in first_pass)
    assert not any(r.resolves_entry_id == entry.id for r in second_pass)  # not resolved twice


# ---------- HTTP endpoint integration (all public, no auth) ----------

def test_ledger_entries_endpoint_requires_no_auth(client):
    resp = client.get("/ledger/entries")
    assert resp.status_code == 200


def test_ledger_verify_endpoint_requires_no_auth(client):
    resp = client.get("/ledger/verify")
    assert resp.status_code == 200
    assert "valid" in resp.json()


def test_ledger_track_record_endpoint_requires_no_auth(client):
    resp = client.get("/ledger/track-record")
    assert resp.status_code == 200
    body = resp.json()
    assert "disclaimer" in body
    assert "paper_trading" in body


def test_ledger_entries_filterable_by_symbol(client, db_session):
    stock = db_session.query(Stock).first()
    pred = _make_prediction(db_session, stock, _random_base_date())
    prediction_ledger.append_prediction_entry(db_session, stock, pred)

    resp = client.get(f"/ledger/entries?symbol={stock.symbol}")
    assert resp.status_code == 200
    assert all(item["symbol"] == stock.symbol for item in resp.json())
    assert len(resp.json()) > 0
