"""The AI portfolio assistant (Phase 19).

Architecture: retrieval-and-cite, never compute.

1. app.assistant.context_builder deterministically fetches already-
   computed data relevant to the question (portfolio summary/health/
   weaknesses always; stock predictions/sentiment, risk attribution,
   discovery candidates, or the prediction ledger's track record only
   when the question's own text calls for them).
2. That data -- and ONLY that data -- is handed to Claude as context,
   with a system prompt instructing it to answer solely from what it was
   given, cite real numbers from it, and refuse (not guess) when the
   question needs something outside that data. The assistant has no
   tool-calling or code-execution ability here: it cannot compute a new
   number even if it wanted to, because nothing in this request gives it
   a way to.
3. A SEPARATE, deterministic keyword guardrail (_contains_advice_language)
   scans the model's own response for buy/sell-advice or price-prediction
   phrasing as defense-in-depth, independent of the system prompt. This
   is the one part of this module that's meaningfully unit-testable
   without a live API key -- the LLM call itself is not (see
   docs/limitations.md).
"""

from __future__ import annotations

import json
import re

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.assistant.context_builder import build_context
from app.config import settings
from app.models.portfolio import Portfolio

STANDARD_DISCLAIMER = (
    "PortfolioIQ is an educational and analytical decision-support system. "
    "Its predictions and portfolio analytics are model-based estimates and "
    "are not guaranteed financial advice."
)

GUARDRAIL_FALLBACK_MESSAGE = (
    "I can't answer that directly -- my response was flagged as sounding like "
    "specific buy/sell advice or a price prediction, which I'm not allowed to "
    "give. Try asking about what the data actually shows (e.g. 'what's my "
    "portfolio's risk contribution by holding?') instead of what you should do."
)

SYSTEM_PROMPT = """You are the PortfolioIQ assistant, answering questions about a user's \
investment portfolio using ONLY the data block provided in each message -- you have no \
other source of information about their portfolio, the market, or any stock.

Hard rules, no exceptions:
1. Answer ONLY using the JSON data block you are given. If the data needed to answer isn't \
in it, say so explicitly and suggest what the user could check instead (e.g. a specific \
page/endpoint) -- never guess, estimate, or fill the gap from general knowledge.
2. When you state a number, it must be a number that actually appears in the data block. \
Cite it near-verbatim (e.g. "your portfolio's annualized volatility is 19.75%") rather than \
paraphrasing it into a different number.
3. NEVER recommend buying, selling, or holding any specific stock, and NEVER say a price, \
return, or portfolio value will or should reach any level in the future. Model predictions \
in the data are probabilistic estimates with a confidence level -- always describe them that \
way ("the model's probabilistic estimate is...", never "it will go up").
4. If asked directly for a recommendation ("should I buy X", "what should I do"), decline \
clearly, explain this system reports data and probabilistic estimates rather than advice, \
and offer to summarize what the relevant data actually shows instead.
5. Keep answers grounded, specific, and reasonably concise. Use the user's own numbers, not \
generic market commentary.
6. Every answer must be consistent with being read alongside this disclaimer, which is \
always shown with your answer: "{disclaimer}" """.format(disclaimer=STANDARD_DISCLAIMER)

_ADVICE_PATTERNS = [
    r"\byou should (buy|sell|hold|invest)\b",
    r"\bi recommend (buying|selling|holding)\b",
    r"\b(strong|definite(ly)?) (buy|sell)\b",
    r"\b(buy|sell) (it |this |that )?now\b",
    r"\bguaranteed? (return|profit|gain)s?\b",
    r"\bwill (definitely |certainly )?(go up|go down|rise|fall|increase|decrease)\b",
    r"\bis going to (rise|fall|surge|crash|rally)\b",
    r"\byou (must|need to) (buy|sell)\b",
]
_ADVICE_RE = re.compile("|".join(_ADVICE_PATTERNS), re.IGNORECASE)


class AssistantNotConfiguredError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY isn't set -- callers should surface
    this as a clear 503, not an unhandled crash."""


def contains_advice_language(text: str) -> tuple[bool, str | None]:
    """Deterministic keyword guardrail -- returns (tripped, matched_text).
    Not semantic (can't catch everything a cleverly-phrased response might
    imply), but fully unit-testable, unlike the LLM call itself."""
    match = _ADVICE_RE.search(text)
    if match:
        return True, match.group(0)
    return False, None


def ask(db: Session, portfolio: Portfolio, question: str) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        raise AssistantNotConfiguredError(
            "The AI assistant is not configured -- set ANTHROPIC_API_KEY in your local .env. "
            "See docs/methodology.md Section 16."
        )

    built = build_context(db, portfolio, question)
    context_json = json.dumps(built["context"], indent=2, default=str)

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.ASSISTANT_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"DATA (the ONLY information you have about this portfolio):\n{context_json}\n\nQUESTION: {question}",
            }
        ],
    )
    answer = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")

    guardrail_tripped, matched_phrase = contains_advice_language(answer)
    if guardrail_tripped:
        answer = GUARDRAIL_FALLBACK_MESSAGE

    return {
        "answer": answer,
        "sources_used": built["sources_used"],
        "guardrail_tripped": guardrail_tripped,
        "guardrail_matched_phrase": matched_phrase if guardrail_tripped else None,
        "model": settings.ASSISTANT_MODEL,
        "disclaimer": STANDARD_DISCLAIMER,
    }
