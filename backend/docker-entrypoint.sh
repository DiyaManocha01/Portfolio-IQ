#!/bin/sh
# Backend container entrypoint: wait for Postgres, apply migrations, seed
# the demo data + train the ML model on first run only, then hand off to
# CMD (uvicorn by default -- see Dockerfile).
#
# Seeding/training only runs once per persisted data volume (guarded by a
# marker file under app/data/), not on every container restart: seed.py
# itself is idempotent for the demo user/portfolio, but re-running it
# would needlessly retrain the ML model (and re-fetch synthetic market
# history) on every restart. Delete the marker (or the volume) to force
# a full reseed.
set -e

SEED_MARKER="app/data/.seeded"

echo "Waiting for the database to accept connections..."
python - <<'PYEOF'
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import settings

engine = create_engine(settings.DATABASE_URL)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except OperationalError:
        time.sleep(2)
else:
    print("Database never became reachable.", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "Applying Alembic migrations..."
alembic upgrade head

if [ ! -f "$SEED_MARKER" ]; then
    echo "No seed marker found -- seeding demo data and training the ML model (first run)..."
    python -m app.data.seed
    mkdir -p app/data
    touch "$SEED_MARKER"
else
    echo "Seed marker present -- skipping seed/train (data volume already populated)."
fi

echo "Starting: $*"
exec "$@"
