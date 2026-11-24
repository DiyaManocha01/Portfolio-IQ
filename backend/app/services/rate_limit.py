from slowapi import Limiter
from slowapi.util import get_remote_address

# Phase 21 added stricter, route-specific limits on auth/assistant
# (login/register: brute-force; assistant: a paid API call per question).
# Phase 34 adds this DEFAULT, applied by SlowAPIMiddleware (app/main.py) to
# every OTHER route that has no `@limiter.limit(...)` of its own. A route
# WITH its own `@limiter.limit(...)` decorator keeps that stricter limit
# (the decorator takes over for that route; this default still applies
# additively, so the decorated limit remains the binding constraint there
# -- see docs/security-review.md). 120/minute per client IP is generous
# for a single real user clicking around the UI, while still bounding the
# damage a scripted client could do against this project's DB/ML-
# inference-backed endpoints.
#
# Real-data upgrade Phase J: the flat 120/minute default didn't
# distinguish a cheap GET from an expensive multi-position simulation or
# covariance optimization (a documented gap, see docs/limitations.md's
# Phase 34 section). `GET /portfolio/optimize` (PyPortfolioOpt, explicitly
# named in that gap), `POST /portfolio/what-if`, `POST
# /portfolio/stress-test`, `GET /portfolio/risk-attribution`, and `GET
# /discover` (O(n) Fit Engine batch ranking over the full universe) now
# each carry their own tighter `@limiter.limit(...)` (20-30/minute,
# reasonable defaults chosen for being expensive but not paid-API-call
# expensive like `/assistant/ask`'s 20/minute -- not load-tested against
# any specific latency/throughput target, since this sandbox has no
# production traffic to measure against).
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
