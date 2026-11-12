# ADR 0013: Market Regime Detection (Phase 30)

**Status:** Accepted
**Date:** 2026-11-12

## Context

Phase 30 asked for an ML/statistical market regime classifier across five
regimes (trending up/down, sideways, high/low volatility), using
transparent features, defensible evaluation, no look-ahead bias, and a
displayed confidence with an explanation of the contributing factors.

## Decision

### Rule-based thresholds, not a trained model

There is no ground-truth "this day was actually a Trending/Sideways/
High-Vol regime" label anywhere -- any such label would itself be a
human judgment call presented as data, which this project's "never
invent data" rule (CLAUDE.md) rules out as a basis for supervised
training or accuracy evaluation. `market_regime_service.classify_regime`
is instead a deterministic function of two already-transparent,
already-computed-elsewhere features (trend, volatility), thresholded at
a fixed, round, pre-declared boundary. The factors ARE the explanation
-- there's no separate explainability layer (unlike Phase 17's SHAP for
the ML direction classifier) because nothing is opaque to begin with.

### Trend is a z-statistic against a zero-drift null, not a self-referential z-score

Volatility is z-scored against its OWN trailing history (is recent
volatility unusual relative to this stock's/index's normal range) --
that's the right null hypothesis for volatility. The same approach does
NOT work for trend: a market that has been steadily trending for a long
time would have that same trend baked into its own trailing history,
so z-scoring the trend against its own past would wrongly report
"nothing unusual" about a textbook sustained trend (caught while
testing a synthetic steady-uptrend series, which an earlier version of
this classifier misclassified as SIDEWAYS). Instead, `trend_z` is a
standard statistical z-statistic: the rolling N-day cumulative return
divided by the standard deviation that zero-drift noise at the recently
observed volatility would be expected to produce over that same N-day
window (`daily_vol * sqrt(N)`). This correctly flags a sustained,
low-noise trend as statistically significant, which the self-referential
approach could not.

### Thresholds: both exactly 1 standard deviation, deliberately equal

`TREND_Z_THRESHOLD` and `VOL_Z_THRESHOLD` are both `1.0` -- not tuned
against any labeled outcome (none exists), and deliberately the SAME
magnitude for both features rather than two independently-chosen
numbers, so there's no hidden asymmetry to justify. An earlier draft
used `0.5` for the trend threshold; testing against a drift-free random
walk showed it crossed by chance roughly a third of the time (expected,
since z-statistics near zero drift accumulate noise), which isn't a
defensible way to distinguish a real trend from noise. `1.0` was chosen
as the smallest round, standard, symmetric cutoff that doesn't fire on
pure noise at an unreasonably high rate.

### Confidence is one uniform, bounded function -- not a probability

Confidence is `tanh(margin / 2)`, where `margin` is how far past the
decisive threshold the classification landed (for TRENDING_*/HIGH or
LOW_VOLATILITY) or the smallest remaining gap to either threshold not
being crossed (for SIDEWAYS). It is exactly 0 right at a boundary (the
genuinely most uncertain point) and approaches 1 far from it. This is
explicitly NOT a probability -- there is no calibration target to
validate it against, unlike the ML direction classifier's calibrated
probability (Phase 6). Applying the exact same formula to every regime,
rather than a different ad hoc confidence calculation per regime, is
itself part of the defensibility.

### Volatility extremes take priority over trend

If `|vol_z| >= 1.0`, the regime is HIGH_VOLATILITY or LOW_VOLATILITY
regardless of what the trend feature says. A market whose volatility
has genuinely spiked or collapsed is more actionably described by that
fact than by whatever modest trend happens to accompany it.

### "Defensible evaluation" for a label-free classifier means directional consistency, not accuracy

With no ground truth, there is no accuracy/precision/recall to report
honestly (reporting one would misrepresent what was actually measured).
The tests instead assert the MODAL regime across many random synthetic
draws under a known generating process (e.g. sustained positive drift
→ modally TRENDING_UP; a genuine recent volatility spike → always
HIGH_VOLATILITY), which is what can honestly be claimed: the classifier
behaves in the statistically expected direction on average, not that
every single draw agrees (a trending series whose recent volatility
also happens to be extreme will correctly register as a volatility
regime instead, by the priority rule above -- that is not noise, it's
the documented design).

### No look-ahead by construction

`classify_regime(bars)` takes only `bars` and nothing else -- every
feature is computed from that list alone, so classifying "as of" some
date can only use data up to that date if the caller passes it that way
(the route always truncates to "now"). The test suite verifies this as
a determinism/purity property: re-slicing the same longer bar list to
an earlier cutoff reproduces the identical result regardless of whether
`classify_regime` was also called on a longer slice elsewhere.

### Applies to the NIFTY 50 benchmark by default, or any stock symbol

`GET /market/regime` with no `symbol` classifies the NIFTY 50 benchmark
(reusing `MarketDataService.get_benchmark_history`, already used for
beta calculations since Phase 5) -- "the market" in "Market Regime
Detection". Passing `symbol` classifies that stock instead, using the
exact same function; this was close to free to support and is useful on
the stock detail page.

## Consequences

- No new tables, no new dependencies.
- 18 new backend tests (hand-calculated confidence math, insufficient-
  history/empty-input edge cases, the no-look-ahead determinism check,
  five scenario tests using the modal-regime approach above, factor/
  structure checks, and route-level tests) plus 2 new frontend tests.
- **Not verified beyond this sandbox's synthetic/dev-sample data**: no
  regime has ever been classified against a real market move, since
  this environment has no live feed (see docs/limitations.md and the
  existing Phase 4/24 ADRs for why).
- **Not integrated into any other feature yet** (Fit Engine, alerts,
  What-If) -- Phase 30 scoped this as a standalone classifier with its
  own display, not a new input to existing calculations. Feeding it into
  those is a natural future extension, deliberately left out here to
  keep this phase's surface area reviewable.
