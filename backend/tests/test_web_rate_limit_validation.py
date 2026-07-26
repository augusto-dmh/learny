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
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from starlette.requests import Request

from app.infrastructure.web.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    get_rate_limiter,
    rate_limit_conversations,
    rate_limit_questions,
    rate_limit_teaching,
    set_rate_limiter,
)
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db


@pytest.fixture
def throttled_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
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


def _questions_request() -> Request:
    """Minimal ASGI request scope for the questions route (client IP + path key)."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/sources/00000000-0000-0000-0000-000000000000/questions",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
        }
    )


def test_rate_limit_questions_throttles_after_window() -> None:
    # QA-22: once the window is exceeded, the questions dependency rejects with
    # 429 + a Retry-After header, via the shared swappable limiter keyed by
    # client IP + route path. The endpoint itself is wired in C2; here the
    # dependency is exercised directly against a deliberately tight limiter.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        request = _questions_request()
        # First 3 attempts pass the limiter (return None, no raise).
        for _ in range(3):
            assert rate_limit_questions(request) is None
        # The 4th attempt trips the limit.
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_questions(request)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert int(exc_info.value.headers["Retry-After"]) >= 1
    finally:
        set_rate_limiter(previous)


def _teaching_request() -> Request:
    """Minimal ASGI request scope for the teaching route (client IP + path key)."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/teaching-sessions",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
        }
    )


def test_rate_limit_teaching_throttles_after_window() -> None:
    # TEACH-18: once the window is exceeded, the teaching dependency rejects with
    # 429 + a Retry-After header, via the shared swappable limiter keyed by
    # client IP + route path. The endpoints themselves are wired in D2/D3; here
    # the dependency is exercised directly against a deliberately tight limiter.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        request = _teaching_request()
        # First 3 attempts pass the limiter (return None, no raise).
        for _ in range(3):
            assert rate_limit_teaching(request) is None
        # The 4th attempt trips the limit.
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_teaching(request)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert int(exc_info.value.headers["Retry-After"]) >= 1
    finally:
        set_rate_limiter(previous)


def _conversations_request() -> Request:
    """Minimal ASGI request scope for the conversations route (client IP + path key)."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/conversations",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
        }
    )


def test_rate_limit_conversations_throttles_after_window() -> None:
    # CONV-22: the unified surface has one policy, and past its window the
    # dependency rejects with 429 + a Retry-After header, via the same swappable
    # limiter keyed by client IP + route path. Exercised directly here against a
    # deliberately tight limiter; the endpoints are covered in the router suite.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        request = _conversations_request()
        for _ in range(3):
            assert rate_limit_conversations(request) is None
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_conversations(request)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert int(exc_info.value.headers["Retry-After"]) >= 1
    finally:
        set_rate_limiter(previous)


def _conversation_turn_request(conversation_id: str) -> Request:
    """A turn request as FastAPI hands it over: concrete path plus the matched route."""

    class _Route:
        path = "/api/conversations/{conversation_id}/turns"

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/api/conversations/{conversation_id}/turns",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
            "route": _Route(),
        }
    )


def test_conversation_turn_budget_is_shared_across_a_clients_conversations() -> None:
    # CONV-22: the turn path interpolates a conversation id, so keying on the
    # concrete path would hand a client a fresh budget for every conversation it
    # starts — against the retrieval and generation this throttle exists to protect.
    # The route template is the bucket, so three turns spread over three
    # conversations spend the same budget as three turns in one.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        for conversation_id in ("aaa", "bbb", "ccc"):
            assert rate_limit_conversations(_conversation_turn_request(conversation_id)) is None
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_conversations(_conversation_turn_request("ddd"))
        assert exc_info.value.status_code == 429
    finally:
        set_rate_limiter(previous)


def test_conversation_routes_keep_their_own_limit_values() -> None:
    # The single dependency means one limit *value* per route template, not one
    # bucket for the surface: exhausting the turn budget must not lock a reader out
    # of renaming or deleting what they already have.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        for _ in range(3):
            assert rate_limit_conversations(_conversation_turn_request("aaa")) is None
        with pytest.raises(HTTPException):
            rate_limit_conversations(_conversation_turn_request("aaa"))
        assert rate_limit_conversations(_conversations_request()) is None
    finally:
        set_rate_limiter(previous)


def test_the_other_limiters_still_key_on_the_concrete_path() -> None:
    # The route-template key belongs to the conversations dependency alone: the
    # shipped limiters keep the exact 429 behaviour they have today.
    from app.infrastructure.web.rate_limit import _client_key

    request = _conversation_turn_request("aaa")

    assert _client_key(request) == "1.2.3.4:/api/conversations/aaa/turns"


def test_teaching_errors_map_to_expected_status_codes() -> None:
    # Conversation error contract: every error of the conversation vocabulary
    # translates to its documented HTTP status through ``register_error_handlers`` —
    # no disclosure (404), unknown scope / bad title / unknown mode (422), target gone
    # and turn race (409). The readable service message is surfaced as the body
    # ``detail`` (no leak). One table, so an error added without a mapping shows up
    # here as a 500 rather than in production.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.application.errors import (
        ConversationNotFound,
        ConversationTargetUnavailable,
        ConversationTurnConflict,
        InvalidConversationMode,
        InvalidConversationScope,
        InvalidConversationTitle,
    )
    from app.infrastructure.web.error_handlers import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/session-not-found")
    def _session_not_found() -> None:
        raise ConversationNotFound("Teaching session not found.")

    @app.get("/invalid-target")
    def _invalid_target() -> None:
        raise InvalidConversationScope("Target does not exist in this source.")

    @app.get("/target-gone")
    def _target_gone() -> None:
        raise ConversationTargetUnavailable("The teaching target no longer exists.")

    @app.get("/turn-conflict")
    def _turn_conflict() -> None:
        raise ConversationTurnConflict("another turn already claimed this turn index")

    @app.get("/invalid-title")
    def _invalid_title() -> None:
        raise InvalidConversationTitle("Title must be at most 200 characters.")

    @app.get("/invalid-mode")
    def _invalid_mode() -> None:
        raise InvalidConversationMode("Unknown conversation mode: 'shout'")

    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/session-not-found").status_code == 404
    assert client.get("/invalid-target").status_code == 422

    gone = client.get("/target-gone")
    assert gone.status_code == 409
    assert gone.json() == {"detail": "The teaching target no longer exists."}

    assert client.get("/turn-conflict").status_code == 409

    # Neither of these is reachable over HTTP today — the routers' own validators
    # reject a blank/oversize title and an unknown mode first — which is exactly why
    # the mapping needs a sensor: the day a validator relaxes, a missing entry here
    # is a 500 instead of a 422.
    bad_title = client.get("/invalid-title")
    assert bad_title.status_code == 422
    assert bad_title.json() == {"detail": "Title must be at most 200 characters."}

    bad_mode = client.get("/invalid-mode")
    assert bad_mode.status_code == 422
    assert bad_mode.json() == {"detail": "Unknown conversation mode: 'shout'"}
