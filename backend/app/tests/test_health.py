"""Tests for Phase 34's GET /health (app/services/health_service.py)."""

from __future__ import annotations


def test_health_requires_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_reports_database_connected(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["database"]["connected"] is True


def test_health_reports_migrations_up_to_date(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["migrations"]["up_to_date"] is True
    assert body["migrations"]["applied"] == body["migrations"]["head"]


def test_health_reports_ml_model_status(client):
    resp = client.get("/health")
    body = resp.json()
    assert "loaded" in body["ml_model"]


def test_health_reports_realtime_feed_disabled_by_default(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["realtime_feed"]["enabled"] is False
    assert body["realtime_feed"]["status"] == "DISABLED"


def test_health_overall_status_ok_when_everything_healthy(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["status"] == "ok"


def test_health_echoes_request_id_header(client):
    resp = client.get("/health")
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0
