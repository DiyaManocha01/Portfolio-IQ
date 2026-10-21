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

## Infrastructure

- **No Docker / deployment setup yet** (Phase 22).
- **No frontend automated tests yet.**
- **Alembic only has one migration (the baseline)** as of Phase 4 — schema
  changes in later phases must each add a proper migration, not assume
  `create_all` ever runs again (it's been removed from `seed.py`).
