"""D2/D3 gate — teaching-session routers (integration, live test DB).

Exercises the owner-scoped teaching endpoints end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec's acceptance criteria
at the route level:

- ``POST /api/teaching-sessions`` — start on an owned ready source with a real
  section anchor → 201 with the target snapshot; missing/non-owned → identical
  404; not-ready → 409; unknown anchor → 422; malformed body → 422; no session →
  401; missing/invalid CSRF or untrusted Origin → 403; rate limit → 429
  (TEACH-01..04, 18, 23).
- ``GET /api/teaching-sessions/{id}`` — owner → 200 with the session and its
  turns ordered by ``turn_index`` with citation snapshots; missing/non-owner →
  404 (TEACH-05, 06, 20).
- ``GET /api/sources/{source_id}/teaching-sessions`` — owner → 200 newest-first
  summaries with turn counts; missing/non-owned → 404 (TEACH-21).

Corpus seeding mirrors ``test_web_questions``; sessions/turns are seeded through
the teaching repositories on the shared rolled-back ``db_conn``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import (
    CorpusSectionRecord,
    Evidence,
    ParsedSection,
    SectionChunk,
    Source,
    TeachingSession,
    TeachingTurn,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyTeachingSessionRepository,
    SqlAlchemyTeachingTurnRepository,
)
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db

_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_MODEL = "local-extractive"
_ANCHOR = "bio.xhtml"
_SECTION_PATH = ("Biology",)
_TITLE = "Biology"


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _start(
    client: TestClient,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.post("/api/teaching-sessions", json=body, headers=headers)


# --- Seeding (mirrors test_web_questions) --------------------------------------


def _persist_source(db_conn: Connection, user_id: str, *, status: str = "ready") -> UUID:
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
        status=status,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source).id


def _seed_section_corpus(db_conn: Connection, source_id: UUID) -> None:
    # One section whose chunk anchor equals the section anchor (as real corpus
    # building derives it), so the section resolves as a teaching target.
    chunk = SectionChunk(
        index=0, text=_PHOTO, section_path=_SECTION_PATH, anchor=_ANCHOR, page_span=None
    )
    section = CorpusSectionRecord(
        section=ParsedSection(
            position=0,
            title=_TITLE,
            depth=0,
            section_path=_SECTION_PATH,
            anchor=_ANCHOR,
            blocks=(),
        ),
        markdown="",
        chunks=(chunk,),
    )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(section,),
    )


def _seed_ready_source(client: TestClient, db_conn: Connection, email: str) -> tuple[str, str]:
    """Register ``email``, seed an owned ready source with one section, return (id, csrf)."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_section_corpus(db_conn, source_id)
    return str(source_id), csrf


def _seed_session(
    db_conn: Connection,
    source_id: UUID,
    *,
    created_at: datetime | None = None,
) -> TeachingSession:
    now = created_at or datetime.now(UTC)
    session = TeachingSession(
        id=uuid4(),
        source_id=source_id,
        target_anchor=_ANCHOR,
        target_section_path=_SECTION_PATH,
        target_title=_TITLE,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemyTeachingSessionRepository(db_conn).add(session)


def _seed_turn(
    db_conn: Connection,
    session: TeachingSession,
    *,
    turn_index: int,
    message: str,
    answer_status: str,
    answer_text: str,
    citations: tuple[Evidence, ...] = (),
) -> TeachingTurn:
    turn = TeachingTurn(
        id=uuid4(),
        session_id=session.id,
        turn_index=turn_index,
        message=message,
        answer_status=answer_status,
        answer_text=answer_text,
        model=_MODEL,
        evidence_count=len(citations),
        citations=citations,
        created_at=datetime.now(UTC),
    )
    return SqlAlchemyTeachingTurnRepository(db_conn).add(turn)


def _citation(source_id: UUID) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=source_id,
        section_path=_SECTION_PATH,
        anchor=_ANCHOR,
        page_span=None,
        snippet=_PHOTO,
        score=0.5,
    )


# --- 201 start (TEACH-01) ------------------------------------------------------


