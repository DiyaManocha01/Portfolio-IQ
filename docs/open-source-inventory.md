# Open-Source Inventory

Authoritative, append-only-in-spirit ledger of every third-party dependency
added to this project: what it is, its license, why it's here, and which
phase introduced it. `docs/THIRD_PARTY_LICENSES.md` is the older,
narrative-grouped version of the same information (kept for readability);
this file is the source of truth going forward per the project's working
rules (rule 7: check and record the license of every new dependency).

When adding a dependency: add a row here in the same commit that adds it
to `requirements.txt` / `package.json`.

## Backend (Python)

| Package | Version | License | Added in | Purpose |
|---|---|---|---|---|
| fastapi | 0.115.6 | MIT | Phase 1 | Web framework |
| uvicorn | 0.34.0 | BSD-3-Clause | Phase 1 | ASGI server |
| sqlalchemy | 2.0.36 | MIT | Phase 1 | ORM |
| psycopg2-binary | 2.9.10 | LGPL-3.0 | Phase 1 | PostgreSQL driver |
| pydantic / pydantic-settings | 2.10.4 / 2.7.1 | MIT | Phase 1 | Validation, settings |
| email-validator | 2.2.0 | CC0-1.0 / BSD-2-Clause (dual) | Phase 1 | Pydantic `EmailStr` support |
| PyJWT | 2.15.1 | MIT | Phase 1 (swapped from python-jose in Phase 21) | JWT encode/decode. Replaced python-jose in Phase 21's security review: python-jose 3.4.0 had an unpatched CVE (PYSEC-2026-4298, no fix version available) and pulled in `ecdsa`/`pyasn1` transitively with their own findings; this app only uses symmetric HS256, which PyJWT supports natively without those extra dependencies. |
| passlib / bcrypt | 1.7.4 / 4.0.1 | BSD-3-Clause / Apache-2.0 | Phase 1 | Password hashing |
| python-multipart | 0.0.32 | Apache-2.0 | Phase 1 (bumped Phase 21) | Form parsing |
| python-dotenv | 1.2.2 | BSD-3-Clause | Phase 1 (bumped Phase 21) | `.env` loading |
| pandas | >=2.2.3 | BSD-3-Clause | Phase 3 | Data manipulation |
| numpy | >=1.26.4 | BSD-3-Clause | Phase 3 | Numerical computing |
| scikit-learn | >=1.5.2 | BSD-3-Clause | Phase 3/6 | ML models, preprocessing, metrics |
| xgboost | >=2.1.3 | Apache-2.0 | Phase 3/6 | Gradient-boosted classifier |
| alembic | 1.14.0 | MIT | Phase 1 (unused until Phase 4) | Schema migrations |
| pytest | 9.0.3 | MIT | Phase 1 (bumped Phase 21) | Testing |
| httpx | 0.28.1 | BSD-3-Clause | Phase 1 | Test client HTTP support |
| **yfinance** | **0.2.51** | **Apache-2.0** | **Phase 4** | **Live/cached market data source** |
| **pyarrow** | **23.0.1** | **Apache-2.0** | **Phase 4 (bumped Phase 21)** | **Parquet read/write for the local market-data cache** |
| **matplotlib** | **3.11.2** | **PSF-based (BSD-style, matplotlib's own permissive license)** | **Phase 6** | **Calibration/reliability plot for the ML prediction pipeline** |
| **feedparser** | **6.0.14** | **BSD-2-Clause** | **Phase 7** | **Parses Economic Times / Moneycontrol RSS feeds for real headline ingestion** |
| **pyportfolioopt** | **1.6.0** | **MIT** | **Phase 9** | **Min-variance / max-Sharpe / HRP portfolio optimization suggestions** |
| **cvxpy** (transitive, via pyportfolioopt) | 1.9.3 | Apache-2.0 | Phase 9 | Convex optimization backend for min-variance/max-Sharpe |
| **clarabel** (transitive) | 0.11.1 | Apache-2.0 | Phase 9 | Conic solver used by cvxpy |
| **osqp** (transitive) | 1.1.3 | Apache-2.0 | Phase 9 | QP solver used by cvxpy |
| **qdldl** (transitive) | 0.1.9.post1 | Apache-2.0 | Phase 9 | Sparse linear algebra, osqp dependency |
| **scs** (transitive) | 3.3.1 | MIT | Phase 9 | Conic solver used by cvxpy |
| **highspy** (transitive) | 1.15.1 | MIT | Phase 9 | LP/MIP solver used by cvxpy |
| **scikit-base** (transitive, via pyportfolioopt's HRP path) | 0.13.2 | BSD-3-Clause | Phase 9 | sktime-ecosystem base classes |
| **sparsediffpy** (transitive) | 0.6.1 | Apache-2.0 | Phase 9 | Sparse differentiation, cvxpy dependency |
| **jinja2** (transitive) | 3.1.6 | BSD-3-Clause | Phase 9 | Templating, osqp dependency |
| **scipy** | 1.17.1 | BSD-3-Clause | Phase 13 | Normal distribution CDF/quantile (`stats.norm`) and skew/kurtosis for the Deflated Sharpe Ratio backtest calculation. Already an indirect dependency of scikit-learn; promoted to an explicit, version-pinned direct dependency now that `app/ml/backtest.py` imports it directly. |
| **shap** | 0.51.0 | MIT | Phase 17 | Per-prediction feature-attribution explanations for the ML direction classifier |
| **slicer** (transitive, via shap) | 0.0.8 | MIT | Phase 17 | Array slicing utility, shap dependency |
| **numba** (transitive, via shap) | 0.68.0 | BSD-2-Clause | Phase 17 | JIT compilation, shap dependency |
| **llvmlite** (transitive, via numba) | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | Phase 17 | LLVM bindings, numba dependency |
| **tqdm** (transitive, via shap) | 4.70.1 | MPL-2.0 AND MIT | Phase 17 | Progress bars, shap dependency. MPL-2.0 is file-level weak copyleft -- fine as an unmodified dependency, not a concern for this project's own code. |
| **anthropic** | 0.73.0 | MIT | Phase 19 | Official SDK for Claude API calls powering the AI portfolio assistant |
| **distro** (transitive, via anthropic) | 1.9.0 | Apache-2.0 | Phase 19 | OS detection, anthropic SDK dependency |
| **docstring-parser** (transitive, via anthropic) | 0.18.0 | MIT | Phase 19 | anthropic SDK dependency |
| **jiter** (transitive, via anthropic) | 0.17.0 | MIT | Phase 19 | Fast JSON parsing, anthropic SDK dependency |
| **sniffio** (transitive, via anthropic) | 1.3.1 | MIT OR Apache-2.0 | Phase 19 | Async library detection, anthropic SDK dependency |
| **slowapi** | 0.1.10 | MIT | Phase 21 | Per-client-IP rate limiting on `/auth/login`, `/auth/register`, and `/assistant/ask` (see `docs/security-review.md`) |
| **limits** (transitive, via slowapi) | 5.8.0 | MIT | Phase 21 | Rate-limit storage/window backend, slowapi dependency |

All Phase 9 transitive dependencies checked individually — all permissive
(MIT/Apache-2.0/BSD-3-Clause), no copyleft. None are pinned in
`requirements.txt` (only the direct `pyportfolioopt` dependency is);
listed here for the license record per rule 7, with versions as actually
resolved by pip at install time in this environment.

### Not-yet-added, expected soon (noted here so the next phase isn't a surprise)

- Phase 7 (FinBERT path): `transformers` + a torch backend — already referenced in code as an optional import, not yet in `requirements.txt` since it's unused in this network-restricted sandbox; will be added and recorded if/when a FinBERT evaluation is actually run (see `scripts/evaluate_finbert.py`, written to be run locally)

## Frontend (JavaScript/TypeScript)

| Package | License | Added in | Purpose |
|---|---|---|---|
| React | MIT | Phase 1 | UI library |
| TypeScript | Apache-2.0 | Phase 1 | Type system |
| Vite | MIT | Phase 1 | Build tool / dev server |
| Tailwind CSS | MIT | Phase 1 | Styling |
| Recharts | MIT | Phase 1 | Charts |
| React Router | MIT | Phase 1 (6.28.1 -> 7.18.4 in Phase 21) | Client-side routing. Bumped to 7.18.4 in Phase 21's security review to pick up a fix for an open-redirect finding in `<Link>`/`useNavigate` (GHSA-wrjc-x8rr-h8h6); verified in a real browser (login redirect, all nav links, a nested `:symbol` param route, back-link, and the catch-all redirect) with no console errors. |
| Axios | MIT | Phase 1 | HTTP client |

## Pretrained models (not vendored, downloaded at runtime when enabled)

| Model | License | Status |
|---|---|---|
| `ProsusAI/finbert` (Hugging Face Hub) | Apache-2.0 | Coded, never downloaded/run in this sandbox (no network access to huggingface.co) |

## Data sources (not code, listed for completeness)

| Source | Terms | Notes |
|---|---|---|
| Yahoo Finance (via `yfinance`) | Yahoo's terms of use apply to data retrieved; `yfinance` itself is Apache-2.0 | Used for real OHLCV, not redistributed, cached locally for this project's own development/testing use only |
