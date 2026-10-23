# Presentation Outline (Phase 23)

A simple, 10-slide outline for a demo/defense deck. **This is an outline
to build a deck from, not a built `.pptx`.** Every number traces to
`docs/methodology.md` — don't add a number that isn't there.

~10-12 minutes + Q&A.

---

## 1. Title

PortfolioIQ — AI Portfolio Intelligence. Name, institution, date.

## 2. The Problem

- Stock tools rate a stock in isolation ("is TCS good?").
- Nobody answers "is TCS good *for my portfolio*?"
- A great stock can still be a bad addition if it duplicates what you
  already hold.

## 3. The Idea — Portfolio Fit Engine

- Score = ML outlook + sentiment + how the stock changes your risk,
  diversification, and concentration.
- Show the formula, big, on its own:
  `Fit = σ(w1·Outlook + w2·Sentiment − w3·ΔRisk + w4·ΔDiversification − w5·ΔConcentration)`
- This is the one slide to be remembered.

## 4. How It's Built

- React + FastAPI + Postgres. scikit-learn/XGBoost for ML, SHAP for
  explanations, PyPortfolioOpt for optimization.
- One line: swappable "live vs. synthetic data" design, so real data
  drops in later without rewriting anything.

## 5. Demo

- `/discover` → pick a stock → see its Fit breakdown.
- "Compare to another stock" / "what would improve this fit".
- What-If simulator: a hypothetical trade, before/after risk — never
  touches the real portfolio.

## 6. ML Results — Said Honestly

- Test accuracy (AUC) ≈ 0.545 — close to random.
- Why: trained on synthetic data with little real signal. Expected, not
  hidden.
- One line: the backtest (ML vs. buy-and-hold) tells the same story.

## 7. Explainability

- Three things, each exact, not approximate:
  - SHAP — why the model predicted this.
  - Counterfactuals — why stock A beats stock B.
  - Risk attribution — which holding's risk is bigger than its size.

## 8. Trust & Security

- Every prediction logged in a tamper-evident, publicly verifiable
  ledger — tested against a simulated tamper attempt.
- Dependency security audit: 42 issues found → 1 left (explained why).
- Rate limiting, Docker deployment.

## 9. Limitations — Said Plainly

- All data here is synthetic (no live network access in this sandbox).
- NIFTY 100 list not yet checked against an official source.
- One advanced stats formula (DSR) not independently verified.

## 10. What's Next / Thank You

- Run it on real market data — everything's built, just needs to be
  switched on and re-measured.
- Repo: `github.com/DiyaManocha01/Portfolio-IQ`
- Questions?

---

## Likely questions, pre-answered

- **"Why is the AUC so low?"** → Synthetic data has little real signal
  by construction. Honest result, not a bug.
- **"Isn't an AI assistant risky for finance?"** → It only repeats
  numbers already computed — never calculates or advises on its own, and
  a separate filter blocks advice-sounding language.
- **"Is the ledger really tamper-proof?"** → Tested it directly: broke a
  record on purpose, the system caught it every time.
- **"What's needed to go live?"** → Real market data access — the code
  is already built for it.
