"""Tests angelone_auth against MOCKED HTTP responses -- no real Angel One
request is ever made (this sandbox cannot reach their hosts anyway, see
that module's docstring). These tests verify this module's own request
construction and response handling, not that Angel One's real API behaves
this way.
"""

from unittest.mock import MagicMock, patch

import pyotp
import pytest

from app.services.market_data import angelone_auth
from app.services.market_data.angelone_auth import AngelOneAuthError, generate_totp, login, refresh


def test_generate_totp_produces_six_digits():
    secret = pyotp.random_base32()
    code = generate_totp(secret)
    assert len(code) == 6
    assert code.isdigit()


@patch("app.services.market_data.angelone_auth.requests.post")
def test_login_success(mock_post):
    mock_post.return_value = MagicMock(
        json=lambda: {
            "status": True,
            "data": {"jwtToken": "jwt-abc", "refreshToken": "refresh-abc", "feedToken": "feed-abc"},
        }
    )
    mock_post.return_value.raise_for_status = lambda: None

    session = login("api-key", "C123", "pw", pyotp.random_base32())

    assert session.jwt_token == "jwt-abc"
    assert session.refresh_token == "refresh-abc"
    assert session.feed_token == "feed-abc"
    sent_headers = mock_post.call_args.kwargs["headers"]
    assert sent_headers["X-PrivateKey"] == "api-key"
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["clientcode"] == "C123"
    assert len(sent_payload["totp"]) == 6


@patch("app.services.market_data.angelone_auth.requests.post")
def test_login_failure_status_false_raises(mock_post):
    mock_post.return_value = MagicMock(json=lambda: {"status": False, "message": "bad creds"})
    mock_post.return_value.raise_for_status = lambda: None

    with pytest.raises(AngelOneAuthError):
        login("api-key", "C123", "pw", pyotp.random_base32())


@patch("app.services.market_data.angelone_auth.requests.post")
def test_refresh_success(mock_post):
    mock_post.return_value = MagicMock(
        json=lambda: {
            "status": True,
            "data": {"jwtToken": "jwt-new", "refreshToken": "refresh-new", "feedToken": "feed-new"},
        }
    )
    mock_post.return_value.raise_for_status = lambda: None

    session = refresh("api-key", "old-refresh-token")
    assert session.jwt_token == "jwt-new"


@patch("app.services.market_data.angelone_auth.requests.post")
def test_refresh_failure_raises(mock_post):
    mock_post.return_value = MagicMock(json=lambda: {"status": False, "message": "expired"})
    mock_post.return_value.raise_for_status = lambda: None

    with pytest.raises(AngelOneAuthError):
        refresh("api-key", "old-refresh-token")
