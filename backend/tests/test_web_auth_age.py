"""The adult-only register gate (integration, live test DB).

An account is created only behind an explicit 18-or-older attestation: the
request body defaults to False at the HTTP boundary, the application service
refuses before any write, and a valid email + password + consent with a missing
or false attestation is a 422 that leaves no user, credential, session, or
invite consumption behind. With the attestation present the flow is exactly as
before.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select

from app.infrastructure.db.metadata import (
    invite_codes,
    sessions,
    user_credentials,
    users,
)
from tests.conftest import SESSION_COOKIE_NAME, TEST_PASSWORD, requires_db

pytestmark = requires_db

AGE_COPY = "You must confirm you are 18 or older to create an account."


def _user_count(conn: Connection) -> int:
    return conn.execute(select(func.count()).select_from(users)).scalar_one()


def _credential_count(conn: Connection) -> int:
    return conn.execute(select(func.count()).select_from(user_credentials)).scalar_one()


def _session_count(conn: Connection) -> int:
    return conn.execute(select(func.count()).select_from(sessions)).scalar_one()


def test_refuses_register_without_the_age_attestation(
    auth_client: TestClient, db_conn: Connection
) -> None:
    before_users = _user_count(db_conn)
    before_credentials = _credential_count(db_conn)
    before_sessions = _session_count(db_conn)
    before_invites = db_conn.execute(select(func.count()).select_from(invite_codes)).scalar_one()

    # Absent field: the boundary default (False) refuses, even though the email,
    # the password, and the terms consent are all valid.
    resp = auth_client.post(
        "/api/auth/register",
        json={
            "email": "adult@example.com",
            "password": TEST_PASSWORD,
            "accepted_tos": True,
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == AGE_COPY

    # Explicit false refuses identically.
    resp = auth_client.post(
        "/api/auth/register",
        json={
            "email": "adult@example.com",
            "password": TEST_PASSWORD,
            "accepted_tos": True,
            "age_attested": False,
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == AGE_COPY

    # The refusal precedes validation policy too: even a malformed email answers
    # the age copy, because the attestation is checked before anything else —
    # and still nothing was written or consumed.
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == AGE_COPY

    assert _user_count(db_conn) == before_users
    assert _credential_count(db_conn) == before_credentials
    assert _session_count(db_conn) == before_sessions
    assert (
        db_conn.execute(select(func.count()).select_from(invite_codes)).scalar_one()
        == before_invites
    )
    assert SESSION_COOKIE_NAME not in auth_client.cookies


def test_registers_with_the_attestation_as_before(
    auth_client: TestClient, db_conn: Connection
) -> None:
    before = _user_count(db_conn)
    resp = auth_client.post(
        "/api/auth/register",
        json={
            "email": "adult@example.com",
            "password": TEST_PASSWORD,
            "accepted_tos": True,
            "age_attested": True,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "adult@example.com"
    assert _user_count(db_conn) == before + 1
    assert _credential_count(db_conn) >= 1
    assert _session_count(db_conn) >= 1
    assert SESSION_COOKIE_NAME in auth_client.cookies

    # /me answers for the new account: the session is real, not just a cookie.
    me = auth_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "adult@example.com"
