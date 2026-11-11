import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import assistant, auth, discover, ledger, market, portfolio, portfolio_fit, screener, stocks
from app.config import settings
from app.database.session import SessionLocal
from app.services.market_data import session_calendar, snapshot_service
from app.services.market_data.fixture_replay_provider import refresh_once as refresh_fixture_cache
from app.services.market_data.instrument_registry import instrument_registry
from app.services.market_data.live_cache import live_cache
from app.services.market_data.ws_connection_manager import WSConnectionManager
from app.services.rate_limit import limiter

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("portfolioiq")

# Two known placeholder values a developer can end up running with: the
# Settings class default (app/config.py), and the .env.example value
# `cp .env.example .env` copies verbatim if SECRET_KEY is never edited.
_INSECURE_DEFAULT_SECRET_KEYS = {
    "dev-secret-key-change-me",
    "change-this-to-a-long-random-string-in-production",
}
if settings.SECRET_KEY in _INSECURE_DEFAULT_SECRET_KEYS or len(settings.SECRET_KEY) < 32:
    logger.warning(
        "SECURITY: SECRET_KEY is set to a known placeholder value or is "
        "shorter than 32 characters. JWT access tokens signed with a "
        "predictable or low-entropy key can be forged by anyone who guesses "
        "or reads it. Set a long, random SECRET_KEY in your .env before "
        "this is reachable by anyone other than you, e.g.: "
        "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )

# Phase 24: the single upstream Angel One connection, and the background
# task that keeps live_cache populated either from it (real feed) or from
# fixture_replay_provider (no credentials / feed disabled). Both are
# module-level so app.api.routes.market can read ws_manager.status without
# a circular import at FastAPI-app-construction time.
ws_manager: WSConnectionManager | None = None
_background_task: asyncio.Task | None = None

_FIXTURE_REFRESH_INTERVAL_SECONDS = 30


async def _background_loop() -> None:
    """Keeps live_cache fresh and persists periodic candles.

    Runs forever (cancelled on shutdown): every tick, if the real feed
    isn't connected, refreshes the FIXTURE-tagged cache from existing
    cached/synthetic data; during market hours, also snapshots whatever is
    currently in the cache (real or fixture) into intraday_candles.
    """
    while True:
        try:
            if ws_manager is None or ws_manager.status != "CONNECTED":
                db = SessionLocal()
                try:
                    refresh_fixture_cache(db, live_cache)
                finally:
                    db.close()

            if session_calendar.is_market_open():
                db = SessionLocal()
                try:
                    snapshot_service.snapshot_cache(db, live_cache)
                finally:
                    db.close()
        except Exception:  # noqa: BLE001 -- a background refresh must never crash the app
            logger.exception("market data background loop iteration failed")

        await asyncio.sleep(_FIXTURE_REFRESH_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ws_manager, _background_task

    ws_manager = WSConnectionManager(
        registry=instrument_registry,
        cache=live_cache,
        api_key=settings.ANGELONE_API_KEY,
        client_code=settings.ANGELONE_CLIENT_CODE,
        password=settings.ANGELONE_PASSWORD,
        totp_secret=settings.ANGELONE_TOTP_SECRET,
    )
    if settings.ENABLE_REALTIME_FEED:
        ws_manager.start()
    _background_task = asyncio.create_task(_background_loop(), name="market-data-background-loop")

    yield

    if _background_task is not None:
        _background_task.cancel()
    if ws_manager is not None:
        await ws_manager.stop()


app = FastAPI(
    title="PortfolioIQ API",
    description=(
        "AI Portfolio Intelligence backend. Educational and analytical "
        "decision-support system -- predictions and analytics are model-based "
        "estimates, not guaranteed financial advice."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(stocks.router)
app.include_router(discover.router)
app.include_router(portfolio_fit.router)
app.include_router(ledger.router)
app.include_router(assistant.router)
app.include_router(market.router)
app.include_router(screener.router)


@app.get("/")
def root():
    return {
        "name": "PortfolioIQ API",
        "status": "ok",
        "disclaimer": (
            "PortfolioIQ is an educational and analytical decision-support system. "
            "Its predictions and portfolio analytics are model-based estimates and "
            "are not guaranteed financial advice."
        ),
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
