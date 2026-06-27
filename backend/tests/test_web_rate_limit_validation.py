"""C3 gate — rate-limit hook + input validation (integration, live test DB).

- Rapid repeated auth attempts hit the rate-limit hook (429) once the window is
  exceeded; the limiter is pluggable (a tight limiter is installed for the test).
- Registration/login validate input at the boundary: malformed email and a weak
  (too-short) password are rejected with 422 (FR-AUTH-010), before any session
  is created.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.infrastructure.web.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    get_rate_limiter,
    set_rate_limiter,
)
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db


@pytest.fixture
def throttled_client(
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Like ``auth_client`` but with a deliberately tight rate limiter."""
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous = get_rate_limiter()
    # Allow 3 attempts per long window so the 4th trips deterministically.
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous)
    get_settings.cache_clear()


def test_repeated_login_attempts_hit_rate_limit(throttled_client: TestClient) -> None:
    payload = {"email": "throttle@example.com", "password": "the wrong password!!"}
    # First 3 attempts pass the limiter (and fail auth with 401).
    for _ in range(3):
        resp = throttled_client.post("/api/auth/login", json=payload)
        assert resp.status_code == 401, resp.text
    # The 4th attempt is throttled before reaching auth logic.
    throttled = throttled_client.post("/api/auth/login", json=payload)
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


def test_repeated_register_attempts_hit_rate_limit(throttled_client: TestClient) -> None:
    for i in range(3):
        resp = throttled_client.post(
            "/api/auth/register",
            json={"email": f"rl{i}@example.com", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 201, resp.text
    throttled = throttled_client.post(
        "/api/auth/register",
        json={"email": "rl-final@example.com", "password": TEST_PASSWORD},
    )
    assert throttled.status_code == 429, throttled.text


def test_register_rejects_malformed_email(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 422, resp.text


def test_register_rejects_weak_password(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "weakpw@example.com", "password": "short"},
    )
    assert resp.status_code == 422, resp.text
    # No session was issued for the rejected registration.
    assert "set-cookie" not in {k.lower() for k in resp.headers}


def test_login_rejects_malformed_email(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/login",
        json={"email": "bad@@example", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 422, resp.text
