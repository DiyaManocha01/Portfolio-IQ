"""Scenario text -> structured shock parameters (Phase 15).

A DELIBERATELY NARROW, deterministic regex pattern-matcher -- NOT a
natural-language-understanding system and NOT an LLM call. It recognizes
a small, fixed set of phrasings ("IT stocks crash 20%", "market falls
15%", "-10% for Healthcare") and translates them into the exact same
structured `market_shock_pct` / `sector_shocks` parameters that
`StressTestService.apply_shock()` already accepts.

This module NEVER computes a shock's impact and NEVER says anything
advisory -- it only produces parameters. Text it cannot confidently parse
raises `ScenarioParseError` rather than guessing; a wrong guess here would
silently misrepresent what the user asked for, which this project's
working rules treat as worse than refusing to parse at all.

Known, documented limitation (see docs/limitations.md): sector aliases
are matched as whole words in the input text. A short, common-English
alias (e.g. a bare "IT" as a pronoun) would be a false-positive risk, so
ambiguous short aliases are deliberately excluded from SECTOR_ALIASES in
favor of more specific phrasings ("tech", "technology", "IT stocks",
"IT sector").
"""

from __future__ import annotations

import re

SECTOR_ALIASES: dict[str, str] = {
    "information technology": "Information Technology",
    "it sector": "Information Technology",
    "it stocks": "Information Technology",
    "tech": "Information Technology",
    "technology": "Information Technology",
    "financial services": "Financial Services",
    "banking": "Financial Services",
    "banks": "Financial Services",
    "bank stocks": "Financial Services",
    "financials": "Financial Services",
    "healthcare": "Healthcare",
    "pharma": "Healthcare",
    "pharmaceuticals": "Healthcare",
    "energy": "Energy",
    "oil and gas": "Energy",
    "oil": "Energy",
    "consumer discretionary": "Consumer Discretionary",
    "auto": "Consumer Discretionary",
    "automobile": "Consumer Discretionary",
    "automobiles": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "fmcg": "Consumer Staples",
    "staples": "Consumer Staples",
    "communication services": "Communication Services",
    "telecom": "Communication Services",
    "industrials": "Industrials",
    "infrastructure": "Industrials",
}

MARKET_WORDS = ("market", "markets", "broad market", "overall market", "stocks", "equities", "nifty", "index")

NEGATIVE_WORDS = (
    "crash", "crashes", "crashed", "crashing",
    "drop", "drops", "dropped", "dropping",
    "fall", "falls", "fell", "falling",
    "decline", "declines", "declined", "declining",
    "plunge", "plunges", "plunged", "plunging",
    "tank", "tanks", "tanked", "tanking",
    "slump", "slumps", "slumped", "slumping",
)
POSITIVE_WORDS = (
    "rally", "rallies", "rallied", "rallying",
    "rise", "rises", "rose", "rising",
    "gain", "gains", "gained", "gaining",
    "surge", "surges", "surged", "surging",
    "jump", "jumps", "jumped", "jumping",
)

_PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)


class ScenarioParseError(ValueError):
    """Raised when scenario text can't be confidently parsed -- never
    guess a shock direction, magnitude, or target."""


def parse_scenario_text(text: str) -> dict:
    """Returns {"market_shock_pct": float} or {"sector_shocks": {sector: float}}.
    Raises ScenarioParseError if magnitude, direction, or target can't be
    confidently identified."""
    lowered = text.lower()

    match = _PERCENT_RE.search(lowered)
    if not match:
        raise ScenarioParseError(f"No percentage magnitude found in: {text!r}")
    magnitude = abs(float(match.group(1)))
    explicit_negative = match.group(1).strip().startswith("-")

    has_negative_word = any(re.search(rf"\b{word}\b", lowered) for word in NEGATIVE_WORDS)
    has_positive_word = any(re.search(rf"\b{word}\b", lowered) for word in POSITIVE_WORDS)

    if explicit_negative and not has_positive_word:
        sign = -1
    elif has_negative_word and not has_positive_word:
        sign = -1
    elif has_positive_word and not has_negative_word and not explicit_negative:
        sign = 1
    else:
        raise ScenarioParseError(
            f"Could not determine a clear direction (gain or loss) from: {text!r}"
        )

    shock_pct = sign * (magnitude / 100.0)

    matched_sector = None
    matched_alias_len = -1
    for alias, sector in SECTOR_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered) and len(alias) > matched_alias_len:
            matched_sector = sector
            matched_alias_len = len(alias)

    if matched_sector:
        return {"sector_shocks": {matched_sector: shock_pct}}

    if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in MARKET_WORDS):
        return {"market_shock_pct": shock_pct}

    raise ScenarioParseError(
        f"Could not identify a sector or 'market' target in: {text!r}. "
        f"Known sectors: {sorted(set(SECTOR_ALIASES.values()))}"
    )
