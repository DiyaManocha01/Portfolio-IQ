# ADR 0015: AI Assistant Context Expansion (Phase 32)

**Status:** Accepted
**Date:** 2026-11-12

## Context

Phase 32 asked for the assistant to answer using actual computed
platform data covering: stock analysis, portfolio risk, Fit Engine
results, market conditions, news sentiment, historical performance, and
What-If simulations -- citing the data and timestamps used, never
inventing or independently calculating a financial number, and never
giving buy/sell instructions or guaranteed-return language.

Auditing `app/assistant/context_builder.py` (Phase 19) against that list
found portfolio risk, stock sentiment, and (via `RISK_KEYWORDS`) risk
attribution already wired, but four sources completely missing -- Fit
Engine results, market conditions, historical performance, What-If
simulations -- and two only partially covered: `stock_details` had
prediction + sentiment but no technical indicators ("stock analysis" is
broader than a directional prediction), and nothing carried an explicit
timestamp a citation could point to.

## Decision

### Four new keyword-triggered context blocks, same pattern as Phase 19

`FIT_KEYWORDS`, `MARKET_KEYWORDS`, and `PERFORMANCE_KEYWORDS` follow the
exact existing `RISK_KEYWORDS`/`DISCOVER_KEYWORDS` pattern: plain
substring matching on the lowered question text, decided entirely in
`context_builder.py`, never by asking the LLM what it needs.

- `fit_engine`: for each mentioned stock, `fit_snapshot_service.
  get_fit_with_change` (Phase 29's cached Fit Engine, reused as-is).
- `market_conditions`: NIFTY 50's regime always included when triggered,
  plus any mentioned stock's own regime, via `market_regime_service.
  classify_regime` (Phase 30, reused as-is) over the same
  `REGIME_HISTORY_DAYS` window `GET /market/regime` itself uses.
- `historical_performance`: a *summary* of `portfolio_performance_service.
  get_advanced_performance` (Phase 31) -- unrealized/realized/total P&L,
  realized volatility, latest cumulative return, max drawdown, and the
  top holding/sector contributions -- not the full day-by-day series.
  The full series already has a dedicated UI (Phase 31's Advanced
  Performance section); handing an LLM hundreds of daily points to
  summarize in prose would risk exactly the kind of restating-as-a-
  slightly-different-number this project's rules exist to prevent, for
  no benefit over summarizing it once, deterministically, in code.

`stock_details` additionally fetches `analytics.compute_indicators`
(the same indicator set `GET /stocks/{symbol}` already serves) for each
mentioned stock, closing the "stock analysis" gap.

### What-If simulations: parse conservatively, refuse rather than guess

A new `app/assistant/whatif_parser.py`, styled after Phase 15's
`scenario_parser.py`, recognizes exactly two phrasings against a single
mentioned stock: an explicit share count ("added 10 shares of X" /
"sold 10 shares of X", added to or subtracted from the current holding)
and a full-exit phrase ("sold all my X"). It returns `None` -- not a
guess -- for anything else: weight-based phrasing ("at 10% weight"), no
mentioned stock or more than one, no extractable quantity, or
conflicting add/remove language in the same question.

This scope was a deliberate choice put to the project owner rather than
decided unilaterally (two options: conservative share-count-only parsing
vs. also supporting weight-based phrasing by reusing Phase 10's
`hypothetical.py`); **conservative was chosen**. When `WHATIF_KEYWORDS`
fire but the parser returns `None`, the context block still exists --
`{"could_not_parse": True, "note": "..."}"`-- explaining to the LLM
*why* nothing could be run, so the system prompt can have it say so
plainly and point the user at the Portfolio Lab's What-If Simulator,
rather than silently omitting the block and leaving the LLM to guess
why. A successful parse calls the existing `WhatIfService.simulate`
(Phase 11) unchanged and returns its real output plus the parser's own
`interpreted_as` note, so the user can see exactly what scenario was
actually run.

### Timestamp citation: a top-level `context_compiled_at`, not retrofitted into every block

Phase 29/30/31's services already attach their own `computed_at`/`as_of`
field to the data they return (`fit_engine`, `market_conditions`,
`historical_performance.as_of`). Rather than retrofitting a timestamp
field onto Phase 19's older blocks (`portfolio_summary`, `portfolio_
health`, `portfolio_weaknesses`, `stock_details`) -- which would be
scope creep on data these services were never asked to timestamp, and
risks overstating precision data cached hours or days ago doesn't
have -- `build_context` now always adds a single top-level
`context_compiled_at` (UTC, wall-clock time of that `build_context`
call). The system prompt (rule 6) instructs the assistant to cite a
block's own `as_of`/`computed_at` when present, and fall back to
`context_compiled_at` otherwise -- so every number is citable as of
*some* timestamp without inventing per-block dates that don't exist.

### System prompt: two new rules, not a rewrite

Rule 6 (timestamp citation, above) and rule 7 (a `what_if_simulation`
block is always a hypothetical, never advice or a prediction; a
`could_not_parse`/`could_not_simulate` result must be relayed plainly,
never papered over with an invented plausible-sounding answer) are
appended to the existing six rules. Rules 1-5 (answer only from the data
block, cite numbers near-verbatim, never recommend or predict, decline
direct advice requests, stay concise and specific) are unchanged.

## Consequences

- No new dependencies -- every new block reuses an already-vetted
  service (Phase 11/29/30/31) and the standard-library `datetime`.
- New file: `app/assistant/whatif_parser.py`.
- `context_builder.py` grows four new keyword tuples and four new
  trigger blocks; `assistant_service.py`'s `SYSTEM_PROMPT` grows two
  rules.
- 15 new backend tests (one per new trigger included/excluded, the
  timestamp field, technical indicators in `stock_details`, and the
  parser's accept/refuse cases) -- all deterministic, no live LLM call,
  consistent with how Phase 19 itself was tested.
- **Known limitation, by design, not an oversight**: the What-If parser
  cannot handle weight-based phrasing, multiple stocks in one question,
  or a quantity-free request ("what if I added some RELIANCE") -- it
  reports `could_not_parse` for all of these rather than guessing. See
  docs/limitations.md.
- The live Claude API call itself (whether it actually cites timestamps,
  phrases a what-if result as hypothetical, etc. in practice) is still
  untested in this sandbox for the same reason Phase 19's LLM call was
  never tested -- no network access to the Anthropic API here. The
  deterministic guardrail and the context contents it's fed remain the
  tested, enforceable boundary.
