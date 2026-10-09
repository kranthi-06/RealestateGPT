"""HTTP-only session cookie helpers.

The browser session token is stored in a Secure, HttpOnly, SameSite cookie so
it is not readable from JavaScript (XSS cannot exfiltrate it), while the same
JWT still works through the ``Authorization: Bearer`` header for API clients
and the test suite. Cookies are only issued over HTTPS in production.
"""
from __future__ import annotations

import logging

from fastapi import Response

from app.core.config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "regpt_session"


def _cookie_secure() -> bool:
    """Only mark the cookie Secure when the deployment is HTTPS-capable."""
    return settings.APP_ENV.strip().lower() == "production"


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the session cookie to a login/register response."""
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        httponly=True,          # not readable by JavaScript
        secure=_cookie_secure(),
        samesite="lax",         # CSRF hardening; same-origin API calls still work
    )


def clear_auth_cookie(response: Response) -> None:
    """Remove the session cookie (logout)."""
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


def token_from_request_cookie(cookies: dict | None) -> str | None:
    """Return the bearer token stored in the session cookie, if present."""
    if not cookies:
        return None
    token = cookies.get(COOKIE_NAME)
    return token if isinstance(token, str) and token else None