def test_start_session_returns_201_with_target_snapshot(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-01: an owned ready source + a real section anchor → 201 with the
    # session id/source_id, the target snapshot, and created_at.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start@example.com")

    resp = _start(auth_client, {"source_id": source_id, "target_anchor": _ANCHOR}, csrf=csrf)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"id", "source_id", "target", "created_at"}
    UUID(body["id"])
    assert body["source_id"] == source_id
    assert body["target"] == {
        "anchor": _ANCHOR,
        "section_path": list(_SECTION_PATH),
        "title": _TITLE,
    }
    assert body["created_at"]


# --- 404 ownership, identical bodies (TEACH-02) --------------------------------


def test_start_missing_and_non_owned_source_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-02: a missing source and another user's source both → 404 with the
    # exact same body — existence is never disclosed.
    owned_id, _ = _seed_ready_source(auth_client, db_conn, "owner@example.com")

    _register(auth_client, "intruder@example.com")  # become a different user
    csrf = _csrf(auth_client)

    non_owned = _start(auth_client, {"source_id": owned_id, "target_anchor": _ANCHOR}, csrf=csrf)
    missing = _start(
        auth_client, {"source_id": str(uuid4()), "target_anchor": _ANCHOR}, csrf=csrf
    )

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


# --- 409 readiness (TEACH-03) --------------------------------------------------


