"""What-if question text -> WhatIfService input (Phase 32).

A DELIBERATELY NARROW, deterministic regex pattern-matcher -- NOT a
natural-language-understanding system and NOT an LLM call. Same
philosophy as Phase 15's ``app/portfolio/scenario_parser.py``: it
recognizes a small, fixed set of phrasings and translates them into the
exact structured ``changes`` list ``WhatIfService.simulate`` already
accepts (``[{"symbol": str, "new_quantity": float}]``, an ABSOLUTE
target quantity).

Deliberately conservative scope (a project decision, not a limitation to
later lift casually -- see docs/adr/0015-assistant-context-expansion.md):
only two phrasings are recognized --

1. "added/bought N shares of SYMBOL" or "sold/removed N shares of SYMBOL"
   -- an explicit share count, added to or subtracted from the current
   holding (floored at zero on a sell).
2. "sold/removed all/my entire SYMBOL" -- a full exit, new_quantity = 0.

Anything else -- weight-based phrasing ("at 10% weight"), no quantity
given, more than one stock mentioned, or an ambiguous mix of add/remove
language -- returns None rather than guessing a default quantity or
target. This project's working rules treat a silently wrong hypothetical
as worse than refusing to simulate one at all: the caller (context_builder)
surfaces the None as an explicit "couldn't parse a specific hypothetical
from this question" note, so the assistant asks the user to be specific or
points them at the Portfolio Lab's What-If page instead of guessing.
"""

from __future__ import annotations

import re

_QUANTITY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:shares?|units?)\b", re.IGNORECASE)

_ADD_VERBS = ("add", "added", "adding", "buy", "bought", "buying", "purchase", "purchased", "purchasing")
_REMOVE_VERBS = ("sell", "sold", "selling", "remove", "removed", "removing")
_FULL_REMOVAL_PHRASES = (
    "all my", "all of my", "my entire", "entirely", "the entire", "my whole", "completely",
)


def parse_whatif_question(
    question: str,
    mentioned_symbols: list[str],
    current_quantities: dict[str, float],
) -> dict | None:
    """Returns {"symbol": str, "new_quantity": float, "note": str} if a
    single, unambiguous hypothetical change could be confidently
    extracted, else None. Never called with more than one mentioned
    symbol -- a multi-stock hypothetical is out of scope for this
    conservative parser (see module docstring)."""
    if len(mentioned_symbols) != 1:
        return None

    symbol = mentioned_symbols[0]
    lowered = question.lower()
    current = current_quantities.get(symbol, 0.0)

    is_add = any(re.search(rf"\b{v}\b", lowered) for v in _ADD_VERBS)
    is_remove = any(re.search(rf"\b{v}\b", lowered) for v in _REMOVE_VERBS)
    if is_add == is_remove:
        # Neither verb found, or both (ambiguous) -- refuse rather than guess.
        return None

    if is_remove and any(phrase in lowered for phrase in _FULL_REMOVAL_PHRASES):
        return {
            "symbol": symbol,
            "new_quantity": 0.0,
            "note": f"Interpreted as fully exiting the {symbol} position (currently {current} shares).",
        }

    quantity_match = _QUANTITY_RE.search(lowered)
    if not quantity_match:
        return None
    quantity = float(quantity_match.group(1))
    if quantity <= 0:
        return None

    if is_add:
        new_quantity = current + quantity
        note = f"Interpreted as adding {quantity} shares of {symbol} to the current {current}."
    else:
        new_quantity = max(current - quantity, 0.0)
        note = f"Interpreted as selling {quantity} shares of {symbol} from the current {current}."

    return {"symbol": symbol, "new_quantity": round(new_quantity, 4), "note": note}
