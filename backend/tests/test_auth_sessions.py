"""Contract tests for cookie-based authentication.

Verifies the password hashing contract, the HttpOnly session cookie
behaviour, that protected routes reject unauthenticated callers, and that
duplicate accounts and bad passwords produce clear typed errors.
"""
from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.cookies import COOKIE_NAME
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ─── Password hashing contract ──────────────────────────────────────────

def test_passwords_are_hashed_with_bcrypt_and_never_stored_plain():
    hashed = hash_password("SuperSecret1")
    assert hashed != "SuperSecret1"
    assert hashed.startswith("$2")  # bcrypt marker
    assert bcrypt.checkpw(b"SuperSecret1", hashed.encode())


def test_password_verification_rejects_wrong_password():
    hashed = hash_password("SuperSecret1")
    assert verify_password("SuperSecret1", hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_password_hashing_is_salted():
    """Two identical passwords must produce different hashes."""
    assert hash_password("SamePassword1") != hash_password("SamePassword1")


# ─── Registration contract ──────────────────────────────────────────────

VALID_USER = {
    "email": "newuser@example.com",
    "full_name": "New User",
    "password": "SuperSecret1",
}


def test_register_returns_token_and_user(client):
    response = client.post("/api/v1/auth/register", json=VALID_USER)
    # Accept either success or a duplicate from an earlier run in the same DB.
    assert response.status_code in (201, 409)
    if response.status_code == 201:
        body = response.json()
        assert body["access_token"]
        assert body["user"]["email"] == "newuser@example.com"


def test_register_rejects_weak_password(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "weak@example.com", "full_name": "Weak Pass", "password": "short",
    })
    assert response.status_code == 422


def test_register_rejects_password_without_digit(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "nodigit@example.com", "full_name": "No Digit", "password": "onlyletters",
    })
    assert response.status_code == 422


def test_register_rejects_invalid_email(client):
    response = client.post("/api/v1/auth/register", json={
        "email": "not-an-email", "full_name": "Bad Email", "password": "SuperSecret1",
    })
    assert response.status_code == 422


def test_register_sets_http_only_session_cookie(client):
    response = client.post("/api/v1/auth/register", json=VALID_USER)
    if response.status_code != 201:
        pytest.skip("account already exists in the shared test database")
    cookies = response.headers.get_list("set-cookie")
    session = [c for c in cookies if c.startswith(f"{COOKIE_NAME}=")]
    assert session, f"no {COOKIE_NAME} cookie set; got {cookies}"
    assert "HttpOnly" in session[0]
    assert "Path=/" in session[0]


def test_login_returns_user_and_sets_cookie(client):
    client.post("/api/v1/auth/register", json=VALID_USER)
    response = client.post("/api/v1/auth/login", json={
        "email": VALID_USER["email"], "password": VALID_USER["password"],
    })
    assert response.status_code == 200
    assert response.json()["user"]["email"] == VALID_USER["email"]
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith(f"{COOKIE_NAME}=") and "HttpOnly" in c for c in cookies)


def test_login_with_wrong_password_is_rejected(client):
    client.post("/api/v1/auth/register", json=VALID_USER)
    response = client.post("/api/v1/auth/login", json={
        "email": VALID_USER["email"], "password": "WrongPassword1",
    })
    assert response.status_code == 401


def test_login_unknown_account_is_rejected(client):
    response = client.post("/api/v1/auth/login", json={
        "email": "nobody-here@example.com", "password": "Whatever1",
    })
    assert response.status_code == 401


def test_logout_clears_the_session_cookie(client):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    cleared = [c for c in cookies if c.startswith(f"{COOKIE_NAME}=")]
    assert cleared, "logout must clear the session cookie"


# ─── Protected routes ───────────────────────────────────────────────────

def test_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_accepts_bearer_token(client):
    client.post("/api/v1/auth/register", json=VALID_USER)
    login = client.post("/api/v1/auth/login", json={
        "email": VALID_USER["email"], "password": VALID_USER["password"],
    })
    token = login.json()["access_token"]
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == VALID_USER["email"]


def test_me_accepts_session_cookie(client):
    """The cookie must authenticate a browser client with no Auth header."""
    client.post("/api/v1/auth/register", json=VALID_USER)
    login = client.post("/api/v1/auth/login", json={
        "email": VALID_USER["email"], "password": VALID_USER["password"],
    })
    token = login.json()["access_token"]
    # Set on the client instance so the jar persists like a real browser.
    client.cookies.set(COOKIE_NAME, token)
    try:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert response.json()["email"] == VALID_USER["email"]
    finally:
        client.cookies.clear()


def test_me_rejects_a_tampered_cookie(client):
    client.cookies.set(COOKIE_NAME, "not.a.valid.token")
    try:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
    finally:
        client.cookies.clear()


def test_protected_saved_routes_require_auth(client):
    assert client.get("/api/v1/saved/properties").status_code == 401
