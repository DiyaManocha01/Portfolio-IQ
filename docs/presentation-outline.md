# Presentation Outline (Phase 23)

A structured outline for a demo/defense deck — section headers, the key
point(s) each slide should make, and a suggested visual. **This is an
outline to build a deck from, not a built `.pptx`.** Every claim listed
here traces to `docs/methodology.md` or a real test/measurement already
in the repo — do not add a number to a slide that isn't in that document
or reproducible from it (per `CLAUDE.md` rule 5).

Target length: ~15-18 slides for a 12-15 minute presentation + Q&A
(typical project defense format). Cut slides 11/13/15 first if time is
tight — they're depth, not core narrative.

---

## 1. Title

- Project name, one-line tagline, your name/institution, date.
- Visual: reuse the one-page project summary's hero treatment (color
  palette, typography) for brand consistency across both artifacts.

## 2. The problem

- Key point: existing stock-analysis tools evaluate a stock in isolation
  ("is TCS a good buy?") — none answer "is TCS good *for my portfolio
  specifically*?" A stock that's objectively strong can still be a bad
  addition if it duplicates a sector you're already overweight in.
- Visual: two logos/mockups side by side — "generic stock screener" vs.
  "PortfolioIQ" — or a simple diagram showing the same stock scoring
  differently against two different example portfolios.

## 3. The core idea — the Portfolio Fit Engine

- Key point: rank candidates by the *change* they'd cause to risk,
  diversification, and sector concentration, combined with ML outlook
  and sentiment — not by standalone stock quality.
- Show the formula (methodology.md Section 7.1):
  `Fit = σ(w1·Outlook + w2·Sentiment − w3·ΔRisk + w4·ΔDiversification − w5·ΔConcentration)`
- Visual: the formula, large and simple — this is the one slide the
  audience should remember.

## 4. System architecture

- Key point: thin API routes → services (all business logic) → ORM →
  Postgres, with a provider-abstraction pattern (market data, sentiment)
  that lets live data drop in without touching calling code.
- Visual: the architecture diagram from `docs/ARCHITECTURE.md` (the
  ```frontend -> FastAPI -> routes -> services -> models -> Postgres```
  block), redrawn cleanly for slides.

## 5. Tech stack

- Key point: full-stack, production-shaped choices (not toy tooling) —
  React/TS, FastAPI, Postgres+Alembic, scikit-learn/XGBoost, SHAP,
  PyPortfolioOpt, Docker Compose.
