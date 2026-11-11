from app.services.market_data.fixture_replay_provider import refresh_once
from app.services.market_data.live_cache import LiveCache
from app.services.market_data.tick_normalizer import TickStatus


def test_refresh_once_populates_cache_tagged_fixture(db_session):
    cache = LiveCache()
    written = refresh_once(db_session, cache, symbols=["RELIANCE", "TCS"])
    assert written == 2

    tick = cache.get("RELIANCE")
    assert tick is not None
    assert tick.status == TickStatus.FIXTURE
    assert tick.source == "FIXTURE"
    assert tick.price > 0


def test_refresh_once_never_uses_live_status(db_session):
    cache = LiveCache()
    refresh_once(db_session, cache, symbols=["TCS"])
    assert cache.get("TCS").status != TickStatus.LIVE
