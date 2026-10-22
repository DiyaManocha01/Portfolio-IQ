import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import assistant, auth, discover, ledger, portfolio, portfolio_fit, stocks
from app.config import settings
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

app = FastAPI(
    title="PortfolioIQ API",
    description=(
        "AI Portfolio Intelligence backend. Educational and analytical "
        "decision-support system -- predictions and analytics are model-based "
        "estimates, not guaranteed financial advice."
    ),
    version="0.1.0",
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
