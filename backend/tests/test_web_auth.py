"""C1 gate — auth routers + cookie sessions (integration, live test DB).

Exercises the full register → me → logout flow through FastAPI's ``TestClient``
against a real Postgres, plus the unauthenticated 401 paths and the 409 on a
duplicate registration. The shared ``auth_client`` fixture (conftest) isolates
each test to a rolled-back transaction and configures a trusted Origin + non-
Secure cookie for HTTP TestClient.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import (
    SESSION_COOKIE_NAME,
    TEST_PASSWORD,
    requires_db,
)

pytestmark = requires_db


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 201, resp.text


def _csrf_token(client: TestClient) -> str:
    """Read the session-bound CSRF token from /me (how the SPA obtains it)."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def test_register_sets_httponly_cookie_and_returns_summary(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "reg@example.com", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "reg@example.com"
    assert "id" in body and "created_at" in body
    # No password material or token is echoed in the body (AC-4 / NFR-SEC-002).
    assert "password" not in body and "csrf_token" not in body

    # The session cookie is set and HttpOnly (not readable by browser JS).
    set_cookie = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    # The cookie value is the opaque token only, not the user id/email.
    assert body["id"] not in set_cookie and body["email"] not in set_cookie


def test_full_register_me_logout_flow(auth_client: TestClient) -> None:
    _register(auth_client, "flow@example.com")

    # /me returns the summary + a CSRF token while the cookie is held.
    me = auth_client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["email"] == "flow@example.com"
    assert me_body["csrf_token"]  # non-empty session-bound token

    # Logout ends the session and clears the cookie (CSRF token required, C2).
    logout = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": me_body["csrf_token"]},
    )
    assert logout.status_code == 204, logout.text

    # After logout the session is gone → /me is 401.
    after = auth_client.get("/api/auth/me")
    assert after.status_code == 401, after.text


def test_login_after_register_succeeds(auth_client: TestClient) -> None:
    _register(auth_client, "login@example.com")
    # Drop the registration cookie to prove login issues a fresh session.
    auth_client.cookies.clear()

    resp = auth_client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "login@example.com"
    assert SESSION_COOKIE_NAME in resp.headers.get("set-cookie", "")

    assert auth_client.get("/api/auth/me").status_code == 200


def test_me_unauthenticated_returns_401(auth_client: TestClient) -> None:
    assert auth_client.get("/api/auth/me").status_code == 401


def test_logout_unauthenticated_returns_401(auth_client: TestClient) -> None:
    assert auth_client.post("/api/auth/logout").status_code == 401


def test_login_wrong_password_returns_401(auth_client: TestClient) -> None:
    _register(auth_client, "wrongpw@example.com")
    auth_client.cookies.clear()
    resp = auth_client.post(
        "/api/auth/login",
        json={"email": "wrongpw@example.com", "password": "the wrong password!!"},
    )
    assert resp.status_code == 401, resp.text


def test_duplicate_registration_returns_409(auth_client: TestClient) -> None:
    _register(auth_client, "dupe@example.com")
    auth_client.cookies.clear()
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "dupe@example.com", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 409, resp.text


def test_session_cookie_attributes_match_settings(auth_client: TestClient) -> None:
    settings = get_settings()
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "attrs@example.com", "password": TEST_PASSWORD},
    )
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert f"path={settings.session_cookie_path}".lower() in set_cookie
    if settings.session_cookie_secure:
        assert "secure" in set_cookie
