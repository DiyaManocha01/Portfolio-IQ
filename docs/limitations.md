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
- **No access to any Angel One host from this sandbox** (Phase 24):
  `apiconnect.angelbroking.com`, `smartapi.angelbroking.com`,
  `margincalculator.angelbroking.com`, and
  `smartapisocket.angelone.in` are all rejected by the egress proxy
  (verified). See `docs/adr/0008-realtime-market-data-angelone.md` for
  exactly what that means was/wasn't verified.

## Real-Time Market Data (Phase 24)

- **Angel One WebSocket binary tick layout is unverified against a real
  frame.** `angelone_ws_client.parse_tick()`'s byte offsets are built from
  Angel One's publicly documented WS 2.0 "Quote" format, never tested
  against a live stream (network blocked here). It's only proven
  self-consistent (pack/unpack with the same offsets round-trips) — not
  proven to match the real wire format. Verify with real credentials
  before trusting it in a demo: log a few raw frames and sanity-check the
  decoded price/token/timestamp.
- **The scrip-master URL in `scripts/fetch_angelone_instruments.py` is
  community-forum-sourced, not found in Angel One's official docs**, and
  that endpoint has reported reliability issues in forum threads
  (intermittent null responses after Angel One's nightly rebuild). If the
  script fails, retry after a few minutes before assuming it's broken.
- **NSE holiday calendar ships empty.** `session_calendar.NSE_HOLIDAYS`
  is deliberately an empty set — this sandbox can't reach nseindia.com,
  and a web search for "NSE holidays 2026" turned up only third-party
  sites that disagree with each other on several dates. Weekday + hours
  logic (9:15–15:30 IST, Mon–Fri) is correct; holiday-awareness is not,
  until that set is populated from NSE's official published circular.
  Until then, `/market/status` will report `OPEN` on an NSE holiday that
  falls on a weekday.
- **This is a personal-use integration, not a licensed multi-tenant data
  feed.** The running system streams from the project owner's own Angel
  One account. All four evaluated broker APIs (Zerodha, Upstox, DhanHQ,
  Angel One) license data to the account holder's own consumption; none
  license redistributing live data to other end users of a built app
  without separate exchange approval (see ADR 0008). Never present or
  demo this as "any signed-up user gets live broker data."
- **11 of the 20 Phase 24 watchlist symbols still use
  `DevSampleProvider`'s generic fallback price/sector** (base price
  1000.0, sector "Unknown") in the non-real-time code paths — a
  pre-existing Phase 4/5 gap (`providers.py`'s `BASE_PRICES`/`SECTORS`
  dicts only cover 13 symbols), not something Phase 24 changed. Only
  RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, LT, ITC, HINDUNILVR,
  BHARTIARTL, SBIN, WIPRO, MARUTI, SUNPHARMA have hand-tuned synthetic
  calibration today.
- **The real-time feed has never run end-to-end.** `ENABLE_REALTIME_FEED`
  defaults to `false`; turning it on requires the project owner's own
  Angel One credentials in a local `.env` (never committed) and running
  `scripts/fetch_angelone_instruments.py` once with real internet access.
  Until then, `/market/status` and `/ws/market` serve honestly-labeled
  `FIXTURE` data (from `fixture_replay_provider.py`, which exposes the
  same number `MarketDataService.get_quote()` already returns — never a
  fabricated "live" movement).

## Fundamental Analysis & Screener (Phase 26)

- **yfinance's fundamental field coverage for NSE-listed tickers is
  unverified.** This sandbox can't reach query1.finance.yahoo.com (same
  constraint as OHLCV data), so no one has confirmed which `Ticker.info`
  fields actually come back non-null for Indian stocks. Run
  `scripts/fetch_fundamentals.py` locally and check its per-symbol null-field
  report before assuming any field is reliably populated.
- **ROCE (Return on Capital Employed) has no yfinance equivalent at all.**
  `LiveYFinanceProvider.get_fundamentals()` always returns `roce=None`;
  only `DevSampleProvider`'s synthetic data populates it (clearly tagged
  `DEV_SAMPLE`). The UI shows "Not available from this data source," never
  a guess.
