"""Lightweight, dependency-free financial sentiment provider.

This is the DEFAULT sentiment provider in this development environment
(see ``app.nlp.sentiment_service``). It uses a small weighted financial
lexicon rather than a neural network, so it has no model-download
requirement and runs instantly. It is intentionally simple and is not a
substitute for FinBERT -- see ``app.nlp.finbert_sentiment`` for the real
transformer-based provider, which can be enabled via ``USE_FINBERT=true``
on a machine with internet access.
"""

from __future__ import annotations

import re

POSITIVE_WORDS = {
    "surge": 0.8, "surges": 0.8, "soar": 0.9, "soars": 0.9, "rally": 0.7, "rallies": 0.7,
    "beat": 0.6, "beats": 0.6, "outperform": 0.7, "outperforms": 0.7, "upgrade": 0.7,
    "upgraded": 0.7, "growth": 0.5, "profit": 0.5, "profits": 0.5, "gain": 0.5, "gains": 0.5,
    "record": 0.6, "strong": 0.5, "robust": 0.6, "expansion": 0.5, "bullish": 0.8,
    "positive": 0.5, "optimistic": 0.6, "improve": 0.4, "improves": 0.4, "improved": 0.4,
    "boost": 0.5, "boosts": 0.5, "win": 0.5, "wins": 0.5, "exceed": 0.6, "exceeds": 0.6,
    "rise": 0.5, "rises": 0.5, "jump": 0.6, "jumps": 0.6, "high": 0.3, "recovery": 0.5,
}

NEGATIVE_WORDS = {
    "plunge": -0.9, "plunges": -0.9, "crash": -0.9, "crashes": -0.9, "slump": -0.7,
    "slumps": -0.7, "miss": -0.6, "misses": -0.6, "downgrade": -0.7, "downgraded": -0.7,
    "loss": -0.6, "losses": -0.6, "decline": -0.5, "declines": -0.5, "fall": -0.5,
    "falls": -0.5, "weak": -0.5, "bearish": -0.8, "negative": -0.5, "pessimistic": -0.6,
    "concern": -0.4, "concerns": -0.4, "risk": -0.3, "risks": -0.3, "cut": -0.5, "cuts": -0.5,
    "lawsuit": -0.6, "fraud": -0.9, "investigation": -0.6, "layoff": -0.7, "layoffs": -0.7,
    "recession": -0.7, "volatile": -0.4, "volatility": -0.3, "drop": -0.5, "drops": -0.5,
    "underperform": -0.6, "underperforms": -0.6, "delay": -0.4, "delays": -0.4,
}

_WORD_RE = re.compile(r"[a-zA-Z']+")


def score_text(text: str) -> float:
    """Returns a sentiment score in [-1, 1]."""
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return 0.0
    total = 0.0
    hits = 0
    for w in words:
        if w in POSITIVE_WORDS:
            total += POSITIVE_WORDS[w]
            hits += 1
        elif w in NEGATIVE_WORDS:
            total += NEGATIVE_WORDS[w]
            hits += 1
    if hits == 0:
        return 0.0
    # average weighted hits, damped slightly by how sparse the hits are
    raw = total / hits
    damped = raw * min(1.0, hits / 3)
    return max(-1.0, min(1.0, damped))


def label_for_score(score: float) -> str:
    if score >= 0.15:
        return "POSITIVE"
    if score <= -0.15:
        return "NEGATIVE"
    return "NEUTRAL"
