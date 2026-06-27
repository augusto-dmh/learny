"""C1 gate — auth routers + cookie sessions (integration, live test DB).

Exercises the full register → me → logout flow through FastAPI's ``TestClient``
against a real Postgres, plus the unauthenticated 401 paths and the 409 on a
duplicate registration.

Isolation: ``get_db_connection`` is overridden to yield the test's
transaction-scoped connection (rolled back after each test), so every request in
a test shares one uncommitted unit of work and no rows leak between tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.config import get_settings
from app.infrastructure.web.dependencies import get_db_connection
from app.main import create_app
from tests.conftest import requires_db

pytestmark = requires_db

PASSWORD = "correct horse battery staple"  # >= 12 chars, satisfies policy
COOKIE_NAME = "learny_session"


@pytest.fixture
def client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # TestClient speaks http://testserver; a Secure cookie would not be sent back
    # over plain HTTP, so disable Secure for the test (mirrors local HTTP dev,
    # NFR-SEC-002 — Secure stays on for the VPS/HTTPS deployment).
    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    app = create_app()

    def _override() -> Iterator[Connection]:
        # Single shared connection; the outer db_conn transaction is rolled back
        # by the conftest fixture, so commits inside the request are not durable.
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _register(client: TestClient, email: str) -> None:
    resp = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201, resp.text


def test_register_sets_httponly_cookie_and_returns_summary(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": "reg@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "reg@example.com"
    assert "id" in body and "created_at" in body
    # No password material or token is echoed in the body (AC-4 / NFR-SEC-002).
    assert "password" not in body and "csrf_token" not in body

    # The session cookie is set and HttpOnly (not readable by browser JS).
    set_cookie = resp.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    # The cookie value is the opaque token only, not the user id/email.
    assert body["id"] not in set_cookie and body["email"] not in set_cookie


def test_full_register_me_logout_flow(client: TestClient) -> None:
    _register(client, "flow@example.com")

    # /me returns the summary + a CSRF token while the cookie is held.
    me = client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["email"] == "flow@example.com"
    assert me_body["csrf_token"]  # non-empty session-bound token

    # Logout ends the session and clears the cookie.
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204, logout.text

    # After logout the session is gone → /me is 401.
    after = client.get("/api/auth/me")
    assert after.status_code == 401, after.text


def test_login_after_register_succeeds(client: TestClient) -> None:
    _register(client, "login@example.com")
    # Drop the registration cookie to prove login issues a fresh session.
    client.cookies.clear()

    resp = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "login@example.com"
    assert COOKIE_NAME in resp.headers.get("set-cookie", "")

    assert client.get("/api/auth/me").status_code == 200


def test_me_unauthenticated_returns_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_logout_unauthenticated_returns_401(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 401


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    _register(client, "wrongpw@example.com")
    client.cookies.clear()
    resp = client.post(
        "/api/auth/login",
        json={"email": "wrongpw@example.com", "password": "the wrong password!!"},
    )
    assert resp.status_code == 401, resp.text


def test_duplicate_registration_returns_409(client: TestClient) -> None:
    _register(client, "dupe@example.com")
    client.cookies.clear()
    resp = client.post(
        "/api/auth/register",
        json={"email": "dupe@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 409, resp.text


def test_session_cookie_attributes_match_settings(client: TestClient) -> None:
    settings = get_settings()
    resp = client.post(
        "/api/auth/register",
        json={"email": "attrs@example.com", "password": PASSWORD},
    )
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert f"path={settings.session_cookie_path}".lower() in set_cookie
    if settings.session_cookie_secure:
        assert "secure" in set_cookie
