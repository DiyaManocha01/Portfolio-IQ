# Research Paper Draft Outline (Phase 23)

A structured skeleton for an academic-style paper built from
`docs/methodology.md`, written to the same honesty standard as the rest
of this project (`CLAUDE.md` rule 5: never invent data, metrics, or
results — every number here must trace to a function in the repo).

**This is an outline, not a finished paper.** Three things are
deliberately left as placeholders rather than filled in, because filling
them would mean inventing content this project doesn't actually have:

1. **Related Work citations** — this project was built in a
   network-restricted sandbox with no access to academic databases, so
   no literature review was performed. Every citation below is a *topic
   to search and cite*, not a citation — do not paste in authors/years/
   venues you haven't personally verified exist and say what's claimed.
2. **The final Abstract** — write this last, after the real paper exists,
   summarizing what the paper actually says rather than what was planned.
3. **Any number not already in `methodology.md` or reproducible by
   running the scripts named next to each result below.**

---

## Working title

*"PortfolioIQ: Portfolio-Relative Stock Ranking via a Composite,
Explainable Fit Score"* — or similar; the real contribution to foreground
in the title is the portfolio-relative ranking idea (Section 3), not the
ML classifier (which the paper should be honest is a secondary, modestly-
performing component — see Section 6).

## Abstract (write last)

