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

Seeding mirrors ``test_web_teaching``: sources and corpus through the real
repositories on the shared rolled-back ``db_conn``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import (
    ANSWERED,
    MODE_ANSWER,
    MODE_TEACH,
    NOT_FOUND_IN_SCOPE,
    Conversation,
    ConversationTurn,
    CorpusSectionRecord,
    Evidence,
    ParsedSection,
    SectionChunk,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationTurnRepository,
    SqlAlchemyCorpusRepository,
    SqlAlchemySourceRepository,
)
from tests.conftest import TEST_PASSWORD, requires_db

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
