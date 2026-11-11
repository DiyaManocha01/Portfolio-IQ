from app.services.market_data.service import MarketDataService
from app.services.screener_service import ScreenerFilters, run_screener


def test_screener_no_filters_returns_full_seeded_universe(db_session):
    results = run_screener(db_session, ScreenerFilters())
    symbols = {r.symbol for r in results}
    assert "TCS" in symbols
    assert "RELIANCE" in symbols
    assert len(results) > 0


def test_screener_sector_filter_narrows_results(db_session):
    all_results = run_screener(db_session, ScreenerFilters())
    it_results = run_screener(db_session, ScreenerFilters(sector="Information Technology"))
    assert len(it_results) <= len(all_results)
    assert all(r.sector == "Information Technology" for r in it_results)
    assert any(r.symbol == "TCS" for r in it_results)


def test_screener_impossible_market_cap_filter_returns_empty(db_session):
    results = run_screener(db_session, ScreenerFilters(market_cap_min=1e20))
    assert results == []


def test_screener_permissive_filter_matches_unfiltered(db_session):
    unfiltered = run_screener(db_session, ScreenerFilters())
    permissive = run_screener(db_session, ScreenerFilters(market_cap_min=0.0, pe_max=10_000.0))
    assert {r.symbol for r in unfiltered} == {r.symbol for r in permissive}


def test_screener_roe_min_filters_correctly(db_session):
    market_data = MarketDataService(db_session)
    stocks_with_roe = []
    for symbol in ["TCS", "RELIANCE", "INFY"]:
        stock = market_data.get_or_create_stock(symbol)
        metric = market_data.get_fundamentals(stock)
        stocks_with_roe.append((symbol, metric.roe))

    threshold = sorted(v for _, v in stocks_with_roe if v is not None)[len(stocks_with_roe) // 2]
    results = run_screener(db_session, ScreenerFilters(roe_min=threshold))
    assert all(r.roe is not None and r.roe >= threshold for r in results)


def test_screener_technical_filter_populates_rsi_and_momentum(db_session):
    results = run_screener(db_session, ScreenerFilters(rsi_min=0.0))
    assert len(results) > 0
    for r in results:
        assert r.rsi_14 is not None
        assert 0.0 <= r.rsi_14 <= 100.0


def test_screener_technical_filter_can_exclude_everything(db_session):
    results = run_screener(db_session, ScreenerFilters(rsi_min=999.0))
    assert results == []


def test_screener_api_route_no_filters(client, auth_headers):
    resp = client.get("/screener", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["results"])
    assert body["count"] > 0
    assert "disclaimer" in body


def test_screener_api_route_with_filters(client, auth_headers):
    resp = client.get("/screener", params={"sector": "Information Technology"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert all(r["sector"] == "Information Technology" for r in body["results"])
