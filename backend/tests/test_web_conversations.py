"""Phase C gate — the unified conversations router (integration, live test DB).

Exercises ``/api/conversations`` end-to-end through FastAPI's ``TestClient``
against a real Postgres, asserting the spec's acceptance criteria at the route
level:

- ``POST   /api/conversations`` — start on an owned ready source, scoped or whole
  book → 201 with the stored scope and notes choice; an omitted ``include_notes``
  → 422 (the notes choice is explicit, ADR-0029); an unresolvable scope anchor →
  422; missing/non-owned source → identical 404; not ready → 409 (CONV-15).
- ``GET    /api/conversations[?source_id=]`` — the caller's conversations across
  every owned source, newest activity first, with ``source_title`` and
  ``turn_count`` (CONV-16).
- ``GET    /api/conversations/{id}`` — the conversation with its ordered turns,
  each carrying its ``mode`` and citation snapshots; missing and non-owned are
  indistinguishable (CONV-17, I-CM-6).
- ``PATCH  /api/conversations/{id}`` — rename with the 1..200 trimmed bound
  (CONV-18).
- ``DELETE /api/conversations/{id}`` — 204, and a second delete → 404 (CONV-19).
- ``POST   /api/conversations/{id}/turns`` — a turn in either mode → 201 with its
  citations; unknown mode / over-limit message → 422; a teach turn without a
  resolvable target → 409; a taken turn index → 409; a failed generation → 502
  with nothing persisted (CONV-20).
- ``POST   /api/conversations/{id}/turns/stream`` — the full UI Message Stream
  frame sequence, ``not_found_in_scope`` on the status frame, and a mid-stream
  failure rendered as the error frame (CONV-21).

Seeding mirrors ``test_web_teaching``: sources and corpus through the real
repositories on the shared rolled-back ``db_conn``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.application.conversations import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.domain.entities import (
    ANSWERED,
    MODE_ANSWER,
    MODE_TEACH,
    NOT_FOUND_IN_SCOPE,
    NOT_FOUND_IN_SOURCE,
    AnswerTextDelta,
    Conversation,
    ConversationTurn,
    CorpusSectionRecord,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    ParsedSection,
    SectionChunk,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationTurnRepository,
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db

_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_CELLS = "cells divide by mitosis to produce two identical daughter cells"
_MODEL = "local-extractive"
_ANCHOR = "bio.xhtml"
_SECTION_PATH = ("Biology",)
_TITLE = "Biology"
_OTHER_ANCHOR = "cells.xhtml"
_OTHER_SECTION_PATH = ("Biology", "Cells")
_OTHER_TITLE = "Cells"
_BOOK_TITLE = "A Book"


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _headers(csrf: str | None, origin: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return headers


def _start(client: TestClient, body: dict, *, csrf: str | None, origin: str | None = None):
    return client.post("/api/conversations", json=body, headers=_headers(csrf, origin))


def _rename(
    client: TestClient,
    conversation_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.patch(
        f"/api/conversations/{conversation_id}", json=body, headers=_headers(csrf, origin)
    )


def _delete(
    client: TestClient, conversation_id: object, *, csrf: str | None, origin: str | None = None
):
    return client.delete(f"/api/conversations/{conversation_id}", headers=_headers(csrf, origin))


# --- Seeding -------------------------------------------------------------------


def _persist_source(db_conn: Connection, user_id: str, *, status: str = "ready") -> UUID:
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=UUID(user_id),
        title=_BOOK_TITLE,
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


def _section(
    *, position: int, title: str, depth: int, section_path: tuple[str, ...], anchor: str, text: str
) -> CorpusSectionRecord:
    chunk = SectionChunk(
        index=0, text=text, section_path=section_path, anchor=anchor, page_span=None
    )
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=depth,
            section_path=section_path,
            anchor=anchor,
            blocks=(),
        ),
        markdown="",
        chunks=(chunk,),
    )


def _seed_corpus(db_conn: Connection, source_id: UUID) -> None:
    """Two sections — a parent and its child — so scope subtrees are exercisable."""
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title=_BOOK_TITLE,
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section(
                position=0,
                title=_TITLE,
                depth=0,
                section_path=_SECTION_PATH,
                anchor=_ANCHOR,
                text=_PHOTO,
            ),
            _section(
                position=1,
                title=_OTHER_TITLE,
                depth=1,
                section_path=_OTHER_SECTION_PATH,
                anchor=_OTHER_ANCHOR,
                text=_CELLS,
            ),
        ),
    )


def _seed_ready_source(client: TestClient, db_conn: Connection, email: str) -> tuple[str, str]:
    """Register ``email``, seed an owned ready source with a corpus, return (id, csrf)."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id)
    return str(source_id), csrf


def _seed_conversation(
    db_conn: Connection,
    source_id: UUID,
    *,
    title: str = _TITLE,
    scope: tuple[str, ...] = (_ANCHOR,),
    include_notes: bool = False,
    target_anchor: str | None = _ANCHOR,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Conversation:
    now = created_at or datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        source_id=source_id,
        title=title,
        scope_anchors=scope,
        include_notes=include_notes,
        target_anchor=target_anchor,
        target_section_path=_SECTION_PATH if target_anchor is not None else None,
        target_title=_TITLE if target_anchor is not None else None,
        created_at=now,
        updated_at=updated_at or now,
    )
    return SqlAlchemyConversationRepository(db_conn).add(conversation)


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


def _seed_turn(
    db_conn: Connection,
    conversation: Conversation,
    *,
    turn_index: int,
    message: str,
    mode: str,
    answer_status: str,
    answer_text: str,
    citations: tuple[Evidence, ...] = (),
) -> ConversationTurn:
    turn = ConversationTurn(
        id=uuid4(),
        conversation_id=conversation.id,
        turn_index=turn_index,
        message=message,
        mode=mode,
        answer_status=answer_status,
        answer_text=answer_text,
        model=_MODEL,
        evidence_count=len(citations),
        citations=citations,
        created_at=datetime.now(UTC),
    )
    return SqlAlchemyConversationTurnRepository(db_conn).add(turn)


_CONVERSATION_FIELDS = {
    "id",
    "source_id",
    "title",
    "scope_anchors",
    "include_notes",
    "created_at",
    "updated_at",
}


