"""Tests for Phase 34's default rate limit (app/services/rate_limit.py).

Deliberately does NOT hammer a real route on the shared `app` fixture:
slowapi's limiter storage is shared process-wide, so firing 120+ requests
at a real endpoint here would pollute that shared state for every other
test file in the suite (the exact class of flakiness Phase 31 already hit
once with the auth rate limiter -- see test_portfolio_performance.py's
`_register` helper and its docstring). Instead, this builds a tiny,
throwaway Starlette app with its own Limiter/storage, isolated from the
real one, to verify the `default_limits` MECHANISM itself: that a route
with no `@limiter.limit(...)` of its own is still covered by the
Limiter's `default_limits` once `SlowAPIMiddleware` is installed.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def _build_app(default_limits: list[str]) -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, default_limits=default_limits)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/undecorated")
    def undecorated():
        return {"ok": True}

    return app


def test_default_limit_applies_to_a_route_with_no_decorator():
    client = TestClient(_build_app(["2/minute"]))
    assert client.get("/undecorated").status_code == 200
    assert client.get("/undecorated").status_code == 200
    assert client.get("/undecorated").status_code == 429


def test_generous_default_limit_does_not_block_normal_use():
    client = TestClient(_build_app(["120/minute"]))
    for _ in range(10):
        assert client.get("/undecorated").status_code == 200
