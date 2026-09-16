from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, discover, portfolio, portfolio_fit, stocks
from app.config import settings

app = FastAPI(
    title="PortfolioIQ API",
    description=(
        "AI Portfolio Intelligence backend. Educational and analytical "
        "decision-support system -- predictions and analytics are model-based "
        "estimates, not guaranteed financial advice."
    ),
    version="0.1.0",
)

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
