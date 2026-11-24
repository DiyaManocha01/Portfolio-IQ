import datetime as dt

from app.models.corporate_event import CorporateEvent, CorporateEventType
from app.models.stock import DataSource
from app.services.market_data.providers import DevSampleProvider
from app.services.market_data.service import MarketDataService


def test_dev_sample_provider_produces_quarterly_earnings():
    provider = DevSampleProvider()
    events = provider.get_corporate_events("TCS")
    assert events  # never empty for DEV_SAMPLE
    assert all(e.event_type == "EARNINGS" for e in events)
    # Sorted ascending by date, as documented.
    dates = [e.event_date for e in events]
    assert dates == sorted(dates)


def test_dev_sample_provider_is_deterministic_per_symbol():
    provider = DevSampleProvider()
    first = provider.get_corporate_events("TCS")
    second = provider.get_corporate_events("TCS")
    assert [e.event_date for e in first] == [e.event_date for e in second]


def test_dev_sample_provider_differs_by_symbol():
    provider = DevSampleProvider()
    tcs_dates = {e.event_date for e in provider.get_corporate_events("TCS")}
    reliance_dates = {e.event_date for e in provider.get_corporate_events("RELIANCE")}
    assert tcs_dates != reliance_dates


def test_service_get_corporate_events_persists_and_dedupes(db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("HCLTECH")

    first = market_data.get_corporate_events(stock)
    assert first  # DEV_SAMPLE always returns some events
    stored_count = (
        db_session.query(CorporateEvent).filter(CorporateEvent.stock_id == stock.id).count()
    )
    assert stored_count == len(first)

    # Calling again within the refresh window must not duplicate rows.
    second = market_data.get_corporate_events(stock)
    assert len(second) == len(first)
    stored_count_again = (
        db_session.query(CorporateEvent).filter(CorporateEvent.stock_id == stock.id).count()
    )
    assert stored_count_again == stored_count


def test_service_get_corporate_events_refreshes_after_window(db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("ASIANPAINT")
    market_data.get_corporate_events(stock)

    # Force every stored row to look stale.
    stale = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=48)
    db_session.query(CorporateEvent).filter(CorporateEvent.stock_id == stock.id).update(
        {CorporateEvent.created_at: stale}
    )
    db_session.commit()

    events = market_data.get_corporate_events(stock, refresh_after_hours=24)
    assert events  # re-fetch succeeded and still returns the (same, deduped) rows


def test_stored_events_are_tagged_dev_sample(db_session):
    market_data = MarketDataService(db_session)
    stock = market_data.get_or_create_stock("ITC")
    events = market_data.get_corporate_events(stock)
    assert all(e.source == DataSource.DEV_SAMPLE for e in events)
    assert all(e.event_type == CorporateEventType.EARNINGS for e in events)


def test_events_api_route(client, auth_headers):
    resp = client.get("/stocks/TCS/events", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "TCS"
    assert "disclaimer" in body
    assert len(body["events"]) > 0
    first = body["events"][0]
    assert set(first.keys()) == {"event_type", "event_date", "description", "is_upcoming", "source"}


def test_events_api_route_unknown_symbol_404(client, auth_headers):
    resp = client.get("/stocks/NOTREAL/events", headers=auth_headers)
    assert resp.status_code == 404


def test_events_api_route_upcoming_flag_matches_today(client, auth_headers):
    resp = client.get("/stocks/TCS/events", headers=auth_headers)
    body = resp.json()
    today = dt.date.today()
    for e in body["events"]:
        event_date = dt.date.fromisoformat(e["event_date"])
        assert e["is_upcoming"] == (event_date >= today)
