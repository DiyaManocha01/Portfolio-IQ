"""Tests for the Phase 4 Parquet cache + validation logic.

IMPORTANT: the DataFrames built inline below are SYNTHETIC, invented
specifically to exercise cache/validation code paths (round-trip I/O,
gap detection, negative-price detection, unadjusted-split detection).
They are NOT real market data and must never be treated as such -- see
docs/limitations.md. Real-data testing (once available) lives in
test_market_data_cache_real_fixture.py, which is skipped unless
scripts/fetch_nifty100.py --out-fixture has been run locally and its
output committed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.market_data import cache


def _clean_df(n=10, start="2024-01-01"):
    dates = pd.date_range(start, periods=n, freq="B")
    close = [100.0 + i for i in range(n)]
    return pd.DataFrame(
        {
            "date": [d.date().isoformat() for d in dates],
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [1_000_000] * n,
        }
    )


def test_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "MANIFEST_PATH", tmp_path / "cache_manifest.json")

    df = _clean_df()
    assert cache.has_cache("TESTSYM") is False

    meta = cache.write_cache("TESTSYM", df, source="synthetic-test", validation_warnings=[])
    assert meta.rows == len(df)
    assert cache.has_cache("TESTSYM") is True

    loaded = cache.read_cache("TESTSYM")
    assert list(loaded["close"]) == list(df["close"])

    manifest = cache.read_manifest()
    assert "TESTSYM" in manifest
    assert manifest["TESTSYM"]["source"] == "synthetic-test"


def test_read_cache_missing_symbol_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    assert cache.read_cache("NOPE") is None


def test_write_cache_rejects_missing_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "MANIFEST_PATH", tmp_path / "cache_manifest.json")
    bad_df = _clean_df().drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing"):
        cache.write_cache("BADSYM", bad_df, source="synthetic-test", validation_warnings=[])


def test_validate_ohlcv_clean_data_has_no_warnings():
    df = _clean_df()
    assert cache.validate_ohlcv(df, "TESTSYM") == []


def test_validate_ohlcv_detects_negative_price():
    df = _clean_df()
    df.loc[2, "close"] = -5.0
    warnings = cache.validate_ohlcv(df, "TESTSYM")
    assert any("non-positive close" in w for w in warnings)


def test_validate_ohlcv_detects_negative_volume():
    df = _clean_df()
    df.loc[0, "volume"] = -100
    warnings = cache.validate_ohlcv(df, "TESTSYM")
    assert any("negative volume" in w for w in warnings)


def test_validate_ohlcv_detects_high_less_than_low():
    df = _clean_df()
    df.loc[1, "high"] = 10.0
    df.loc[1, "low"] = 50.0
    warnings = cache.validate_ohlcv(df, "TESTSYM")
    assert any("high < low" in w for w in warnings)


def test_validate_ohlcv_detects_large_gap():
    df = _clean_df(n=5)
    # push the last date far out to create an artificial 30-day gap
    df.loc[4, "date"] = "2024-02-15"
    warnings = cache.validate_ohlcv(df, "TESTSYM", max_gap_days=10)
    assert any("gap" in w for w in warnings)


def test_validate_ohlcv_detects_likely_unadjusted_split():
    df = _clean_df(n=5)
    df.loc[3, "close"] = df.loc[2, "close"] * 0.4  # a sudden 60% drop
    warnings = cache.validate_ohlcv(df, "TESTSYM")
    assert any("split/dividend-adjusted" in w for w in warnings)


def test_validate_ohlcv_empty_dataframe():
    df = pd.DataFrame(columns=cache.REQUIRED_COLUMNS)
    warnings = cache.validate_ohlcv(df, "TESTSYM")
    assert any("no rows" in w for w in warnings)
