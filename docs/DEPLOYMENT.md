# Deployment (Phase 22)

A Docker Compose setup for running the full stack (PostgreSQL + backend
+ frontend) locally without manually installing Python/Node/Postgres.
This is a **local/demo deployment**, not a hardened production setup --
see "What this is not" at the end.

## Quickstart

```bash
cp .env.example .env                    # Compose-level vars: Postgres creds, VITE_API_BASE_URL
cp backend/.env.example backend/.env    # backend app config -- SECRET_KEY, ANTHROPIC_API_KEY, etc.

# Edit backend/.env: set SECRET_KEY to something other than the placeholder
# (see docs/security-review.md -- the app warns at startup if you don't).

docker compose up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000 (docs at `/docs`)
- Postgres: `localhost:5432` (exposed for local `psql`/GUI access)

First boot runs Alembic migrations, seeds the demo user/portfolio, and
trains the ML model on synthetic data (`backend/docker-entrypoint.sh`) --
this takes roughly a minute or two. Watch it with:

```bash
docker compose logs -f backend
```

Demo login: `demo@portfolioiq.app` / `demo1234` (same as the non-Docker
setup in the root `CLAUDE.md`).

## What each piece does

| Service | Image | Role |
|---|---|---|
| `db` | `postgres:16-alpine` | Database. Data persists in the named volume `pgdata`. |
| `backend` | built from `backend/Dockerfile` | FastAPI app. `backend/docker-entrypoint.sh` waits for Postgres, runs `alembic upgrade head`, seeds + trains the ML model on first boot only (guarded by a marker file in the `backend_data` volume), then execs `uvicorn`. |
| `frontend` | built from `frontend/Dockerfile` | Vite production build served as static files by nginx (`frontend/nginx.conf` adds the SPA fallback route so client-side routing survives a page refresh/deep link). |

## Persisted state

Two named volumes, both created automatically by `docker compose up`:

- `pgdata` — the Postgres data directory.
- `backend_data` — mounted at `/app/app/data` inside the backend
  container. Holds the trained ML model artifacts, the market-data/news
  caches, and the entrypoint's seed marker. **Deleting this volume forces
  a full reseed + retrain on the next `docker compose up`** (useful if
  you want a clean slate); deleting only `pgdata` without also deleting
  `backend_data` would leave the entrypoint skipping seeding against an
  empty database, which would break the app -- if you reset one, reset
  both: `docker compose down -v`.

## A real caveat: `VITE_API_BASE_URL` is baked in at build time

Vite inlines `import.meta.env.VITE_API_BASE_URL` into the compiled
JavaScript at build time -- there is no runtime environment-variable
injection for a plain static build like this one (unlike the backend,
which reads its env at container *start*). This means:

- Changing `VITE_API_BASE_URL` in `.env` and running `docker compose up`
  again **will not** pick up the change -- you must
  `docker compose build frontend` (or `docker compose up --build`) to
  rebuild the image with the new value baked in.
- The value must be a URL **reachable from the end user's browser**, not
  from inside the Compose network -- `http://backend:8000` would resolve
  fine container-to-container but fail from a browser on the host
  machine, which doesn't know what `backend` means. The default,
  `http://localhost:8000`, is correct for the common case of running
  Compose and opening the frontend in a browser on the same machine; it
  is wrong for any setup where the browser and the Docker host are
  different machines (e.g. deploying to a remote server), where it must
  be set to that server's actual reachable address before building.

## What has (and has not) been verified from this project's own
development sandbox

Per this project's working rules (`CLAUDE.md` rule 8: "this sandbox may
block market-data/HF hosts... fetch/cache scripts that need real network
access are written to be run by the project owner locally, not executed
here"), the same honesty standard applies to this phase's own
verification, extended to a related but distinct constraint:

- **Both Dockerfiles pass `docker build --check`** (BuildKit's
  structural/syntax lint) with no warnings.
- **`docker compose config` was run and inspected** -- the full resolved
  service definitions, environment variable interpolation, volumes, and
  healthchecks were checked by hand against what's described above. This
  caught and fixed a real bug: `backend/.env.example`'s `NEWS_API_KEY=`
  line originally had a trailing inline comment, which `python-dotenv`
  (what the app itself uses) tolerates but Docker Compose's own
  `env_file` parser does not -- it folded the comment text into the
  value. Moved to its own line; re-verified with `docker compose config`
  that `NEWS_API_KEY` now resolves to an empty string as intended.
- **A full `docker compose build` / `docker compose up` has NOT been
  completed from a clean state in this sandbox.** This sandbox's
  containers cannot complete outbound HTTPS to package registries
  (PyPI, npm) -- verified directly: requests fail with
  `CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate
  chain`, meaning this sandbox's own egress network performs TLS
  interception that containers don't trust by default (the host trusts
  it via a CA bundle wired into host-level tooling; a fresh container
  does not inherit that trust, and plumbing it in would be a
  sandbox-specific hack that has no business being in a Dockerfile meant
  to run on a real developer's machine or a real server, where no such
  interception exists). Docker Hub image pulls were separately,
  intermittently rate-limited from this sandbox's shared egress IP
  (`429 Too Many Requests`, resolved after a handful of retries each
  time) -- unrelated to the TLS issue, and not expected to reproduce on
  a normal network.
