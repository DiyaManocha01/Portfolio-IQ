"""FinBERT-backed sentiment provider (real transformer model).

Requires the ``transformers`` and ``torch`` packages and internet access to
download ``ProsusAI/finbert`` from Hugging Face on first use. Disabled by
default in this development environment (``USE_FINBERT=false`` in .env)
because this sandbox has no outbound access to huggingface.co. The
architecture is fully wired up so flipping the flag on a machine with
internet access (and the extra packages installed) requires no other code
changes -- see ``app.nlp.sentiment_service.get_sentiment_provider``.
"""

from __future__ import annotations

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline  # optional dependency, imported lazily

        _pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    return _pipeline


def score_text(text: str) -> tuple[float, str]:
    """Returns (score in [-1, 1], label)."""
    clf = _get_pipeline()
    result = clf(text[:512])[0]
    label = result["label"].upper()
    confidence = float(result["score"])
    if label == "POSITIVE":
        return confidence, "POSITIVE"
    if label == "NEGATIVE":
        return -confidence, "NEGATIVE"
    return 0.0, "NEUTRAL"
