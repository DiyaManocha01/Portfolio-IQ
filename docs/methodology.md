# Methodology

Started in Phase 4, extended every batch. This is the document a research
paper or IP filing would cite for "how was this computed" — every formula
implemented in the codebase should have a corresponding entry here, with a
pointer to the exact function that implements it. If a number in the app or
a paper draft can't be traced to an entry here and a script in the repo,
treat that number as unverified (see `docs/limitations.md`).

## 1. Data (Phase 4)

### 1.1 Universe

`backend/app/services/market_data/nifty100.py` defines `SYMBOLS`: an
approximate, **unverified-against-a-live-source** list of ~100 large NSE
equities, standing in for the NIFTY 100 index until it's checked against an
official NSE Indices snapshot (see `docs/limitations.md`). The benchmark
for beta calculations (Phase 5) is the NIFTY 50 index, `^NSEI`.

### 1.2 Source and adjustment

Real price history comes from Yahoo Finance via `yfinance`
(`LiveYFinanceProvider`), requested with `auto_adjust=True` — i.e. OHLC
values are adjusted for splits and dividends by the data provider before
this project ever sees them. This project does not perform its own
corporate-action adjustment; it relies on yfinance's.

### 1.3 Caching

`backend/app/services/market_data/cache.py`: one Parquet file per symbol
under `app/data/cache/`, written by `scripts/fetch_nifty100.py` (run
locally — see ADR 0002 for why). `LiveYFinanceProvider` reads this cache
before ever calling the network.

### 1.4 Validation (`cache.validate_ohlcv`)

Given a raw OHLCV DataFrame for a symbol, checks (and returns
human-readable warnings for, rather than silently discarding):

| Check | Rule |
|---|---|
| Required columns present | `date, open, high, low, close, volume` |
| Non-empty | at least one row |
| Positive prices | `open, high, low, close > 0` for every row |
| Non-negative volume | `volume >= 0` for every row |
| High/low consistency | `high >= low` for every row |
| Trading gaps | flags any gap between consecutive trading dates longer than `max_gap_days` (default 10 calendar days) — a possible halt, delisting, or provider outage, not assumed to be a holiday |
| Likely-unadjusted split | flags any single-day `abs(pct_change(close)) > 0.40` — real large-cap single-day moves of that size are rare; this usually means a split/bonus wasn't reflected in the adjusted series |

### 1.5 Known data-quality limitations

See `docs/limitations.md` — survivorship bias in the symbol universe,
no official re-verification of the NIFTY 100 list, no real fixture
committed yet.

## 2. Stock Analysis (Phase 5)

Implemented in `backend/app/services/analytics.py`, served via
`GET /stocks/{symbol}/analysis` (`backend/app/api/routes/stocks.py`).

### 2.1 Returns, volatility, drawdown, moving averages, RSI

Unchanged from the Phase 1-3 implementation: `daily_returns`,
`cumulative_returns`, `volatility_annualized` (std of daily returns ×
√252), `max_drawdown` (largest peak-to-trough decline of cumulative
value), `sma`/`ema`, `rsi` (14-period, Wilder-style gain/loss ratio).

### 2.2 MACD (`analytics.macd`)

Standard definition: `MACD line = EMA(12) - EMA(26)`, `signal line =
EMA(9) of the MACD line`, `histogram = MACD line - signal line`. Returned
as a full time series (all three columns), not just the latest value, so
the frontend can plot the histogram crossing zero.

### 2.3 Beta vs. NIFTY 50 (`analytics.beta`)

`beta = Cov(stock_returns, benchmark_returns) / Var(benchmark_returns)`,
computed over daily returns aligned by date (inner join, so only trading
days present in both series count). Benchmark is NIFTY 50 (`^NSEI`),
fetched via `MarketDataService.get_benchmark_history()` — same
provider/cache path as any other symbol, never persisted to the
`stocks`/`market_data` tables (it isn't a holding or a discoverable stock).

**Returns `None`, not 0 or 1, when fewer than 20 overlapping observations
exist** — a missing beta must never be silently presented as "beta of
zero" (implying no market sensitivity) or "beta of one" (implying average
market sensitivity); both would be a specific, false claim about an
unknown quantity.

**Known instability, verified empirically, not just asserted:** on the
synthetic `DevSampleProvider` data (TCS seeded with an embedded
`BETAS["TCS"] = 0.85`), the measured beta over a 120-day window came out
as **-0.22** — wrong sign, nowhere near the embedded value — purely from
small-sample noise (idiosyncratic daily volatility dominates the signal at
that window length). Over the full ~287-day seeded history, it recovers to
**0.85**, exactly matching the embedded value. **Conclusion: a beta
computed on fewer than ~250 trading days (about a year) should be treated
as unreliable**, regardless of data source — this is a property of the
estimator on noisy daily data, not specific to synthetic data, and the
same caution applies once this runs on real cached NIFTY data. The 20-row
floor in `analytics.beta()` is a crash-guard against a degenerate
calculation, not a claim of statistical stability at that sample size —
callers should prefer the endpoint's default window (400 calendar days)
over a short one when beta matters.

### 2.4 Synthetic benchmark construction (DevSampleProvider only)

A broad index like NIFTY 50 is approximately the diversified market factor
itself — single-stock idiosyncratic noise averages out across its ~50
constituents. `DevSampleProvider` models this by generating the `^NSEI`
series with `beta = 1.0` (fixed) and an idiosyncratic-noise multiplier of
0.08 versus 0.7 for individual stocks (an illustrative modeling choice, not
calibrated against real index tracking-error data). `LiveYFinanceProvider`
fetches the real index level instead once real data is available (Phase 4
cache, populated locally).

## 3. ML Direction Classifier (Phase 6)

Implemented in `backend/app/ml/features.py` and `backend/app/ml/train.py`.
Supersedes the Phase 1-3 pipeline -- see ADR 0003 for why.

### 3.1 Label

Binary: `close[t+1] > close[t]`, a 1-day horizon (`LABEL_HORIZON_DAYS = 1`
in `features.py`, a named constant so the embargo below always matches it).

### 3.2 Features

Unchanged set from Phase 1-3: `return_1d`, `return_5d`, `sma5_ratio`,
`sma20_ratio`, `ema20_ratio`, `rsi_14`, `volatility_10d`, `momentum_10d`,
`volume_ratio` -- all computed using only data available up to and
including day t.

### 3.3 Purged walk-forward cross-validation (`purged_walk_forward_splits`)

Per stock, data is split into `N_SPLITS + 1 = 6` contiguous chronological
blocks. For fold `i`: train = blocks `[0..i]`, test = block `i+1`. Before
use, the training set is **purged**: the last `embargo` (= 1 day) rows
immediately preceding the test block are dropped, because a training row's
label depends on the *next* day's price -- without the purge, a training
row at the very boundary would have "seen" a price that only becomes known
at the start of the test period.