150-250 words covering: the problem (existing tools rank stocks in
isolation, not relative to a specific portfolio's composition), the
approach (a weighted, z-scored, logistic-sigmoid composite of ML outlook,
sentiment, and three portfolio-level deltas), what was evaluated (the
formula's internal consistency — exact decompositions, algebraic
identities — and the ML component's honestly-reported, close-to-random
performance on synthetic data), and the paper's actual conclusion (e.g.
"the methodology is sound and reproducible; the ML signal requires real
market data to evaluate meaningfully, which is identified as the primary
direction for follow-up work").

## 1. Introduction

- Motivate the gap: robo-advisors and stock screeners typically score a
  stock in isolation or against a generic risk profile, not against the
  marginal effect on a specific existing portfolio.
- State the contribution precisely: a composite Fit score where three of
  five terms are *portfolio-level deltas* (risk, diversification,
  concentration), not stock-level properties — and where the scoring
  function's structure (additive in logit space) makes two further
  explanation types exactly computable: ranking-gap decomposition and
  ceteris-paribus counterfactual scenarios (Sections 3.4-3.5).
- State what this paper does NOT claim: it does not claim the ML
  direction-prediction component is a validated trading signal (Section 6
  reports this honestly), and all quantitative results in this draft are
  measured on a synthetic, clearly-labeled development dataset pending
  real-market validation (Section 7.3).

## 2. Related Work *(topics to research — not citations)*

Search and cite real, verified papers for each of these topics before
submission; do not invent author names or venues:

- Portfolio-aware / personalized stock recommendation (vs. generic
  stock-scoring or screener systems).
- Modern portfolio theory and diversification measures: Herfindahl-
  Hirschman Index in portfolio context, the diversification ratio
  (Choueifaty & Coignard — verify and correctly cite the original paper,
  not just this project's secondary paraphrase of it).
- Shrinkage covariance estimation (Ledoit & Wolf — verify and cite the
  original paper directly; this project's implementation uses
  `sklearn.covariance.LedoitWolf`, which itself cites the source).
- Purged / embargoed cross-validation for financial time series (the
  technique used in Section 4 traces to methodology associated with
  Marcos López de Prado's work — verify the specific paper/book and cite
  it directly rather than this project's own summary of it).
- The Probabilistic / Deflated Sharpe Ratio (Bailey & López de Prado,
  2014) — **this project's own implementation was never checked against
  the original paper** (no network access in the dev sandbox); before
  citing this project's DSR numbers in a paper, independently verify the
  formula against the primary source first, not just cite it on faith.
- SHAP / explainable ML (Lundberg & Lee) — verify and cite the original
  NeurIPS paper.
- Portfolio optimization methods: mean-variance (Markowitz), Hierarchical
  Risk Parity (López de Prado) — verify and cite both directly; this
  project's HRP implementation is via the `pyportfolioopt` library, not a
  from-scratch implementation, and the paper should say so.
- FinBERT and financial-domain sentiment models — verify and cite
  (`ProsusAI/finbert`, and whatever paper documents its training).

## 3. System Design and Methodology

Map directly onto `docs/methodology.md`'s section numbers — each
subsection below should essentially restate that section's content in
academic prose, with its formulas:

- **3.1 Data pipeline** (methodology.md §1) — universe construction,
  caching, the OHLCV validation checks. State plainly that the symbol
  universe is unverified against an official NSE source as of this
  writing (a limitation, not a hidden gap).
- **3.2 Feature engineering and label definition** (§3.1-3.2).
- **3.3 Purged walk-forward cross-validation** (§3.3) — the paper's
  methodological contribution-adjacent section: explain precisely why a
  naive shuffled split leaks information in a time-series setting, and
  how the purge/embargo addresses it. Include the fold diagram.
- **3.4 The Portfolio Fit score** (§7.1-7.4) — the paper's central
  contribution. State the formula, the five terms, the z-scoring
  procedure and why the z-scoring population matters (§7.3 — this is a
  genuinely interesting methodological point: the same stock's score
  legitimately differs depending on what population it's compared
  against, which is worth discussing as a finding in itself, not just an
  implementation detail).
- **3.5 Exact explanation methods enabled by additivity** (§13.1-13.3) —
  frame this as the paper's second contribution: because the score is
  additive in logit space, ranking-gap decomposition and single-term
  counterfactual scenarios are exact, not approximated (unlike, e.g.,
  SHAP's own approximation of Shapley values for non-additive models).
  Be precise about what's NOT claimed: the counterfactual is
  ceteris-paribus and single-term, not a joint minimal-change search
  (§13.3) — state this limitation in the methodology section itself, not
  only in a later limitations section, since it's a property of the
  method, not an experimental shortfall.
- **3.6 Portfolio risk analytics** (§5) — Ledoit-Wolf shrinkage, VaR/CVaR,
  HHI, diversification ratio, with the formulas.
- **3.7 Backtesting protocol** (§10.1-10.4) — the long/flat strategy
  definition, the DSR and paired-bootstrap significance tests.

## 4. Implementation

- Brief, not the paper's focus: stack (FastAPI/Postgres/React), the
  provider-abstraction pattern that separates synthetic development data
  from a (built but unexecuted in this sandbox) live-data path, test
  coverage (270 automated tests). A paragraph, not a section the reader
  needs to study — point to `docs/ARCHITECTURE.md` for full detail rather
  than reproducing it here.

## 5. Experimental Setup

- **State plainly and prominently**: all results in this draft are
  measured on a deterministic synthetic dataset (`DevSampleProvider`),
  generated as a random walk with an injected shared market factor for
  realistic cross-stock correlation — described exactly, not vaguely, so
  a reviewer can assess what the numbers can and can't support.
- Why synthetic: this project was developed in a network-restricted
  sandbox with no access to live market data vendors (stated as an
  environment fact, not an excuse) — the live-data path is fully
  implemented and tested up to the network boundary (§methodology.md
  intro to each relevant section) but has never been executed against
  real data.
- The seeded universe: 7 held + 6 unheld stocks (list them), ~287 days of
  synthetic history per symbol.

## 6. Results

Pull numbers directly from `methodology.md` — do not round further or
restate them differently than the source:

- **6.1 ML classifier performance** (§3.8): selected model
  `logistic_regression`, held-out test AUC (calibrated) = 0.545, vs.
  majority-class baseline accuracy 0.496 and momentum baseline AUC 0.519.
  State directly: this is close to random, consistent with a synthetic
  random walk's limited true signal by construction — framed as the
  *expected, correct* outcome of evaluating honestly on this data, not a
  failure of the method.
- **6.2 Backtest** (§10.5): ML strategy Sharpe -0.459 vs. buy-and-hold
  +0.233; paired bootstrap mean Sharpe difference -0.0161, 95% CI
  [-0.0611, +0.0246] (includes zero); DSR = 0.619. State the
  interpretation methodology.md already gives: not statistically
  distinguishable from "no effect" at this sample size, consistent with
  the AUC result expressed as trading performance.
- **6.3 Portfolio Fit Engine — worked example** (§7.6, §11.5, §13.4):
  reproduce the SUNPHARMA example end-to-end — factor breakdown, the
  risk-attribution table, and the SUNPHARMA-vs-WIPRO comparison — as a
  worked case study demonstrating the method, explicitly scoped as an
  illustration, not a generalizable finding, given n=1.
- **6.4 Optimization** (§6.5): the three methods' expected
  return/vol/Sharpe and largest suggested reallocation, with the explicit
  caveat already in methodology.md about why `max_sharpe`'s 84%-into-one-
  stock result is an honest artifact of noisy historical-mean expected-
  return estimates on a small synthetic universe, not a validated
  recommendation.
- **6.5 Feature ablation** (§10.6): the AUC-delta table, with the
  explicit caveat that on synthetic data these deltas are within the
  range of noise and should be re-run on real data before drawing
  conclusions about feature importance.

## 7. Discussion

- **7.1 What the Fit Engine's design contributes independent of the ML
  component's performance**: the portfolio-relative framing, the exact
  explanation methods, and the z-scoring-population finding (§7.3) are
  contributions regardless of how well the ML outlook term itself
  performs — make this argument explicitly, since a reviewer's first
  question will be "but the AUC is basically random."
- **7.2 Threats to validity**: synthetic data (primary), small universe
  (13 stocks) limiting statistical power, N=3 trials for the DSR's
  extreme-value approximation (undersized for the asymptotic theory it
  relies on — state this precisely, from methodology.md §10.3), the
  DSR formula's lack of independent verification against the primary
  source, survivorship bias in the symbol universe once real data is
  used.
- **7.3 What would change with real data**: every number in Section 6
  needs re-measurement against real NIFTY data before any claim here
  generalizes beyond "the methodology runs correctly." State this as the
  paper's primary call to action, not a footnote.

## 8. Limitations

Consolidate (don't just repeat) the caveats already stated inline in
Sections 5-7 — a reviewer should be able to read this section alone and
get an accurate, undiluted picture of what's NOT yet established:
synthetic data throughout, unverified symbol universe, unverified DSR
formula, ceteris-paribus (not joint) counterfactuals, N=3 DSR trials,
no human-labeled sentiment ground truth (FinBERT-vs-lexicon comparison
measures agreement between two unsupervised scorers, not accuracy — state
this distinction explicitly, it's an easy one to misstate).

## 9. Conclusion and Future Work

- Restate the two contributions (portfolio-relative Fit score; exact
  explanation methods enabled by its additive structure) without
  overclaiming the ML component.
- Future work, in priority order (matches `docs/ROADMAP.md`'s own
  ordering): run against real NIFTY data and re-measure every result
  above; independently verify the DSR formula against the primary
  source; verify the NIFTY 100 universe against an official NSE listing;
  extend the counterfactual method to a joint minimal-change search (a
  harder optimization problem, explicitly out of scope here); human-
  labeled sentiment evaluation for the FinBERT-vs-lexicon comparison.

## References

Populate only with citations you have personally verified (real title,
real authors, real venue, and the claim attributed to it actually appears
in that source). Do not carry over any citation-shaped text from Section
2 without doing that verification first — this project's own working
rules treat an unverified citation the same as an unverified number.

## Appendix: formula reference

A compact table mapping every formula in Section 3 to its exact source:
`methodology.md` section number + the implementing function (e.g.
`backend/app/portfolio/fit_service.py::compute_fit`). Useful for
reviewers checking reproducibility and for you when revising — build it
directly from `methodology.md`'s own cross-references rather than
re-deriving them.
