# Security Review (Phase 21)

Scope: a practical security pass over the existing application and its
dependencies, done as the second phase of Batch 10 alongside the Phase 20
frontend work. This is **a student project's own self-review, not an
external audit or a penetration test** — it establishes a documented
baseline and fixes what could be fixed safely within this phase's scope,
and is explicit below about what is deferred and why. Nothing here should
be read as a certification of production-readiness.

Every claim below is backed by a command actually run in this repository
(`pip-audit`, `npm audit`, the backend/frontend test suites, a live
rate-limit check with `curl`) — nothing is asserted from memory.

## 1. Dependency vulnerability audit

### Backend (`pip-audit`)

Before this phase: **42 known vulnerabilities across 8 packages**
(`ecdsa`, `pyarrow`, `pytest`, `python-dotenv`, `python-jose`,
`python-multipart`, `setuptools`, `starlette`).

Actions taken, each verified by re-running the full backend test suite
(`python -m pytest app/tests/ -q`) after the change:

| Package | Before | After | Action |
|---|---|---|---|
| `python-jose` | 3.3.0 | removed | **Replaced with PyJWT 2.15.1.** `python-jose` 3.4.0 (the latest release) still carries an unpatched finding (PYSEC-2026-4298, no fix version published) and pulls in `ecdsa`/`pyasn1`, which had their own findings, purely to support asymmetric JWT algorithms this app never uses. `app/services/security.py` only ever signs/verifies with `settings.ALGORITHM` (`HS256`, symmetric), which PyJWT supports natively with a much smaller dependency footprint. The swap touched exactly one file (`app/services/security.py`: `jose.jwt`/`jose.JWTError` → `jwt`/`jwt.PyJWTError`) and is covered by the existing auth test suite (login, register, token verification, expiry). |
| `python-multipart` | 0.0.20 | 0.0.32 | Direct version bump, no code change needed. |
| `python-dotenv` | 1.0.1 | 1.2.2 | Direct version bump, no code change needed. |
| `pytest` | 8.3.4 | 9.0.3 | Direct version bump; full suite re-verified green. |
| `pyarrow` | 18.1.0 | 23.0.1 | Direct version bump; parquet cache/validation tests (`test_market_data_cache.py` and related) specifically re-run and verified passing, since this is the library behind Phase 4's market-data cache. |
| `setuptools` | 79.0.1 | 83.0.0 | Not pinned in `requirements.txt` (a transitive/build-time tool); upgraded in the venv and confirmed with `pip check` that nothing else requires the older version. |
| `ecdsa`, `pyasn1` | (transitive via python-jose) | removed | No longer installed at all, as a consequence of the PyJWT swap. |