Fold-level results are pooled across stocks (each stock contributes its
own fold `i`, concatenated with every other stock's fold `i`) before
computing that fold's metrics -- so a fold's reported AUC reflects
performance across the whole stock universe for that time slice, not one
stock alone.

**5 folds** are used for model selection (mean validation ROC-AUC across
folds decides the winning candidate); **the 5th (most recent) fold's test
block is the single, final, honest held-out test** -- touched exactly
once, after model selection is already locked in, matching the spirit of
the Phase 1-3 pipeline's held-out test but now reached via a leakage-safe
multi-fold process instead of one split.

### 3.4 Candidates and selection

Unchanged: Logistic Regression (now wrapped in
`Pipeline(StandardScaler, LogisticRegression)` so scaling happens inside
each CV fold rather than being fit once outside all of them), Random
Forest, XGBoost. Selected by mean validation ROC-AUC across the 5 folds.

### 3.5 Calibration

The winning model type is re-fit wrapped in
`sklearn.calibration.CalibratedClassifierCV(method="sigmoid", cv=3)` on the
final training set. Sigmoid (Platt) scaling was chosen over isotonic
regression because our per-fold sample sizes (a few hundred rows) are
small enough that isotonic's non-parametric flexibility risks overfitting
the calibration curve itself.

**Documented limitation:** `CalibratedClassifierCV`'s internal `cv=3` folds
are NOT time-aware (standard scikit-learn k-fold, potentially mixing
chronological order within the calibration step). This is a known
simplification, not silently accepted -- see `docs/limitations.md`. A
fully rigorous implementation would need a custom purged calibration
split; deferred as out of scope for this phase.

A reliability diagram (`calibration_curve`, 8 quantile bins, uncalibrated
vs. calibrated overlaid) is saved to
`app/data/models/calibration_plot.png` on every training run.

### 3.6 Baselines (always computed, same held-out test set)

- **Majority-class**: predicts the training set's single most common label
  for every test row. AUC is reported as 0.5 by convention (a constant
  predictor has no ROC curve / no discriminative power -- `roc_auc_score`
  is not computed on it, since scikit-learn would error on a degenerate
  constant-prediction input).
- **Momentum**: predicts "up" when the prior day's return (`return_1d`)
  was positive; AUC uses that same return value as a continuous ranking
  score (standard practice for giving a baseline a comparable AUC).

### 3.7 Versioning

`model_version` = first 12 hex characters of
`sha256(json({features, label_horizon_days, n_splits, calibration_method, selected_model}))`.
Deliberately a fingerprint of the methodology, not an incrementing
counter: it changes automatically the moment any of those inputs change,
and two predictions sharing a `model_version` are guaranteed to have come
from the same training methodology (not just "a recent run"). Stored on
every `predictions` row (`backend/alembic/versions/0002_add_model_version_to_predictions.py`).

### 3.8 Current honest results (synthetic data, as of this write-up)

From a real seed run, not invented: selected model `logistic_regression`,
mean validation AUC ~0.52 across candidates, final held-out test AUC
(calibrated) **0.545**, vs. majority-class baseline accuracy 0.496 and
momentum baseline AUC 0.519. The real model modestly beats both baselines
-- consistent with "close to random, as expected for data with very
limited true signal by construction" (see `docs/limitations.md`), reported
exactly as measured, with the measurement method next to it, not asserted
without a script that produced it (`app/ml/train.py::train_and_select_model`,
re-run via `python -m app.data.seed`).

## 4. News Ingestion & Sentiment Aggregation (Phase 7)

Implemented in `backend/app/services/news/` (RSS ingestion) and
`backend/app/services/news_service.py` (aggregation).

### 4.1 Real headline source

Economic Times and Moneycontrol public RSS feeds (`services/news/rss_feeds.py`)
— chosen over a general-purpose news API by explicit project-owner decision:
free, no API key, genuinely India/NSE-focused. Fetched by
`scripts/fetch_news_rss.py`, run locally (this sandbox cannot reach either
host — verified, same restriction as Yahoo Finance and Hugging Face).

### 4.2 Headline-to-stock matching

These are category-level feeds (e.g. "Markets", "Business"), not
per-symbol, so each entry is matched against every seeded stock's
distinctive name fragments (`services/news/matching.py`) via
case-insensitive, word-boundary regex search over the title + summary.
Bare short/ambiguous tickers (e.g. `LT` for Larsen & Toubro) are
deliberately excluded from the match terms — only the full/distinctive
company name is matched for those, to avoid obvious false positives (`LT`
colliding with "Lt." as an abbreviation, a unit, etc.).

**Not validated against a labeled ground-truth set.** This is a documented
precision/recall tradeoff, not a solved problem — see `docs/limitations.md`.

### 4.3 Caching and NewsService integration

`services/news/cache.py` — a JSON file cache (`app/data/news_cache/rss_headlines.json`,
gitignored), written by the fetch script, read cache-first by
`NewsService.get_recent_news()` when `USE_LIVE_NEWS=true`. Real headlines
are ingested into the `news`/`news_sentiment` tables tagged
`DataSource.LIVE` (idempotent — re-running doesn't duplicate a headline
already stored, matched by headline text + published timestamp). If
`USE_LIVE_NEWS` is off, or no real headline matched a given stock, the
original synthetic template-headline generator is used unchanged — the
real-ingestion path is strictly additive, default behavior is unchanged.

### 4.4 Time-decayed sentiment aggregation

`news_service.py::_time_decayed_average()`: an exponentially time-weighted
mean of each article's sentiment score,
`weight_i = 0.5 ** (age_days_i / half_life_days)`, with
`half_life_days = 7.0` (`SENTIMENT_HALF_LIFE_DAYS`, a documented, chosen
constant — not derived from data; see the constant's docstring for the
reasoning and the explicit note that it should be tuned once real headline
volume/cadence from Phase 7's RSS ingestion gives a basis to do so
empirically). Returned alongside the original simple (equal-weighted)
average as `average_score_time_decayed`, so both are visible for
comparison rather than silently replacing one with the other.

### 4.5 FinBERT evaluation protocol and its limits

`scripts/evaluate_finbert.py` (run locally, needs Hugging Face access this
sandbox doesn't have) compares FinBERT against the lexicon scorer on real
cached headlines. **Important distinction, stated here precisely because
it's easy to misstate**: there is no human-labeled sentiment ground truth
for these headlines in this project, so the script measures *agreement
between two unsupervised scorers*, not accuracy against a correct answer —
reporting it as "accuracy" would be a false claim.

**Documented limitation**: FinBERT (`ProsusAI/finbert`) was trained on
English financial text, primarily Reuters TRC2 and the Financial
PhraseBank corpus — both Western/US-centric sources. Indian financial
English headlines (ET/Moneycontrol) share financial terminology and
should transfer reasonably, but India-specific terms (SEBI, RBI, GST,
Indian corporate structures), occasional code-mixed Hindi-English
phrasing in regional business press, and India-specific context are not
represented in FinBERT's training data. No rigorous NLP evaluation of this
gap exists in this project — it would require human-labeled Indian
financial headlines, which this project does not have.

---

## 5. Portfolio Risk Analytics (Phase 8)

Implemented in `backend/app/portfolio/risk_service.py`. See
`docs/adr/0004-portfolio-risk-rebuild.md` for what this supersedes.

### 5.1 Inputs

A portfolio's holdings' daily close-price returns, aligned on common
trading dates over a `lookback_days` window (default 180), current
value-weighted (not day-by-day re-based — a documented MVP simplification
carried over unchanged from the original service).

### 5.2 Volatility, Sharpe, max drawdown (unchanged from the MVP)

- Annualized volatility = `std(daily portfolio returns) * sqrt(252)`.
- Sharpe ratio = `mean(excess daily return) / std(daily return) * sqrt(252)`,
  6% annual risk-free rate assumption (approximate Indian T-bill).
- Max drawdown = largest peak-to-trough decline of the cumulative
  portfolio value series over the window.

### 5.3 Ledoit-Wolf shrinkage covariance

`sklearn.covariance.LedoitWolf` fit on the holdings' daily return matrix,
annualized (`* 252`). Shrinkage pulls the (noisy) sample covariance matrix
toward a more structured target, controlled by an intensity the estimator
chooses itself from the data (`shrinkage_intensity`, returned in the API
response, range `[0, 1]`; `0` would mean "no shrinkage needed", `1` would
mean "ignore the sample covariance entirely"). Used for the risk
contribution calculation (`contrib_i = w_i * (Cov @ w)_i`, normalized to
sum to 100%) — same marginal-contribution-to-variance formula as before,
just a better-conditioned input matrix.

Falls back to the raw sample covariance (`covariance_method: "sample"`,
`shrinkage_intensity: 0.0`) when there are fewer than 2 holdings or fewer
return observations than holdings — shrinkage is undefined/degenerate in
that regime, and silently returning a shrunk-looking number would misstate
what was actually computed.

### 5.4 Historical VaR and CVaR

Computed at 95% and 99% confidence directly from the realized portfolio
daily-return series — no normal-distribution assumption:

```
alpha = 1 - confidence
var_quantile = returns.quantile(alpha)      # e.g. the 5th percentile
VaR  = -var_quantile                         # reported as a positive loss fraction
tail = returns[returns <= var_quantile]
CVaR = -mean(tail)                           # expected loss *given* VaR is breached
```

Both are floored at 0 (a VaR/CVaR cannot be presented as negative — that
would mean "the model expects a gain on the worst days", which is not a
sensible reading of a loss threshold). `CVaR >= VaR` always holds by
construction (the tail mean is at least as extreme as the quantile that
defines it).

### 5.5 HHI and effective number of bets

`HHI(weights) = sum(w_i^2)` after normalizing weights to sum to 1.
Computed separately for holding weights and sector weights. Range: `1/n`
(perfectly spread across `n` positions) to `1` (single position/sector).

`effective_number_of_bets = 1 / HHI(holding weights)`. **This is the
weight-concentration definition** — equal weights across `n` holdings
gives exactly `n`; it does not account for correlation between holdings.
A PCA/eigenvalue-based "effective number of *independent* bets" (which
would account for correlation — two highly correlated holdings
contributing less than two genuinely independent ones) is a different,
more involved calculation and is explicitly out of scope for this phase
(see ADR 0004's alternatives-considered section).

### 5.6 Diversification ratio

Choueifaty & Coignard's diversification ratio:

```
DR = (sum_i w_i * standalone_annualized_vol_i) / portfolio_annualized_vol
```

`DR >= 1` whenever the holdings aren't perfectly correlated (the usual
case); `DR == 1` only in the perfectly-correlated edge case, since
diversification can never make a portfolio *more* volatile than its
weighted-average components would suggest. Note the portfolio volatility
in this ratio is still derived from the Ledoit-Wolf-shrunk covariance
matrix (Section 5.3), while `standalone_annualized_vol_i` uses each
holding's raw sample standard deviation — so the strict `>= 1` bound is a
property of the *sample*-covariance case, not guaranteed to the last
decimal once shrinkage reshapes the diagonal too. In practice (measured
against the seeded demo portfolio) this is not an issue: `DR = 1.412`.

### 5.7 Measured example (seeded demo portfolio, DEV_SAMPLE data)

From a direct run against the seeded demo portfolio (not hand-picked,
reproducible via `python -m app.data.seed` then `GET /portfolio/risk`):

| Metric | Value |
|---|---|
| `annualized_volatility` | 0.1975 |
| `var_95` / `cvar_95` | 0.0177 / 0.0211 |
| `var_99` / `cvar_99` | 0.0224 / 0.0257 |
| `hhi_holdings` | 0.1464 |
| `hhi_sector` | 0.2264 |
| `effective_number_of_bets` | 6.83 |
| `diversification_ratio` | 1.412 |
| `covariance_method` | `ledoit_wolf` |
| `shrinkage_intensity` | 0.0412 |

These are DEV_SAMPLE (synthetic) numbers — they say the formulas run
correctly against this portfolio's shape, not anything about real market
risk. Must be re-measured once real cached NIFTY data populates holdings.

---

## 6. Portfolio Optimization Suggestions (Phase 9)

Implemented in `backend/app/portfolio/optimization_service.py` using
PyPortfolioOpt (MIT license — `docs/open-source-inventory.md`).

### 6.1 What this is and isn't

Given the current holdings, this computes a hypothetical *target*
allocation under a chosen method and compares it to the current
allocation. It never touches the real portfolio — no DB write, no trade —
and the response always carries a disclaimer saying so. This is the
optimization half of what Phase 11's What-If Simulator will build on; it
answers "what would an optimizer suggest", not "what should you do."

### 6.2 Three methods

- **`min_variance`**: the minimum-volatility point on the efficient
  frontier (`EfficientFrontier.min_volatility`).
- **`max_sharpe`**: the maximum-Sharpe-ratio portfolio
  (`EfficientFrontier.max_sharpe`), same 6% annual risk-free rate
  assumption as `risk_service.py`'s Sharpe ratio. Raises (caught and
  surfaced as `feasible: false` with the underlying message) when no held
  stock's historical expected return exceeds the risk-free rate — a real
  possibility on this project's synthetic data, not silently hidden.
- **`risk_parity`**: **Hierarchical Risk Parity (HRP)**
  (`pypfopt.HRPOpt`) — a clustering-based allocation method. This is
  explicitly *not* the simpler "naive"/equal-risk-contribution risk parity
  that the name might suggest to a reader unfamiliar with the distinction;
  PyPortfolioOpt doesn't implement the naive version, and this project
  does not claim to compute something it didn't.

### 6.3 Inputs

- **Expected returns**: `pypfopt.expected_returns.mean_historical_return`
  — each stock's own historical compound annual growth rate over the
  lookback window (default 180 days, same as Phase 8's risk window). This
  is historical, not the Phase 6 ML outlook — the two are deliberately
  kept separate and neither silently substitutes for the other.
- **Covariance**: PyPortfolioOpt's own Ledoit-Wolf shrinkage
  (`risk_models.CovarianceShrinkage(...).ledoit_wolf()`), computed
  independently of Phase 8's `shrunk_covariance()` since PyPortfolioOpt
  needs its own internal representation — same methodology, separate
  computation.
- **Constraints**: long-only, no leverage (`weight_bounds=(0, 1)`). This
  app holds real retail positions; a short/leverage suggestion would be a
  meaningless hypothetical here.

### 6.4 Output

Per-holding `current_weight_pct` / `suggested_weight_pct` / `delta_pct`,
plus the suggested portfolio's expected annual return/volatility/Sharpe
under the stated risk-free-rate assumption.

### 6.5 Measured example (seeded demo portfolio, DEV_SAMPLE data)

Not hand-picked — reproducible via `python -m app.data.seed` then
`GET /portfolio/optimize?method=...`:

| Method | Expected return | Expected vol | Expected Sharpe | Largest suggested weight |
|---|---|---|---|---|
| `min_variance` | 2.8% | 16.8% | -0.19 | ITC: 62.7% (currently 16.9%) |
| `max_sharpe` | 32.5% | 30.2% | 0.878 | ICICIBANK: 84.3% (currently 14.6%) |
| `risk_parity` (HRP) | 11.6% | 18.4% | 0.305 | ITC: 29.5% (currently 16.9%) |

The large suggested reallocations (e.g. 84% into a single stock for
`max_sharpe`) are an honest artifact of optimizing historical
expected-return estimates on a modest synthetic holding set, not a
validated recommendation — see `docs/limitations.md`. These numbers are
DEV_SAMPLE (synthetic); they demonstrate the methodology runs correctly,
not anything about real-market optimal allocations.

---

## 7. Portfolio Fit Engine (Phase 10)

Implemented in `backend/app/portfolio/fit_service.py` and
`backend/app/portfolio/hypothetical.py`. See
`docs/adr/0005-fit-engine-rebuild.md` for what this supersedes. This is
PortfolioIQ's core differentiator -- "how well does this stock fit MY
portfolio", not "is this stock good".

### 7.1 The formula

```
Fit = w1*Outlook + w2*Sentiment - w3*dRisk + w4*dDiversification - w5*dConcentration
```

Each term is a **z-score** (standardized against a batch of stocks' raw
values for that term, mean-centered, unit-variance) before weighting, not
a raw number -- see 7.3.

### 7.2 Raw terms (before z-scoring)

- **Outlook** = `prediction.probability - 0.5` (Phase 6's calibrated
  model), centered so 50% (no signal) maps to 0. Neutral (0) if the model
  isn't trained.
- **Sentiment** = Phase 7's `average_score_time_decayed`. Neutral (0) if
  no recent news.
- **dRisk / dDiversification / dConcentration**: computed by
  `hypothetical.py`'s `current_metrics()` and
  `hypothetical_metrics_after_adding()` -- both using the IDENTICAL
  covariance-quadratic-form calculation (Ledoit-Wolf shrinkage, same as
  Phase 8), differing only in the weight vector/symbol set. The
  hypothetical scenario adds the candidate at a 10% target weight,
  scaling existing holdings down proportionally. `dRisk = hypothetical_vol
  - current_vol`, `dDiversification = hypothetical_div_ratio -
  current_div_ratio`, `dConcentration = hypothetical_hhi - current_hhi`.
  For an already-held stock, all three are exactly 0 by construction (the
  "hypothetical" scenario for an already-held stock is defined as
  identical to the current one -- "adding more" isn't a meaningful
  scenario here).

### 7.3 Z-scoring

For a batch of stocks being scored together, each raw term's mean and
standard deviation are computed across that batch, and every stock's raw
value for that term is converted to `z = (raw - mean) / std` (0 if
`std ≈ 0`, i.e. every stock in the batch has an identical raw value for
that term). **The batch matters**: `/portfolio-fit/{symbol}` z-scores
against the full stock universe (the most statistically meaningful
population available for a single symbol); `/discover` z-scores against
its own candidate batch (the unheld stocks, scored together in one
pass). **The same stock's fit_score can therefore differ between the two
endpoints** -- this is intentional (a z-score only means something
relative to a defined population), not a bug, and is called out here so
it's never mistaken for an inconsistency.

### 7.4 Weights, presets, and the final score

```
logit = sum(sign[term] * weight[term] * z[term] for term in terms)
fit_score = 100 / (1 + exp(-logit))   # logistic sigmoid, range (0, 100)
```

where `sign` is `+1` for Outlook/Sentiment/dDiversification and `-1` for
dRisk/dConcentration (higher risk or concentration is a worse outcome).
Three named presets (each summing to weight 1.0):

| Preset | Outlook | Sentiment | Risk | Diversification | Concentration |
|---|---|---|---|---|---|
| `balanced` (default) | 0.25 | 0.15 | 0.20 | 0.25 | 0.15 |
| `risk_averse` | 0.15 | 0.10 | 0.35 | 0.25 | 0.15 |
| `growth_seeking` | 0.40 | 0.20 | 0.10 | 0.15 | 0.15 |

A user's stated risk tolerance (Conservative/Moderate/Aggressive) maps to
a default preset (`risk_averse`/`balanced`/`growth_seeking`) when no
explicit `?preset=` is given.

**Important honesty note on "contribution":** each factor's reported
`contribution = sign * weight * z` is in pre-sigmoid (logit/additive)
units. These sum EXACTLY to `logit`, the sigmoid's input -- they do NOT
sum linearly to the displayed 0-100 `fit_score`, because the sigmoid
transform is nonlinear. Treating factor contributions as if they
partition the final score additively would misrepresent the math.

### 7.5 Diagnostics (not scoring inputs)

`volatility` (the candidate's own standalone annualized vol) and
`correlation_with_portfolio` (simple average pairwise correlation with
current holdings) are still reported on `/discover` for UI context, but
no longer feed the Fit score directly -- the portfolio-level
dRisk/dDiversification deltas already account for correlation properly
through the covariance matrix, which is strictly more rigorous than a
naive average correlation.

### 7.6 Measured example (seeded demo portfolio, DEV_SAMPLE data)

Reproducible via `python -m app.data.seed` then `GET /portfolio-fit/SUNPHARMA`
(balanced preset, z-scored against the full universe):

| Factor | Contribution (logit) | Raw value | Z-score |
|---|---|---|---|
| Diversification Impact | +0.640 | +0.047 | +2.562 |
| Risk Impact | +0.499 | -0.011 | -2.496 |
| Concentration Impact | +0.162 | -0.018 | -1.080 |
| News Sentiment | -0.079 | +0.059 | -0.527 |
| ML Outlook | -0.277 | -0.004 | -1.109 |

`logit = 0.945` -> `fit_score = 72.0`. The same stock via `/discover`
(z-scored against the unheld-candidate batch instead) scores `63.8` --
the documented population-dependence from 7.3, not an inconsistency.

---

## 8. What-If Simulator (Phase 11)

Implemented in `backend/app/portfolio/whatif_service.py`. Net-new (no
prior behavior superseded, so no ADR — see CLAUDE.md rule 9, which
requires an ADR only when superseding an existing decision).

### 8.1 What this is

Lets the user hypothesize arbitrary changes to their holdings -- buy more
of something, sell some or all of a position, add a stock they don't yet
hold -- and see the before/after impact on portfolio risk, with an
optional transaction-cost estimate. **Never writes to the database**; the
real portfolio is read, never mutated, verified by a dedicated test that
diffs `/portfolio` before and after calling the endpoint.

### 8.2 Why this is a separate module from Phase 10's `hypothetical.py`

Phase 10 needed one narrow thing: "what if we added this one candidate at
a fixed 10% weight" (a covariance-matrix-implied volatility, no VaR). This
phase needs two things that module doesn't provide: arbitrary
multi-position rebalancing (not just one addition at a fixed weight), and
Value-at-Risk/CVaR, which fundamentally requires a realized return series
(an empirical quantile) rather than just a covariance matrix. Rather than
overload one module with two shapes of "hypothetical", `whatif_service.py`
is self-contained, computing `before` and `after` with the EXACT same
method (the realized-weighted-return-series approach, matching
`PortfolioRiskService.compute()`'s own definition of annualized
volatility) -- the property that actually matters for a trustworthy delta
is internal consistency, not bit-for-bit reuse of Phase 10's code.

### 8.3 Request / computation

- Input: a list of `{symbol, new_quantity}` -- an ABSOLUTE target
  quantity, not a delta. `new_quantity: 0` fully exits a position; a
  symbol not currently held with `new_quantity > 0` is a hypothetical new
  buy.
- Before/after portfolio value weights are built from real current
  holdings with these overrides applied, then both are run through the
  same `_portfolio_metrics()`: annualized volatility, Sharpe, historical
  VaR/CVaR (95%/99%, Phase 8's `historical_var_cvar`), diversification
  ratio, and holdings HHI (Phase 8's `diversification_ratio`/`hhi`).
- `deltas` = after - before for every metric.

### 8.4 Indian transaction cost estimate (optional, `include_costs=true` by default)

Per changed position, modeled on commonly-cited NSE equity delivery-trade
charges:

| Charge | Rate | Side |
|---|---|---|
| Brokerage | 0% (configurable) | both |
| STT (Securities Transaction Tax) | 0.1% | both |
| Stamp duty | 0.015% | buy only |
| Exchange transaction charges | ~0.003% | both |
| SEBI turnover fee | ~0.0001% | both |
| GST | 18% of (brokerage + exchange charges) | both |

**These are illustrative, commonly-cited approximate rates, NOT sourced
from any specific broker's live rate card or a regulatory filing checked
for this project.** Brokerage defaults to 0%, matching the now-common
Indian discount-broker convention of zero brokerage on equity delivery
trades, but is a parameter, not a verified figure. See
`docs/limitations.md` -- this must never be read as real cost guidance.

### 8.5 Measured example (seeded demo portfolio, DEV_SAMPLE data)

Swapping the entire TCS position for 20 shares of SUNPHARMA (reproducible
via `POST /portfolio/what-if` with
`{"changes": [{"symbol": "TCS", "new_quantity": 0}, {"symbol": "SUNPHARMA", "new_quantity": 20}]}`):

| Metric | Before | After | Delta |
|---|---|---|---|
| Annualized volatility | 0.1975 | ~0.186 | -0.012 |
| Diversification ratio | 1.412 | ~1.44 | +0.02-0.05 |
| HHI (holdings) | 0.1464 | ~0.13 | -0.02 |

Directionally consistent with Phase 10's finding that SUNPHARMA (a new
sector for this portfolio) improves diversification -- a useful
cross-check between the two phases' independently-implemented machinery,
though exact figures vary slightly between runs depending on which
holding is swapped and current prices.

---

## 9. Personalized Discovery (Phase 12)

Implemented in `backend/app/portfolio/discover_service.py` and
`backend/app/api/routes/auth.py` (`/auth/me/preferences`). Net-new,
building on Phase 10's Fit Engine rather than superseding it.

### 9.1 What's genuinely new here

`/discover` already ranked by the Fit Engine as of Phase 10 -- this phase
adds the two pieces that were still missing for "personalized": a way for
the user to actually express a preference, and the Fit Engine's
explainability surfaced in the list view itself, not only behind a
per-stock drill-in.

### 9.2 Sector exclusion preferences

`PUT /auth/me/preferences` with `{"excluded_sectors": [...]}` stores the
list as JSON in `UserProfile.preferences` -- a free-form `Text` column
that has existed since Phase 1 and was unused until now, so this needed
**no Alembic migration**. `/discover` hard-filters any stock in an
excluded sector out of the candidate set entirely, before Fit scoring
runs (not a scoring penalty -- a real exclusion). If every present sector
happens to be excluded, discovery falls back to the unfiltered set rather
than silently returning nothing -- a degenerate preference configuration
should never produce an empty, unexplained result.

### 9.3 Query parameters

- `?preset=` -- overrides the user's risk-tolerance-derived default
  preset for this call only (same pattern as `/portfolio-fit/{symbol}`).
- `?sector=` -- restricts candidates to one sector (case-insensitive
  exact match), for explicit sector browsing.

### 9.4 `top_factor`

Each `/discover` item now carries `top_factor: {name, explanation}` --
the single highest-contribution factor from that stock's Fit breakdown
(Phase 10's `factors[0]` after its descending sort). This is NOT
independently computed; it's read directly from the same
`compute_fit_batch()` call that produces `portfolio_fit`, so it is
guaranteed consistent with the detailed breakdown a user would see by
following through to `/portfolio-fit/{symbol}` (modulo the documented
population-dependent score difference from Section 7.3 -- the top
factor's *name* is far more stable across the two endpoints than the
exact score, but is not guaranteed identical in a close contest between
two similarly-weighted factors).

---

## 10. Backtesting (Phase 13)

Implemented in `backend/app/ml/backtest.py`, run via
`backend/scripts/run_backtest.py`. Unlike the market-data/news fetch
scripts, this needs **no network access** -- it runs entirely against
data already in the local database, so (unlike Phases 4/7's fetch
scripts) it was actually executed in this sandbox, and every number below
is real output, not a projection of what the script would produce.

### 10.1 What's backtested

A simple long/flat strategy derived from the Phase 6 classifier: on each
day the model predicts POSITIVE with probability >= 0.55 (the same
threshold `app.ml.predict` uses for the POSITIVE direction label), the
strategy "takes" that stock's realized next-day return; otherwise it's
flat (0 return). Evaluated via the SAME purged walk-forward folds used
for model selection (`app.ml.features.purged_walk_forward_splits`) --
the model is retrained fresh on each fold's train split and only ever
predicts on that fold's held-out test split, pooled across all seeded
stocks. Compared against two baselines evaluated on the exact same
pooled out-of-sample rows: buy-and-hold (always long) and naive momentum
(long when yesterday's return was positive).

### 10.2 Metrics computed

Annualized return/volatility/Sharpe, max drawdown, historical VaR/CVaR
(reusing Phase 8's exact `historical_var_cvar` function), a **Probabilistic/
Deflated Sharpe Ratio** (PSR/DSR, Bailey & Lopez de Prado 2014) for the ML
strategy, a **paired bootstrap** significance test against buy-and-hold,
and a **feature-group ablation**.

### 10.3 Deflated Sharpe Ratio — formula and an explicit verification caveat

```
SR0 = sqrt(V[SR_trials]) * [(1-gamma)*Phi^-1(1-1/N) + gamma*Phi^-1(1-1/(N*e))]
PSR(SR*) = Phi( (SR_hat - SR*) * sqrt(T-1) / sqrt(1 - gamma3*SR_hat + ((gamma4-1)/4)*SR_hat^2) )
DSR = PSR(SR0)
```
where `gamma` = Euler-Mascheroni constant (≈0.5772), `N` = number of
trials, `V[SR_trials]` = variance of the trials' own per-period Sharpe
ratios, `gamma3`/`gamma4` = the strategy return series' skewness and
**Pearson (non-excess) kurtosis** (normal distribution = 3 -- scipy's
`kurtosis(fisher=True)` default is *excess* kurtosis and must have 3
added back before use here), `T` = number of return observations, all
Sharpe ratios **per-period (daily), not annualized** (annualizing first
would double-count the T-scaling).

**This formula was NOT independently verified against the original
Bailey & Lopez de Prado (2014) paper** -- this sandbox has no network
access to fetch it. It was implemented after cross-checking three
independent secondary sources (a Quantt write-up, the `endgame-ml`
library's docs, and the `fynance` library's docs), which converged on the
same structure above, including the "per-period not annualized" and
"Pearson not excess kurtosis" conventions. It has not been checked
against any of those libraries' own numerical reference output. Treat
this implementation as demonstrating the methodology, not as a verified
reproduction of the published metric -- see `docs/limitations.md`.

`N` = 3 trials: the three candidate model types from Phase 6
(`logistic_regression`, `random_forest`, `xgboost`), each independently
backtested the same way to get its own per-period Sharpe; `V[SR_trials]`
is the sample variance (ddof=1) across those three Sharpes. This is an
honestly tiny trial count for an asymptotic extreme-value approximation
designed for much larger N -- the resulting DSR number should be read
accordingly (see 10.5).

### 10.4 Paired bootstrap

1000 resamples (with replacement) of matched (ML-strategy, buy-and-hold)
daily return pairs from the same pooled out-of-sample rows; each
resample's per-period Sharpe difference is recorded. Reports the mean
difference, a 95% bootstrap confidence interval, and the fraction of
resamples where the ML strategy's Sharpe did NOT exceed buy-and-hold's
(a one-sided bootstrap p-value against "no improvement").

### 10.5 Measured results (seeded demo portfolio, DEV_SAMPLE synthetic data)

Reproducible via `python scripts/run_backtest.py` (selected model:
`logistic_regression`, matching `model_metadata.json`):

| Strategy | Ann. return | Ann. vol | Sharpe | Max drawdown | CVaR 95% |
|---|---|---|---|---|---|
| ML strategy | +1.46% | 9.02% | **-0.459** | -18.22% | 1.29% |
| Buy and hold | +8.99% | 27.75% | **+0.233** | -31.91% | 3.58% |
| Momentum | -0.34% | 19.00% | -0.239 | -40.18% | 2.92% |

**The ML strategy underperforms buy-and-hold here** -- Sharpe -0.459 vs.
+0.233. The paired bootstrap confirms this isn't noise in the strategy's
favor: mean Sharpe difference vs. buy-and-hold = **-0.0161** (per-period),
95% CI **[-0.0611, +0.0246]** (includes zero -- not statistically
distinguishable from "no effect" either way at this sample size), and
**75.8%** of bootstrap resamples showed the ML strategy's Sharpe did NOT
exceed buy-and-hold's. Deflated Sharpe Ratio = **0.619** (skewness 0.73,
Pearson kurtosis 38.9 -- very fat-tailed, an expected consequence of a
strategy that's flat most days and only occasionally takes a position) --
a DSR well below a conventional ~0.95 "likely genuine skill" threshold,
consistent with everything else here.

**This is the expected, honest result, not a bug**: Phase 6 already
reported this model's test AUC (~0.545) as barely above random on
synthetic data, and this backtest is the same finding expressed as
trading performance instead of a classification metric. Both numbers
tell the same story from different angles.

### 10.6 Feature-group ablation (same seeded data, `logistic_regression`)

| Feature group removed | Mean validation AUC | Delta vs. full (0.5245) |
|---|---|---|
| *(none — full feature set)* | 0.5245 | 0.0000 |
| returns (`return_1d`, `return_5d`) | 0.5147 | -0.0099 |
| moving averages (`sma5/20_ratio`, `ema20_ratio`) | 0.5061 | **-0.0184** |
| oscillators (`rsi_14`, `momentum_10d`) | 0.5272 | +0.0026 |
| volatility (`volatility_10d`) | 0.5300 | +0.0055 |
| volume (`volume_ratio`) | 0.5246 | +0.0001 |

Removing moving-average features hurts the most (-0.0184 AUC); removing
oscillator, volatility, or volume features doesn't hurt and even nudges
AUC up slightly -- on synthetic random-walk data with no real structure,
this kind of small, directionless fluctuation around 0.50-0.53 AUC is
expected noise, not meaningful feature importance. This ablation should
be re-run once the model trains on real NIFTY data before drawing any
real conclusion about which features matter.

---

## 11. Risk Attribution (Phase 14)

Implemented in `backend/app/portfolio/risk_attribution_service.py`, using
a new pure function `marginal_contribution_to_risk()` added to Phase 8's
`risk_service.py`. New endpoint `GET /portfolio/risk-attribution`;
`GET /portfolio/risk` is untouched (purely additive, no ADR needed).

### 11.1 The question this answers

Phase 8 already computes `risk_contribution_pct` per holding (component
contribution to variance, normalized to sum to 100%) -- but a reader
still has to compare that by eye against the holding's money weight to
notice "this position is small in money but large in risk." This phase
puts the two numbers side by side and computes the ratio directly.

### 11.2 Marginal contribution to risk (MCR)

Portfolio variance is `sigma_p^2 = w' Cov w`. By the chain rule:

```
d(sigma_p)/d(w_i) = (Cov @ w)_i / sigma_p = MCR_i
```

in the SAME units as `sigma_p` itself (e.g. if `sigma_p` is an annualized
volatility of 0.20, `MCR_i` is roughly "how many points of annualized
vol a small increase in holding i's weight would add"). Phase 8 already
computes `(Cov @ w)_i` internally (as `marginal_contrib`, for the
variance-based `risk_contribution_pct`) but never divided by `sigma_p` or
exposed it raw -- this phase does both.

### 11.3 Euler's theorem check

Component contribution `CC_i = w_i * MCR_i` sums EXACTLY to `sigma_p`
(portfolio volatility is a degree-1-homogeneous function of the weights,
so Euler's theorem applies) -- verified in
`test_component_contributions_sum_exactly_to_portfolio_vol_eulers_theorem`
with a hand-worked 2-asset example where this produces an exact 50/50
risk split despite 60/40 money weights (a genuinely clean, pen-and-paper
checkable test case -- see the test file for the full derivation).

### 11.4 `risk_concentration_ratio`

```
risk_concentration_ratio = risk_contribution_pct / weight_pct
```

`> 1` means a holding contributes disproportionately MORE risk than its
money weight would suggest; `< 1` means less. This single number is the
actual point of this phase's UI -- sorted by `risk_contribution_pct`
descending, the holdings at the top with a ratio well above 1 are the
ones concentrating risk beyond what their position size alone would
imply.

### 11.5 Measured example (seeded demo portfolio, DEV_SAMPLE data)

| Symbol | Weight % | Risk contribution % | Concentration ratio |
|---|---|---|---|
| ICICIBANK | 14.62% | 19.87% | **1.359** |
| INFY | 17.39% | 18.70% | 1.075 |
| RELIANCE | 15.02% | 14.66% | 0.976 |
| TCS | 13.51% | 12.98% | 0.961 |
| HDFCBANK | 11.28% | 12.16% | 1.078 |
| LT | 11.30% | 11.18% | 0.989 |
| ITC | 16.88% | 10.44% | **0.618** |

ICICIBANK stands out: 14.6% of money but 19.9% of portfolio risk. ITC is
the opposite -- a large money position (16.9%) contributing
disproportionately less risk (10.4%). Weight % and risk contribution %
each independently sum to ~100% (verified by test).

---

## 12. Stress / Scenario Testing (Phase 15)

Implemented in `backend/app/portfolio/stress_test_service.py` and
`backend/app/portfolio/scenario_parser.py`. New endpoint
`POST /portfolio/stress-test`. Net-new (no ADR — nothing existing
superseded).

### 12.1 Shock mechanism — CAPM beta scaling

For a market-wide shock, each holding's estimated shocked return is:

```
stock_shock_pct = market_shock_pct * beta_vs_nifty50
```

a standard single-factor (CAPM) approximation: a stock with beta 1.5
is estimated to move 1.5x the market shock; a stock with beta 0.5 moves
half as much. Beta uses a 400-day lookback — Phase 5's own documented
recommendation for when beta matters for a decision (stress testing
is exactly such a decision; Phase 5's analysis endpoint defaults to a
shorter window for general display, this phase does not). A holding with
insufficient overlapping history to estimate beta (Phase 5: fewer than
20 overlapping trading days with the benchmark) falls back to beta=1.0
(the market-average assumption), with `used_fallback_beta: true` on that
holding — never silently assumed.

A **sector-specific shock** (`sector_shocks: {sector: pct}`) overrides
beta-scaling entirely for holdings in that sector — applied directly as
that holding's shock, since a sector-level assumption already encodes
sector-specific information the single-factor market-beta model can't.

### 12.2 Named historical scenario presets — explicitly stylized, not literal replay

`SCENARIO_PRESETS` (`covid_2020_crash`, `gfc_2008`, `moderate_correction`)
use publicly well-known, illustrative approximate index-level magnitude
figures (e.g. "NIFTY fell roughly 35-40% peak-to-trough in Feb-Mar 2020"),
**not fetched or verified against a primary source in this sandbox**, and
applied as a SINGLE stylized shock number through the same beta-scaling
mechanism as any hypothetical shock — this is explicitly NOT a literal
day-by-day replay of the actual 2008/2020 price path (this project has no
real historical price data for those periods cached here to replay
literally). Every preset's `note` field states this caveat directly in
the API response, not just in docs.

### 12.3 Scenario text parser — regex, not NLU, translation only

`scenario_parser.py` recognizes a small, fixed set of phrasings
("IT stocks crash 20%", "market drops 15%", "-10% for Healthcare") via
deterministic regex matching against a sector-alias table and a
direction-word list — it is explicitly NOT a natural-language-
understanding system and makes NO call to an LLM. It produces ONLY
structured parameters (`market_shock_pct` or `sector_shocks`), fed into
the exact same deterministic shock calculation as any other input to this
endpoint — it never computes a result and never says anything advisory.
Text it can't confidently parse (no percentage found, an ambiguous
direction, no identifiable sector/market target) raises
`ScenarioParseError` rather than guessing, since a wrong silent guess
would misrepresent what the user actually asked for.

### 12.4 Measured example (seeded demo portfolio, DEV_SAMPLE data)

A -20% market shock (reproducible via
`POST /portfolio/stress-test {"market_shock_pct": -0.20}`):

| Symbol | Beta used | Shock applied | Loss |
|---|---|---|---|
| ICICIBANK | 1.273 | -25.47% | -9,963 |
| INFY | 0.925 | -18.49% | -8,608 |
| RELIANCE | 0.903 | -18.07% | -7,264 |
| HDFCBANK | 1.056 | -21.12% | -6,375 |
| TCS | 0.850 | -16.99% | -6,145 |
| LT | 0.933 | -18.67% | -5,648 |
| ITC | 0.535 | -10.70% | -4,834 |

Total portfolio loss: -18.25% (not a flat -20%, because the
portfolio-weighted average beta is below 1.0) — a sanity-checkable
consequence of the beta-scaling mechanism, not a separately-tuned number.

---

## 13. Counterfactual Explanations for Fit Ranking (Phase 16)

Implemented in `backend/app/portfolio/fit_counterfactual_service.py`. New
endpoints `GET /portfolio-fit/{symbol}/compare/{other_symbol}` and
`GET /portfolio-fit/{symbol}/counterfactual`. Net-new (no ADR).

### 13.1 Why this is tractable

Phase 10's Fit score is `sigmoid(logit)` where
`logit = sum(sign[term] * weight[term] * z[term])` is **additive** across
the five terms. That additivity is what makes two explanation types
directly computable without approximation:

### 13.2 "Why did A rank above B?" — an exact decomposition

```
logit_A - logit_B = sum_term (contribution_A[term] - contribution_B[term])
```

This is an algebraic identity, not an approximation — verified by test
(`test_term_deltas_sum_exactly_to_logit_gap`). Both stocks are evaluated
against the SAME z-scoring population (the full stock universe, via
`PortfolioFitService.compute_fit()` for each), so the comparison is valid
— comparing logits computed against two *different* populations (e.g.
one from `/discover`'s batch, one from this full-universe comparison)
would NOT be valid; see Section 7.3's documented population-dependence.

### 13.3 "What would need to change to rank higher?" — ceteris-paribus, single-term

For a target (another stock's logit, or a target 0-100 Fit score via the
inverse sigmoid `logit = ln(p/(1-p))`), the gap `target_logit -
current_logit` is distributed across each term IN ISOLATION:

```
required_z_delta[term] = gap / (sign[term] * weight[term])
required_raw_delta[term] = required_z_delta[term] * population_std[term]
```

**This is deliberately NOT a joint, minimal-change search across all five
terms simultaneously** — that is a genuinely different (and harder,
unsolved here) constrained-optimization problem. Every result is labeled
"if ONLY this term changed, holding every other term fixed" — both in the
API response's `note` field and here. A small `required_z_delta` does NOT
mean that term is realistically the easiest lever to move in practice;
the model has no concept of which of its own inputs are actually
achievable to change.

### 13.4 Measured example (seeded demo portfolio, DEV_SAMPLE data)

`GET /portfolio-fit/SUNPHARMA/compare/WIPRO` (balanced preset):

| Term | Contribution (SUNPHARMA) | Contribution (WIPRO) | Delta |
|---|---|---|---|
| Diversification Impact | +0.640 | -0.191 | **+0.832** |
| Risk Impact | +0.499 | +0.121 | +0.378 |
| ML Outlook | -0.277 | +0.071 | -0.348 |
| News Sentiment | -0.079 | -0.019 | -0.060 |
| Concentration Impact | +0.162 | +0.162 | 0.000 |

Sum of deltas = 0.8015 = `logit_gap` exactly. SUNPHARMA's fit advantage
over WIPRO (72.0 vs. 53.6) is driven almost entirely by diversification
and risk impact, partially offset by a worse ML outlook term.

---

## 14. Per-Prediction SHAP Explanations (Phase 17)

Implemented in `backend/app/ml/shap_explain.py`, wired into
`app/ml/predict.py`. See `docs/adr/0006-shap-per-prediction-explanations.md`
for what this supersedes (Phase 6's static, training-run-wide
`feature_importance_rank`).

### 14.1 Fast, model-specific explainers

- `logistic_regression`: `shap.LinearExplainer` on the fitted
  `LogisticRegression` step, applied to the scaler-TRANSFORMED feature
  row (LinearExplainer operates on the linear model's own standardized
  input space).
- `random_forest` / `xgboost`: `shap.TreeExplainer`, directly on raw
  features.

Measured at single-digit milliseconds per explanation, vs. ~7.5 seconds
for the generic `shap.Explainer` (permutation-based) against this
project's actual trained models — a real, measured engineering decision.

### 14.2 What's explained: the base estimator, not the calibrated model

SHAP explains `calibrated_model.calibrated_classifiers_[0].estimator` --
the UNCALIBRATED base model extracted from the deployed
`CalibratedClassifierCV`. Phase 6's calibration (Platt/sigmoid scaling)
is a monotonic 1-D remapping of this base score, so it does not change
which features matter or their direction -- but `base_value +
sum(shap_values)` reconstructs the base estimator's own raw score, NOT
the exact calibrated probability actually served to the user. Verified
directly (reproducible via `test_shap_values_reconstruct_base_estimator_logodds_exactly`):
for a real TCS prediction, SHAP's `base_value + sum(shap_values) =
0.2559`, exactly matching `math.log(p/(1-p))` computed from the base
estimator's own `predict_proba` (also `0.2559`) -- an exact algebraic
identity, not an approximation.

### 14.3 Output space differs by model type — an explicit, checked caveat

| Model type | SHAP output space |
|---|---|
| `random_forest` | Natural probability-contribution space (a random forest's leaves are themselves probability estimates — no separate margin concept) |
| `logistic_regression` | Log-odds (margin), pre-sigmoid |
| `xgboost` | Log-odds (margin), pre-sigmoid |

Verified directly against this project's actual trained models (not
assumed from documentation): an XGBoost model's `base_value ≈ 0.00046`
(near zero, consistent with log-odds for a roughly-balanced problem) with
`predict_proba` showing 0.532 — these are NOT the same number, confirming
log-odds space. Every API response reports `shap_output_space` explicitly
so comparing raw SHAP magnitudes across model types without checking it
is never silently wrong.

### 14.4 Background sample

A pooled sample of up to 100 training feature rows (`SHAP_BACKGROUND_SAMPLE_SIZE`),
saved during `train.py::train_and_select_model` alongside the model
artifact (`shap_background.joblib`, gitignored, regenerated on every
retrain) — tied to the exact same training run's data as the deployed
model, used as the SHAP explainer's baseline distribution.

### 14.5 Graceful degradation

If SHAP explanation fails for any reason (missing background sample, an
unrecognized model type, an older model artifact predating this phase),
`predict_for_stock()` falls back to Phase 6's static
`feature_importance_rank` rather than failing the prediction — a
prediction without its per-prediction explanation is still useful.

### 14.6 Measured example (seeded demo data, TCS prediction)

`GET /stocks/TCS/prediction` (model: `logistic_regression`):

| Feature | SHAP value (log-odds) |
|---|---|
| `return_5d` | +0.376 |
| `ema20_ratio` | -0.324 |
| `sma20_ratio` | +0.120 |
| `volume_ratio` | +0.066 |
| *(remaining 5 features)* | each < 0.01 in magnitude |

`important_features` for TCS: `["5-day momentum", "Exponential moving
average trend", "Moving average trend"]`. For INFY (same model, different
feature row): `["Exponential moving average trend", "5-day momentum",
"Moving average trend"]` — a genuinely different ranking (reordered, not
identical), confirming this is per-prediction, not a relabeled static
list.

## 15. Verified Public Track Record (Phase 18)

Implemented in `backend/app/ml/prediction_ledger.py` and
`backend/app/models/prediction_ledger.py`. New, deliberately
UNAUTHENTICATED endpoints: `GET /ledger/entries`, `GET /ledger/verify`,
`GET /ledger/track-record`. See `docs/adr/0007-prediction-ledger.md`.

### 15.1 Hash chain

Every entry's `entry_hash = sha256(previous_entry_hash + canonical_json(payload))`.
`GET /ledger/verify` walks every entry in insertion order, recomputes
each hash from its own stored payload, and checks it against what's
stored -- any alteration of any past entry's payload breaks the chain
from that point forward, which is what "tamper-evident" means
concretely here. Demonstrated directly, not just claimed: disabling the
DB trigger and corrupting a stored field with raw SQL (simulating
privileged access) was caught by `verify_chain()` every time it was
tested.

### 15.2 Two entry kinds, one append-only table

- **`"prediction"`** entries: appended by `predict_for_stock()` the
  first time a (stock, model, day) prediction is genuinely made --
  verified NOT to double-append on repeated same-day reads.
- **`"resolution"`** entries: appended once a prediction's real outcome
  becomes knowable (the next trading day's close exists in the cache),
  linked via `resolves_entry_id`. **The original prediction entry is
  never edited** -- an outcome is always a new chain entry, which is
  what makes "insert-only" true without exception, not an update in
  disguise.

A Postgres trigger (added in the table's own Alembic migration) rejects
any `UPDATE` or `DELETE` against `prediction_ledger` at the database
level -- not just an application-code promise.

### 15.3 Resolution: never guessed

`resolve_due_entries()` only resolves a prediction once BOTH its own
day's close price AND the next trading day's close price already exist
in the cache. `realized_return = close_next / close_pred_date - 1`;
`realized_direction` is `"UP"`/`"DOWN"`/`"FLAT"` by strict sign --
deliberately a different vocabulary from the model's own
`POSITIVE`/`NEGATIVE`/`NEUTRAL` direction, to keep "what the model
predicted" and "what actually happened" visually distinct everywhere
they appear together.

### 15.4 Track record: hit rate + genuine forward paper-trading

`GET /ledger/track-record` reports:
- **Directional hit rate**: among resolved `POSITIVE`/`NEGATIVE`
  predictions only (`NEUTRAL` isn't a directional bet, excluded from
  this specific ratio, its own frequency still visible in the raw entry
  list).
- **Paper trading**: long when the prediction was `POSITIVE`, flat
  otherwise -- the SAME strategy definition as Phase 13's backtest, but
  computed here from real, already-made, immutable predictions in
  chronological order, not a retrospective walk-forward simulation. This
  is the key distinction between Phase 13 and Phase 18: Phase 13 asks
  "how would this methodology have performed historically if replayed
  honestly"; Phase 18 asks "how has the actually-deployed model's
  real, dated, unchangeable output performed since it started being
  recorded." Different questions, deliberately not conflated.

### 15.5 Starting point: honestly thin

As of this phase shipping, the ledger contains only whatever predictions
have genuinely been made since -- no history has been backdated or
fabricated to make the track record look more established. Both the
`/ledger/track-record` response and this document say so directly. A
near-empty or all-pending track record on a freshly deployed instance is
the CORRECT, honest state, not a bug to paper over.

---

*(Sections 16+ — the AI assistant, UI/UX polish, testing/security,
deployment, and final documentation — are added as each corresponding
phase is implemented, not written in advance.)*
