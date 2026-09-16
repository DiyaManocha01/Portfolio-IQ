"""Market data provider abstraction.

PortfolioIQ separates *where data comes from* (a provider) from *how it is
used* (MarketDataService). This lets a real brokerage/market-data API be
dropped in later without touching any calling code.

Two providers are implemented:

- ``DevSampleProvider``: generates deterministic, clearly-labeled synthetic
  OHLCV data using a seeded random walk anchored to a realistic base price
  per symbol. This is what the app uses by default, since this development
  environment has no outbound network access to live market-data vendors.
  Data returned by this provider is always tagged ``DataSource.DEV_SAMPLE``.

- ``LiveYFinanceProvider``: a real implementation using the ``yfinance``
  package. It is wired into the abstraction so it can be enabled by setting
  ``USE_LIVE_MARKET_DATA=true`` in ``.env`` on a machine that has internet
  access. Data returned by this provider is tagged ``DataSource.LIVE``.
"""

from __future__ import annotations

import hashlib
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta

from app.models.stock import DataSource

# Realistic base prices (INR) used only to seed synthetic development data.
BASE_PRICES: dict[str, float] = {
    "TCS": 3450.0,
    "RELIANCE": 2950.0,
    "HDFCBANK": 1650.0,
    "INFY": 1850.0,
    "ICICIBANK": 1150.0,
    "LT": 3550.0,
    "ITC": 465.0,
    # Additional discovery-universe stocks (not in the seeded demo portfolio,
    # so /discover has real, currently-unheld candidates to rank).
    "HINDUNILVR": 2450.0,
    "BHARTIARTL": 1550.0,
    "SBIN": 780.0,
    "WIPRO": 550.0,
    "MARUTI": 11500.0,
    "SUNPHARMA": 1750.0,
}

SECTORS: dict[str, tuple[str, str]] = {
    "TCS": ("Information Technology", "IT Services"),
    "INFY": ("Information Technology", "IT Services"),
    "WIPRO": ("Information Technology", "IT Services"),
    "RELIANCE": ("Energy", "Oil & Gas / Conglomerate"),
    "HDFCBANK": ("Financial Services", "Private Bank"),
    "ICICIBANK": ("Financial Services", "Private Bank"),
    "SBIN": ("Financial Services", "Public Sector Bank"),
    "LT": ("Industrials", "Engineering & Construction"),
    "ITC": ("Consumer Staples", "FMCG / Diversified"),
    "HINDUNILVR": ("Consumer Staples", "FMCG"),
    "BHARTIARTL": ("Communication Services", "Telecom"),
    "MARUTI": ("Consumer Discretionary", "Automobile"),
    "SUNPHARMA": ("Healthcare", "Pharmaceuticals"),
}

# Approximate market beta per symbol, used to inject realistic co-movement
# (a shared market factor) into the otherwise-independent per-stock random
# walks below. Without this, synthetic stocks would show near-zero
# correlation with each other, which is unrealistic and undersells the
# correlation/risk-contribution analytics.
BETAS: dict[str, float] = {
    "TCS": 0.85,
    "INFY": 0.9,
    "WIPRO": 0.85,
    "RELIANCE": 1.05,
    "HDFCBANK": 1.1,
    "ICICIBANK": 1.15,
    "SBIN": 1.25,
    "LT": 1.0,
    "ITC": 0.6,
    "HINDUNILVR": 0.55,
    "BHARTIARTL": 0.9,
    "MARUTI": 1.0,
    "SUNPHARMA": 0.5,
}

STOCK_NAMES: dict[str, str] = {
    "TCS": "Tata Consultancy Services",
    "RELIANCE": "Reliance Industries",
    "HDFCBANK": "HDFC Bank",
    "INFY": "Infosys",
    "ICICIBANK": "ICICI Bank",
    "LT": "Larsen & Toubro",
    "ITC": "ITC Limited",
    "HINDUNILVR": "Hindustan Unilever",
    "BHARTIARTL": "Bharti Airtel",
    "SBIN": "State Bank of India",
    "WIPRO": "Wipro",
    "MARUTI": "Maruti Suzuki India",
    "SUNPHARMA": "Sun Pharmaceutical Industries",
}


