# Known Limitations

Kept updated as limitations are found, per the project's working rules.
Each entry says what's limited, why, and what (if anything) would resolve
it. Nothing here is a hidden caveat — if it affects a number shown in the
UI, the methodology doc, or a future paper, it's listed here.

## Environment / network

- **No live market-data access from this sandbox.** The egress proxy
  blocks `query1.finance.yahoo.com` (verified directly: `CONNECT` refused).
  `LiveYFinanceProvider` therefore cannot be exercised against live data
  here — only against the local Parquet cache (Phase 4), which must be
  populated by running `scripts/fetch_nifty100.py` on a machine with real
  internet access.
- **No Hugging Face access from this sandbox.** `huggingface.co` is
  similarly blocked, so the FinBERT sentiment provider (`nlp/finbert_sentiment.py`)
  has never downloaded model weights or been run here. The lexicon-based
  provider (`nlp/lexicon_sentiment.py`) is the only sentiment path actually
  exercised in this environment. `scripts/evaluate_finbert.py` (Phase 7)
  has similarly never been run here for the same reason.
- **No access to Economic Times / Moneycontrol RSS from this sandbox**
  either (Phase 7). `scripts/fetch_news_rss.py` has never been run here;
  all news shown by the running app in this environment is the synthetic
  template generator (`USE_LIVE_NEWS=false`, the default).

## News & Sentiment (Phase 7)

