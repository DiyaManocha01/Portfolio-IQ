Hand-written TEST-ONLY fixtures for the fundamentals cache round-trip
tests. Unlike `app/tests/fixtures/real_ohlcv_sample/` (genuinely fetched
via `scripts/fetch_nifty100.py --out-fixture`), the numbers in this
directory are plausible-looking but made up -- never fetched from
yfinance or any real source. Do not use these as real financial data for
anything, including a demo, a slide, or a paper claim. Real fundamentals
come only from running `scripts/fetch_fundamentals.py` locally.
