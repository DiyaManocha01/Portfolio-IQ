"""Tests for scripts/backup_db.py (Phase 34).

Unlike Phase 4/7/24's fetch scripts (blocked external hosts, untestable
here), this one only needs the local Postgres instance this test suite
already runs against -- so `test_run_backup_produces_a_restorable_dump`
genuinely runs `pg_dump` for real, not just against mocked internals."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.backup_db import _parse_database_url, _rotate_old_backups, run_backup


def test_parse_database_url_extracts_pg_dump_flags():
    conn = _parse_database_url("postgresql+psycopg2://portfolioiq:secretpw@localhost:5432/portfolioiq")
    assert conn == {"host": "localhost", "port": "5432", "user": "portfolioiq", "password": "secretpw", "dbname": "portfolioiq"}


def test_parse_database_url_defaults_port_and_host():
    conn = _parse_database_url("postgresql+psycopg2://user@/mydb")
    assert conn["host"] == "localhost"
    assert conn["port"] == "5432"


def test_rotate_old_backups_keeps_only_the_n_most_recent(tmp_path):
    for name in ["mydb_2026-01-01T000000Z.dump", "mydb_2026-01-02T000000Z.dump", "mydb_2026-01-03T000000Z.dump"]:
        (tmp_path / name).write_text("x")

    deleted = _rotate_old_backups(tmp_path, "mydb", keep=2)

    remaining = sorted(p.name for p in tmp_path.glob("mydb_*.dump"))
    assert remaining == ["mydb_2026-01-02T000000Z.dump", "mydb_2026-01-03T000000Z.dump"]
    assert [p.name for p in deleted] == ["mydb_2026-01-01T000000Z.dump"]


def test_rotate_old_backups_never_touches_unrelated_files(tmp_path):
    (tmp_path / "mydb_2026-01-01T000000Z.dump").write_text("x")
    (tmp_path / "otherdb_2026-01-01T000000Z.dump").write_text("x")
    (tmp_path / "notes.txt").write_text("x")

    _rotate_old_backups(tmp_path, "mydb", keep=0)

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["notes.txt", "otherdb_2026-01-01T000000Z.dump"]


def test_run_backup_produces_a_restorable_dump(tmp_path):
    from app.config import settings

    dest = run_backup(settings.DATABASE_URL, tmp_path, keep=7)

    assert dest.exists()
    assert dest.stat().st_size > 0

    listing = subprocess.run(["pg_restore", "--list", str(dest)], capture_output=True, text=True)
    assert listing.returncode == 0
    assert "TABLE DATA" in listing.stdout or "TABLE" in listing.stdout
