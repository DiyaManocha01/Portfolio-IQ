#!/usr/bin/env python3
"""Back up the PortfolioIQ PostgreSQL database via `pg_dump` (Phase 34).

Unlike Phase 4/7/24's fetch scripts, this one CAN and was run in this
sandbox -- it only needs the local Postgres instance, not blocked
external hosts. Still intended to be run by the project owner on a real
schedule (e.g. a daily cron job or a CI nightly job), not invoked by the
application itself: a backup that only ever runs when someone remembers
to run it by hand is not a real backup strategy.

Writes a single custom-format (`-Fc`) dump -- compressed, and restorable
with `pg_restore` (selectively, by table, if needed) rather than psql's
plain-SQL format. Old backups beyond `--keep` are deleted, oldest first,
so this is safe to put on a frequent cron schedule without silently
filling the disk.

Usage:
    cd backend
    source venv/bin/activate
    python scripts/backup_db.py                       # backs up DATABASE_URL from .env
    python scripts/backup_db.py --out-dir /var/backups/portfolioiq
    python scripts/backup_db.py --keep 14              # keep the 14 most recent, delete older

Restoring (never done automatically -- always a deliberate, reviewed
action):
    pg_restore --clean --if-exists -d portfolioiq /path/to/backup_2026-11-12T120000Z.dump
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "backups"
DEFAULT_KEEP = 7


def _parse_database_url(url: str) -> dict:
    """Extracts pg_dump's connection flags from a SQLAlchemy-style
    DATABASE_URL (postgresql+psycopg2://user:pass@host:port/dbname) --
    pg_dump itself doesn't understand the `+psycopg2` driver suffix."""
    parsed = urlparse(url.replace("postgresql+psycopg2://", "postgresql://"))
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/"),
    }


def run_backup(database_url: str, out_dir: Path, keep: int) -> Path:
    conn = _parse_database_url(database_url)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    dest = out_dir / f"{conn['dbname']}_{timestamp}.dump"

    cmd = [
        "pg_dump",
        "-Fc",  # custom format: compressed, restorable with pg_restore
        "-h", conn["host"],
        "-p", conn["port"],
        "-U", conn["user"],
        "-f", str(dest),
        conn["dbname"],
    ]
    env = {"PGPASSWORD": conn["password"]} if conn["password"] else {}
    import os

    result = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True, text=True)
    if result.returncode != 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}")

    _rotate_old_backups(out_dir, conn["dbname"], keep)
    return dest


def _rotate_old_backups(out_dir: Path, dbname: str, keep: int) -> list[Path]:
    """Deletes all but the `keep` most recent backups for this database
    in `out_dir`, oldest first. Only ever touches files matching this
    script's own naming pattern, never anything else in `out_dir`."""
    existing = sorted(out_dir.glob(f"{dbname}_*.dump"), key=lambda p: p.name)
    to_delete = existing[:-keep] if keep > 0 else existing
    for path in to_delete:
        path.unlink()
    return to_delete


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help=f"default: {DEFAULT_OUT_DIR}")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"backups to retain (default: {DEFAULT_KEEP})")
    args = parser.parse_args()

    from app.config import settings

    try:
        dest = run_backup(settings.DATABASE_URL, args.out_dir, args.keep)
    except RuntimeError as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        sys.exit(1)

    size_kb = dest.stat().st_size / 1024
    print(f"Wrote {dest} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
