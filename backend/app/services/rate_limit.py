from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance: imported by main.py (to register it + its
# exception handler on the app) and by any route module that wants to
# rate-limit specific endpoints (e.g. auth login/register, to slow down
# credential-stuffing / brute-force attempts).
limiter = Limiter(key_func=get_remote_address)
