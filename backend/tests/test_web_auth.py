"""C1 gate — auth routers + cookie sessions (integration, live test DB).

Exercises the full register → me → logout flow through FastAPI's ``TestClient``
against a real Postgres, plus the unauthenticated 401 paths and the 409 on a
duplicate registration. The shared ``auth_client`` fixture (conftest) isolates
each test to a rolled-back transaction and configures a trusted Origin + non-
Secure cookie for HTTP TestClient.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, insert, select

from app.core.config import get_settings
from app.infrastructure.db.metadata import invite_codes, sessions, users
from tests.conftest import (
    SESSION_COOKIE_NAME,
    TEST_PASSWORD,
    requires_db,
)

pytestmark = requires_db


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True},
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
        json={"email": "reg@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
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
        json={"email": "dupe@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 409, resp.text


def test_session_cookie_attributes_match_settings(auth_client: TestClient) -> None:
    settings = get_settings()
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "attrs@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert f"path={settings.session_cookie_path}".lower() in set_cookie
    if settings.session_cookie_secure:
        assert "secure" in set_cookie


# ---- Invite-gated register (DOOR-20/21/22) ----------------------------------

INVITE_COPY = "This instance is invite-only. A valid invite code is required to register."


def _seed_invite(db_conn: Connection, code: str, remaining: int, *, expires_at=None) -> None:
    db_conn.execute(
        insert(invite_codes).values(code=code, remaining_uses=remaining, expires_at=expires_at)
    )


# ---- Disposable + ToS rails (DOOR-23/24/25) ---------------------------------

GENERIC_EMAIL_COPY = "Invalid email address."
TOS_COPY = "You must accept the Terms of Service to create an account."


def test_register_with_listed_disposable_domain_is_422_generic(
    auth_client: TestClient, db_conn: Connection
) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={
            "email": "throwaway@mailinator.com",
            "password": TEST_PASSWORD,
            "accepted_tos": True,
        },
    )
    assert resp.status_code == 422, resp.text
    # The body is the exact generic invalid-email copy — the response never
    # names disposability as the reason (DOOR-23).
    assert resp.json() == {"detail": GENERIC_EMAIL_COPY}
    assert (
        db_conn.execute(select(users).where(users.c.email == "throwaway@mailinator.com")).first()
        is None
    )


def test_disposable_and_malformed_rejections_share_one_body(auth_client: TestClient) -> None:
    disposable = auth_client.post(
        "/api/auth/register",
        json={
            "email": "throwaway@yopmail.com",
            "password": TEST_PASSWORD,
            "accepted_tos": True,
        },
    )
    malformed = auth_client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert disposable.status_code == malformed.status_code == 422
    assert disposable.json() == malformed.json() == {"detail": GENERIC_EMAIL_COPY}


def test_register_allows_duck_dot_com_alias(auth_client: TestClient) -> None:
    # duck.com is a documented privacy alias, never rejected as disposable (DOOR-24).
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "reader@duck.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "reader@duck.com"


def test_register_without_tos_is_422(auth_client: TestClient, db_conn: Connection) -> None:
    # Consent omitted entirely — the boundary default is refusal (DOOR-25).
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "noservice@example.com", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json() == {"detail": TOS_COPY}
    assert "set-cookie" not in {k.lower() for k in resp.headers}
    assert (
        db_conn.execute(select(users).where(users.c.email == "noservice@example.com")).first()
        is None
    )


def test_register_with_tos_false_is_422(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={
            "email": "declined@example.com",
            "password": TEST_PASSWORD,
            "accepted_tos": False,
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json() == {"detail": TOS_COPY}


def test_register_with_tos_stamps_the_account(auth_client: TestClient, db_conn: Connection) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "consenting@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 201, resp.text
    stamped = db_conn.execute(
        select(users.c.accepted_tos_at).where(users.c.email == "consenting@example.com")
    ).scalar_one()
    assert stamped is not None


@pytest.fixture
def invite_client(auth_client: TestClient, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """``auth_client`` with ``LEARNY_INVITE_REQUIRED`` on (DOOR-20..22).

    The register wiring reads the flag from settings per request, so flipping the
    environment and clearing the settings cache after ``auth_client`` is built is
    enough. Every auth route stays behind the auth throttle and Origin gate — the
    invite gate itself lives in the register handler, below them.
    """
    monkeypatch.setenv("LEARNY_INVITE_REQUIRED", "true")
    get_settings.cache_clear()
    yield auth_client
    get_settings.cache_clear()


def test_register_without_invite_code_is_403_and_creates_nothing(
    invite_client: TestClient, db_conn: Connection
) -> None:
    resp = invite_client.post(
        "/api/auth/register",
        json={"email": "gate@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": INVITE_COPY}
    # No session cookie was minted for the rejected register.
    assert SESSION_COOKIE_NAME not in resp.headers.get("set-cookie", "")

    # No user row (and therefore no session row) survives the rejection.
    assert db_conn.execute(select(users).where(users.c.email == "gate@example.com")).first() is None
    assert db_conn.execute(select(func.count()).select_from(sessions)).scalar_one() == 0


def test_register_with_unknown_invite_code_is_403(
    invite_client: TestClient, db_conn: Connection
) -> None:
    resp = invite_client.post(
        "/api/auth/register",
        json={
            "email": "unknown-code@example.com",
            "password": TEST_PASSWORD,
            "invite_code": "not-a-code",
            "accepted_tos": True,
        },
    )
    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": INVITE_COPY}
    assert (
        db_conn.execute(select(users).where(users.c.email == "unknown-code@example.com")).first()
        is None
    )


def test_register_with_exhausted_invite_code_is_403(
    invite_client: TestClient, db_conn: Connection
) -> None:
    _seed_invite(db_conn, "spent", 0)
    resp = invite_client.post(
        "/api/auth/register",
        json={
            "email": "spent@example.com",
            "password": TEST_PASSWORD,
            "invite_code": "spent",
            "accepted_tos": True,
        },
    )
    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": INVITE_COPY}
    assert (
        db_conn.execute(select(users).where(users.c.email == "spent@example.com")).first() is None
    )


def test_register_with_expired_invite_code_is_403(
    invite_client: TestClient, db_conn: Connection
) -> None:
    _seed_invite(
        db_conn,
        "stale",
        3,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    resp = invite_client.post(
        "/api/auth/register",
        json={
            "email": "stale@example.com",
            "password": TEST_PASSWORD,
            "invite_code": "stale",
            "accepted_tos": True,
        },
    )
    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": INVITE_COPY}
    assert (
        db_conn.execute(select(users).where(users.c.email == "stale@example.com")).first() is None
    )


def test_register_with_valid_invite_returns_201_with_session(
    invite_client: TestClient, db_conn: Connection
) -> None:
    _seed_invite(db_conn, "WELCOME", 1)
    resp = invite_client.post(
        "/api/auth/register",
        json={
            "email": "invited@example.com",
            "password": TEST_PASSWORD,
            "invite_code": "WELCOME",
            "accepted_tos": True,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "invited@example.com"
    # The invited register still mints its session cookie (DOOR-21 / AD-327).
    set_cookie = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert invite_client.get("/api/auth/me").status_code == 200

    # The consume decremented the remaining uses (1 → 0).
    left = db_conn.execute(
        select(invite_codes.c.remaining_uses).where(invite_codes.c.code == "WELCOME")
    ).scalar_one()
    assert left == 0


def test_valid_invite_consumes_one_use_per_register_then_refuses(
    invite_client: TestClient, db_conn: Connection
) -> None:
    _seed_invite(db_conn, "TWICE", 2)

    for i in range(2):
        resp = invite_client.post(
            "/api/auth/register",
            json={
                "email": f"invitee{i}@example.com",
                "password": TEST_PASSWORD,
                "invite_code": "TWICE",
                "accepted_tos": True,
            },
        )
        assert resp.status_code == 201, resp.text
        invite_client.cookies.clear()

    # Both uses are gone: the same code can no longer register anyone (DOOR-22).
    third = invite_client.post(
        "/api/auth/register",
        json={
            "email": "invitee-too-late@example.com",
            "password": TEST_PASSWORD,
            "invite_code": "TWICE",
            "accepted_tos": True,
        },
    )
    assert third.status_code == 403, third.text
    assert third.json() == {"detail": INVITE_COPY}
    left = db_conn.execute(
        select(invite_codes.c.remaining_uses).where(invite_codes.c.code == "TWICE")
    ).scalar_one()
    assert left == 0
