"""C3 gate — rate-limit hook + input validation (integration, live test DB).

- Rapid repeated auth attempts hit the rate-limit hook (429) once the window is
  exceeded; the limiter is pluggable (a tight limiter is installed for the test).
- The expensive authenticated surfaces (conversations, quiz generation, upload,
  ingest-start) throttle on the caller's ``user_id``, so two learners behind one
  shared IP each get their own full budget; an unauthenticated request is a 401
  that spends nothing; a limiter that cannot record a hit fails closed with 503.
- Registration/login validate input at the boundary: malformed email and a weak
  (too-short) password are rejected with 422 (FR-AUTH-010), before any session
  is created.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from starlette.requests import Request

from app.domain.entities import (
    CorpusSectionRecord,
    ParsedSection,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.web.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    LimiterUnavailable,
    get_rate_limiter,
    rate_limit_conversations,
    rate_limit_quiz,
    rate_limit_upload,
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
    app = create_app()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))

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
            json={
                "email": f"rl{i}@example.com",
                "password": TEST_PASSWORD,
                "accepted_tos": True,
            },
        )
        assert resp.status_code == 201, resp.text
    throttled = throttled_client.post(
        "/api/auth/register",
        json={"email": "rl-final@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert throttled.status_code == 429, throttled.text


def test_register_rejects_malformed_email(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 422, resp.text


def test_register_rejects_weak_password(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "weakpw@example.com", "password": "short", "accepted_tos": True},
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


def _user() -> User:
    """A caller identity for direct dependency exercises (only ``id`` keys the bucket)."""
    return User(id=uuid4(), email="asker@example.com", created_at=datetime.now(UTC))


def test_rate_limit_conversations_throttles_after_window() -> None:
    # CONV-22: the unified surface has one policy, and past its window the
    # dependency rejects with 429 + a Retry-After header, via the same swappable
    # limiter keyed by user id + route template. Exercised directly here against a
    # deliberately tight limiter; the endpoints are covered in the router suite.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        user = _user()
        request = _conversations_request()
        for _ in range(3):
            assert rate_limit_conversations(user, request) is None
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_conversations(user, request)
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


def test_conversation_turn_budget_is_shared_across_a_users_conversations() -> None:
    # CONV-22: the turn path interpolates a conversation id, so keying on the
    # concrete path would hand a learner a fresh budget for every conversation they
    # start — against the retrieval and generation this throttle exists to protect.
    # The user + route template is the bucket, so three turns spread over three
    # conversations spend the same budget as three turns in one.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        user = _user()
        for conversation_id in ("aaa", "bbb", "ccc"):
            assert (
                rate_limit_conversations(user, _conversation_turn_request(conversation_id)) is None
            )
        with pytest.raises(HTTPException) as exc_info:
            rate_limit_conversations(user, _conversation_turn_request("ddd"))
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
        user = _user()
        for _ in range(3):
            assert rate_limit_conversations(user, _conversation_turn_request("aaa")) is None
        with pytest.raises(HTTPException):
            rate_limit_conversations(user, _conversation_turn_request("aaa"))
        assert rate_limit_conversations(user, _conversations_request()) is None
    finally:
        set_rate_limiter(previous)


def test_the_other_limiters_still_key_on_the_concrete_path() -> None:
    # The route-template key belongs to the conversations dependency alone: the
    # shipped limiters keep the exact 429 behaviour they have today.
    from app.infrastructure.web.rate_limit import _client_key

    request = _conversation_turn_request("aaa")

    assert _client_key(request) == "1.2.3.4:/api/conversations/aaa/turns"


# --- User-keyed budgets on the expensive surfaces (integration) -----------------


_BOOK_TEXT = "photosynthesis converts sunlight into chemical energy in green plants"


class _UnavailableLimiter:
    """A limiter that cannot record a hit at all (Redis down, fail closed)."""

    def hit(self, key: str) -> tuple[bool, int]:
        raise LimiterUnavailable("redis down")


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _seed_ready_source(db_conn: Connection, user_id: str) -> str:
    """Persist an owned ready source with a one-section corpus; return its id."""
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=UUID(user_id),
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    source_id = SqlAlchemySourceRepository(db_conn).add(source).id
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            CorpusSectionRecord(
                section=ParsedSection(
                    position=0,
                    title="Biology",
                    depth=0,
                    section_path=("Biology",),
                    anchor="bio.xhtml",
                    blocks=(),
                ),
                markdown="",
                chunks=(
                    SectionChunk(
                        index=0,
                        text=_BOOK_TEXT,
                        section_path=("Biology",),
                        anchor="bio.xhtml",
                        page_span=None,
                    ),
                ),
            ),
        ),
    )
    return str(source_id)


def _start_conversation(client: TestClient, source_id: str, *, csrf: str):
    return client.post(
        "/api/conversations",
        json={"source_id": source_id, "include_notes": False},
        headers={"X-CSRF-Token": csrf},
    )


def _post_turn(client: TestClient, conversation_id: str, *, csrf: str):
    return client.post(
        f"/api/conversations/{conversation_id}/turns",
        json={"message": "explain photosynthesis", "mode": "answer"},
        headers={"X-CSRF-Token": csrf},
    )


def _stream_turn(client: TestClient, conversation_id: str, *, csrf: str):
    return client.post(
        f"/api/conversations/{conversation_id}/turns/stream",
        json={"message": "explain photosynthesis", "mode": "answer"},
        headers={"X-CSRF-Token": csrf},
    )


def test_two_users_behind_one_ip_each_get_their_own_ask_budget(
    throttled_client: TestClient, db_conn: Connection
) -> None:
    # The expensive-surface budget follows the learner, not the client IP. Both
    # registrations ride one TestClient (one shared IP — ``testclient`` is a
    # trusted hop), so under IP keying the second learner would have inherited the
    # first one's exhausted bucket and 429ed on their first Ask.
    first_id = _register(throttled_client, "ask-a@example.com")
    csrf_a = _csrf(throttled_client)
    started = _start_conversation(
        throttled_client, _seed_ready_source(db_conn, first_id), csrf=csrf_a
    )
    assert started.status_code == 201, started.text
    conversation_a = started.json()["id"]
    for _ in range(3):
        turn = _post_turn(throttled_client, conversation_a, csrf=csrf_a)
        assert turn.status_code == 201, turn.text
    exhausted = _post_turn(throttled_client, conversation_a, csrf=csrf_a)
    assert exhausted.status_code == 429, exhausted.text
    assert "retry-after" in {k.lower() for k in exhausted.headers}

    second_id = _register(throttled_client, "ask-b@example.com")
    csrf_b = _csrf(throttled_client)
    started_b = _start_conversation(
        throttled_client, _seed_ready_source(db_conn, second_id), csrf=csrf_b
    )
    assert started_b.status_code == 201, started_b.text
    turn_b = _post_turn(throttled_client, started_b.json()["id"], csrf=csrf_b)
    assert turn_b.status_code == 201, turn_b.text


def test_unauthenticated_ask_request_is_401_and_spends_no_budget(
    throttled_client: TestClient, db_conn: Connection
) -> None:
    # The user-keyed dependency resolves the caller before it records a hit, so an
    # anonymous request is a plain 401 and the next authenticated learner still has
    # the whole window: if the 401 spent anything, the third turn below would trip.
    anon = throttled_client.post(
        "/api/conversations",
        json={"source_id": str(uuid4()), "include_notes": False},
    )
    assert anon.status_code == 401, anon.text

    user_id = _register(throttled_client, "anon-budget@example.com")
    csrf = _csrf(throttled_client)
    started = _start_conversation(throttled_client, _seed_ready_source(db_conn, user_id), csrf=csrf)
    assert started.status_code == 201, started.text
    conversation_id = started.json()["id"]
    for _ in range(3):
        turn = _post_turn(throttled_client, conversation_id, csrf=csrf)
        assert turn.status_code == 201, turn.text
    exhausted = _post_turn(throttled_client, conversation_id, csrf=csrf)
    assert exhausted.status_code == 429, exhausted.text


def test_stream_turn_spends_its_budget_before_the_stream_starts(
    throttled_client: TestClient, db_conn: Connection
) -> None:
    # The streaming sibling carries the same per-user dependency as the JSON twin,
    # so each streamed turn spends one hit — from its own route-template bucket —
    # before the first SSE byte: three streams fill the window, the fourth is a
    # plain 429 with Retry-After, never a 200 SSE response, and the JSON turn
    # route's separate budget is untouched by the stream's spend.
    user_id = _register(throttled_client, "stream-rl@example.com")
    csrf = _csrf(throttled_client)
    started = _start_conversation(throttled_client, _seed_ready_source(db_conn, user_id), csrf=csrf)
    assert started.status_code == 201, started.text
    conversation_id = started.json()["id"]

    for _ in range(3):
        streamed = _stream_turn(throttled_client, conversation_id, csrf=csrf)
        assert streamed.status_code == 200, streamed.text
    denied_stream = _stream_turn(throttled_client, conversation_id, csrf=csrf)
    assert denied_stream.status_code == 429, denied_stream.text
    assert "retry-after" in {k.lower() for k in denied_stream.headers}
    assert "x-vercel-ai-ui-message-stream" not in {k.lower() for k in denied_stream.headers}

    turn = _post_turn(throttled_client, conversation_id, csrf=csrf)
    assert turn.status_code == 201, turn.text


def _tutor_card_request() -> Request:
    """A tutor-card request as FastAPI hands it over: concrete path plus matched route."""

    class _Route:
        path = "/api/conversations/{conversation_id}/tutor-card"

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/conversations/aaa/tutor-card",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
            "route": _Route(),
        }
    )


def test_tutor_card_budget_is_per_user_on_the_quiz_limiter() -> None:
    # The tutor-card accept rides ``rate_limit_quiz``, so user-id keying changes
    # its bucket too: one learner exhausting it leaves the next learner's budget
    # intact, keyed on the tutor-card template.
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        first = _user()
        for _ in range(3):
            assert rate_limit_quiz(first, _tutor_card_request()) is None
        with pytest.raises(HTTPException):
            rate_limit_quiz(first, _tutor_card_request())
        assert rate_limit_quiz(_user(), _tutor_card_request()) is None
    finally:
        set_rate_limiter(previous)


def _quiz_deck_request() -> Request:
    """A deck-POST request with its matched route template."""

    class _Route:
        path = "/api/sources/{source_id}/quiz/deck"

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/sources/aaa/quiz/deck",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
            "route": _Route(),
        }
    )


def _upload_request() -> Request:
    """An upload request (no interpolated id, so the concrete path is the bucket)."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/sources",
            "headers": [],
            "query_string": b"",
            "client": ("1.2.3.4", 12345),
        }
    )