- **`debt_to_equity`'s units are unconfirmed.** Yahoo Finance's own
  convention is reportedly a percent-like number (e.g. 45.2, not 0.452),
  but this couldn't be verified against a live response here. The value is
  stored and displayed exactly as the source returns it -- do not assume a
  scale when using it in a calculation until you've confirmed it against
  a real fetch.
- **The screener operates on the seeded demo/discover universe, not the
  full (already-unverified) NIFTY 100 list** -- same scope as the
  pre-existing `GET /stocks` endpoint.
- **`GET /stocks/{symbol}/fundamentals` and `GET /screener` don't require
  auth**, matching `stocks.py`'s existing behavior for the rest of the
  non-user-scoped stock endpoints -- see ADR 0009 for the pre-existing
  docs-vs-code discrepancy this surfaced (ARCHITECTURE.md's route table has
  long claimed `stocks.py` requires auth; the code never enforced it, and
  that predates this phase).

## Intelligent Alerts (Phase 27)

- **No alert has ever fired against real data.** Evaluation runs against
  whatever `DevSampleProvider`/synthetic data this environment has
  seeded -- the price/RSI/volume/sentiment/volatility/concentration/fit
  numbers are real computations, but on development-sample inputs, not a
  genuine market event. See the Phase 4/7/24 limitations above for why.
- **Alerts only evaluate while the backend process is running.** No
  scheduler was added (deliberate -- see ADR 0010); evaluation piggybacks
  on the Phase 24 background loop (every ~30s) plus an on-demand
  `POST /alerts/evaluate`. A rule created while the server is down simply
  waits until the next time it's up; nothing is missed silently, but
  nothing fires silently either.
- **Dedup windows are a design choice, not a measured optimum.** The
  60-second cooldown and once-per-calendar-day limits (for daily-move
  types) were chosen for reasonable behavior, not tuned against any real
  alert-volume data -- there is none to tune against yet.

## Paper Trading (Phase 28)

- **No simulated trade has ever executed against a real market price.**
  Execution prices come from `MarketDataService.get_quote`, the same
  real-or-dev-sample price every other feature uses, but this sandbox
  has no live feed (see the Phase 4/24 limitations above), so every
  trade in this environment's tests and demos fills against
  development-sample data.
- **Fees reuse Phase 11's illustrative, unsourced cost model.**
  `estimate_indian_trade_cost` was never validated against a real
  broker's actual charges -- see the What-If Simulator limitations below
  for the same caveat, which applies identically here.
- **Performance series uses the same "current holdings held constant"
  simplification as the real portfolio.** `get_performance` is not a
  transaction-by-transaction historical reconstruction; it shows what
  the account's current holdings would be worth across the lookback
  window, exactly the same simplification already documented for
  `portfolio_calc.py::get_performance_series()`. A paper account that
  has since sold a position will not show that position's historical
  contribution.
- **The benchmark comparison is NIFTY 50 buy-and-hold only**, normalized
  to the account's starting cash -- not a backtested trading strategy,
  not risk-adjusted, and not a claim that this is how the hypothetical
  account "should" have performed.
- **`total_pnl` and `unrealized_pnl + realized_pnl` will not always
  match while a position is open.** This is intentional, not a bug --
  see ADR 0011 for the fee-drag reasoning.

## Dynamic Portfolio Fit Engine (Phase 29)

- **`fit_score_snapshots` grows unboundedly.** Every cache miss writes a
  new row and none are ever pruned -- fine for this project's scope and
  timeframe, not something a long-running production deployment would
  leave unaddressed.
- **The change explanation names one factor, not the full picture.**
  `_explain_change` reports only the single factor whose contribution
  shifted the most; a move driven by several factors moving together in
  the same direction will still be attributed to just the largest one.
  The full per-factor breakdown remains available in `factors` for
  anyone who wants it.
- **`/discover`'s batch ranking is not cached, by design.** Caching it
  would require caching raw per-term values separately from the final
  z-scored result (batch z-scoring recomputes mean/std across whatever
  candidates are in the batch), which is a genuinely different design
  than the single-stock cache this phase built -- out of scope here, see
  ADR 0012.
- **No cache hit or miss in this sandbox has ever been driven by a real
  market change.** The fingerprint depends on the stock's latest price
  date and the ML model's version; this environment's price data and
  model are only as fresh as whatever was last seeded/trained here, not
  live. See the Phase 4/24 limitations above for why.