# --- POST /api/conversations (CONV-15) -----------------------------------------


def test_start_scoped_conversation_returns_201_with_scope_and_notes_choice(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-15: an owned ready source + a real section anchor + an explicit notes
    # choice → 201 carrying the scope exactly as given and that choice, titled after
    # the scoped section when no title was supplied.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-scoped@example.com")

    resp = _start(
        auth_client,
        {"source_id": source_id, "scope_anchors": [_ANCHOR], "include_notes": True},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == _CONVERSATION_FIELDS
    UUID(body["id"])
    assert body["source_id"] == source_id
    assert body["scope_anchors"] == [_ANCHOR]
    assert body["include_notes"] is True
    assert body["title"] == _TITLE
    assert body["created_at"] and body["updated_at"]


def test_start_whole_book_conversation_defaults_title_to_the_book(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-15: an omitted scope is the whole book — an empty scope list, titled
    # after the source.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-whole@example.com")

    resp = _start(auth_client, {"source_id": source_id, "include_notes": False}, csrf=csrf)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["scope_anchors"] == []
    assert body["include_notes"] is False
    assert body["title"] == _BOOK_TITLE


def test_start_uses_the_given_title_trimmed(auth_client: TestClient, db_conn: Connection) -> None:
    # CONV-15: a supplied title wins over the default and is stored trimmed.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-title@example.com")

    resp = _start(
        auth_client,
        {"source_id": source_id, "include_notes": False, "title": "  Photosynthesis  "},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == "Photosynthesis"


def test_start_without_include_notes_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-15 / ADR-0029: the notes choice is explicit per conversation, so a body
    # that omits it is rejected rather than silently defaulted — and nothing is
    # created.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-nonotes@example.com")

    resp = _start(auth_client, {"source_id": source_id, "scope_anchors": [_ANCHOR]}, csrf=csrf)

    assert resp.status_code == 422, resp.text
    listed = auth_client.get("/api/conversations")
    assert listed.json() == []


def test_start_unresolvable_scope_anchor_returns_422_and_creates_nothing(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-15 / AD-201: an anchor that addresses nothing in the corpus fails the
    # whole start with 422 — a conversation that silently dropped part of its scope
    # would promise a reader something it does not enforce.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-badscope@example.com")

    resp = _start(
        auth_client,
        {"source_id": source_id, "scope_anchors": [_ANCHOR, "nope.xhtml"], "include_notes": False},
        csrf=csrf,
    )

    assert resp.status_code == 422, resp.text
    listed = auth_client.get("/api/conversations")
    assert listed.json() == []


def test_start_over_long_scope_list_and_anchor_return_422_and_create_nothing(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-15: the scope is the one field whose size the client picks, and it is
    # re-expanded against the corpus on every turn for the conversation's life — so
    # both its length and each anchor's length are bounded by the server's settings,
    # like ``message`` and ``title`` are, before the corpus is ever read.
    from app.core.config import get_settings

    settings = get_settings()
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-scopecap@example.com")

    too_many = _start(
        auth_client,
        {
            "source_id": source_id,
            "scope_anchors": [_ANCHOR] * (settings.conversation_scope_max_anchors + 1),
            "include_notes": False,
        },
        csrf=csrf,
    )
    too_long = _start(
        auth_client,
        {
            "source_id": source_id,
            "scope_anchors": ["a" * (settings.conversation_scope_anchor_max_chars + 1)],
            "include_notes": False,
        },
        csrf=csrf,
    )

    assert too_many.status_code == 422, too_many.text
    assert too_long.status_code == 422, too_long.text
    assert auth_client.get("/api/conversations").json() == []


def test_start_stores_a_repeated_scope_anchor_once(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-15: a repeated anchor is collapsed before it is stored, so the scope a
    # client reads back is the set of sections it actually named.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-scopedupe@example.com")

    resp = _start(
        auth_client,
        {"source_id": source_id, "scope_anchors": [_ANCHOR, _ANCHOR], "include_notes": False},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["scope_anchors"] == [_ANCHOR]


def test_start_missing_and_non_owned_source_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # Edge case: an unowned source is 404 (not 422) and indistinguishable from a
    # source that never existed.
    owned_id, _ = _seed_ready_source(auth_client, db_conn, "start-owner@example.com")

    _register(auth_client, "start-intruder@example.com")  # become a different user
    csrf = _csrf(auth_client)

    non_owned = _start(auth_client, {"source_id": owned_id, "include_notes": False}, csrf=csrf)
    missing = _start(auth_client, {"source_id": str(uuid4()), "include_notes": False}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_start_not_ready_source_returns_409(auth_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(auth_client, "start-notready@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id, status="uploaded")

    resp = _start(auth_client, {"source_id": str(source_id), "include_notes": False}, csrf=csrf)

    assert resp.status_code == 409, resp.text


def test_start_over_long_title_returns_422(auth_client: TestClient, db_conn: Connection) -> None:
    from app.application.conversations import TITLE_MAX_CHARS

    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-longtitle@example.com")

    resp = _start(
        auth_client,
        {"source_id": source_id, "include_notes": False, "title": "t" * (TITLE_MAX_CHARS + 1)},
        csrf=csrf,
    )

    assert resp.status_code == 422, resp.text


def test_start_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "start-401@example.com")
    auth_client.cookies.clear()
    resp = _start(auth_client, {"source_id": source_id, "include_notes": False}, csrf="x")
    assert resp.status_code == 401, resp.text


def test_start_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "start-403@example.com")
    resp = _start(auth_client, {"source_id": source_id, "include_notes": False}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_start_untrusted_origin_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "start-origin@example.com")
    resp = _start(
        auth_client,
        {"source_id": source_id, "include_notes": False},
        csrf=csrf,
        origin="http://evil.example.com",
    )
    assert resp.status_code == 403, resp.text


# --- GET /api/conversations (CONV-16) ------------------------------------------


def test_list_returns_newest_activity_first_with_source_title_and_turn_count(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-16: the global list spans the caller's sources, orders by updated_at
    # descending, and names the book each conversation is about.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "list@example.com")
    base = datetime.now(UTC)
    stale = _seed_conversation(
        db_conn, UUID(source_id), title="Older", created_at=base, updated_at=base
    )
    active = _seed_conversation(
        db_conn,
        UUID(source_id),
        title="Newer",
        created_at=base,
        updated_at=base + timedelta(minutes=5),
    )
    _seed_turn(
        db_conn,
        active,
        turn_index=0,
        message="explain photosynthesis",
        mode=MODE_ANSWER,
        answer_status=ANSWERED,
        answer_text=_PHOTO,
    )

    resp = auth_client.get("/api/conversations")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [row["id"] for row in body] == [str(active.id), str(stale.id)]
    assert set(body[0]) == {
        "id",
        "source_id",
        "source_title",
        "title",
        "scope_anchors",
        "include_notes",
        "turn_count",
        "created_at",
        "updated_at",
    }
    assert body[0]["source_title"] == _BOOK_TITLE
    assert body[0]["title"] == "Newer"
    assert body[0]["scope_anchors"] == [_ANCHOR]
    assert body[0]["turn_count"] == 1
    assert body[1]["turn_count"] == 0


def test_list_filters_by_source_and_excludes_other_users(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-16: ``source_id`` narrows the list; another user's conversations are
    # unreachable, and narrowing by a source the caller does not own discloses
    # nothing (an empty list, not a 404).
    owned_id, _ = _seed_ready_source(auth_client, db_conn, "list-owner@example.com")
    mine = _seed_conversation(db_conn, UUID(owned_id), title="Mine")

    intruder_id = _register(auth_client, "list-intruder@example.com")
    other_source = _persist_source(db_conn, intruder_id)
    _seed_conversation(db_conn, other_source, title="Theirs")

    theirs = auth_client.get("/api/conversations")
    assert [row["title"] for row in theirs.json()] == ["Theirs"]

    filtered = auth_client.get("/api/conversations", params={"source_id": owned_id})
    assert filtered.status_code == 200, filtered.text
    assert filtered.json() == []

    # Back as the owner, the filter returns exactly that source's conversations.
    login = auth_client.post(
        "/api/auth/login",
        json={"email": "list-owner@example.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 200, login.text
    owned = auth_client.get("/api/conversations", params={"source_id": owned_id})
    assert [row["id"] for row in owned.json()] == [str(mine.id)]


def test_list_without_pagination_returns_a_bounded_default_page(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-16: a reader with more history than one page gets one page — the newest
    # of it — rather than everything they have ever asked.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "list-default@example.com")
    base = datetime.now(UTC)
    seeded = [
        _seed_conversation(
            db_conn,
            UUID(source_id),
            title=f"Conversation {i}",
            updated_at=base + timedelta(minutes=i),
        )
        for i in range(DEFAULT_PAGE_LIMIT + 3)
    ]

    resp = auth_client.get("/api/conversations")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == DEFAULT_PAGE_LIMIT
    newest_first = [str(c.id) for c in reversed(seeded)]
    assert [row["id"] for row in body] == newest_first[:DEFAULT_PAGE_LIMIT]


def test_list_limit_and_offset_return_that_window_of_the_order(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-16: the page a caller names is the window it gets, taken from the same
    # newest-activity order the unparameterized read uses.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "list-window@example.com")
    base = datetime.now(UTC)
    seeded = [
        _seed_conversation(
            db_conn,
            UUID(source_id),
            title=f"Conversation {i}",
            updated_at=base + timedelta(minutes=i),
        )
        for i in range(5)
    ]
    newest_first = [str(c.id) for c in reversed(seeded)]

    window = auth_client.get("/api/conversations", params={"limit": 2, "offset": 1})
    past_the_end = auth_client.get("/api/conversations", params={"limit": 2, "offset": 5})

    assert window.status_code == 200, window.text
    assert [row["id"] for row in window.json()] == newest_first[1:3]
    # Walking off the end is an empty page, not an error: a caller paging to the end
    # of its history stops on an empty answer.
    assert past_the_end.status_code == 200, past_the_end.text
    assert past_the_end.json() == []


def test_list_paged_to_the_end_returns_every_conversation_exactly_once(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-16: the dock walks this list a page at a time. Conversations touched in
    # the same instant share an ``updated_at``, which alone cannot order them, so a
    # walk over a tie-heavy list is where a reader would silently lose a thread —
    # or be shown one twice — between two pages.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "list-walk@example.com")
    tied_at = datetime.now(UTC)
    seeded = [
        _seed_conversation(db_conn, UUID(source_id), title=f"Conversation {i}", updated_at=tied_at)
        for i in range(7)
    ]
    # The fixture is only a sensor if the rows really are tied.
    assert len({c.updated_at for c in seeded}) == 1

    walked: list[str] = []
    offset = 0
    while True:
        page = auth_client.get("/api/conversations", params={"limit": 3, "offset": offset})
        assert page.status_code == 200, page.text
        rows = page.json()
        if not rows:
            break
        walked.extend(row["id"] for row in rows)
        offset += 3

    assert len(walked) == len(seeded), "a page either repeated a conversation or dropped one"
    assert set(walked) == {str(c.id) for c in seeded}
    # And the walk is the order itself: asking for the whole list in one page spells
    # out the same sequence the windows did, which a partial order would not.
    whole = auth_client.get("/api/conversations", params={"limit": MAX_PAGE_LIMIT})
    assert [row["id"] for row in whole.json()] == walked


def test_list_rejects_a_page_outside_its_bounds(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-16: the bounds are the endpoint's own — a caller cannot ask for zero rows,
    # for more than the cap, or for a negative window start.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "list-bounds@example.com")
    _seed_conversation(db_conn, UUID(source_id))

    assert auth_client.get("/api/conversations", params={"limit": 0}).status_code == 422
    assert (
        auth_client.get("/api/conversations", params={"limit": MAX_PAGE_LIMIT + 1}).status_code
        == 422
    )
    assert auth_client.get("/api/conversations", params={"offset": -1}).status_code == 422
    # The cap itself is allowed — the rejection is of values beyond it.
    assert (
        auth_client.get("/api/conversations", params={"limit": MAX_PAGE_LIMIT}).status_code == 200
    )


def test_list_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    _seed_ready_source(auth_client, db_conn, "list-401@example.com")
    auth_client.cookies.clear()
    assert auth_client.get("/api/conversations").status_code == 401


# --- GET /api/conversations/{id} (CONV-17) -------------------------------------


def test_read_returns_conversation_with_ordered_turns_and_modes(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-17: the detail carries the conversation plus its turns in turn_index
    # order, each naming its mode and carrying its citation snapshots.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "read@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    _seed_turn(
        db_conn,
        conversation,
        turn_index=0,
        message="explain photosynthesis",
        mode=MODE_TEACH,
        answer_status=ANSWERED,
        answer_text=_PHOTO,
        citations=(_citation(UUID(source_id)),),
    )
    _seed_turn(
        db_conn,
        conversation,
        turn_index=1,
        message="unmatched",
        mode=MODE_ANSWER,
        answer_status=NOT_FOUND_IN_SCOPE,
        answer_text="",
    )

    resp = auth_client.get(f"/api/conversations/{conversation.id}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _CONVERSATION_FIELDS | {"turns"}
    assert body["id"] == str(conversation.id)
    assert body["scope_anchors"] == [_ANCHOR]

    turns = body["turns"]
    assert [t["turn_index"] for t in turns] == [0, 1]
    assert set(turns[0]) == {
        "turn_index",
        "message",
        "mode",
        "answer_status",
        "text",
        "citations",
        "evidence_count",
        "model",
        "created_at",
    }
    assert turns[0]["mode"] == MODE_TEACH
    assert turns[0]["answer_status"] == ANSWERED
    assert turns[0]["text"] == _PHOTO
    assert turns[0]["model"] == _MODEL
    assert turns[0]["evidence_count"] == 1
    citation = turns[0]["citations"][0]
    assert citation["anchor"] == _ANCHOR
    assert citation["source_id"] == source_id
    assert citation["snippet"] == _PHOTO

    assert turns[1]["mode"] == MODE_ANSWER
    assert turns[1]["answer_status"] == NOT_FOUND_IN_SCOPE
    assert turns[1]["text"] == ""
    assert turns[1]["citations"] == []


def test_read_missing_and_non_owned_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # I-CM-6: an ownership failure is indistinguishable from absence — same status
    # AND same body.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "read-owner@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    _register(auth_client, "read-intruder@example.com")  # become a different user

    non_owned = auth_client.get(f"/api/conversations/{conversation.id}")
    missing = auth_client.get(f"/api/conversations/{uuid4()}")

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_read_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "read-401@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    auth_client.cookies.clear()
    assert auth_client.get(f"/api/conversations/{conversation.id}").status_code == 401


# --- PATCH /api/conversations/{id} (CONV-18) -----------------------------------


def test_rename_returns_200_with_new_title_and_bumped_activity(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-18: the rename is stored trimmed and bumps updated_at, so the renamed
    # conversation rises in the list.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "rename@example.com")
    old = datetime.now(UTC) - timedelta(days=1)
    conversation = _seed_conversation(
        db_conn, UUID(source_id), title="Before", created_at=old, updated_at=old
    )

    resp = _rename(auth_client, conversation.id, {"title": "  After  "}, csrf=csrf)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _CONVERSATION_FIELDS
    assert body["title"] == "After"
    assert body["updated_at"] > body["created_at"]

    read = auth_client.get(f"/api/conversations/{conversation.id}")
    assert read.json()["title"] == "After"


def test_rename_blank_and_over_long_titles_return_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-18: the 1..200 trimmed bound — a whitespace-only title and an oversize
    # one are both rejected, with the stored title untouched.
    from app.application.conversations import TITLE_MAX_CHARS

    source_id, csrf = _seed_ready_source(auth_client, db_conn, "rename-422@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id), title="Kept")

    blank = _rename(auth_client, conversation.id, {"title": "   "}, csrf=csrf)
    empty = _rename(auth_client, conversation.id, {"title": ""}, csrf=csrf)
    oversize = _rename(
        auth_client, conversation.id, {"title": "t" * (TITLE_MAX_CHARS + 1)}, csrf=csrf
    )

    assert blank.status_code == 422, blank.text
    assert empty.status_code == 422, empty.text
    assert oversize.status_code == 422, oversize.text
    assert auth_client.get(f"/api/conversations/{conversation.id}").json()["title"] == "Kept"


def test_rename_accepts_a_title_at_the_bound(auth_client: TestClient, db_conn: Connection) -> None:
    # The bound is inclusive: exactly TITLE_MAX_CHARS is accepted.
    from app.application.conversations import TITLE_MAX_CHARS

    source_id, csrf = _seed_ready_source(auth_client, db_conn, "rename-bound@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    resp = _rename(auth_client, conversation.id, {"title": "t" * TITLE_MAX_CHARS}, csrf=csrf)

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "t" * TITLE_MAX_CHARS


def test_rename_missing_and_non_owned_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "rename-owner@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    _register(auth_client, "rename-intruder@example.com")
    csrf = _csrf(auth_client)

    non_owned = _rename(auth_client, conversation.id, {"title": "Mine now"}, csrf=csrf)
    missing = _rename(auth_client, uuid4(), {"title": "Mine now"}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_rename_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "rename-403@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    resp = _rename(auth_client, conversation.id, {"title": "No token"}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_rename_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "rename-401@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    auth_client.cookies.clear()
    resp = _rename(auth_client, conversation.id, {"title": "Nope"}, csrf="x")
    assert resp.status_code == 401, resp.text


# --- DELETE /api/conversations/{id} (CONV-19) ----------------------------------


def test_delete_returns_204_and_removes_the_conversation_with_its_turns(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-19: the conversation and its turns are gone; a second delete reports
    # absence rather than leaving orphans behind.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "delete@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    _seed_turn(
        db_conn,
        conversation,
        turn_index=0,
        message="explain",
        mode=MODE_TEACH,
        answer_status=ANSWERED,
        answer_text=_PHOTO,
        citations=(_citation(UUID(source_id)),),
    )

    resp = _delete(auth_client, conversation.id, csrf=csrf)

    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    assert auth_client.get(f"/api/conversations/{conversation.id}").status_code == 404
    assert auth_client.get("/api/conversations").json() == []

    second = _delete(auth_client, conversation.id, csrf=csrf)
    assert second.status_code == 404, second.text


def test_delete_missing_and_non_owned_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "delete-owner@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    _register(auth_client, "delete-intruder@example.com")
    csrf = _csrf(auth_client)

    non_owned = _delete(auth_client, conversation.id, csrf=csrf)
    missing = _delete(auth_client, uuid4(), csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_delete_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "delete-403@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    resp = _delete(auth_client, conversation.id, csrf=None)
    assert resp.status_code == 403, resp.text


def test_delete_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "delete-401@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    auth_client.cookies.clear()
    assert _delete(auth_client, conversation.id, csrf="x").status_code == 401


# --- POST /api/conversations/{id}/turns (CONV-20) ------------------------------


def _post_turn(
    client: TestClient,
    conversation_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.post(
        f"/api/conversations/{conversation_id}/turns", json=body, headers=_headers(csrf, origin)
    )


def _turn_stream(
    client: TestClient,
    conversation_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.post(
        f"/api/conversations/{conversation_id}/turns/stream",
        json=body,
        headers=_headers(csrf, origin),
    )


def _embed_all(db_conn: Connection, source_id: UUID) -> None:
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source_id)
    vectors = adapter.embed_documents([c.text for c in chunks])
    index.set_embeddings(
        list(zip((c.id for c in chunks), vectors, strict=True)), model=adapter.model
    )


_TURN_FIELDS = {
    "turn_index",
    "message",
    "mode",
    "answer_status",
    "text",
    "citations",
    "evidence_count",
    "model",
    "created_at",
}


def test_post_answer_turn_returns_201_with_mode_and_citations(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20: an answer-mode turn in a scoped conversation → 201 carrying the mode
    # it ran in, the grounded citations, and the adapter's model identity.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-answer@example.com")
    _embed_all(db_conn, UUID(source_id))
    conversation = _seed_conversation(db_conn, UUID(source_id))

    resp = _post_turn(
        auth_client,
        conversation.id,
        {"message": "photosynthesis sunlight energy", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == _TURN_FIELDS
    assert body["turn_index"] == 0
    assert body["mode"] == MODE_ANSWER
    assert body["answer_status"] == ANSWERED
    # The scope is the section and its subtree, so the answer is drawn from it.
    assert _PHOTO in body["text"]
    assert body["model"] == _MODEL
    assert body["evidence_count"] >= 1
    assert {c["anchor"] for c in body["citations"]} <= {_ANCHOR, _OTHER_ANCHOR}
    assert body["citations"][0]["source_id"] == source_id

    # Persisted: the conversation reads back with that turn.
    read = auth_client.get(f"/api/conversations/{conversation.id}")
    assert [t["turn_index"] for t in read.json()["turns"]] == [0]
    assert read.json()["turns"][0]["mode"] == MODE_ANSWER


def test_post_teach_turn_returns_201_in_teach_mode(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20: the same conversation answers in teach mode when the turn asks for
    # it — the mode is a per-turn choice, not a property of the conversation.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-teach@example.com")
    _embed_all(db_conn, UUID(source_id))
    conversation = _seed_conversation(db_conn, UUID(source_id))

    resp = _post_turn(
        auth_client,
        conversation.id,
        {"message": "photosynthesis sunlight energy", "mode": MODE_TEACH},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == MODE_TEACH
    assert body["answer_status"] == ANSWERED
    assert body["citations"]


def test_post_turn_in_scoped_conversation_reports_not_found_in_scope(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20 / I-CM-3: when a scoped conversation finds nothing, the verdict names
    # the reader's own selection rather than the book.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-scope-nf@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))  # corpus NOT embedded

    resp = _post_turn(
        auth_client,
        conversation.id,
        {"message": "zzzqqq nonsensical unmatchable token", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["answer_status"] == NOT_FOUND_IN_SCOPE
    assert body["text"] == ""
    assert body["citations"] == []
    assert body["evidence_count"] == 0


def test_scoped_turn_never_cites_evidence_outside_its_scope(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # I-CM-3 end-to-end: scope is a promise the database keeps. The same question is
    # asked twice over the same embedded corpus — the whole-book conversation cites
    # the sibling section that answers it, and the scoped one never can, because the
    # anchors reach retrieval on every turn. Drop the scoping and the second half of
    # this test starts citing the first half's evidence.
    genetics = "mendel crossed pea plants and found dominant inherited traits"
    user_id = _register(auth_client, "scope-promise@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title=_BOOK_TITLE,
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section(
                position=0,
                title=_TITLE,
                depth=0,
                section_path=_SECTION_PATH,
                anchor=_ANCHOR,
                text=_PHOTO,
            ),
            _section(
                position=1,
                title="Genetics",
                depth=0,
                section_path=("Genetics",),
                anchor="gen.xhtml",
                text=genetics,
            ),
        ),
    )
    _embed_all(db_conn, source_id)

    scoped = _start(
        auth_client,
        {"source_id": str(source_id), "scope_anchors": [_ANCHOR], "include_notes": False},
        csrf=csrf,
    )
    whole_book = _start(
        auth_client,
        {"source_id": str(source_id), "scope_anchors": [], "include_notes": False},
        csrf=csrf,
    )
    assert scoped.status_code == 201, scoped.text
    assert whole_book.status_code == 201, whole_book.text

    question = "mendel pea plants dominant inherited traits"
    in_scope = _post_turn(
        auth_client, scoped.json()["id"], {"message": question, "mode": MODE_ANSWER}, csrf=csrf
    )
    over_book = _post_turn(
        auth_client, whole_book.json()["id"], {"message": question, "mode": MODE_ANSWER}, csrf=csrf
    )

    assert over_book.status_code == 201, over_book.text
    assert "gen.xhtml" in {c["anchor"] for c in over_book.json()["citations"]}, (
        "the evidence is reachable when nothing is scoped away"
    )

    assert in_scope.status_code == 201, in_scope.text
    assert {c["anchor"] for c in in_scope.json()["citations"]} <= {_ANCHOR}, (
        "a scoped turn never cites outside its scope"
    )


def test_post_turn_in_whole_book_conversation_reports_not_found_in_source(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20 / I-CM-3: a whole-book conversation keeps the original verdict —
    # nothing was scoped away, so the book itself came up short.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-book-nf@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id), scope=(), target_anchor=None)

    resp = _post_turn(
        auth_client,
        conversation.id,
        {"message": "zzzqqq nonsensical unmatchable token", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["answer_status"] == NOT_FOUND_IN_SOURCE


def test_post_turn_unknown_and_missing_mode_return_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20: only the two named modes are accepted, and the mode is required —
    # a turn never runs in a mode the caller did not ask for.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-mode@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    unknown = _post_turn(
        auth_client, conversation.id, {"message": "explain", "mode": "summarize"}, csrf=csrf
    )
    absent = _post_turn(auth_client, conversation.id, {"message": "explain"}, csrf=csrf)

    assert unknown.status_code == 422, unknown.text
    assert absent.status_code == 422, absent.text
    assert auth_client.get(f"/api/conversations/{conversation.id}").json()["turns"] == []


def test_post_turn_blank_and_over_long_messages_return_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20: the message bound is the conversation setting, applied to the
    # trimmed value.
    from app.core.config import get_settings

    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-msg@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    over = "a" * (get_settings().conversation_message_max_chars + 1)

    blank = _post_turn(
        auth_client, conversation.id, {"message": "   ", "mode": MODE_ANSWER}, csrf=csrf
    )
    oversize = _post_turn(
        auth_client, conversation.id, {"message": over, "mode": MODE_ANSWER}, csrf=csrf
    )

    assert blank.status_code == 422, blank.text
    assert oversize.status_code == 422, oversize.text


def test_teach_turn_in_whole_book_conversation_returns_409(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # I-CM-7 / AD-201: a whole-book conversation teaches nothing in particular, so a
    # teach turn is a state conflict — a valid request against the wrong state.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "teach-book@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id), scope=(), target_anchor=None)

    resp = _post_turn(
        auth_client, conversation.id, {"message": "teach me", "mode": MODE_TEACH}, csrf=csrf
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]
    assert auth_client.get(f"/api/conversations/{conversation.id}").json()["turns"] == []


def test_teach_turn_with_vanished_target_returns_409(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # I-CM-7: a re-ingest that dropped the taught section → 409, nothing persisted.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "teach-gone@example.com")
    conversation = _seed_conversation(
        db_conn, UUID(source_id), scope=("vanished.xhtml",), target_anchor="vanished.xhtml"
    )

    resp = _post_turn(
        auth_client, conversation.id, {"message": "teach me", "mode": MODE_TEACH}, csrf=csrf
    )

    assert resp.status_code == 409, resp.text


def test_answer_turn_survives_a_vanished_scope_anchor(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # Edge case: an answer turn proceeds against the surviving anchors instead of
    # widening to the whole book — the vanished anchor simply matches nothing.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "answer-gone@example.com")
    _embed_all(db_conn, UUID(source_id))
    conversation = _seed_conversation(
        db_conn, UUID(source_id), scope=("vanished.xhtml",), target_anchor="vanished.xhtml"
    )

    resp = _post_turn(
        auth_client,
        conversation.id,
        {"message": "photosynthesis sunlight energy", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["answer_status"] == NOT_FOUND_IN_SCOPE
    assert resp.json()["citations"] == []


def test_post_turn_missing_and_non_owned_conversation_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "turn-owner@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    _register(auth_client, "turn-intruder@example.com")
    csrf = _csrf(auth_client)

    non_owned = _post_turn(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf=csrf
    )
    missing = _post_turn(auth_client, uuid4(), {"message": "hi", "mode": MODE_ANSWER}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_post_turn_not_ready_source_returns_409(
    auth_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(auth_client, "turn-notready@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id, status="uploaded")
    _seed_corpus(db_conn, source_id)
    conversation = _seed_conversation(db_conn, source_id)

    resp = _post_turn(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf=csrf
    )

    assert resp.status_code == 409, resp.text


def test_post_turn_claiming_a_taken_index_returns_409(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # I-CM-2: the (conversation_id, turn_index) unique is the arbiter — a writer whose
    # next index is already taken loses with a conflict, never a gap or a duplicate.
    # A seeded turn at index 1 with no index 0 puts the next computed index straight
    # onto a taken one. The failed insert aborts this transaction, so nothing is read
    # back afterwards.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-conflict@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    _seed_turn(
        db_conn,
        conversation,
        turn_index=1,
        message="already here",
        mode=MODE_ANSWER,
        answer_status=NOT_FOUND_IN_SCOPE,
        answer_text="",
    )

    resp = _post_turn(
        auth_client,
        conversation.id,
        {"message": "zzzqqq unmatchable", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 409, resp.text


def test_post_turn_generation_failure_returns_502_and_persists_nothing(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-20: a failing generation port → 502 with a generic body that leaks no
    # internal detail, and no turn row.
    from app.infrastructure.web.dependencies import get_generation

    source_id, csrf = _seed_ready_source(auth_client, db_conn, "turn-502@example.com")
    _embed_all(db_conn, UUID(source_id))
    conversation = _seed_conversation(db_conn, UUID(source_id))

    class _RaisingAnswerAdapter:
        model = _MODEL

        def generate(
            self,
            *,
            message: str,
            mode: str,
            evidence: Sequence[Evidence],
            history: Sequence[HistoryTurn] = (),
            target_section_path: tuple[str, ...] | None = None,
        ) -> GeneratedAnswer:
            raise RuntimeError("provider-secret-internal-detail")

    auth_client.app.dependency_overrides[get_generation] = lambda: _RaisingAnswerAdapter()
    try:
        resp = _post_turn(
            auth_client,
            conversation.id,
            {"message": "photosynthesis sunlight", "mode": MODE_ANSWER},
            csrf=csrf,
        )
    finally:
        auth_client.app.dependency_overrides.pop(get_generation, None)

    assert resp.status_code == 502, resp.text
    assert "provider-secret-internal-detail" not in resp.text
    assert auth_client.get(f"/api/conversations/{conversation.id}").json()["turns"] == []


def test_post_turn_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "turn-403@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    resp = _post_turn(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf=None
    )
    assert resp.status_code == 403, resp.text


def test_post_turn_unauthenticated_returns_401(
    auth_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "turn-401@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    auth_client.cookies.clear()
    resp = _post_turn(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf="x"
    )
    assert resp.status_code == 401, resp.text


# --- POST /api/conversations/{id}/turns/stream (CONV-21) -----------------------


def _parse_ui_stream(text: str) -> list:
    parts: list = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            parts.append(payload if payload == "[DONE]" else json.loads(payload))
    return parts


def _part_types(parts: list) -> list[str]:
    return [p["type"] if isinstance(p, dict) else p for p in parts]


def test_turn_stream_emits_the_full_frame_sequence_and_persists_the_turn(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-21: the answered stream emits start → text-start → deltas → text-end →
    # data-citations → data-answer-status → finish → [DONE], with the protocol
    # header, and persists the turn on completion.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "stream-ok@example.com")
    _embed_all(db_conn, UUID(source_id))
    conversation = _seed_conversation(db_conn, UUID(source_id))

    resp = _turn_stream(
        auth_client,
        conversation.id,
        {"message": "photosynthesis sunlight energy", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-vercel-ai-ui-message-stream"] == "v1"
    parts = _parse_ui_stream(resp.text)
    assert _part_types(parts) == [
        "start",
        "text-start",
        "text-delta",
        "text-end",
        "data-citations",
        "data-answer-status",
        "finish",
        "[DONE]",
    ]
    delta = next(p for p in parts if isinstance(p, dict) and p["type"] == "text-delta")
    assert _PHOTO in delta["delta"]
    citations = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-citations")
    assert {c["anchor"] for c in citations["data"]} <= {_ANCHOR, _OTHER_ANCHOR}
    answer_status = next(
        p for p in parts if isinstance(p, dict) and p["type"] == "data-answer-status"
    )
    assert answer_status["data"] == {"status": ANSWERED}

    read = auth_client.get(f"/api/conversations/{conversation.id}")
    turns = read.json()["turns"]
    assert len(turns) == 1
    assert turns[0]["answer_status"] == ANSWERED
    assert turns[0]["mode"] == MODE_ANSWER


def test_turn_stream_carries_not_found_in_scope_in_the_status_frame(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-21: the scoped not-found verdict reaches the client on the wire, so a UI
    # can offer to widen the scope rather than claim the book has nothing.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "stream-scope@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))  # corpus NOT embedded

    resp = _turn_stream(
        auth_client,
        conversation.id,
        {"message": "zzzqqq unmatchable token", "mode": MODE_ANSWER},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    parts = _parse_ui_stream(resp.text)
    assert "text-delta" not in _part_types(parts)
    answer_status = next(
        p for p in parts if isinstance(p, dict) and p["type"] == "data-answer-status"
    )
    assert answer_status["data"] == {"status": NOT_FOUND_IN_SCOPE}

    read = auth_client.get(f"/api/conversations/{conversation.id}")
    assert read.json()["turns"][0]["answer_status"] == NOT_FOUND_IN_SCOPE


def test_turn_stream_mid_stream_failure_emits_the_error_frame_and_persists_nothing(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-21: a provider failure after the first delta is rendered as a protocol
    # error part followed by [DONE] — no finish frame — and persists nothing.
    from app.infrastructure.web.dependencies import get_generation

    source_id, csrf = _seed_ready_source(auth_client, db_conn, "stream-mid@example.com")
    _embed_all(db_conn, UUID(source_id))
    conversation = _seed_conversation(db_conn, UUID(source_id))

    class _MidStreamRaisingAnswerAdapter:
        model = _MODEL

        def generate(
            self,
            *,
            message: str,
            mode: str,
            evidence: Sequence[Evidence],
            history: Sequence[HistoryTurn] = (),
            target_section_path: tuple[str, ...] | None = None,
        ) -> GeneratedAnswer:
            raise AssertionError("stream path must not call generate")

        def generate_stream(
            self,
            *,
            message: str,
            mode: str,
            evidence: Sequence[Evidence],
            history: Sequence[HistoryTurn] = (),
            target_section_path: tuple[str, ...] | None = None,
        ):
            yield AnswerTextDelta(text="partial ")
            raise RuntimeError("provider-secret-internal-detail")

    auth_client.app.dependency_overrides[get_generation] = lambda: _MidStreamRaisingAnswerAdapter()
    try:
        resp = _turn_stream(
            auth_client,
            conversation.id,
            {"message": "photosynthesis sunlight", "mode": MODE_ANSWER},
            csrf=csrf,
        )
    finally:
        auth_client.app.dependency_overrides.pop(get_generation, None)

    assert resp.status_code == 200, resp.text
    parts = _parse_ui_stream(resp.text)
    types = _part_types(parts)
    assert types[-2:] == ["error", "[DONE]"]
    assert "finish" not in types
    error_part = next(p for p in parts if isinstance(p, dict) and p["type"] == "error")
    assert error_part["errorText"] == "Answer generation failed. Please try again."
    assert "provider-secret-internal-detail" not in resp.text

    assert auth_client.get(f"/api/conversations/{conversation.id}").json()["turns"] == []


def test_turn_stream_pre_stream_guards_return_plain_http(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # CONV-21: ownership, mode/message validation and the teach invariant are all
    # decided before any SSE byte, so the client sees plain HTTP errors.
    source_id, csrf = _seed_ready_source(auth_client, db_conn, "stream-guard@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id), scope=(), target_anchor=None)

    missing = _turn_stream(auth_client, uuid4(), {"message": "hi", "mode": MODE_ANSWER}, csrf=csrf)
    blank = _turn_stream(
        auth_client, conversation.id, {"message": "  ", "mode": MODE_ANSWER}, csrf=csrf
    )
    unknown_mode = _turn_stream(
        auth_client, conversation.id, {"message": "hi", "mode": "summarize"}, csrf=csrf
    )
    teach_conflict = _turn_stream(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_TEACH}, csrf=csrf
    )

    assert missing.status_code == 404, missing.text
    assert "start" not in missing.text
    assert blank.status_code == 422, blank.text
    assert unknown_mode.status_code == 422, unknown_mode.text
    assert teach_conflict.status_code == 409, teach_conflict.text
    assert "start" not in teach_conflict.text


def test_turn_stream_missing_and_non_owned_conversation_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # I-CM-6 on the last route that lacked the pair. The missing half alone cannot
    # fail in the case that matters: an id that does not exist 404s off the
    # repository lookup even if the owner check were skipped. This is also the route
    # where a bypass is worst — it would stream another reader's book as SSE frames
    # before anything else noticed.
    source_id, _ = _seed_ready_source(auth_client, db_conn, "stream-owner@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))

    _register(auth_client, "stream-intruder@example.com")
    csrf = _csrf(auth_client)

    non_owned = _turn_stream(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf=csrf
    )
    missing = _turn_stream(auth_client, uuid4(), {"message": "hi", "mode": MODE_ANSWER}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()
    # Not one frame of the owner's book went out first.
    assert "start" not in non_owned.text


def test_turn_stream_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "stream-403@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    resp = _turn_stream(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf=None
    )
    assert resp.status_code == 403, resp.text


def test_turn_stream_unauthenticated_returns_401(
    auth_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(auth_client, db_conn, "stream-401@example.com")
    conversation = _seed_conversation(db_conn, UUID(source_id))
    auth_client.cookies.clear()
    resp = _turn_stream(
        auth_client, conversation.id, {"message": "hi", "mode": MODE_ANSWER}, csrf="x"
    )
    assert resp.status_code == 401, resp.text


def test_turn_endpoints_stay_synchronous_handlers() -> None:
    # The streaming contract (``to_sse_response``): a coroutine handler would run the
    # eager guards, query embedding and retrieval on the event loop and block every
    # concurrent request, and no functional test would notice. Pin the shape.
    import inspect

    from app.infrastructure.web.conversations import (
        post_conversation_turn,
        post_conversation_turn_stream,
    )

    assert not inspect.iscoroutinefunction(post_conversation_turn_stream)
    assert not inspect.iscoroutinefunction(post_conversation_turn)


# --- Rate limit: one policy for the whole surface (CONV-22) --------------------


@pytest.fixture
def throttled_conversations_client(  # noqa: ANN201
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
):
    """Like ``auth_client`` but with a deliberately tight conversations limiter.

    Mirrors ``throttled_teaching_client``: 3 attempts per long window so the 4th
    call trips the ``rate_limit_conversations`` 429 branch deterministically. The
    key is client IP + route template, so the register/csrf setup calls consume
    separate buckets and never eat the conversation budget, while every conversation
    of one client shares the budget of the route it is posting to.
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
    throttled_conversations_client: TestClient, db_conn: Connection
) -> None:
    # CONV-22: past the window the start endpoint rejects with 429 and tells the
    # client when to come back.
    source_id, csrf = _seed_ready_source(
        throttled_conversations_client, db_conn, "rl-start@example.com"
    )
    for _ in range(3):
        resp = _start(
            throttled_conversations_client,
            {"source_id": source_id, "include_notes": False},
            csrf=csrf,
        )
        assert resp.status_code == 201, resp.text

    throttled = _start(
        throttled_conversations_client,
        {"source_id": source_id, "include_notes": False},
        csrf=csrf,
    )

    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}
    assert int(throttled.headers["retry-after"]) >= 1


def test_turn_rate_limit_returns_429(
    throttled_conversations_client: TestClient, db_conn: Connection
) -> None:
    # CONV-22: the same policy governs the turn endpoint (corpus is not embedded, so
    # each accepted turn is a cheap not-found). The budget is keyed by the route
    # template, so it is spent here across three *different* conversations — keying
    # on the concrete path would give a client a fresh budget per conversation it
    # starts, which is exactly the flood the throttle exists to stop.
    source_id, csrf = _seed_ready_source(
        throttled_conversations_client, db_conn, "rl-turn@example.com"
    )
    conversations = [_seed_conversation(db_conn, UUID(source_id)) for _ in range(3)]
    body = {"message": "zzzqqq unmatchable", "mode": MODE_ANSWER}
    for conversation in conversations:
        resp = _post_turn(throttled_conversations_client, conversation.id, body, csrf=csrf)
        assert resp.status_code == 201, resp.text

    throttled = _post_turn(throttled_conversations_client, conversations[0].id, body, csrf=csrf)
    assert throttled.status_code == 429, throttled.text


def test_turn_stream_rate_limit_returns_429_before_any_frame(
    throttled_conversations_client: TestClient, db_conn: Connection
) -> None:
    # CONV-22: the streaming sibling is throttled by the same policy, and the
    # rejection is a plain 429 — no SSE frame is ever opened.
    source_id, csrf = _seed_ready_source(
        throttled_conversations_client, db_conn, "rl-stream@example.com"
    )
    conversation = _seed_conversation(db_conn, UUID(source_id))
    body = {"message": "zzzqqq unmatchable", "mode": MODE_ANSWER}
    for _ in range(3):
        resp = _turn_stream(throttled_conversations_client, conversation.id, body, csrf=csrf)
        assert resp.status_code == 200, resp.text

    throttled = _turn_stream(throttled_conversations_client, conversation.id, body, csrf=csrf)
    assert throttled.status_code == 429, throttled.text
    assert "start" not in throttled.text


def test_every_mutating_conversation_route_carries_the_one_policy() -> None:
    # CONV-22 / ADR-0029: one policy for the whole unified surface. Asserted over the
    # route inventory rather than per endpoint, so a route added later cannot quietly
    # ship without the limiter — or with a second limiter beside it.
    from app.infrastructure.web.conversations import router
    from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
    from app.infrastructure.web.rate_limit import rate_limit_conversations

    routes = [route for route in router.routes if route.path.startswith("/api/conversations")]
    assert len(routes) == len(router.routes) == 7

    mutating = {"POST", "PATCH", "DELETE", "PUT"}
    for route in routes:
        declared = [dependency.dependency for dependency in route.dependencies]
        if route.methods & mutating:
            assert declared == [
                rate_limit_conversations,
                enforce_origin,
                enforce_csrf,
            ], f"{sorted(route.methods)} {route.path}"
        else:
            assert declared == [], f"{sorted(route.methods)} {route.path}"
