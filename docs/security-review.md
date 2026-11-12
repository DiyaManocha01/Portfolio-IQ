# Security Review (Phase 21, re-audited Phase 34)

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

## 5. Phase 34 re-audit (Production Readiness)

Re-ran everything in Section 1 from scratch (13 phases and ~20 new
dependencies have landed since Phase 21), plus a fresh pass on
authentication coverage now that the route count has roughly doubled
(12 route files vs. Phase 21's handful).

### 5.1 Backend (`pip-audit`), re-run

**14 findings, same single package as Phase 21: `starlette` 0.41.3**
(transitive, via `fastapi==0.115.6`). Nothing else in `requirements.txt`
(now 32 direct entries, including Phase 19's `anthropic`, Phase 24's
`requests`/`websockets`/`pyotp`, and this phase's `sentry-sdk`) has any
known finding — the PyJWT/python-multipart/python-dotenv/pytest/pyarrow
fixes from Phase 21 are all still in place and clean.

Phase 21 deferred this with a version-gap argument (`fastapi` lagging
the fix). This re-audit goes further and checks whether any of the 7
underlying CVEs are actually REACHABLE through this app's own route
code, independent of the version-gap question:

| CVE | What it needs | Used anywhere in `app/`? |
|---|---|---|
| PYSEC-2026-1941 (multipart large-file thread blocking) | `UploadFile`/multipart form parsing | No — `grep` for `UploadFile`, `Form(` across `app/` (excluding tests): no matches |
| PYSEC-2026-1942 (Range-header quadratic DoS) | `FileResponse` / `StaticFiles` | No — not used; the frontend is served separately by nginx (Phase 22), not FastAPI |
| PYSEC-2026-2281 (StaticFiles UNC path, Windows only) | `StaticFiles` + a Windows host | No — `StaticFiles` unused, and the Docker deployment target is Linux |
| PYSEC-2026-2280 (`HTTPEndpoint` verb-lookup) | Class-based `HTTPEndpoint` routes | No — every route in this app is a plain `@router.get/post/...` function |
| PYSEC-2026-249 (urlencoded-form `max_fields` bypass) | `application/x-www-form-urlencoded` bodies | No — every route body is a JSON Pydantic model |
| PYSEC-2026-161 / PYSEC-2026-248 (Host-header `request.url` reconstruction) | Code that trusts/redirects on `request.url` | No — the only `request.url` use anywhere in `app/` is `RequestContextMiddleware`'s own request-logging (Phase 34, this re-audit), which only reads `.path` for a log line, never redirects or makes a security decision from it |

**Decision (confirmed with the project owner before writing this up,
given the dependency bump needed to actually close it is large): document
and defer, do not bump `fastapi`/`starlette` in this phase.** A real fix
needs `starlette>=1.3.1`; checking every `fastapi` release's own pinned
range (`0.115.14` allows `<0.47.0`, `0.118.0`→`<0.49.0`, `0.128.0`→`<0.51.0`
— none reach `1.3.1`) shows only the LATEST release, `fastapi==0.162.5`
(`starlette>=0.46.0`, no upper bound), permits a fully patched starlette.
That's a ~47-minor-version jump across the entire backend — real
regression risk (Pydantic validation edge cases, dependency-injection
behavior, response serialization) across every one of this app's 60+
routes, for a set of CVEs this re-audit found have no reachable path in
this codebase's actual usage. Tracked here and in `docs/limitations.md`
as a candidate for its own dedicated, ADR-backed upgrade phase, not
silently left unmentioned.

### 5.2 Frontend (`npm audit`), re-run

**7 findings (3 moderate, 2 high, 2 critical)** before this re-audit —
`follow-redirects` (high, `axios`'s transitive dependency, the same
finding Phase 21 already fixed once) had reappeared, alongside
`esbuild`/`vite`/`vite-node`/`tinypool`/`@vitest/mocker`/`vitest`
(all dev/test tooling, not shipped in the production bundle).

- `npm audit fix` (non-breaking): re-resolved `follow-redirects` again —
  a `package-lock.json`-only change (no `package.json` edit), re-verified
  with the full Vitest suite (71/71) and `npm run build` (clean). Why it
  reappeared: most likely a lockfile regenerated during this long
  session's repeated `npm install`s resolved `axios`'s transitive range
  to the vulnerable patch version again; nothing in this project's own
  `package.json` pins it directly, so this can recur and should be
  re-checked periodically, not treated as permanently fixed by one
  historical commit.
- **Remaining 6 findings are all dev/test tooling only**
  (`vite`/`vitest`/`esbuild`/`vite-node`/`tinypool`/`@vitest/mocker`),
  including one critical (`tinypool`, a prototype-pollution-to-RCE
  advisory in `vitest`'s worker pool). None of these packages are in the
  production bundle (`vite build`'s output references none of them) —
  the exposure is to a developer's own machine while running `npm run
  dev`/`vitest`, not to an end user of the deployed app. Fixing requires
  `vite@5.4.21 → 8.3.8` and `vitest@2.1.9 → 5.1.0`, both semver-major
  jumps to the exact test infrastructure Phase 21 built this project's
  test coverage on. Same reasoning as the backend `starlette` deferral:
  documented, deferred, tracked in `docs/limitations.md`, not silently
  dropped.

### 5.3 Authentication coverage, re-verified across all 12 route files

Spot-checked every route file added since Phase 21 (`alerts.py`,
`discover.py`, `health.py`, `ledger.py`, `market.py`, `paper_trading.py`,
`portfolio_fit.py`, `screener.py`, `stocks.py`) for whether each route
requires auth via `Depends(get_current_user)` / `Depends
(get_current_portfolio)` (`app/api/deps.py`). Result: consistent with
the intended design, no gap found --

- **Require auth** (touch a specific user's own data): `portfolio.py`,
  `alerts.py`, `paper_trading.py`, `portfolio_fit.py`, `assistant.py`,
  `discover.py`.
- **Deliberately public** (general market/stock data, not user-specific):
  `stocks.py`, `market.py`'s REST routes, `screener.py`, `ledger.py`
  (Phase 18's own "verified public track record" design), and this
  phase's `health.py` (a liveness/readiness probe must be reachable
  without credentials).
- `GET /ws/market` (Phase 24) carries its JWT as a query parameter
  (`?token=...`), not an `Authorization` header, because a browser's
  native WebSocket API cannot send custom headers during the handshake.
  This is an accepted, documented tradeoff (a token in a URL can leak via
  proxy/server logs or the `Referer` header in a way a header cannot) —
  unchanged since Phase 24, re-confirmed still the only viable approach
  for browser-native WebSocket auth without introducing a separate
  short-lived-ticket exchange step this project doesn't otherwise need.

### 5.4 New in this phase

- **Rate limiting now covers every route, not just auth/assistant.**
  `app/services/rate_limit.py`'s `Limiter` carries `default_limits=
  ["120/minute"]`, applied by the existing `SlowAPIMiddleware` to any
  route without its own `@limiter.limit(...)` (`auth`/`assistant` keep
  their stricter, Phase-21-set limits, which remain the binding
  constraint on those routes). `GET /health` is explicitly exempted
  (`@limiter.exempt`) so a load balancer's liveness probe is never itself
  rate-limited. Verified with an isolated throwaway `Limiter` instance
  (`app/tests/test_rate_limit.py`) rather than hammering the real shared
  limiter state 120+ times inside the real test suite.
- **Structured JSON logging + a per-request correlation ID**
  (`app/services/logging_config.py`, `RequestContextMiddleware` in
  `app/main.py`) — every log line is now one JSON object (level, logger,
  message, `request_id`, plus any `extra=` fields), and every request's
  `request_id` is echoed back as an `X-Request-ID` response header, so a
  user-reported error can be traced to its exact log lines. Replaces the
  previous bare `logging.basicConfig(level=logging.WARNING)`.
- **Error tracking via Sentry, opt-in.** `sentry_sdk.init()` only runs if
  `SENTRY_DSN` is set in a local `.env` — a true no-op in this sandbox
  and for anyone who hasn't configured their own Sentry project, the same
  pattern already established for `ANTHROPIC_API_KEY`/`ANGELONE_*`.
- **`GET /health` now reports real dependency status** (DB connectivity,
  Alembic migration head vs. applied, ML model loaded, realtime feed
  status) instead of an unconditional `{"status": "ok"}` — see
  `app/services/health_service.py`.
- **A `pg_dump`-based backup script**, `scripts/backup_db.py` — unlike
  the Phase 4/7/24 fetch scripts, this one genuinely runs in this sandbox
  (only needs the local Postgres instance, no blocked external host) and
  was actually exercised here: a real dump was produced and verified
  restorable with `pg_restore --list`, and the retention/rotation logic
  was verified to delete only its own prior backups past `--keep`. Still
  meant to be run by the project owner on a real schedule (cron/CI), not
  invoked by the application itself.
- **`SECRET_KEY` startup warning**: unchanged logic from Phase 21,
  re-verified it still fires correctly now that it goes through the new
  JSON log formatter instead of the plain-text one.