## Market Regime Detection (Phase 30)

- **Not validated against any ground truth, because none exists.**
  There is no dataset of "this day was actually a Trending/Sideways/
  High-Vol regime" to check classifications against -- the tests verify
  statistically expected *directional* behavior (sustained drift ->
  modally the matching trend regime; a genuine volatility spike/collapse
  -> always the matching volatility regime), not accuracy against
  labeled outcomes. See ADR 0013.
- **`confidence` is not a probability.** It is a bounded, monotonic
  function of distance from the classification threshold, with no
  calibration target -- do not treat it as "percent chance this regime
  is correct."
- **Thresholds are round, symmetric, and declared up front, not tuned.**
  Both the trend and volatility z-thresholds are exactly 1.0 standard
  deviation. A different, equally defensible choice would reclassify
  some borderline cases differently; this is a property of any
  threshold-based classifier with no ground truth to tune against, not
  a flaw unique to this one.
- **Volatility extremes always override trend**, by design -- a strongly
  trending period whose recent volatility also happens to be unusual
  will be reported as a volatility regime, not a trend regime. This is
  documented, intentional behavior (see ADR 0013), not a missed trend.
- **Not integrated into any other feature yet.** The regime classifier
  is a standalone display (Market page, stock detail page) as of Phase
  30 -- it does not feed into the Fit Engine, alerts, or What-If
  Simulator. That would be a natural future extension.
- **No regime has ever been classified against a real market move**,
  since this sandbox has no live market-data feed -- see the Phase 4/24
  limitations above for why.

## Advanced Portfolio Performance (Phase 31)

- **Realized P&L only covers sales made through the new `/sell`
  endpoint, starting Phase 31.** The `transactions` table existed since
  the original schema but was never populated for the real portfolio
  before this phase; holdings bought, sold, or removed earlier have no
  transaction history and are never backfilled (CLAUDE.md rule 5).
  `realized_pnl` will read 0 for every portfolio until a real sale
  happens from here on.
- **Sell transactions on the real portfolio carry no fee/cost model**,
  unlike Paper Trading's reuse of the Phase 11 Indian brokerage-cost
  model. Phase 31 asked for a realized/unrealized distinction, not a
  cost model, and the real portfolio has never modeled fees anywhere
  else.
- **Sector/holding contribution is to total return (P&L), not risk.**
  It is a different percentage from Phase 14's risk-attribution, which
  allocates portfolio volatility, and the two are not expected to match
  for the same holding.
- **The benchmark comparison is NIFTY 50 buy-and-hold only**, normalized
  to the portfolio's own starting value -- not a backtested strategy,
  not risk-adjusted.
- **Corporate-action handling has never been exercised against a real
  split or dividend in this sandbox.** `auto_adjust=True` is now passed
  explicitly to yfinance, which should already correct for splits and
  dividends in live data, but no stock held here has ever actually
  undergone one during this project's development, since the real-data
  provider has no live network access in this environment (see the
  Phase 4/24 limitations above).
- **`annualized_volatility_realized` and `/portfolio/risk`'s
  `annualized_volatility` can legitimately differ** -- they're computed
  from different underlying return series (this phase's own performance
  series vs. each holding's return series combined via the covariance
  matrix), and disagreement between them is not a bug.

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

## What-If Simulator (Phase 11)

- **Indian transaction cost rates are illustrative, not verified against
  any specific broker or regulatory source for this project.** STT,
  stamp duty, exchange charges, SEBI fee, and GST rates are commonly-cited
  approximate figures for NSE equity delivery trades, hardcoded as
  constants in `whatif_service.py`. Real brokers' actual charges vary, and
  regulatory rates can change; these numbers must never be presented as
  accurate cost guidance, only as an illustrative order-of-magnitude
  estimate. Brokerage defaults to 0% (matching common modern Indian
  discount-broker practice) but is not verified against any particular
  broker either.
- **No market-impact or liquidity modeling.** The simulator assumes any
  simulated trade executes instantly at the latest quoted close price,
  regardless of size -- a large hypothetical trade in a low-liquidity
  stock would, in reality, move the execution price; this is not modeled.