- Visual: logo/pill row (reuse the one-pager's stack section).

## 6. Live demo — Portfolio Fit in action

- Key point: this is the centerpiece. Walk through `/discover` →
  click a candidate → `/portfolio-fit/{symbol}` factor breakdown →
  "Compare to Another Stock" → "What would improve this fit?"
- Visual: live app (or screenshots as fallback) — screenshots already
  exist from Phase 20 verification; recapture fresh ones for the deck if
  the seeded data has changed.
- Script note: narrate the factor breakdown out loud — "this stock adds
  +0.64 to the diversification term because it's in a sector I don't
  hold" is a concrete, defensible sentence to say live.

## 7. Live demo — Portfolio Lab (What-If + Optimization)

- Key point: hypothetical simulation that never touches the real
  portfolio — show a before/after risk change from a simulated trade,
  and an optimizer suggestion with its disclaimer visible.
- Visual: live app, Portfolio Lab page.

## 8. ML pipeline — methodology, not just a model

- Key point: purged walk-forward cross-validation (not a shuffled
  train/test split — explain *why* that matters for time-series: a
  shuffled split leaks future information into training). Calibrated
  probability output, baselines always computed alongside the model.
- Visual: a simple timeline diagram of the purged walk-forward folds
  (blocks of train/test, with the purge gap marked) — methodology.md
  Section 3.3 describes exactly what to draw.

## 9. ML results — reported honestly

- Key point: test AUC ≈ 0.545 on synthetic training data — close to
  random, and *that's the correct, expected result*, not a failure to
  hide. Explain why: a synthetic random walk has very little true
  learnable signal by construction; the number is honest, not inflated.
- Visual: a simple bar comparing majority-class baseline / momentum
  baseline / the model's AUC — three bars, the model only modestly ahead.
- This slide is a credibility move, not a weakness to downplay: explain
  to the panel *why* reporting an unimpressive number honestly, with the
  reasoning next to it, is itself the point of the project's design
  philosophy (see slide 14).

## 10. Backtest — the same finding from a trading angle

- Key point: the ML strategy underperforms buy-and-hold in the backtest
  (Sharpe -0.459 vs. +0.233) — consistent with the AUC result, not a
  separate bad outcome. The paired bootstrap shows this isn't
  distinguishable from "no effect" either way at this sample size.
- Visual: the three-strategy comparison table from methodology.md
  Section 10.5 (ML / buy-and-hold / momentum), simplified to the Sharpe
  row only for a slide.

## 11. Explainability — SHAP, counterfactuals, risk attribution

- Key point: three different explanation layers answer three different
  questions — SHAP ("why did the model predict this"), Fit
  counterfactuals ("why does A rank above B / what would improve this
  stock's fit"), risk attribution ("which holding is contributing more
  risk than its money weight suggests"). All three are exact
  decompositions or algebraic identities where the methodology allows it
  (sum of SHAP values, sum of term deltas) — not approximations.
- Visual: three small panels, one per explanation type, each showing its
  real example number from methodology.md (Sections 11.5, 13.4, 14.6).

## 12. Trust infrastructure — the prediction ledger

- Key point: every prediction is appended to a hash-chained,
  database-trigger-enforced, publicly verifiable ledger — tamper-evident
  by construction, demonstrated against a simulated privileged tamper
  attempt, not just claimed.
- Visual: a simple hash-chain diagram (entry N's hash depends on entry
  N-1's hash + its own payload) and the public `/ledger/verify` response
  shape.

## 13. The AI assistant — retrieval-and-cite, not a chatbot that guesses

- Key point: the assistant never computes a new number — it only cites
  already-computed data, with a system prompt plus a separate regex
  guardrail against advice-like language as defense-in-depth.
- Visual: the architecture from methodology.md Section 16.1 — question →
  deterministic context builder → Claude (data-only) → guardrail filter
  → answer.

## 14. Engineering discipline — how this was built

- Key point: 22 phases, each ending in passing tests + updated docs + a
  commit, with ADRs recorded whenever a phase superseded earlier
  behavior rather than silently changing it. 270 automated tests
  (233 backend + 37 frontend). A documented, append-only methodology
  doc (`docs/methodology.md`) traces every number in the app back to the
  function that computed it.
- Visual: a simple phase timeline (1→22) with category color-coding
  (foundation / simulation / trust / hardening), or the phase table from
  `docs/ROADMAP.md`.

## 15. Security & deployment maturity

- Key point: a real dependency-vulnerability audit (42 findings → 1,
  with the remainder explicitly deferred and why), rate limiting on
  auth/assistant endpoints, Docker Compose for full-stack deployment.
- Visual: the before/after vulnerability count, simply stated.

## 16. Limitations — stated, not hidden

- Key point: synthetic DEV_SAMPLE data in this environment (verified
  network-blocked, not just untried), the NIFTY 100 list unverified
  against a live source, the DSR formula not independently verified
  against the original paper, Docker Compose not yet run end-to-end from
  this sandbox. Every one of these is written down in
  `docs/limitations.md` with the reasoning, not glossed over.
- Visual: plain text list — this slide works better quiet than busy.

## 17. What's next

- Key point: run every live-data path for real (already built, never
  executed against the real internet here), re-verify the NIFTY 100
  list, re-measure every synthetic-data number against real NIFTY data,
  then the genuinely-unstarted items (geopolitical intelligence, alerts,
  portfolio evolution tracking) from `docs/ROADMAP.md`.
- Visual: short bullet list, 4-5 items max.

## 18. Thank you / Q&A

- Repo link (`github.com/DiyaManocha01/Portfolio-IQ`), your contact info.
- Visual: same hero treatment as the title slide, for bookending.

---

## Anticipated questions worth pre-preparing an answer for

- *"Why is the AUC so low?"* — Slide 9's answer, memorized: synthetic
  random-walk data has very little true signal by construction; this is
  the honest, expected result, and the project reports it rather than
  cherry-picking a flattering metric.
- *"Isn't an LLM assistant risky for a finance app?"* — Slide 13's
  architecture: it never computes a number itself, only cites
  already-computed data, with two independent layers (prompt + regex)
  refusing advice-like language.
- *"How do you know the ledger is really tamper-evident and not just
  claimed?"* — It was tested against a simulated privileged tamper
  (disabling the DB trigger, editing a field with raw SQL) and caught
  every time — point to the specific test if asked for proof.
- *"What would you need real money/users for?"* — Live market data
  execution and the NIFTY 100 re-verification is the single highest-value
  next step, already fully built and gated only by network access in
  this sandbox, not by missing code.