**After these fixes: 14 remaining findings, all in a single package
(`starlette` 0.41.3).** `starlette` is not a direct dependency —
`fastapi==0.115.6` pins `starlette<0.42.0,>=0.40.0` (verified by
inspecting `fastapi`'s own package metadata), and no patched `starlette`
release exists inside that range (the fix versions pip-audit reports
start at 0.47.2). Resolving this requires bumping `fastapi` itself —
`fastapi` is currently 46 minor versions behind the latest release
(0.115.6 vs. 0.161.0 at time of writing). That is a meaningfully larger,
higher-risk change (full-framework regression risk across every route,
not just a dependency swap) than fits inside a bounded testing/security
phase, and CLAUDE.md's working rule 9 requires an ADR before superseding
an existing architectural decision like the pinned framework version.
**Deferred, tracked here and in `docs/limitations.md`, as a candidate for
its own dedicated phase with an ADR**, not silently left unmentioned.

### Frontend (`npm audit`)

Before this phase: **17 vulnerabilities (7 moderate, 8 high, 2
critical)**.

- `npm audit fix` (non-breaking): resolved `follow-redirects` (a
  transitive dependency of `axios`, a production dependency — credential
  header handling across redirects) and `source-map-js`/
  `postcss-selector-parser`/`postcss-nested` (build-time only).
- **`react-router-dom` 6.28.1 → 7.18.4** (a production dependency,
  shipped in the bundle): the only remaining *production-dependency*
  finding was an open-redirect in `<Link>`/`useNavigate`
  (GHSA-wrjc-x8rr-h8h6). `react-router-dom` 7's declarative mode
  (`<BrowserRouter>`/`<Routes>`/`<Route>`, exactly what this app uses) is
  backward-compatible with 6's API; the peer dependency requirement
  (`react >=18`) is already satisfied. Verified with: `tsc -b && vite
  build` (clean), the full Vitest suite (37/37 passing), and a live
  Playwright pass through every route — login redirect, every sidebar
  nav link, the `/discover/:symbol` nested param route, the "Back to
  Discover" link, and the unknown-route catch-all redirect — with zero
  console errors.
- **Remaining findings are all dev/build tooling only**
  (`@vitest/mocker`, `tinypool`, `esbuild`/`vite`, `braces`/
  `postcss-selector-parser` via `tailwindcss`) — none of these packages
  are included in the production build (`vite build`'s output bundle);
  they run only on the developer's own machine or CI, never reachable by
  an end user of the deployed app. Fixing them requires `vitest@5`
  (needs `vite@6/7/8`, a breaking bump from this project's `vite@5.4.21`)
  and `tailwindcss@4` (a different config format entirely) — both
  larger, separately-scoped upgrades, deferred for the same "don't
  silently supersede an existing pin without an ADR" reason as
  `starlette` above. Risk is low: dev-tooling exposure, not a production
  attack surface.

## 2. Rate limiting (new)

Added `slowapi` (MIT license; recorded in `docs/open-source-inventory.md`'s
Backend table, same commit as the `requirements.txt` addition).
A shared `Limiter` (`app/services/rate_limit.py`, keyed by client IP) is
registered on the FastAPI app and applied to:

- `POST /auth/login` and `POST /auth/register` — **10 requests/minute**
  per IP. These had no rate limiting at all before this phase, making
  credential-stuffing / brute-force login attempts and registration spam
  unconstrained. Verified live: 10 rapid login attempts each return 401
  (wrong password) as normal, the 11th through 13th return 429 (`curl`
  output captured during this phase).
- `POST /assistant/ask` — **20 requests/minute** per IP. This endpoint
  triggers a paid external API call (Anthropic) per request;
  `docs/limitations.md`'s Phase 19 section already flagged "cost and
  latency... not modeled or rate-limited" as a known gap. This closes
  that gap at the "bound the rate of spend" level — it does not model or
  cap total cost, and an attacker distributing requests across many IPs
  would not be rate-limited by this alone.

**Bug found and fixed while adding this**: `app/api/routes/assistant.py`
had `from __future__ import annotations` (PEP 563 postponed
evaluation), which is a documented incompatibility with
`slowapi`'s decorator — FastAPI's parameter-source introspection broke
under it, causing the JSON body parameter to be misread as a query
parameter (a live `422 Unprocessable Entity` instead of reading the
request body at all). Caught by the existing
`test_assistant_endpoint_returns_503_when_unconfigured` test failing
after the decorator was added — not shipped. Fixed by removing the
unused future-import (nothing in that file relies on postponed
evaluation); full suite re-verified green afterward.

**Caveats, stated plainly**: this is IP-based rate limiting with an
in-memory store (`slowapi`'s default) — it resets on every process
restart and does not share state across multiple backend processes/pods.
It is a real, working mitigation for a single-process deployment (which
is what this project currently is), not a production-grade distributed
rate limiter (that would need a shared backend like Redis, which this
project does not currently run).

## 3. `SECRET_KEY` startup warning (new)

Found while reviewing `app/config.py`: the code-level default
(`"dev-secret-key-change-me"`) was already an obviously-fake value, but
`.env.example`'s own default — `"change-this-to-a-long-random-string-in-production"`,
copied verbatim into `.env` by anyone following this project's own
`cp .env.example .env` setup instructions without additionally editing
`SECRET_KEY` — was a *second*, different placeholder, so a naive
default-value check alone would have missed the actual value this
sandbox (and plausibly any default local setup) is running with.

`app/main.py` now logs a `WARNING`-level message at startup
(`logging.basicConfig` + a named `portfolioiq` logger, verified to
actually reach stdout under `uvicorn`, not swallowed by its own logging
config) if `SECRET_KEY` matches either known placeholder, or is under 32
characters (a generic low-entropy check, not just a literal-string
match, so a different-but-still-weak key is also caught). This is a
warning, not a hard failure — the app still starts and works in this
sandbox and for any local/dev use — but makes the gap visible rather
than silent. Verified live: the warning appears in the server's startup
log in this environment's current (placeholder) configuration.

## 4. What this review did **not** cover (explicitly out of scope)

- No penetration testing, fuzzing, or external security tool beyond
  `pip-audit`/`npm audit` was used.
- No review of PostgreSQL's own configuration/hardening, OS-level
  security, or network/firewall posture — out of scope for an
  application-level review, and this sandbox's own database setup is a
  local dev instance, not a deployed one.
- SQL injection: not separately fuzzed, but the codebase was spot-checked
  for raw SQL string interpolation (`grep` for f-string/`%`-formatted
  `.execute(` calls) and found none — all queries go through SQLAlchemy's
  ORM/parameterized query builder, which is the standard mitigation.
  Not a formal guarantee, a spot-check.
- CORS is an explicit origin allowlist (`CORS_ORIGINS` in `.env`, not a
  wildcard) — already correct, unchanged by this phase.
- Password hashing (`passlib[bcrypt]`) and JWT expiry
  (`ACCESS_TOKEN_EXPIRE_MINUTES`) were already in place from Phase 1 and
  reviewed as sound; unchanged by this phase.
- No security review of the `anthropic` SDK integration's own prompt-
  injection surface beyond what Phase 19's guardrail already documents
  in `docs/limitations.md` ("AI Portfolio Assistant" section) — that
  caveat stands as written, not re-litigated here.