def test_user_keyed_limiters_fail_closed_when_the_limiter_is_down() -> None:
    # A limiter that cannot record the hit never allows the request through: every
    # user-keyed dependency maps ``LimiterUnavailable`` to 503, never to allow.
    previous = get_rate_limiter()
    set_rate_limiter(_UnavailableLimiter())
    try:
        user = _user()
        for throttle, request in (
            (rate_limit_conversations, _conversations_request()),
            (rate_limit_quiz, _quiz_deck_request()),
            (rate_limit_upload, _upload_request()),
        ):
            with pytest.raises(HTTPException) as exc_info:
                throttle(user, request)
            assert exc_info.value.status_code == 503
    finally:
        set_rate_limiter(previous)


def test_user_keyed_route_returns_503_when_the_limiter_is_down(
    throttled_client: TestClient,
) -> None:
    # The same mapping end to end on a wired route: the caller is authenticated,
    # so the failure is the limiter's (503), not the session's (401).
    _register(throttled_client, "down@example.com")
    csrf = _csrf(throttled_client)
    previous = get_rate_limiter()
    set_rate_limiter(_UnavailableLimiter())
    try:
        resp = throttled_client.post(
            "/api/conversations",
            json={"source_id": str(uuid4()), "include_notes": False},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 503, resp.text
    finally:
        set_rate_limiter(previous)


def test_ingest_start_passes_the_user_keyed_limiter(ingestion_client: TestClient) -> None:
    # Ingest-start had no limiter of its own; it rides the same per-user upload
    # policy now. The first three attempts pass the gate and die on the unknown
    # source (404) — the limiter counts them regardless of outcome — so the fourth
    # is a 429 with Retry-After before the handler runs.
    _register(ingestion_client, "ingest-rl@example.com")
    csrf = _csrf(ingestion_client)
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        for _ in range(3):
            resp = ingestion_client.post(
                f"/api/sources/{uuid4()}/ingestion", headers={"X-CSRF-Token": csrf}
            )
            assert resp.status_code == 404, resp.text
        throttled = ingestion_client.post(
            f"/api/sources/{uuid4()}/ingestion", headers={"X-CSRF-Token": csrf}
        )
        assert throttled.status_code == 429, throttled.text
        assert "retry-after" in {k.lower() for k in throttled.headers}
    finally:
        set_rate_limiter(previous)


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
        ConversationClosed,
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

    @app.get("/conversation-closed")
    def _conversation_closed() -> None:
        raise ConversationClosed("This conversation is closed.")

    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/session-not-found").status_code == 404
    assert client.get("/invalid-target").status_code == 422

    gone = client.get("/target-gone")
    assert gone.status_code == 409
    assert gone.json() == {"detail": "The teaching target no longer exists."}

    assert client.get("/turn-conflict").status_code == 409
    closed = client.get("/conversation-closed")
    assert closed.status_code == 409
    assert closed.json() == {"detail": "This conversation is closed."}

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