- **To get real signal anyway**, a one-off, *not-committed* variant of
  `backend/Dockerfile` was built locally in this sandbox with the
  sandbox's CA bundle temporarily trusted inside the build stage, purely
  to prove `pip install -r requirements.txt` actually resolves with no
  conflicts against the full pinned dependency set (including the
  heavier ML stack: pandas, scikit-learn, xgboost, scipy, shap,
  pyportfolioopt/cvxpy and their transitive solver dependencies) --
  **it succeeded**: the install completed cleanly (a ~910MB image) and a
  follow-up check imported every key package from the installed
  location (`fastapi` 0.115.6, `sqlalchemy`, `pandas`, `numpy`,
  `sklearn`, `xgboost`, `shap`, `pypfopt`, `scipy`, `anthropic`,
  `slowapi`, `jwt`) with no import errors. This is real signal that the
  dependency set in `requirements.txt` is installable as pinned on a
  standard Linux/CPython 3.11 target with no C toolchain needed (see the
  comment at the top of `backend/Dockerfile`) -- it does not by itself
  prove the full multi-stage build, the entrypoint script's
  migrate/seed/train sequence, or the running app, which is the
  remaining gap described above.
- **This specific gap (full `docker compose up` end-to-end, including a
  real browser hitting the running frontend/backend) should be run once
  by the project owner on a normal machine** before relying on this
  setup for a demo -- the Dockerfiles and compose file are believed
  correct based on the checks above, but "believed correct based on
  static checks" is not the same claim as "verified end-to-end," and
  this file says so plainly rather than implying the stronger claim.

## What this is not

- Not a production hardening guide: no TLS termination/reverse proxy,
  no secrets manager (env vars in a `.env` file), no resource limits,
  no multi-replica/orchestration story beyond what Compose itself gives
  you, no log aggregation pipeline (Phase 34 gives you structured JSON
  log LINES -- see below -- not a place those lines are shipped to).
- The rate limiting added in Phase 21, expanded in Phase 34 (`slowapi`,
  in-memory storage) does not share state across multiple backend
  replicas -- fine for this single-`backend`-container Compose setup,
  not for a scaled deployment.

## Production readiness additions (Phase 34)

### Database backups

`pgdata` is still a plain Docker volume with no automatic backup of its
own -- Postgres' own backup/restore strategy stays out of Compose's
scope. What Phase 34 adds is `backend/scripts/backup_db.py`: a
`pg_dump`-based backup you run yourself, on whatever schedule you choose
(a host cron job, a CI nightly job, a Kubernetes CronJob if you deploy
there) -- the application never calls it itself.

```bash
cd backend && source venv/bin/activate
python scripts/backup_db.py                       # backs up DATABASE_URL from .env, keeps 7
python scripts/backup_db.py --out-dir /var/backups/portfolioiq --keep 14

# Restore (always a deliberate, reviewed action -- never automatic):
pg_restore --clean --if-exists -d portfolioiq /path/to/backup.dump
```

Against a Compose deployment specifically, run `pg_dump` against the
exposed `localhost:5432` port (already published by the `db` service)
rather than from inside a container, or add a short-lived `docker compose
run` invocation if you'd rather not expose Postgres's port to the host at
all.

### Structured logging and error tracking

The backend now logs one JSON object per line (`LOG_LEVEL` in `.env`,
default `INFO`) instead of plain text -- pipe `docker compose logs
backend` into any JSON-aware log tool (`jq`, a log-aggregation agent)
rather than parsing free text. Every request's logs carry a `request_id`
that's also returned as the `X-Request-ID` response header, so a
specific user-reported error can be traced to its exact log lines.

Error tracking is opt-in via `SENTRY_DSN` (empty by default, a true
no-op): set it in `backend/.env` to your own Sentry project's DSN to get
real exception alerting. Neither this repo nor this sandbox runs or
pays for a Sentry account on your behalf -- you create your own project
at https://sentry.io if you want this.

### Backend container healthcheck

`backend` now has a Docker healthcheck (`docker-compose.yml`) that polls
Phase 34's `GET /health` -- real DB/migration/model status, not just "the
process accepted a TCP connection." `frontend` now depends on `backend`
being reported *healthy*, not merely started, before Compose considers
it safe to come up -- tightening the previous plain `depends_on:
[backend]` (process started) to `condition: service_healthy` (process
and its real dependencies are actually working). Verified with `docker
compose config` (clean resolution, no syntax errors) in this sandbox;
not run through a live `docker compose up` for the same network-access
reasons the "What has (and has not) been verified" section above
already describes.

## Before a public demo: verify data licensing first

**Do not expose this application publicly (a public URL, a demo for
people outside this project) until you have personally verified the
market-data redistribution terms.** This project's own
`docs/open-source-inventory.md` already notes that Yahoo Finance data
(via `yfinance`) is used here for this project's own development/testing
only, not redistributed -- a public demo that displays live or cached
Yahoo Finance-sourced prices to third parties is a materially different
use than a local dev/demo instance only you look at, and Yahoo's terms
of use (not this project's choice to make) govern whether that's
permitted. The same applies to any Angel One-sourced real-time data if
`ENABLE_REALTIME_FEED` is ever turned on for a public instance. This is
a standing caution, not a one-time checkbox: re-verify if you change
data providers or redistribution scope later.
