from slowapi import Limiter
from slowapi.util import get_remote_address

# Phase 21 added stricter, route-specific limits on auth/assistant
# (login/register: brute-force; assistant: a paid API call per question).
# Phase 34 adds this DEFAULT, applied by SlowAPIMiddleware (app/main.py) to
# every OTHER route that has no `@limiter.limit(...)` of its own --
# previously portfolio/stocks/market/discover/screener/alerts/paper-trading/
# portfolio-fit/ledger had no rate limiting at all. A route WITH its own
# `@limiter.limit(...)` decorator keeps that stricter limit (the decorator
# takes over for that route; this default still applies additively, so the
# decorated limit remains the binding constraint there -- see
# docs/security-review.md). 120/minute per client IP is generous for a
# single real user clicking around the UI, while still bounding the damage
# a scripted client could do against this project's DB/ML-inference-backed
# endpoints, several of which are non-trivial computations
# (optimization, backtesting, what-if simulation).
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