def test_start_not_ready_source_returns_409(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-03: an owned source whose status != "ready" → 409.
    user_id = _register(auth_client, "notready@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id, status="uploaded")

    resp = _start(auth_client, {"source_id": str(source_id), "target_anchor": _ANCHOR}, csrf=csrf)

    assert resp.status_code == 409, resp.text


# --- 422 unknown anchor / malformed body (TEACH-04) ----------------------------


def test_start_unknown_anchor_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-04: a target anchor that matches no section of the corpus → 422.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "unknown@example.com")

    resp = _start(
        auth_client, {"source_id": source_id, "target_anchor": "nope.xhtml"}, csrf=csrf
    )

    assert resp.status_code == 422, resp.text


def test_start_missing_source_id_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # A body without source_id is rejected with 422 before the service runs.
    _register(auth_client, "malformed@example.com")
    csrf = _csrf(auth_client)

    resp = _start(auth_client, {"target_anchor": _ANCHOR}, csrf=csrf)

    assert resp.status_code == 422, resp.text


# --- 401 / 403 auth + CSRF (TEACH-23) ------------------------------------------


def test_start_unauthenticated_returns_401(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-23: no session → 401.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "unauth@example.com")
    auth_client.cookies.clear()
    resp = _start(auth_client, {"source_id": source_id, "target_anchor": _ANCHOR}, csrf="x")
    assert resp.status_code == 401, resp.text


def test_start_missing_csrf_returns_403(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-23: a state-changing POST without the CSRF token → 403.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "nocsrf@example.com")
    resp = _start(auth_client, {"source_id": source_id, "target_anchor": _ANCHOR}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_start_untrusted_origin_returns_403(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-23: an untrusted Origin on a state-changing POST → 403.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "origin@example.com")
    resp = _start(
        auth_client,
        {"source_id": source_id, "target_anchor": _ANCHOR},
        csrf=csrf,
        origin="http://evil.example.com",
    )
    assert resp.status_code == 403, resp.text


# --- 200 read state (TEACH-05/06/20) -------------------------------------------


def test_read_session_returns_ordered_turns_with_citations(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-05/20: the owner GETs the session → 200 with the target snapshot and
    # all turns ordered by turn_index ascending, each with its citation snapshots.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "read@example.com")
    session = _seed_session(db_conn, UUID(source_id))
    _seed_turn(
        db_conn,
        session,
        turn_index=0,
        message="explain photosynthesis",
        answer_status="answered",
        answer_text=_PHOTO,
        citations=(_citation(UUID(source_id)),),
    )
    _seed_turn(
        db_conn,
        session,
        turn_index=1,
        message="unmatched",
        answer_status="not_found_in_source",
        answer_text="",
    )

    resp = auth_client.get(f"/api/teaching-sessions/{session.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(session.id)
    assert body["source_id"] == source_id
    assert body["target"] == {
        "anchor": _ANCHOR,
        "section_path": list(_SECTION_PATH),
        "title": _TITLE,
    }

    turns = body["turns"]
    assert [t["turn_index"] for t in turns] == [0, 1]

    answered = turns[0]
    assert set(answered) == {
        "turn_index",
        "message",
        "answer_status",
        "text",
        "citations",
        "evidence_count",
        "model",
        "created_at",
    }
    assert answered["answer_status"] == "answered"
    assert answered["text"] == _PHOTO
    assert answered["model"] == _MODEL
    assert answered["evidence_count"] == 1
    assert len(answered["citations"]) == 1
    citation = answered["citations"][0]
    assert citation["source_id"] == source_id
    assert citation["anchor"] == _ANCHOR
    assert citation["section_path"] == list(_SECTION_PATH)
    assert citation["snippet"] == _PHOTO
    assert citation["page_span"] is None

    not_found = turns[1]
    assert not_found["answer_status"] == "not_found_in_source"
    assert not_found["text"] == ""
    assert not_found["citations"] == []


def test_read_missing_and_non_owned_session_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-06: a missing session and another user's session both → 404, identical.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "owner-read@example.com")
    session = _seed_session(db_conn, UUID(source_id))

    _register(auth_client, "intruder-read@example.com")  # become a different user

    non_owned = auth_client.get(f"/api/teaching-sessions/{session.id}")
    missing = auth_client.get(f"/api/teaching-sessions/{uuid4()}")

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


# --- 200 list (TEACH-21) -------------------------------------------------------


def test_list_sessions_returns_newest_first_with_turn_count(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-21: the owner lists a source's sessions → 200 newest-first, each with
    # its target snapshot, created_at, and turn_count.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "list@example.com")
    base = datetime.now(UTC)
    older = _seed_session(db_conn, UUID(source_id), created_at=base)
    newer = _seed_session(db_conn, UUID(source_id), created_at=base + timedelta(minutes=1))
    _seed_turn(
        db_conn,
        newer,
        turn_index=0,
        message="hi",
        answer_status="answered",
        answer_text=_PHOTO,
    )

    resp = auth_client.get(f"/api/sources/{source_id}/teaching-sessions")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [s["id"] for s in body] == [str(newer.id), str(older.id)]
    assert set(body[0]) == {"id", "target", "created_at", "turn_count"}
    assert body[0]["turn_count"] == 1
    assert body[1]["turn_count"] == 0
    assert body[0]["target"] == {
        "anchor": _ANCHOR,
        "section_path": list(_SECTION_PATH),
        "title": _TITLE,
    }


def test_list_missing_and_non_owned_source_return_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-21 (TEACH-02 semantics): missing and non-owned sources both → 404.
    owned_id, _ = _seed_ready_source(auth_client, db_conn, "owner-list@example.com")

    _register(auth_client, "intruder-list@example.com")  # become a different user

    non_owned = auth_client.get(f"/api/sources/{owned_id}/teaching-sessions")
    missing = auth_client.get(f"/api/sources/{uuid4()}/teaching-sessions")

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text


# --- 429 rate limit (TEACH-18) -------------------------------------------------


@pytest.fixture
def throttled_teaching_client(  # noqa: ANN201
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
):
    """Like ``auth_client`` but with a deliberately tight teaching limiter.

    Mirrors ``throttled_questions_client``: 3 attempts per long window so the 4th
    ``POST /api/teaching-sessions`` trips the ``rate_limit_teaching`` 429 branch
    deterministically. The per-IP+route key means the register/csrf setup calls
    consume separate buckets and never eat the teaching budget.
    """
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous = get_rate_limiter()
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


def test_start_rate_limit_returns_429_with_retry_after(
    throttled_teaching_client: TestClient, db_conn: Connection
) -> None:
    # TEACH-18: once the window is exceeded, the endpoint returns 429 + Retry-After.
    source_id, csrf = _seed_ready_source(
        throttled_teaching_client, db_conn, "rl@example.com"
    )
    # First 3 starts pass the limiter (201).
    for _ in range(3):
        resp = _start(
            throttled_teaching_client,
            {"source_id": source_id, "target_anchor": _ANCHOR},
            csrf=csrf,
        )
        assert resp.status_code == 201, resp.text
    # The 4th is throttled before reaching the service.
    throttled = _start(
        throttled_teaching_client,
        {"source_id": source_id, "target_anchor": _ANCHOR},
        csrf=csrf,
    )
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}