- **Before/after metrics use a different volatility estimation method
  than Phase 10's Fit Engine** (realized-weighted-return-series here vs.
  covariance-quadratic-form in `hypothetical.py`) — see
  `docs/methodology.md` Section 8.2 for why these are two legitimate,
  separately-scoped tools rather than one shared implementation, and why
  that is a deliberate design choice, not an inconsistency to be
  reconciled.
- **Same lookback-window and small-holdings-count instability as Phase 8**
  applies here too — the before/after comparison is only as stable as the
  underlying 180-day return history.
- **Tax implications (capital gains) of a simulated sale are not
  modeled at all** — only transaction-level costs (STT, stamp duty, etc.),
  not income tax on any realized gain/loss. A real sale's tax impact can
  be far larger than the modeled transaction costs and is a materially
  different calculation this project does not attempt.

## Personalized Discovery (Phase 12)

- **Only sector exclusion is implemented as a preference** -- no
  preferred-sector boost, no per-stock exclusion, no risk-level filter
  beyond the existing preset selection. Scoped deliberately narrow to
  avoid double-counting with the Fit Engine's own diversification
  scoring (a "preferred sector" boost would overlap with what
  dDiversification/dConcentration already measure).
- **`top_factor`'s name can occasionally differ from what
  `/portfolio-fit/{symbol}` would show for the same stock** in a close
  contest between two similarly-weighted factors, since the two endpoints
  z-score against different populations (Section 7.3) -- the underlying
  `compute_fit_batch()` call is identical in method, but a different
  batch can occasionally flip which factor ranks first by a small margin.
- **No validation that `excluded_sectors` values match real sector
  names** -- a typo'd sector name is silently a no-op (nothing in that
  "sector" exists to filter), not an error. Not treated as a bug since it
  degrades safely to "no filtering happened," but worth knowing if a
  sector exclusion doesn't seem to be taking effect.

## Backtesting (Phase 13)

- **The Deflated Sharpe Ratio formula was not independently verified
  against the original Bailey & Lopez de Prado (2014) paper.** This
  sandbox has no network access to fetch it. It was implemented after
  cross-checking three independent secondary sources that converged on
  the same formula structure, but has not been checked against any
  published reference numerical example. Treat the DSR number this
  project produces as demonstrating the methodology runs correctly, not
  as a verified reproduction of the published metric. If this project
  is used for a paper/IP submission, re-derive and check this formula
  against the primary source before citing a DSR value from this code.
- **N=3 trials (the three Phase 6 candidate model types) is far smaller
  than the asymptotic extreme-value approximation underlying SR0 is
  designed for.** The DSR this produces is a real, honestly-computed
  number from real code, but should not be read as a statistically
  reliable multiple-testing correction at this trial count — more trials
  (more candidate strategies/models actually tested) would be needed for
  the approximation to be trustworthy.
- **The backtested "strategy" is a simplified long/flat signal
  (probability >= 0.55 → long, else flat)** — not a realistic trading
  strategy (no position sizing, no transaction costs, no slippage, can't
  go short). It exists to produce a real return series for the
  Sharpe/VaR/DSR/bootstrap machinery to operate on, not as a strategy
  recommendation.
- **All Phase 13 numbers are measured on synthetic DEV_SAMPLE data** —
  the same caveat as Phase 6: a random walk has no real learnable signal
  by construction, so the ML strategy honestly underperforming
  buy-and-hold here says the methodology works, not that the underlying
  model is bad (or good) at predicting real markets. Must be re-measured
  once the model trains on real cached NIFTY data.
- **The ablation study reuses the uncalibrated AUC-ranking methodology**
  from Phase 6's candidate selection (not the calibrated, backtested
  Sharpe) — a feature group's effect on classification AUC and its
  effect on backtested trading performance are related but not
  identical questions; this project only measures the former for
  ablation.
- **The equity-curve x-axis is a pooled observation index, not a
  calendar axis** — because folds and stocks are pooled together, a
  given x position does not correspond to one real calendar date across
  strategies in a visually intuitive way; this is stated directly in the
  chart's axis label, not hidden.

## Stress / Scenario Testing (Phase 15)

