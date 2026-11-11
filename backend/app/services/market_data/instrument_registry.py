"""Resolves PortfolioIQ symbols against a broker's OFFICIAL instrument master.

Never invents a security/instrument token. The actual Angel One scrip
master requires outbound network access this sandbox doesn't have (same
constraint as nifty100.py / the yfinance cache -- verified), so the
resolved-token file this module reads is produced by running
``backend/scripts/fetch_angelone_instruments.py`` on a machine with real
internet access, exactly the ``fetch_nifty100.py`` pattern already used for
OHLCV history. Until that's been run, ``is_ready()`` is False and
``resolve_all()`` reports every watchlist symbol as unresolved rather than
guessing at a token.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INSTRUMENTS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "angelone_instruments.json"
)


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str
    trading_symbol: str
    token: str


class InstrumentRegistry:
    def __init__(self, source_path: Path | None = None) -> None:
        self._path = source_path or DEFAULT_INSTRUMENTS_PATH
        self._instruments: dict[str, Instrument] | None = None

    def is_ready(self) -> bool:
        return self._path.exists()

    def _load(self) -> dict[str, Instrument]:
        if self._instruments is not None:
            return self._instruments
        if not self._path.exists():
            self._instruments = {}
            return self._instruments
        raw = json.loads(self._path.read_text())
        instruments: dict[str, Instrument] = {}
        for symbol, entry in raw.items():
            if symbol.startswith("_"):  # e.g. "_NOTE" in hand-written test fixtures
                continue
            instruments[symbol] = Instrument(
                symbol=symbol,
                exchange=entry["exchange"],
                trading_symbol=entry["tradingsymbol"],
                token=entry["symboltoken"],
            )
        self._instruments = instruments
        return instruments

    def reload(self) -> None:
        """Forces the next call to re-read the file (tests swap files mid-run)."""
        self._instruments = None

    def resolve(self, symbol: str) -> Instrument | None:
        return self._load().get(symbol.upper())

    def resolve_all(self, symbols: list[str]) -> tuple[dict[str, Instrument], list[str]]:
        """Returns (resolved, missing). ``missing`` is reported, never fabricated."""
        resolved: dict[str, Instrument] = {}
        missing: list[str] = []
        for symbol in symbols:
            instrument = self.resolve(symbol)
            if instrument is None:
                missing.append(symbol)
            else:
                resolved[symbol] = instrument
        return resolved, missing


# Process-wide singleton, same rationale as live_cache.
instrument_registry = InstrumentRegistry()
