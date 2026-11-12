"""Health/readiness checks for GET /health (Phase 34).

Deliberately split from the trivial liveness check FastAPI's own startup
already implies (if the process is up and serving requests, it's "alive"):
this answers "is everything this process DEPENDS ON actually working,"
which a plain `{"status": "ok"}` never could -- a DB outage, an unapplied
migration, or an untrained model would previously all look identical
("the API is up") even though real requests would be failing underneath.

Each check is independent and never raises -- a failing DB check must
not prevent reporting that the DB is down; it must say so.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.ml.predict import ModelNotTrainedError, PredictionService

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _check_database(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"connected": True}
    except Exception as exc:  # noqa: BLE001 -- reporting the failure IS the point
        return {"connected": False, "error": str(exc)}


def _check_migrations(db: Session) -> dict:
    try:
        applied = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        return {"applied": None, "head": None, "up_to_date": False, "error": str(exc)}

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(_ALEMBIC_INI))
        head = ScriptDirectory.from_config(cfg).get_current_head()
    except Exception as exc:  # noqa: BLE001 -- e.g. alembic.ini not found at this cwd
        return {"applied": applied, "head": None, "up_to_date": None, "error": str(exc)}

    return {"applied": applied, "head": head, "up_to_date": applied == head}


def _check_ml_model(db: Session) -> dict:
    try:
        service = PredictionService(db)
        return {"loaded": True, "model_version": service.model_version}
    except ModelNotTrainedError:
        return {"loaded": False, "model_version": None}


def _check_realtime_feed() -> dict:
    if not settings.ENABLE_REALTIME_FEED:
        return {"enabled": False, "status": "DISABLED"}

    from app.main import ws_manager  # local import: avoids a circular import at module load time

    return {"enabled": True, "status": ws_manager.status if ws_manager is not None else "DISABLED"}


def check_health(db: Session) -> dict:
    database = _check_database(db)
    migrations = _check_migrations(db) if database["connected"] else {"applied": None, "head": None, "up_to_date": False}
    ml_model = _check_ml_model(db) if database["connected"] else {"loaded": False, "model_version": None}
    realtime_feed = _check_realtime_feed()

    healthy = database["connected"] and bool(migrations.get("up_to_date"))
    return {
        "status": "ok" if healthy else "degraded",
        "database": database,
        "migrations": migrations,
        "ml_model": ml_model,
        "realtime_feed": realtime_feed,
    }
