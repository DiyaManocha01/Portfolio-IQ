"""Structured logging + per-request correlation IDs (Phase 34).

Replaces the previous single `logging.basicConfig(level=logging.WARNING)`
call in `app/main.py` with a configurable level (`settings.LOG_LEVEL`) and
a JSON formatter, so logs from a real deployment can be ingested by any
log-aggregation tool (ELK, CloudWatch, etc.) without a custom parser --
one JSON object per line, not a hand-formatted string.

No new dependency: this uses only the standard library's `logging` and
`contextvars`, deliberately, rather than adding `python-json-logger` or
similar for what a ~30-line `Formatter` subclass already does cleanly.

The correlation ID (`request_id`) is a `contextvars.ContextVar` set by
`RequestContextMiddleware` (app/main.py) at the start of every request and
read back here by `JsonFormatter` -- so every log line emitted anywhere
during that request's handling (a route, a service, this module itself)
automatically carries the same ID, without having to thread it through
every function call by hand. It is also echoed back as the `X-Request-ID`
response header, so a user-reported error can be correlated to the exact
log lines for that request.
"""

from __future__ import annotations

import contextvars
import json
import logging
import time

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord(
    "", 0, "", 0, "", (), None,
).__dict__.keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Renders each log record as one JSON object per line.

    Any extra fields passed via `logger.info(..., extra={...})` are
    included as-is (as long as they don't collide with a standard
    LogRecord attribute name) -- this is how route/service code can
    attach structured context (e.g. a symbol, a status code) without
    needing its own formatter.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_RECORD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Call once at startup (app/main.py). Idempotent: clears any handlers
    a previous call (or a test re-importing main) left on the root logger
    first, so logs are never duplicated."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def new_request_id() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


def monotonic_ms() -> float:
    return time.monotonic() * 1000
