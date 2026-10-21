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
  exercised in this environment.

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
  real cached NIFTY data (Phase 6) — the current figure says nothing about
  real-world model quality and must never be quoted as if it does.
- **No probability calibration yet.** Phase 6 will add isotonic/Platt
  calibration; until then, the model's raw `predict_proba` output is used
  directly, which is a known source of miscalibrated confidence in
  gradient-boosted/ensemble classifiers.

## Infrastructure

- **No Docker / deployment setup yet** (Phase 22).
- **No frontend automated tests yet.**
- **Alembic only has one migration (the baseline)** as of Phase 4 — schema
  changes in later phases must each add a proper migration, not assume
  `create_all` ever runs again (it's been removed from `seed.py`).
