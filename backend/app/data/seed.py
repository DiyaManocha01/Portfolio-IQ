"""Development seed script.

Creates the database schema (if needed), a demo user with a populated
portfolio, synthetic market history for the seeded stock universe, sample
news + sentiment, and trains the ML direction-classifier so predictions
work immediately after seeding.

Run with:  python -m app.data.seed
"""

from __future__ import annotations

from app.database.session import Base, SessionLocal, engine
from app.ml.predict import PredictionService
from app.ml.train import train_and_select_model
from app.models.portfolio import Holding, Portfolio
from app.models.user import RiskTolerance, User, UserProfile
from app.services.market_data.service import MarketDataService
from app.services.news_service import NewsService
from app.services.security import hash_password

DEMO_EMAIL = "demo@portfolioiq.app"
DEMO_PASSWORD = "demo1234"

HOLDINGS = [
    ("TCS", 10, 3200.0),
    ("RELIANCE", 15, 2700.0),
    ("HDFCBANK", 20, 1550.0),
    ("INFY", 25, 1700.0),
    ("ICICIBANK", 30, 1100.0),
    ("LT", 8, 3400.0),
    ("ITC", 100, 420.0),
]

# Extra stocks seeded with market data/news but NOT added as holdings, so
# /discover has real, currently-unheld candidates to rank by Portfolio Fit.
DISCOVER_ONLY_SYMBOLS = ["HINDUNILVR", "BHARTIARTL", "SBIN", "WIPRO", "MARUTI", "SUNPHARMA"]

ALL_SYMBOLS = [h[0] for h in HOLDINGS] + DISCOVER_ONLY_SYMBOLS


def seed():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        market_data = MarketDataService(db)
        news_service = NewsService(db)

        print("Seeding stocks + market data + news/sentiment...")
        stocks = {}
        for symbol in ALL_SYMBOLS:
            stock = market_data.get_or_create_stock(symbol)
            written = market_data.sync_history(stock, days=400)
            news_service.generate_sample_news(stock)
            stocks[symbol] = stock
            print(f"  {symbol}: {written} market_data rows, news generated")

        print("Seeding demo user + portfolio...")
        user = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if not user:
            user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD), full_name="Demo Investor")
            db.add(user)
            db.flush()
            db.add(UserProfile(user_id=user.id, risk_tolerance=RiskTolerance.MODERATE, investment_horizon_years=7))
            db.add(Portfolio(user_id=user.id, name="My Portfolio"))
            db.commit()
            db.refresh(user)
            print(f"  Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"  Demo user already exists: {DEMO_EMAIL}")

        portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
        for symbol, qty, avg_price in HOLDINGS:
            stock = stocks[symbol]
            existing = (
                db.query(Holding)
                .filter(Holding.portfolio_id == portfolio.id, Holding.stock_id == stock.id)
                .first()
            )
            if existing:
                continue
            db.add(Holding(portfolio_id=portfolio.id, stock_id=stock.id, quantity=qty, avg_buy_price=avg_price))
        db.commit()
        print(f"  Portfolio has {len(portfolio.holdings)} holdings")

        print("Training ML direction-classifier (Logistic Regression / Random Forest / XGBoost)...")
        metadata = train_and_select_model(db)
        print(f"  Selected model: {metadata['selected_model']}")
        print(f"  Validation metrics: {metadata['candidates_val_metrics']}")
        print(f"  Held-out test metrics: {metadata['test_metrics']}")

        print("Generating initial predictions for all seeded stocks...")
        prediction_service = PredictionService(db)
        for symbol, stock in stocks.items():
            pred = prediction_service.predict_for_stock(stock)
            print(f"  {symbol}: {pred.direction.value} (p={pred.probability:.2f}, {pred.confidence.value})")

        print("\nSeed complete.")
        print(f"Demo login -> email: {DEMO_EMAIL}  password: {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
