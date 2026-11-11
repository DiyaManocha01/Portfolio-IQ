"""Angel One SmartAPI REST authentication (login + token refresh).

Built from Angel One's publicly documented REST auth contract
(https://smartapi.angelone.in/docs/Authentication). NOT VERIFIED
end-to-end against the live API: this sandbox's egress proxy rejects
every Angel One host (apiconnect.angelbroking.com, smartapi.angelbroking.com,
margincalculator.angelbroking.com -- confirmed while planning Phase 24), so
nothing here has exchanged a real request/response with Angel One. Treat
this module as "built to the documented contract, not yet proven against
the real service" until you run it locally with real credentials -- see
docs/adr/0008-realtime-market-data-angelone.md.

Credentials are never hardcoded or logged: they come from app.config
settings (backend-only env vars), and this module never prints a password,
TOTP secret, or token value.
"""

from __future__ import annotations

from dataclasses import dataclass

import pyotp
import requests

LOGIN_URL = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/loginByPassword"
REFRESH_URL = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/jwt/v1/generateTokens"
REQUEST_TIMEOUT_SECONDS = 15


class AngelOneAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class AngelOneSession:
    jwt_token: str
    refresh_token: str
    feed_token: str


def _headers(api_key: str) -> dict[str, str]:
    # X-ClientLocalIP/PublicIP/MACAddress are REQUIRED by Angel One's API
    # but their actual values aren't checked for correctness by the
    # service (per public integration reports) -- placeholder values are
    # the commonly-documented approach. Revisit if your account enforces
    # stricter validation.
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "X-MACAddress": "00:00:00:00:00:00",
        "X-PrivateKey": api_key,
    }


def generate_totp(totp_secret: str) -> str:
    return pyotp.TOTP(totp_secret).now()


def login(api_key: str, client_code: str, password: str, totp_secret: str) -> AngelOneSession:
    payload = {
        "clientcode": client_code,
        "password": password,
        "totp": generate_totp(totp_secret),
    }
    resp = requests.post(LOGIN_URL, json=payload, headers=_headers(api_key), timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status"):
        raise AngelOneAuthError(f"Angel One login failed: {body.get('message', body)}")
    data = body["data"]
    return AngelOneSession(
        jwt_token=data["jwtToken"],
        refresh_token=data["refreshToken"],
        feed_token=data["feedToken"],
    )


def refresh(api_key: str, refresh_token: str) -> AngelOneSession:
    payload = {"refreshToken": refresh_token}
    resp = requests.post(REFRESH_URL, json=payload, headers=_headers(api_key), timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("status"):
        raise AngelOneAuthError(f"Angel One token refresh failed: {body.get('message', body)}")
    data = body["data"]
    return AngelOneSession(
        jwt_token=data["jwtToken"],
        refresh_token=data.get("refreshToken", refresh_token),
        feed_token=data.get("feedToken", ""),
    )