- **Headline-to-stock matching is unvalidated.** `services/news/matching.py`
  matches category-level RSS headlines to stocks via regex search for
  distinctive company-name fragments. This has NOT been measured against a
  labeled ground-truth set — both false positives (an unrelated headline
  happening to contain a matched term) and false negatives (a relevant
  headline phrased in a way that doesn't match any term) are expected and
  unquantified.
- **Bare short tickers are deliberately excluded from matching** (e.g.
  `LT`) to avoid obvious collisions, at the cost of missing headlines that
  refer to a company only by its bare ticker.
- **RSS feed URLs can go stale.** `fetch_news_rss.py` reports (does not
  silently ignore) a feed returning zero entries or a fetch error, but the
  feed list itself (`services/news/rss_feeds.py`) is not continuously
  verified — it may need updating if Economic Times or Moneycontrol change
  their feed URLs.
- **The FinBERT-vs-lexicon "agreement rate"** produced by
  `evaluate_finbert.py` is NOT an accuracy measurement — there is no
  human-labeled sentiment ground truth for these headlines in this
  project. It measures how often two unsupervised scorers agree, nothing
  more. See `docs/methodology.md` Section 4.5 for the full caveat and the
  documented FinBERT English/US-training-data limitation for Indian
  financial text.
- **`SENTIMENT_HALF_LIFE_DAYS = 7.0`** (the time-decay aggregation
  constant) is a documented, chosen default, not empirically derived or
  tuned against real headline cadence (since real cadence data requires
  running the RSS fetch script, which hasn't happened in this sandbox).

## Data

- **NIFTY 100 symbol list is unverified against a live/official source**
  (`services/market_data/nifty100.py`). Compiled from general knowledge,
  not fetched from NSE's index methodology page or a dated index snapshot.
  Must be re-verified against an official source before Phase 13
  (backtesting) or any paper/IP write-up cites results computed over it.
- **Survivorship bias in the symbol universe.** The cache only covers
  symbols currently believed to be in the NIFTY 100; companies that were
  large/index members historically but have since been delisted, merged,
  or dropped are absent. Any backtest run over this universe is biased
  toward companies that happened to survive and remain large — this must
  be stated alongside any backtest result (Phase 13), not just here.
- **No real OHLCV fixture is committed yet.** `fetch_nifty100.py --out-fixture`
  produces one, but it requires network access this sandbox doesn't have.
  Until a human runs it and commits the output, `test_market_data_cache.py`
  tests only against synthetic, clearly-labeled fixtures — they test the
  cache/validation *code*, not real-data behavior.
- **Demo/seeded data is synthetic.** The 13 symbols seeded by
  `app/data/seed.py` via `DevSampleProvider` are a deterministic random
  walk with an injected shared market factor for realistic cross-stock
  correlation — not real prices. Every API response carrying this data is
  tagged `"data_source": "DEV_SAMPLE"`; never present it as real.

## ML

- **Validation/test AUC is close to random (~0.50-0.56)** on the current
  synthetic training data (see `backend/app/data/models/model_metadata.json`
  after running the seed script). This is expected and reported honestly:
  a synthetic random walk has very little real learnable signal by
  construction. This number must be re-measured once the model trains on
  real cached NIFTY data (Phase 4's cache, populated locally) — the current
  figure says nothing about real-world model quality and must never be
  quoted as if it does.
- **`CalibratedClassifierCV`'s internal calibration folds are not
  time-aware** (Phase 6). The outer purged walk-forward CV used for model
  *selection* is correctly time-ordered and embargoed, but scikit-learn's
  `CalibratedClassifierCV(cv=3)` used for the final probability
  *calibration* step uses an ordinary (non-time-aware) internal k-fold.
  This is a real simplification, not a silently-accepted gap — a fully
  rigorous version would need a custom purged calibration split. See ADR
  0003 and `docs/methodology.md` Section 3.5.
- **Isotonic calibration was considered and rejected for now** (sigmoid/Platt
  used instead) because per-fold training sample sizes (a few hundred rows
  on synthetic data) are small enough that isotonic regression risks
  overfitting the calibration curve itself. Revisit once training runs on
  the full real NIFTY 100 cache, which will have far more data per fold.

## Portfolio Risk (Phase 8)

- **Shrinkage intensity is auto-selected per computation, not tuned.**
  `sklearn.covariance.LedoitWolf` picks its own shrinkage intensity from
  the data on every call — there is no fixed/validated target intensity,
  and it is not cross-validated against a downstream objective (e.g.
  out-of-sample portfolio variance forecasting accuracy). It is reported
  (`shrinkage_intensity` in the API response) rather than hidden, but its
  "correctness" has not been separately validated.
- **VaR/CVaR are historical-simulation, not parametric or Monte Carlo.**
  They assume the realized return distribution over the lookback window
  (default 180 days) is representative of near-future risk — a classic
  historical-VaR assumption that breaks down in regime changes. No
  parametric (variance-covariance) or simulated alternative is computed
  alongside it for comparison yet.
- **"Effective number of bets" is the weight-concentration definition**
  (`1/HHI`), not the PCA/correlation-aware "effective number of
  *independent* bets." The two numbers answer different questions and are
  not interchangeable — see `docs/methodology.md` Section 5.5 and ADR
  0004's alternatives-considered section for why the more involved
  correlation-aware version was deferred rather than approximated.
- **Diversification ratio's strict `>= 1` theoretical bound is not
  guaranteed to the last decimal**, because the portfolio volatility in
  the ratio comes from the Ledoit-Wolf-shrunk covariance matrix while the
  standalone volatilities used in its numerator come from raw sample
  standard deviations — shrinkage can reshape the covariance diagonal
  slightly away from the raw sample variances that the strict
  subadditivity proof assumes. Not observed as an issue in practice
  (measured at 1.412 on the seeded demo portfolio) but not proven
  impossible either; the integration test uses a `> 0.9` sanity floor
  rather than asserting the strict bound for this reason.
- **All Phase 8 metrics inherit Phase 4's data limitations** (synthetic
  DEV_SAMPLE data by default; real NIFTY cache numbers require the user to
  run `fetch_nifty100.py` locally) and the existing small-holdings-count
  instability noted for beta in Phase 5 — a covariance matrix estimated
  from 5-15 holdings over a 180-day window is inherently noisier than one
  estimated from a larger universe or longer window, which is exactly the
  problem Ledoit-Wolf shrinkage mitigates but does not eliminate.

## Portfolio Optimization (Phase 9)

- **Mean-variance optimization is highly sensitive to the expected-return
  estimate.** `mean_historical_return` is just each stock's own past
  compound growth rate over the lookback window — a famously noisy
  estimator of a genuinely forward-looking "expected return." This is why
  `max_sharpe` on the seeded demo portfolio concentrates 84% of suggested
  weight into a single stock: mean-variance optimization is known to
  produce extreme, concentrated allocations when fed noisy return
  estimates, and this project does not apply any of the standard
  mitigations (Black-Litterman views, return shrinkage, max-position
  constraints beyond the long-only bound) yet. The suggestion is honestly
  computed, not honestly *advisable* without those safeguards — the
  disclaimer on every response says so.
- **`risk_parity` is Hierarchical Risk Parity (HRP), not naive/equal-risk-
  contribution risk parity.** The two are different algorithms that can
  produce different weights; see `docs/methodology.md` Section 6.2. Using
  the term "risk parity" without qualification elsewhere in casual
  conversation about this feature would be imprecise.
- **`max_sharpe` can be infeasible** (raises, caught and surfaced as
  `feasible: false`) when no held stock's historical expected return
  exceeds the 6% risk-free rate assumption — expected on synthetic data
  with near-zero or negative drift, reported rather than papered over.
- **No position-size, sector, or turnover constraints** beyond long-only
  are applied — a suggested reallocation could imply selling an entire
  position or concentrating heavily in one name, with no cost/tax/turnover
  penalty modeled (that's deferred to Phase 11's What-If Simulator, which
  will optionally model Indian transaction costs).
- **Same lookback-window and small-holdings-count instability as Phase 8**
  — the covariance matrix feeding the optimizer has the same estimation
  noise discussed there, mitigated by shrinkage but not eliminated.

## Portfolio Fit Engine (Phase 10)

- **Factor "contribution" is in pre-sigmoid (logit) units, not a linear
  share of the 0-100 fit_score.** Contributions sum exactly to the
  sigmoid's input; the final `100 / (1 + exp(-logit))` squash is
  nonlinear, so they do not partition the displayed score additively.
  Documented in `docs/methodology.md` Section 7.4 — a UI that sums
  contributions and expects the total to equal `fit_score` would be
  wrong.
- **The same stock's fit_score differs between `/portfolio-fit/{symbol}`
  and `/discover`** because each z-scores against a different population
  (the full universe vs. the unheld-candidate batch). This is intentional
  — see Section 7.3 — but worth stating plainly since it could otherwise
  look like a bug to anyone comparing the two screens side by side.
- **The hypothetical "add at 10% target weight" sizing is a fixed
  convention, not tuned or user-configurable yet.** A stock's measured
  dRisk/dDiversification/dConcentration would differ at a different
  hypothetical sizing (e.g. 5% vs. 20%) — this project does not currently
  report sensitivity to that choice. Phase 11's What-If Simulator, which
  lets the user specify an actual target weight/amount, is the intended
  way to explore this directly rather than relying on the Fit Engine's
  fixed convention.
- **Z-scoring against a small universe (the current ~13-20 seeded
  stocks) is less statistically stable than against a larger one.** Once
  a full NIFTY 100 cache is populated (Phase 4's `fetch_nifty100.py`, run
  locally), z-scores will be computed against a much larger, more
  representative population — current scores should be read as
  demonstrating the methodology, not as stable rankings.
- **Computing raw terms for the full universe is O(n) per fit/discover
  request** (one `hypothetical_metrics_after_adding()` simulation per
  candidate stock, each itself doing a covariance fit). Fine at the
  current seeded-universe scale; would need caching or batching if the
  universe grows to the full NIFTY 100 and this becomes a per-request
  cost on a hot path — not yet implemented, noted here rather than hidden.
- **Correlation with current holdings is reported as a simple average**
  (a diagnostic only, not a Fit score input) — the same unweighted-average
  simplification the old service used, still not accounting for how
  correlated the *existing* holdings are with each other.

## Infrastructure

- **No Docker / deployment setup yet** (Phase 22).
- **No frontend automated tests yet.**
- **Alembic only has one migration (the baseline)** as of Phase 4 — schema
  changes in later phases must each add a proper migration, not assume
  `create_all` ever runs again (it's been removed from `seed.py`).
