"""C2 gate — session-bound CSRF protection (integration, live test DB).

Proves the synchronizer-token gate on a state-changing endpoint (logout):
- write without a CSRF token → 403,
- write with a wrong CSRF token → 403,
- write with the valid session-bound token → accepted,
- write from an untrusted Origin → 403 (even with a valid token),
- pre-session endpoints (register) are Origin-checked,
- an unauthenticated write fails auth (401) before the CSRF gate.

Reuses the shared ``auth_client`` fixture (conftest).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TEST_PASSWORD, requires_db

pytestmark = requires_db


def _register(client: TestClient, email: str) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 201, resp.text


def _csrf_token(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def test_write_without_csrf_token_is_rejected(auth_client: TestClient) -> None:
    _register(auth_client, "csrf-missing@example.com")
    resp = auth_client.post("/api/auth/logout")
    assert resp.status_code == 403, resp.text
    # The session is still valid (the rejected write changed nothing).
    assert auth_client.get("/api/auth/me").status_code == 200


def test_write_with_invalid_csrf_token_is_rejected(auth_client: TestClient) -> None:
    _register(auth_client, "csrf-wrong@example.com")
    resp = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": "not-the-real-token"},
    )
    assert resp.status_code == 403, resp.text
    assert auth_client.get("/api/auth/me").status_code == 200


def test_write_with_valid_csrf_token_is_accepted(auth_client: TestClient) -> None:
    _register(auth_client, "csrf-ok@example.com")
    token = _csrf_token(auth_client)
    resp = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": token},
    )
    assert resp.status_code == 204, resp.text
    # Session is gone after the accepted logout.
    assert auth_client.get("/api/auth/me").status_code == 401


def test_write_from_untrusted_origin_is_rejected(auth_client: TestClient) -> None:
    _register(auth_client, "csrf-origin@example.com")
    token = _csrf_token(auth_client)
    resp = auth_client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": token, "Origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403, resp.text
    assert auth_client.get("/api/auth/me").status_code == 200


def test_register_from_untrusted_origin_is_rejected(auth_client: TestClient) -> None:
    # Pre-session endpoints are Origin-checked even though they carry no token.
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "csrf-pre@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403, resp.text


def test_unauthenticated_write_is_401_not_403(auth_client: TestClient) -> None:
    # No session → authentication fails first (401), before the CSRF gate.
    resp = auth_client.post("/api/auth/logout")
    assert resp.status_code == 401, resp.text
