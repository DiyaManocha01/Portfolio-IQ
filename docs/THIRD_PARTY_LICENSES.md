# Third-Party Licenses

PortfolioIQ is built entirely on established open-source libraries via
their published package registries (PyPI / npm). No third-party source
code was copied from other repositories; all functionality in this project
was written for PortfolioIQ specifically.

## Backend (Python / PyPI)

| Package | License | Purpose |
|---|---|---|
| FastAPI | MIT | Web framework |
| Uvicorn | BSD-3-Clause | ASGI server |
| SQLAlchemy | MIT | ORM |
| psycopg2-binary | LGPL-3.0 | PostgreSQL driver |
| Pydantic / pydantic-settings | MIT | Data validation & settings |
| python-jose | MIT | JWT encode/decode |
| passlib + bcrypt | BSD-3-Clause / Apache-2.0 | Password hashing |
| pandas | BSD-3-Clause | Data manipulation |
| NumPy | BSD-3-Clause | Numerical computing |
| scikit-learn | BSD-3-Clause | Logistic Regression, Random Forest, preprocessing, metrics |
| XGBoost | Apache-2.0 | Gradient-boosted classifier |
| joblib | BSD-3-Clause | Model persistence |
| transformers (optional, FinBERT path) | Apache-2.0 | Sentiment pipeline |
| pytest | MIT | Testing |

### Pretrained model (optional path)
`ProsusAI/finbert` (Hugging Face Hub) -- Apache-2.0 licensed model weights,
used only when `USE_FINBERT=true`. Not downloaded or bundled in this
environment (no outbound network access to Hugging Face here); the
lexicon-based sentiment provider is the default and requires no external
model download.

## Frontend (JavaScript/TypeScript / npm)

| Package | License | Purpose |
|---|---|---|
| React | MIT | UI library |
| TypeScript | Apache-2.0 | Type system |
| Vite | MIT | Build tool / dev server |
| Tailwind CSS | MIT | Styling |
| Recharts | MIT | Charts |
| React Router | MIT | Client-side routing |
| Axios | MIT | HTTP client |

All packages above are used as published dependencies via `pip` /
`npm install` per their respective package manifests (`requirements.txt`,
`package.json`) -- no vendored or modified copies of their source are
included in this repository. License notices are preserved as distributed
by each package; none require additional attribution beyond normal
dependency usage.

## Sample data

All market data, financial news, and price history used in the default
development configuration is **synthetically generated** by PortfolioIQ's
own `DevSampleProvider` and news-template generator -- it is not scraped,
copied, or redistributed from any third-party data vendor. See
`docs/ARCHITECTURE.md` for details on the provider abstraction and how a
live data source can be substituted later.
