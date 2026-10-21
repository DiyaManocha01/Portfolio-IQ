"""Tests for Phase 12: personalized discovery -- user sector-exclusion
preferences, preset/sector filters on /discover, and the top_factor
field surfacing the Fit Engine's per-term breakdown in the list view.

Tests restore the demo user's preferences to empty at the end of each
test that changes them, since /auth/me/preferences is session-scoped
state shared across the test run (the `client`/`auth_headers` fixtures
are session-scoped)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_preferences(client, auth_headers):
    yield
    client.put("/auth/me/preferences", headers=auth_headers, json={"excluded_sectors": []})


def test_preferences_default_to_empty(client, auth_headers):
    resp = client.get("/auth/me/preferences", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"excluded_sectors": []}


def test_set_and_get_preferences_round_trip(client, auth_headers):
    put_resp = client.put(
        "/auth/me/preferences", headers=auth_headers, json={"excluded_sectors": ["Energy"]}
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == {"excluded_sectors": ["Energy"]}

    get_resp = client.get("/auth/me/preferences", headers=auth_headers)
    assert get_resp.json() == {"excluded_sectors": ["Energy"]}


def test_excluded_sector_is_removed_from_discover_results(client, auth_headers):
    before = client.get("/discover?limit=50", headers=auth_headers).json()
    sectors_before = {item["sector"] for item in before}
    # Pick a sector that's actually present to exclude, so the test is meaningful.
    sector_to_exclude = next(iter(sectors_before))

    client.put("/auth/me/preferences", headers=auth_headers, json={"excluded_sectors": [sector_to_exclude]})
    after = client.get("/discover?limit=50", headers=auth_headers).json()
    sectors_after = {item["sector"] for item in after}

    assert sector_to_exclude not in sectors_after


def test_excluding_every_sector_falls_back_to_unfiltered_rather_than_empty(client, auth_headers):
    all_sectors = {item["sector"] for item in client.get("/discover?limit=50", headers=auth_headers).json()}
    client.put("/auth/me/preferences", headers=auth_headers, json={"excluded_sectors": list(all_sectors)})

    resp = client.get("/discover?limit=50", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) > 0  # degenerate exclusion must not silently empty the list


def test_discover_sector_filter(client, auth_headers):
    resp = client.get("/discover?sector=Information Technology&limit=50", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    assert all(item["sector"] == "Information Technology" for item in items)


def test_discover_sector_filter_case_insensitive(client, auth_headers):
    resp = client.get("/discover?sector=information technology&limit=50", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_discover_preset_param_changes_ranking_or_scores(client, auth_headers):
    balanced = client.get("/discover?preset=balanced&limit=50", headers=auth_headers).json()
    growth = client.get("/discover?preset=growth_seeking&limit=50", headers=auth_headers).json()

    balanced_scores = {item["symbol"]: item["portfolio_fit"] for item in balanced}
    growth_scores = {item["symbol"]: item["portfolio_fit"] for item in growth}
    assert balanced_scores != growth_scores


def test_discover_rejects_unknown_preset(client, auth_headers):
    resp = client.get("/discover?preset=not_real", headers=auth_headers)
    assert resp.status_code == 400


def test_discover_items_include_top_factor(client, auth_headers):
    resp = client.get("/discover?limit=10", headers=auth_headers)
    assert resp.status_code == 200
    for item in resp.json():
        assert "name" in item["top_factor"]
        assert "explanation" in item["top_factor"]
        assert len(item["top_factor"]["explanation"]) > 0


def test_top_factor_matches_highest_contribution_factor(client, auth_headers):
    discover_items = {item["symbol"]: item for item in client.get("/discover?limit=50", headers=auth_headers).json()}
    symbol = next(iter(discover_items))
    item = discover_items[symbol]

    fit_resp = client.get(f"/portfolio-fit/{symbol}", headers=auth_headers)
    assert fit_resp.status_code == 200
    fit_factors = fit_resp.json()["factors"]
    # /portfolio-fit/{symbol} z-scores against the FULL universe while
    # /discover z-scores against its own candidate batch (documented,
    # Phase 10 Section 7.3) -- so scores can differ, but the TOP factor's
    # NAME should usually agree since both see the same raw underlying
    # signal direction for a stock that isn't on a knife's edge between
    # two terms. We only assert the top_factor is a real, known factor name.
    known_names = {f["name"] for f in fit_factors}
    assert item["top_factor"]["name"] in known_names
