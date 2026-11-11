from pathlib import Path

from app.services.market_data import cache
from app.services.market_data.providers import DevSampleProvider, FundamentalSnapshot
from app.services.market_data.service import MarketDataService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fundamentals_sample"


def test_dev_sample_fundamentals_are_deterministic():
    provider = DevSampleProvider()
    first = provider.get_fundamentals("TCS")
    second = provider.get_fundamentals("TCS")
    assert first == second


def test_dev_sample_fundamentals_differ_by_symbol():
    provider = DevSampleProvider()
    tcs = provider.get_fundamentals("TCS")
    reliance = provider.get_fundamentals("RELIANCE")
    assert tcs != reliance


def test_dev_sample_fundamentals_shape():
    provider = DevSampleProvider()
    snap = provider.get_fundamentals("TCS")
    assert isinstance(snap, FundamentalSnapshot)
    assert snap.pe_ratio is not None
    assert snap.roce is not None  # synthetic data populates it, unlike the live provider


def test_fundamentals_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "FUNDAMENTALS_MANIFEST_PATH", tmp_path / "fundamentals_manifest.json")

    data = {field: 1.0 for field in cache.FUNDAMENTAL_FIELDS}
    data["roce"] = None
    cache.write_fundamentals_cache("TESTSYM", data, source="yfinance")

    read_back = cache.read_fundamentals_cache("TESTSYM")
    assert read_back == data


def test_fundamentals_cache_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    assert cache.read_fundamentals_cache("NOPE") is None


def test_write_fundamentals_cache_rejects_incomplete_dict(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(cache, "FUNDAMENTALS_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError):
        cache.write_fundamentals_cache("TESTSYM", {"pe_ratio": 1.0}, source="yfinance")


def test_committed_fixture_loads_with_expected_keys():
    """Sanity check that the committed hand-written fixture (test-only, see
    its README) has exactly the keys FundamentalSnapshot expects."""
    import json

    data = json.loads((FIXTURE_DIR / "RELIANCE.json").read_text())
    assert set(data.keys()) == set(cache.FUNDAMENTAL_FIELDS)
    FundamentalSnapshot(**data)  # must not raise


def test_service_get_fundamentals_creates_and_caches_row(db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("HINDUNILVR")

    first = market_data.get_fundamentals(stock)
    second = market_data.get_fundamentals(stock)

    assert first.id == second.id  # same day -> cached row reused, not refetched
    assert first.pe_ratio is not None


def test_fundamentals_api_route(client, auth_headers):
    resp = client.get("/stocks/WIPRO/fundamentals", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "WIPRO"
    assert "disclaimer" in body
    assert body["roce"] is not None  # DEV_SAMPLE in this environment


def test_fundamentals_api_route_unknown_symbol_404(client, auth_headers):
    resp = client.get("/stocks/NOTREAL/fundamentals", headers=auth_headers)
    assert resp.status_code == 404