- **Single-factor (CAPM beta) approximation only.** Real market stress
  typically involves correlation spikes (diversification benefits
  shrinking exactly when they're needed most) and idiosyncratic,
  holding-specific effects — neither is modeled here. A beta-scaled shock
  is a standard, well-understood first approximation, not a realistic
  simulation of how a real crisis would actually distribute across these
  specific holdings.
- **Historical scenario presets are stylized single-number shocks, not a
  literal historical replay.** The documented magnitude figures (e.g.
  "COVID 2020: ~-38%") are publicly well-known approximate facts, not
  independently verified against a primary source in this sandbox, and
  not tied to any actual historical daily price path for these specific
  holdings (which this project has no cached data for).
- **Beta fallback (1.0) when insufficient history exists is a real
  assumption, not a measurement** — flagged per-holding
  (`used_fallback_beta`) but still just an assumption, most likely to
  bind for newly-added candidate stocks.
- **The scenario text parser is regex pattern-matching, not natural
  language understanding.** It recognizes a small, fixed vocabulary of
  sector aliases and direction words — a real-world phrasing outside that
  vocabulary will correctly fail to parse (raising `ScenarioParseError`)
  rather than silently misinterpreting it, but this means the parser's
  practical coverage of plain-English requests is narrow by design, not
  an oversight to be "fixed" by loosening the matching (which would trade
  the current fail-safe behavior for a fail-silent one).
- **No cross-sector correlation or event-driven co-movement is modeled**
  in a sector-specific shock — shocking one sector doesn't propagate any
  spillover effect to other sectors, even though real sector shocks
  usually do have some spillover.

## Counterfactual Explanations for Fit Ranking (Phase 16)

- **The counterfactual is ceteris-paribus and single-term, never a joint
  minimal-change search.** `what_would_improve_rank()` answers "if ONLY
  this term changed, how much would it need to move" for each of the 5
  terms independently — it does NOT search for the smallest combined
  change across multiple terms that would close the gap (a genuinely
  different, harder optimization problem this project does not attempt).
  A required single-term change being numerically small must not be read
  as "this is the easiest or most realistic way to improve the ranking."
- **Comparisons are only valid within the same z-scoring population.**
  `/portfolio-fit/{symbol}/compare/{other_symbol}` and `/counterfactual`
  both z-score against the full stock universe (matching the single-stock
  `/portfolio-fit/{symbol}` endpoint's population) — comparing a logit
  from this endpoint against a logit computed via `/discover`'s
  batch-scoped z-scoring (Section 7.3) would not be valid, and this
  service never mixes the two.
- **No causal claim is made or implied.** A term's raw value moving by
  the computed `required_raw_delta` is a mathematical statement about
  this specific linear(-in-z-space) formula, not a claim that the
  underlying real-world quantity (e.g. sentiment, ML outlook) is easy or
  even possible to move by that amount, or that doing so would have no
  side effects on the other terms in reality (the ceteris-paribus
  assumption is a modeling simplification, not a fact about markets).

## Per-Prediction SHAP Explanations (Phase 17)

- **SHAP output units differ by model type** — `random_forest`'s
  TreeExplainer output is in natural probability-contribution space,
  while `logistic_regression` and `xgboost` are in log-odds (margin)
  space. `shap_output_space` is reported explicitly on every prediction;
  comparing raw `shap_values` magnitudes across a model-type switch (if
  retraining later selects a different candidate) without checking this
  field would be a real error.
- **SHAP explains the uncalibrated base estimator, not the calibrated,
  actually-served model.** Calibration is monotonic (doesn't change
  feature ranking/direction), but `base_value + sum(shap_values)` does
  NOT reconstruct the exact served probability — it reconstructs the base
  estimator's own raw score. This is a real, documented approximation
  trade-off, not an oversight (see ADR 0006's alternatives-considered
  section for why a slower, more "complete" approach was not used).
- **The background sample (100 pooled training rows) is a fixed
  convention**, not validated against SHAP literature's recommended
  background size for this specific problem — a reasonable default, not
  a tuned choice.
- **Still runs on synthetic DEV_SAMPLE data** — like Phase 6's model
  itself, the feature attributions are honestly computed from a model
  with near-random predictive power on this data; a feature with a large
  SHAP value here is driving a prediction that itself has little real
  predictive value, not necessarily a "genuinely important" signal in any
  market sense.

## Verified Public Track Record (Phase 18)

- **Tamper-EVIDENT, not tamper-PROOF.** The hash chain + DB trigger
  combination detects alteration by an application bug or unprivileged
  access, and was directly tested against a simulated privileged tamper
  (trigger disabled, raw SQL edit) -- caught every time. But someone with
  full database administrator access could still truncate the whole
  table and start a fresh chain from scratch, and nothing inside this
  system would detect that from outside the database itself. A genuinely
  tamper-proof public record needs external anchoring (periodically
  publishing the latest hash somewhere outside this project's own
  control) -- explicitly out of scope for this phase.
- **The ledger starts nearly empty.** No history has been backdated or
  fabricated. A thin or all-pending track record reflects how new the
  ledger is, not a data gap or a bug -- stated directly in the
  `/ledger/track-record` API response itself, not only here.
- **Resolution uses cached OHLCV data**, which for this project's
  default `DEV_SAMPLE` mode is synthetic. A resolved "outcome" against
  synthetic data confirms the resolution mechanism works correctly; it
  is not a real market outcome. Must be re-evaluated once real NIFTY
  cache data is the default.
- **Resolution is lazy** (triggered by `/ledger/verify` and
  `/ledger/track-record` calls catching up pending entries), not a
  scheduled job -- there's no cron infrastructure in this environment. A
  real deployment would run `resolve_due_entries()` on a daily schedule
  instead; documented as a simplification, not hidden.
- **The directional hit rate excludes `NEUTRAL` predictions** from its
  denominator (they aren't a directional bet) -- a `NEUTRAL`-heavy model
  will show a hit rate computed over a small subset of its total
  predictions, which must be read alongside `directional_predictions_resolved`,
  not in isolation.
- **Paper trading has no position sizing, transaction costs, or
  compounding assumptions beyond simple chronological compounding** --
  it is a direct measurement tool for the recorded predictions, not a
  realistic trading simulation (Phase 11's What-If Simulator and Phase 13's
  backtest separately model transaction costs and realistic position
  sizing for their own, different purposes).

## AI Portfolio Assistant (Phase 19)

- **The live LLM call has never been executed in this sandbox.** No
  `ANTHROPIC_API_KEY` is configured here. Every deterministic piece
  (context routing, JSON-serialization of fetched data, the guardrail
  filter, the 503-when-unconfigured path) is tested and verified; the
  actual Claude API round-trip is not, and can't be until the project
  owner sets a real key locally. Network reachability to
  `api.anthropic.com` WAS verified directly from this sandbox (got a
  real 401 response, not a connection error) -- unlike Yahoo
  Finance/Hugging Face/the RSS hosts, which are actually blocked -- so
  the integration is expected to work once a key is set, but this is an
  expectation, not a demonstrated fact.
- **The guardrail is keyword-based, not semantic.** It catches a
  specific, hand-picked set of advice-like phrasings and was tested
  against them, but a sufficiently differently-worded piece of advice
  ("TCS looks like a great opportunity right now" with no "buy"/"sell"
  verb) could slip through the regex. The system prompt is the primary
  defense; the keyword filter is explicitly defense-in-depth, not a
  complete solution, and both layers rely on the underlying model
  actually following instructions it has no mechanism to be forced to
  follow.
- **The data router's keyword matching can both over- and
  under-trigger.** A question containing "risk" in an unrelated sense
  would still pull in risk data (harmless -- more context, not wrong
  context); a question that needs stock-specific data but doesn't
  literally contain that stock's ticker symbol (e.g. "what about the IT
  stock I hold") would NOT trigger `stock_details` and the assistant
  would correctly have to say it lacks that specific data, per its
  system prompt -- a real coverage gap, not a crash, but a gap.
- **No conversation memory.** Each `/assistant/ask` call is independent
  -- there's no multi-turn context carried between questions.
  **Cost and latency are real** (an external paid API call per
  question). As of Phase 21, `/assistant/ask` is rate-limited
  (20 requests/minute per client IP, via the same `slowapi` limiter used
  on the auth endpoints) as a basic cost-control/abuse backstop -- this
  bounds the *rate* of paid API calls a single client can trigger, it
  does not model or cap total cost.
- **The assistant cannot verify its own citations are accurate** beyond
  what the system prompt instructs -- there's no automated check that a
  cited number in the response text actually matches a value in the
  context block (that would require parsing the LLM's natural-language
  output for embedded numbers and cross-checking them, not attempted
  here).

### Phase 32 additions

- **The What-If parser (`app/assistant/whatif_parser.py`) only
  recognizes two phrasings, deliberately** (a project decision, not an
  oversight -- see ADR 0015): an explicit share count ("added/sold N
  shares of X") or a full exit ("sold all my X"), against exactly one
  mentioned stock. Weight-based phrasing ("at 10% weight"), a
  quantity-free request ("what if I added some RELIANCE"), and
  multi-stock scenarios ("what if I added X and sold Y") all return
  `could_not_parse` rather than a guessed result -- a real coverage gap
  for anyone asking the assistant those questions, not a crash. The
  Portfolio Lab's What-If Simulator (Phase 11/20) handles all of these
  directly.
- **`historical_performance` is a summary, not the full daily series**
  -- an LLM asked to describe a 180-point series in prose risks
  restating a value as a slightly different number even when told to
  cite near-verbatim; the summary avoids handing it a wrong-restating
  opportunity it doesn't need, but means a question like "what was my
  return on March 3rd specifically" cannot be answered by the assistant
  even though the full series exists at `GET /portfolio/performance/
  advanced`.
- **`market_conditions` and `fit_engine` only trigger with the right
  keywords plus a mentioned stock (for `fit_engine`) or trigger
  market-wide regardless of a stock being named (for
  `market_conditions`)** -- same category of over/under-triggering
  already documented above for Phase 19's original keyword sets.
- **`context_compiled_at` is a single top-level timestamp, not a
  per-block one for every piece of data.** Phase 19's original blocks
  (`portfolio_summary`, `portfolio_health`, `portfolio_weaknesses`,
  `stock_details`) have no block-level timestamp of their own; the
  assistant is instructed to fall back to `context_compiled_at` for
  those, which is accurate for when the context was assembled but not
  for when each underlying number was actually computed/cached.

## Infrastructure

- **Alembic only has one migration (the baseline)** as of Phase 4 — schema
  changes in later phases must each add a proper migration, not assume
  `create_all` ever runs again (it's been removed from `seed.py`).

## Deployment (Phase 22)

- **Docker Compose setup added, but full `docker compose up` has not
  been run end-to-end from this project's own development sandbox.**
  Both Dockerfiles pass `docker build --check` and `docker compose
  config` was inspected by hand (catching and fixing a real
  `backend/.env.example` parsing bug along the way — see
  `docs/DEPLOYMENT.md`), but this sandbox's containers cannot complete
  outbound HTTPS to PyPI/npm (verified: `CERTIFICATE_VERIFY_FAILED` —
  this sandbox's egress performs TLS interception that the host trusts
  via tooling not present inside a fresh container) and separately hit
  intermittent Docker Hub pull rate-limiting. A one-off, not-committed
  variant of the backend Dockerfile with the sandbox's CA temporarily
  trusted was used to get real signal on whether `pip install -r
  requirements.txt` actually resolves against the full pinned dependency
  set — see `docs/DEPLOYMENT.md`'s "What has (and has not) been
  verified" section for the result. **The project owner should run
  `docker compose up --build` once on a normal machine** before relying
  on this for a demo.
- **No production hardening** (TLS/reverse proxy, secrets manager,
  resource limits, log aggregation, multi-replica orchestration) — this
  is a local/demo Compose setup, stated plainly as such in
  `docs/DEPLOYMENT.md`.
- **The Phase 21 rate limiter's in-memory storage does not span multiple
  backend replicas** — a non-issue for this single-`backend`-container
  Compose setup, a real gap for any scaled deployment.

## Testing & Security (Phase 21)

- **Frontend automated tests were added in Phase 21** (Vitest + React
  Testing Library) covering `utils/format.ts` and smoke-level rendering
  of the Phase 20 UI (loading/error/data states, form submission,
  mocked service responses) — not full user-flow coverage, and no
  visual-regression or accessibility testing.
- **See `docs/security-review.md`** for the full Phase 21 dependency
  audit, what was upgraded/replaced vs. deferred and why, and what the
  new auth/assistant rate limiting does and does not cover.