@dataclass
class OHLCVBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketDataProvider(ABC):
    source: DataSource

    @abstractmethod
    def get_history(self, symbol: str, days: int = 365) -> list[OHLCVBar]:
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> OHLCVBar:
        ...


class DevSampleProvider(MarketDataProvider):
    """Deterministic synthetic OHLCV generator.

    NOTE: This is clearly-labeled development sample data, not real market
    data. It uses a per-symbol seeded random walk so results are stable
    across runs (important for reproducible demos and ML training).
    """

    source = DataSource.DEV_SAMPLE

    def _seed_for(self, symbol: str) -> int:
        return int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % (2**31)

    def _market_shocks(self, all_dates: list[date]) -> list[float]:
        """Shared daily market-factor shocks, same for every symbol/run (fixed seed).

        Injecting a common factor gives synthetic stocks realistic
        (positive, sector-correlated) co-movement instead of being
        statistically independent of each other.
        """
        market_rng = random.Random(20240101)
        return [market_rng.gauss(0, 0.011) for _ in all_dates]

    def get_history(self, symbol: str, days: int = 365) -> list[OHLCVBar]:
        base_price = BASE_PRICES.get(symbol, 1000.0)
        rng = random.Random(self._seed_for(symbol))
        beta = BETAS.get(symbol, 1.0)

        bars: list[OHLCVBar] = []
        price = base_price * 0.85  # start a bit below "current" so there's a visible trend
        today = date.today()

        # simple drift + mean-reversion + noise random walk, business days only
        annual_drift = rng.uniform(0.04, 0.14)
        daily_drift = annual_drift / 252
        daily_vol = rng.uniform(0.012, 0.024)

        all_dates: list[date] = []
        d = today - timedelta(days=days)
        while d <= today:
            if d.weekday() < 5:
                all_dates.append(d)
            d += timedelta(days=1)

        market_shocks = self._market_shocks(all_dates)

        for i, d in enumerate(all_dates):
            idiosyncratic_shock = rng.gauss(0, daily_vol * 0.7)
            market_shock = beta * market_shocks[i]
            mean_reversion = (base_price - price) / base_price * 0.02
            change = daily_drift + idiosyncratic_shock + market_shock + mean_reversion
            open_p = price
            close_p = max(price * (1 + change), 1.0)
            high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, daily_vol / 2)))
            low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, daily_vol / 2)))
            volume = int(rng.uniform(0.6, 1.6) * 2_500_000)

            bars.append(
                OHLCVBar(
                    date=d,
                    open=round(open_p, 2),
                    high=round(high_p, 2),
                    low=round(low_p, 2),
                    close=round(close_p, 2),
                    volume=volume,
                )
            )
            price = close_p

        return bars

    def get_quote(self, symbol: str) -> OHLCVBar:
        history = self.get_history(symbol, days=5)
        return history[-1]


class LiveYFinanceProvider(MarketDataProvider):
    """Real market-data provider backed by Yahoo Finance via yfinance.

    Requires outbound internet access and the ``yfinance`` package. Not used
    by default in this development environment (no external network access),
    but implemented so a production deployment can flip ``USE_LIVE_MARKET_DATA``
    on without any other code changes.
    """

    source = DataSource.LIVE

    def get_history(self, symbol: str, days: int = 365) -> list[OHLCVBar]:
        import yfinance as yf  # local import: optional dependency

        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period=f"{days}d")
        bars = []
        for idx, row in hist.iterrows():
            bars.append(
                OHLCVBar(
                    date=idx.date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                )
            )
        return bars

    def get_quote(self, symbol: str) -> OHLCVBar:
        history = self.get_history(symbol, days=5)
        if not history:
            raise ValueError(f"No live data available for {symbol}")
        return history[-1]


def get_provider(use_live: bool) -> MarketDataProvider:
    if use_live:
        return LiveYFinanceProvider()
    return DevSampleProvider()
