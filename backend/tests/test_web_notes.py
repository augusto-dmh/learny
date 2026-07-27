"""T6 gate — notes + highlights router (integration, live test DB).

Exercises the owner-scoped notes endpoints end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec ACs at the route level:

- ``POST   /api/notes`` — gone: a note cannot be created without a reading anchor,
  and a note that predates the rule still lists, opens, edits, and deletes (WSN-09).
- ``GET    /api/notes`` — owner → 200 summaries newest-first; ``?tag=`` filters
  case-insensitively; no session → 401 (NF-13). ``?source_id=`` narrows it to one
  book: only that book's notes, a twice-anchored one listed once with the passage it
  came from and that passage's derived page, an orphaned anchor kept with its quote
  and no page, composed with ``?tag=``; non-owned/unknown → identical 404, a
  malformed id → 422 (WSN-01/02/03/10/11/15).
- ``GET    /api/notes/{id}`` — owner → 200 detail; missing/non-owned → identical
  404; no session → 401 (NF-05/10).
- ``PATCH  /api/notes/{id}`` — owner → 200 rewritten; over-cap body → 422;
  missing/non-owned → 404; missing CSRF → 403 (NF-05).
- ``DELETE /api/notes/{id}`` — owner → 204; missing/non-owned → 404; missing CSRF →
  403 (NF-05).
- ``GET    /api/notes/{id}/backlinks`` — owner → 200 inbound links; unknown → 404
  (NF-10).
- ``POST   /api/sources/{id}/highlights`` — the one creation path: owned ready source
  → 201 note + anchor jump-back fields, with or without a quote; unknown source /
  unknown anchor → 404; stale selection → 409; over-cap body → 422; no session → 401;
  missing CSRF / untrusted Origin → 403; rate limit → 429 (NF-06/09/10).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.application.quiz_qc import content_key
from app.domain.entities import (
    CorpusSectionRecord,
    Note,
    NoteAnchor,
    ParsedBlock,
    ParsedSection,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    SectionChunk,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
)
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db

# A tight body cap so the over-cap 422 path is exercised cheaply; every note body
# in this module stays well under it.
NOTES_MAX_BODY = 50

# A small page quantum so a seeded chapter can cross a page boundary in a few words,
# making a book-scoped row's derived page an exact, readable number.
NOTES_WORDS_PER_PAGE = 10


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def notes_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the notes routers, isolated to a rolled-back txn.

    Mirrors ``sources_client`` (shared ``db_conn``, non-Secure cookie, trusted
    Origin, generous limiter) but pins ``notes_max_body_chars`` to
    :data:`NOTES_MAX_BODY` so the over-cap reject stays cheap, and the page quantum to
    :data:`NOTES_WORDS_PER_PAGE` so a book-scoped row's page is an exact small number
    rather than one that depends on the deployment default. Create/update commit in
    a UoW factory before the after-commit embed enqueue (AD-016), so the factory is
    overridden to yield the shared ``db_conn`` *without committing* and the enqueuer is
    a recording fake (on ``app.state`` so tests can assert its calls).
    """
    from contextlib import contextmanager

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import (
        get_db_connection,
        get_note_index_enqueuer,
        get_note_uow,
    )
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app
    from tests.fakes import FakeNoteIndexEnqueuer

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    monkeypatch.setenv("LEARNY_NOTES_MAX_BODY_CHARS", str(NOTES_MAX_BODY))
    monkeypatch.setenv("LEARNY_WORDS_PER_PAGE", str(NOTES_WORDS_PER_PAGE))
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    @contextmanager
    def _shared_uow() -> Iterator[Connection]:
        # Yield the shared rolled-back connection WITHOUT committing, so the note
        # write is observed by the test's one transaction (isolation kept exactly as
        # ``get_db_connection`` is overridden).
        yield db_conn

    enqueuer = FakeNoteIndexEnqueuer()
    app.state.note_enqueuer = enqueuer

    app.dependency_overrides[get_db_connection] = _override
    app.dependency_overrides[get_note_uow] = lambda: _shared_uow
    app.dependency_overrides[get_note_index_enqueuer] = lambda: enqueuer
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


@pytest.fixture
def throttled_notes_client(  # noqa: ANN201
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
):
    """Like ``notes_client`` but with a deliberately tight limiter (3/window).

    The limiter key is per-IP+route, so the register/csrf setup calls consume
    separate buckets and never eat into the note-write budget — the 4th capture trips
    ``rate_limit_notes`` deterministically (NF-09).
    """
    from contextlib import contextmanager

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import (
        get_db_connection,
        get_note_index_enqueuer,
        get_note_uow,
    )
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app
    from tests.fakes import FakeNoteIndexEnqueuer

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    @contextmanager
    def _shared_uow() -> Iterator[Connection]:
        yield db_conn

    enqueuer = FakeNoteIndexEnqueuer()
    app.state.note_enqueuer = enqueuer

    app.dependency_overrides[get_db_connection] = _override
    app.dependency_overrides[get_note_uow] = lambda: _shared_uow
    app.dependency_overrides[get_note_index_enqueuer] = lambda: enqueuer
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _patch_note(client: TestClient, note_id: object, body: dict, *, csrf: str | None):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return client.patch(f"/api/notes/{note_id}", json=body, headers=headers)


def _delete_note(client: TestClient, note_id: object, *, csrf: str | None):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return client.delete(f"/api/notes/{note_id}", headers=headers)


def _post_highlight(
    client: TestClient,
    source_id: object,
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
    return client.post(f"/api/sources/{source_id}/highlights", json=body, headers=headers)


def _created_note(client: TestClient, csrf: str, source_id: object, **fields) -> dict:
    """Create a note the only way the API allows — an anchored capture — and return it."""
    body = {"anchor": "ch1", "title": "Untitled", "body_markdown": "", "tags": []}
    body.update(fields)
    resp = _post_highlight(client, source_id, body, csrf=csrf)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Seeding -------------------------------------------------------------------


def _persist_source(db_conn: Connection, user_id: str, *, title: str = "A Book") -> UUID:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=UUID(user_id),
        title=title,
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source).id


def _seed_corpus(db_conn: Connection, source_id: UUID, *, anchor: str, block_html: str) -> None:
    """Replace ``source_id``'s corpus with a single section holding one block."""
    section = ParsedSection(
        position=0,
        title="Chapter 1",
        depth=1,
        section_path=("Chapter 1",),
        anchor=anchor,
        blocks=(ParsedBlock(position=0, block_type="paragraph", html_fragment=block_html),),
        anchor_aliases=(),
    )
    record = CorpusSectionRecord(
        section=section,
        markdown=block_html,
        chunks=(
            SectionChunk(
                index=0,
                text=block_html,
                section_path=("Chapter 1",),
                anchor=anchor,
                page_span=None,
            ),
        ),
        block_hashes=(f"hash-{anchor}-0",),
    )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[record],
    )


def _capture_target(db_conn: Connection, user_id: str) -> UUID:
    """Seed an owned, ingested source a capture can anchor a note to (anchor ``ch1``)."""
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(
        db_conn,
        source_id,
        anchor="ch1",
        block_html="<p>The quick brown fox jumps over the lazy dog.</p>",
    )
    return source_id


def _seed_two_chapter_corpus(
    db_conn: Connection, source_id: UUID, *, first_chapter_words: int
) -> None:
    """Replace ``source_id``'s corpus with ``ch1`` then ``ch2``, ch1 the given length.

    The lead chapter's length is what pushes ``ch2`` past a page boundary, so a note
    anchored there has a page number the whole book's word counts produced.
    """
    texts = {
        "ch1": " ".join(["word"] * first_chapter_words),
        "ch2": "The quick brown fox jumps over the lazy dog.",
    }
    records = []
    for position, (anchor, text) in enumerate(texts.items()):
        title = f"Chapter {position + 1}"
        records.append(
            CorpusSectionRecord(
                section=ParsedSection(
                    position=position,
                    title=title,
                    depth=0,
                    section_path=(title,),
                    anchor=anchor,
                    blocks=(
                        ParsedBlock(
                            position=0, block_type="paragraph", html_fragment=f"<p>{text}</p>"
                        ),
                    ),
                    anchor_aliases=(),
                ),
                markdown=text,
                chunks=(
                    SectionChunk(
                        index=0, text=text, section_path=(title,), anchor=anchor, page_span=None
                    ),
                ),
                block_hashes=(f"hash-{anchor}-0",),
            )
        )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=records,
    )


def _seed_anchor(
    db_conn: Connection,
    note_id: object,
    source_id: UUID,
    *,
    anchor: str,
    quote_exact: str,
    status: str = "active",
    created: datetime | None = None,
) -> None:
    """Attach one more anchor to an existing note, directly (no capture route needed)."""
    now = created or datetime.now(UTC)
    SqlAlchemyNoteRepository(db_conn).add_anchor(
        NoteAnchor(
            id=uuid4(),
            note_id=UUID(str(note_id)),
            source_id=source_id,
            source_title="A Book",
            anchor=anchor,
            section_path=("Chapter 1",),
            block_hash=None,
            block_ordinal=None,
            start_offset=None,
            end_offset=None,
            quote_exact=quote_exact,
            quote_prefix="",
            quote_suffix="",
            status=status,
            created_at=now,
            updated_at=now,
        )
    )


def _seed_anchorless_note(db_conn: Connection, user_id: str, *, title: str, body: str = "") -> UUID:
    """Persist a note with no anchor — the shape every note written before the rule has."""
    now = datetime.now(UTC)
    note = Note(
        id=uuid4(),
        user_id=UUID(user_id),
        title=title,
        body_markdown=body,
        created_at=now,
        updated_at=now,
    )
    SqlAlchemyNoteRepository(db_conn).add(note)
    return note.id


# --- Creation requires an anchor (WSN-08) --------------------------------------


def test_creating_a_note_without_an_anchor_has_no_route(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """The rootless create is gone: nothing can post a note that carries no passage."""
    _register(notes_client, "note-rootless@example.com")
    csrf = _csrf(notes_client)

    resp = notes_client.post(
        "/api/notes",
        json={"title": "Rootless", "body_markdown": "no passage", "tags": []},
        headers={"X-CSRF-Token": csrf},
    )

    assert resp.status_code == 405, resp.text
    assert notes_client.get("/api/notes").json() == []


def test_capture_untrusted_origin_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-origin@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)

    resp = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "ch1", "title": "X"},
        csrf=csrf,
        origin="http://evil.example.com",
    )

    assert resp.status_code == 403, resp.text


def test_capture_rate_limit_returns_429(
    throttled_notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(throttled_notes_client, "note-rl@example.com")
    csrf = _csrf(throttled_notes_client)
    source_id = _capture_target(db_conn, user_id)

    for _ in range(3):
        resp = _post_highlight(
            throttled_notes_client, source_id, {"anchor": "ch1", "title": "X"}, csrf=csrf
        )
        assert resp.status_code == 201, resp.text
    throttled = _post_highlight(
        throttled_notes_client, source_id, {"anchor": "ch1", "title": "X"}, csrf=csrf
    )

    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


# --- Notes written before the anchor rule (WSN-09, WSN-16) ---------------------


def test_anchorless_note_still_lists_and_opens(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A note with no anchor predates the rule; nothing about reading it changed."""
    user_id = _register(notes_client, "note-legacy-read@example.com")
    note_id = _seed_anchorless_note(db_conn, user_id, title="Old thought", body="written before")

    listed = notes_client.get("/api/notes")
    opened = notes_client.get(f"/api/notes/{note_id}")

    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert [row["id"] for row in rows] == [str(note_id)]
    assert rows[0]["anchor_statuses"] == []
    assert opened.status_code == 200, opened.text
    assert opened.json()["title"] == "Old thought"
    assert opened.json()["body_markdown"] == "written before"
    assert opened.json()["anchors"] == []


def test_anchorless_note_still_edits_and_stays_anchorless(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """Editing one never grows it an anchor: its anchored state is fixed at creation."""
    user_id = _register(notes_client, "note-legacy-edit@example.com")
    csrf = _csrf(notes_client)
    note_id = _seed_anchorless_note(db_conn, user_id, title="Old", body="first")

    resp = _patch_note(
        notes_client,
        note_id,
        {"title": "Reworked", "body_markdown": "second", "tags": ["kept"]},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Reworked"
    assert resp.json()["body_markdown"] == "second"
    assert resp.json()["tags"] == ["kept"]
    assert resp.json()["anchors"] == []
    assert notes_client.get(f"/api/notes/{note_id}").json()["anchors"] == []


def test_anchorless_note_still_deletes(notes_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(notes_client, "note-legacy-delete@example.com")
    csrf = _csrf(notes_client)
    note_id = _seed_anchorless_note(db_conn, user_id, title="Old", body="going away")

    resp = _delete_note(notes_client, note_id, csrf=csrf)

    assert resp.status_code == 204, resp.text
    assert notes_client.get(f"/api/notes/{note_id}").status_code == 404
    assert notes_client.get("/api/notes").json() == []


def test_anchorless_and_anchored_notes_list_side_by_side(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """The rule constrains creation only — both kinds coexist in one list."""
    user_id = _register(notes_client, "note-legacy-mixed@example.com")
    csrf = _csrf(notes_client)
    legacy_id = _seed_anchorless_note(db_conn, user_id, title="Rootless")
    source_id = _capture_target(db_conn, user_id)
    anchored = _created_note(notes_client, csrf, source_id, title="Anchored")

    rows = notes_client.get("/api/notes").json()

    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {str(legacy_id), anchored["id"]}
    assert by_id[str(legacy_id)]["anchor_statuses"] == []
    assert by_id[anchored["id"]]["anchor_statuses"] == ["active"]


# --- List (NF-13) --------------------------------------------------------------


def test_list_notes_newest_edited_first_and_owner_scoped(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-list@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    _created_note(notes_client, csrf, source_id, title="First")
    _created_note(notes_client, csrf, source_id, title="Second")

    resp = notes_client.get("/api/notes")

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["title"] for r in rows] == ["Second", "First"]
    assert set(rows[0]) == {
        "id",
        "title",
        "tags",
        "anchor_statuses",
        "anchor",
        "created_at",
        "updated_at",
    }
    # The cross-book list has no single book to represent a note by, so it carries no
    # passage and no page.
    assert [r["anchor"] for r in rows] == [None, None]


def test_list_notes_filters_by_tag_case_insensitively(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-tagfilter@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    _created_note(notes_client, csrf, source_id, title="Tagged", tags=["python"])
    _created_note(notes_client, csrf, source_id, title="Untagged")

    resp = notes_client.get("/api/notes", params={"tag": "PYTHON"})

    assert resp.status_code == 200, resp.text
    assert [r["title"] for r in resp.json()] == ["Tagged"]


def test_list_notes_unauthenticated_returns_401(
    notes_client: TestClient, db_conn: Connection
) -> None:
    notes_client.cookies.clear()
    assert notes_client.get("/api/notes").status_code == 401


# --- List scoped to one book (WSN-01/02/03/10/11/15) ---------------------------


def test_list_notes_scoped_to_a_book_lists_only_its_notes_with_their_passages(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-by-book@example.com")
    csrf = _csrf(notes_client)
    this_book = _persist_source(db_conn, user_id, title="This Book")
    _seed_two_chapter_corpus(db_conn, this_book, first_chapter_words=25)
    other_book = _capture_target(db_conn, user_id)
    _created_note(
        notes_client,
        csrf,
        this_book,
        anchor="ch2",
        quote_exact="quick brown",
        title="On this book",
    )
    _created_note(notes_client, csrf, other_book, title="On the other book")
    _seed_anchorless_note(db_conn, user_id, title="No book at all")

    resp = notes_client.get("/api/notes", params={"source_id": str(this_book)})

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [row["title"] for row in rows] == ["On this book"]
    passage = rows[0]["anchor"]
    assert passage["anchor"] == "ch2"
    assert passage["section_title"] == "Chapter 2"
    assert passage["section_path"] == ["Chapter 2"]
    assert passage["quote_exact"] == "quick brown"
    assert passage["status"] == "active"
    # 25 words precede chapter two; at 10 words to a page that is page 3, counted from
    # the book's first word rather than restarted per chapter.
    assert passage["page"] == 3


def test_list_notes_scoped_to_a_book_lists_a_twice_anchored_note_once(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-twice-anchored@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(
        notes_client, csrf, source_id, quote_exact="quick brown", title="Twice anchored"
    )
    _seed_anchor(
        db_conn,
        note["id"],
        source_id,
        anchor="ch1",
        quote_exact="the lazy dog",
        created=datetime.now(UTC) + timedelta(hours=1),
    )

    rows = notes_client.get("/api/notes", params={"source_id": str(source_id)}).json()

    assert [row["title"] for row in rows] == ["Twice anchored"]
    # The row stands for the passage the note came from — its earliest anchor here.
    assert rows[0]["anchor"]["quote_exact"] == "quick brown"


def test_list_notes_scoped_to_a_book_keeps_an_orphaned_rows_quote_and_shows_no_page(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-orphan-row@example.com")
    source_id = _capture_target(db_conn, user_id)
    note_id = _seed_anchorless_note(db_conn, user_id, title="Outlived its section")
    _seed_anchor(
        db_conn,
        note_id,
        source_id,
        anchor="ch-gone",
        quote_exact="a passage the re-ingest lost",
        status="orphaned",
    )

    rows = notes_client.get("/api/notes", params={"source_id": str(source_id)}).json()

    assert [row["title"] for row in rows] == ["Outlived its section"]
    assert rows[0]["anchor"]["quote_exact"] == "a passage the re-ingest lost"
    assert rows[0]["anchor"]["status"] == "orphaned"
    assert rows[0]["anchor"]["page"] is None


def test_list_notes_scoped_to_a_book_composes_with_the_tag_filter(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-book-and-tag@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    other_book = _capture_target(db_conn, user_id)
    _created_note(notes_client, csrf, source_id, title="Tagged here", tags=["python"])
    _created_note(notes_client, csrf, source_id, title="Untagged here")
    _created_note(notes_client, csrf, other_book, title="Tagged elsewhere", tags=["python"])

    rows = notes_client.get(
        "/api/notes", params={"source_id": str(source_id), "tag": "PYTHON"}
    ).json()

    assert [row["title"] for row in rows] == ["Tagged here"]


def test_list_notes_scoped_to_a_book_with_no_notes_is_an_empty_list(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-empty-book@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    empty_book = _capture_target(db_conn, user_id)
    _created_note(notes_client, csrf, source_id, title="Elsewhere")

    resp = notes_client.get("/api/notes", params={"source_id": str(empty_book)})

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_list_notes_non_owned_and_unknown_source_return_identical_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    owner_id = _register(notes_client, "note-book-owner@example.com")
    source_id = _capture_target(db_conn, owner_id)
    _created_note(notes_client, _csrf(notes_client), source_id, title="Owned")

    _register(notes_client, "note-book-intruder@example.com")  # become a different user

    non_owned = notes_client.get("/api/notes", params={"source_id": str(source_id)})
    missing = notes_client.get("/api/notes", params={"source_id": str(uuid4())})

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()  # no existence disclosure


def test_list_notes_rejects_a_source_id_that_is_not_a_uuid(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-bad-source@example.com")

    assert notes_client.get("/api/notes", params={"source_id": "not-a-uuid"}).status_code == 422


# --- Get (NF-05/10) ------------------------------------------------------------


def test_get_note_returns_200_detail(notes_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(notes_client, "note-get@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, csrf, source_id, title="Readable", body_markdown="body")

    resp = notes_client.get(f"/api/notes/{note['id']}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Readable"
    assert resp.json()["body_markdown"] == "body"


def test_get_note_missing_and_non_owned_return_identical_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-get-owner@example.com")
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, _csrf(notes_client), source_id, title="Owned")

    _register(notes_client, "note-get-intruder@example.com")  # become a different user

    non_owned = notes_client.get(f"/api/notes/{note['id']}")
    missing = notes_client.get(f"/api/notes/{uuid4()}")

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()  # no existence disclosure


def test_get_note_unauthenticated_returns_401(
    notes_client: TestClient, db_conn: Connection
) -> None:
    notes_client.cookies.clear()
    assert notes_client.get(f"/api/notes/{uuid4()}").status_code == 401


# --- Update (NF-05) ------------------------------------------------------------


def test_update_note_rewrites_and_returns_detail(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-update@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, csrf, source_id, title="Old", tags=["old"])

    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "New", "body_markdown": "changed", "tags": ["new"]},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "New"
    assert body["body_markdown"] == "changed"
    assert body["tags"] == ["new"]


def test_update_note_over_cap_body_returns_422(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-update-cap@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, csrf, source_id, title="X")
    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "X", "body_markdown": "x" * (NOTES_MAX_BODY + 1)},
        csrf=csrf,
    )
    assert resp.status_code == 422, resp.text


def test_update_note_non_owned_returns_404(notes_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(notes_client, "note-update-owner@example.com")
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, _csrf(notes_client), source_id, title="Owned")

    _register(notes_client, "note-update-intruder@example.com")
    csrf = _csrf(notes_client)
    resp = _patch_note(notes_client, note["id"], {"title": "Hijack"}, csrf=csrf)
    assert resp.status_code == 404, resp.text


def test_update_note_missing_csrf_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-update-csrf@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, csrf, source_id, title="X")
    resp = _patch_note(notes_client, note["id"], {"title": "Y"}, csrf=None)
    assert resp.status_code == 403, resp.text


# --- Async embed enqueue (NL-01, NL-07) ----------------------------------------


def test_update_note_body_change_enqueues_embed_after_commit(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """Editing the body re-embeds after commit (NL-01)."""
    user_id = _register(notes_client, "note-embed-update@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer
    note = _created_note(notes_client, csrf, source_id, title="N", body_markdown="")

    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "N", "body_markdown": "now it has content", "tags": []},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert enq.embed_calls == [UUID(note["id"])]


def test_capturing_a_note_with_a_body_enqueues_its_embed(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A captured note with a body is queued for embedding (NL-01).

    Capture is the only way a note is born, so if it does not enqueue, no note is ever
    embedded and the notes retrieval arm — which only sees rows whose embedding is
    present — silently stops seeing anything created from now on.
    """
    user_id = _register(notes_client, "note-embed-capture@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer

    note = _created_note(
        notes_client, csrf, source_id, title="Captured", body_markdown="worth embedding"
    )

    assert enq.embed_calls == [UUID(note["id"])]


def test_capturing_a_bare_highlight_enqueues_no_embed(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A capture with no body has nothing to embed, so nothing is queued (NL-01)."""
    user_id = _register(notes_client, "note-embed-bare@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer

    _created_note(notes_client, csrf, source_id, title="Bare", body_markdown="")

    assert enq.embed_calls == []


def test_update_note_title_or_tags_only_enqueues_no_embed(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A PATCH that leaves the body byte-identical enqueues no re-embed (NL-01)."""
    user_id = _register(notes_client, "note-embed-titleonly@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer
    note = _created_note(notes_client, csrf, source_id, title="Keep")
    written = _patch_note(
        notes_client,
        note["id"],
        {"title": "Keep", "body_markdown": "stable body", "tags": []},
        csrf=csrf,
    )
    assert written.status_code == 200, written.text
    assert enq.embed_calls == [UUID(note["id"])]  # the body edit embedded once

    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "Renamed", "body_markdown": "stable body", "tags": ["x"]},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    # No second enqueue — only the body edit's embed remains.
    assert enq.embed_calls == [UUID(note["id"])]


def _promote_note(db_conn: Connection, note_id: UUID, user_id: str) -> None:
    """Seed one live ``note`` card for ``note_id`` so the refresh gate sees it (NL-10)."""
    now = datetime.now(UTC)
    question = "What does this note state?"
    answer = "A fact."
    SqlAlchemyQuizItemRepository(db_conn).upsert(
        QuizItem(
            id=uuid4(),
            source_id=None,
            user_id=UUID(user_id),
            origin=QuizItemOrigin.NOTE,
            note_id=note_id,
            item_type=QuizItemType.FREE_RECALL,
            question=question,
            answer=answer,
            section_path=("N",),
            anchor=f"note:{note_id}",
            source_excerpt="body",
            chunk_hash="f" * 64,
            content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
            status=QuizItemStatus.ACTIVE,
            generation_meta={},
            created_at=now,
            updated_at=now,
        ),
        embedding=None,
    )


def test_update_promoted_note_body_change_enqueues_refresh(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A body edit on a note with live cards enqueues a regenerate-and-match (NL-10)."""
    user_id = _register(notes_client, "note-refresh-promoted@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer
    note = _created_note(notes_client, csrf, source_id, title="N", body_markdown="first body")
    _promote_note(db_conn, UUID(note["id"]), user_id)

    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "N", "body_markdown": "a reworded body", "tags": []},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert enq.refresh_calls == [UUID(note["id"])]


def test_update_unpromoted_note_body_change_enqueues_no_refresh(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A body edit on a note with no cards enqueues an embed but no refresh (NL-10 gate)."""
    user_id = _register(notes_client, "note-refresh-unpromoted@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer
    note = _created_note(notes_client, csrf, source_id, title="N", body_markdown="first body")

    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "N", "body_markdown": "a reworded body", "tags": []},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert enq.refresh_calls == []


def test_update_promoted_note_title_only_enqueues_no_refresh(
    notes_client: TestClient, db_conn: Connection
) -> None:
    """A title/tags-only edit never regenerates cards — the body is byte-identical."""
    user_id = _register(notes_client, "note-refresh-titleonly@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer
    note = _created_note(notes_client, csrf, source_id, title="Keep", body_markdown="stable body")
    _promote_note(db_conn, UUID(note["id"]), user_id)

    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "Renamed", "body_markdown": "stable body", "tags": ["x"]},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert enq.refresh_calls == []


def test_delete_note_enqueues_nothing(notes_client: TestClient, db_conn: Connection) -> None:
    """Deleting a note enqueues no index work — its index rows die with it (NL-07)."""
    user_id = _register(notes_client, "note-embed-delete@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    enq = notes_client.app.state.note_enqueuer
    note = _created_note(notes_client, csrf, source_id, title="Doomed", body_markdown="")

    resp = _delete_note(notes_client, note["id"], csrf=csrf)

    assert resp.status_code == 204, resp.text
    assert enq.embed_calls == []
    assert enq.refresh_calls == []


# --- Delete (NF-05) ------------------------------------------------------------


def test_delete_note_returns_204_then_404(notes_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(notes_client, "note-delete@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, csrf, source_id, title="Doomed")

    resp = _delete_note(notes_client, note["id"], csrf=csrf)
    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    # It is gone afterwards.
    assert notes_client.get(f"/api/notes/{note['id']}").status_code == 404


def test_delete_note_non_owned_returns_404(notes_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(notes_client, "note-delete-owner@example.com")
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, _csrf(notes_client), source_id, title="Owned")

    _register(notes_client, "note-delete-intruder@example.com")
    csrf = _csrf(notes_client)
    resp = _delete_note(notes_client, note["id"], csrf=csrf)
    assert resp.status_code == 404, resp.text


def test_delete_note_missing_csrf_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "note-delete-csrf@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    note = _created_note(notes_client, csrf, source_id, title="X")
    resp = _delete_note(notes_client, note["id"], csrf=None)
    assert resp.status_code == 403, resp.text


# --- Backlinks (NF-10) ---------------------------------------------------------


def test_backlinks_returns_inbound_links(notes_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(notes_client, "note-backlinks@example.com")
    csrf = _csrf(notes_client)
    source_id = _capture_target(db_conn, user_id)
    target = _created_note(notes_client, csrf, source_id, title="Target")
    linker = _created_note(notes_client, csrf, source_id, title="Link", body_markdown="[[Target]]")

    resp = notes_client.get(f"/api/notes/{target['id']}/backlinks")

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["note_id"] for r in rows] == [linker["id"]]
    assert rows[0]["title"] == "Link"


def test_backlinks_unknown_note_returns_404(notes_client: TestClient, db_conn: Connection) -> None:
    _register(notes_client, "note-backlinks-404@example.com")
    _csrf(notes_client)
    resp = notes_client.get(f"/api/notes/{uuid4()}/backlinks")
    assert resp.status_code == 404, resp.text


# --- Capture highlight (NF-06/10) ----------------------------------------------


def test_capture_highlight_returns_201_with_anchor_jumpback(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "hl-ok@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(
        db_conn,
        source_id,
        anchor="ch1",
        block_html="<p>The quick brown fox jumps over the lazy dog.</p>",
    )

    resp = _post_highlight(
        notes_client,
        source_id,
        {
            "anchor": "ch1",
            "quote_exact": "quick brown fox",
            "title": "highlight",
            "body_markdown": "",
        },
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["anchors"]) == 1
    anchor = body["anchors"][0]
    # NF-10 jump-back payload: source_id + anchor + quote + orphan-badge status.
    assert anchor["source_id"] == str(source_id)
    assert anchor["anchor"] == "ch1"
    assert anchor["quote_exact"] == "quick brown fox"
    assert anchor["source_title"] == "A Book"
    assert anchor["status"] == "active"
    assert anchor["section_path"] == ["Chapter 1"]


def test_capture_highlight_without_a_quote_returns_201_with_a_section_level_anchor(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "hl-noquote@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(
        db_conn,
        source_id,
        anchor="ch1",
        block_html="<p>The quick brown fox jumps over the lazy dog.</p>",
    )

    resp = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "ch1", "title": "About this chapter", "body_markdown": ""},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["anchors"]) == 1
    anchor = body["anchors"][0]
    assert anchor["source_id"] == str(source_id)
    assert anchor["anchor"] == "ch1"
    assert anchor["section_path"] == ["Chapter 1"]
    assert anchor["quote_exact"] == ""
    assert anchor["block_ordinal"] is None
    assert anchor["start_offset"] is None
    assert anchor["end_offset"] is None
    assert anchor["status"] == "active"
    # The note is durable, not just echoed back.
    assert [row["id"] for row in notes_client.get("/api/notes").json()] == [body["id"]]


def test_capture_highlight_without_a_quote_over_cap_body_persists_nothing(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "hl-noquote-toolong@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id, anchor="ch1", block_html="<p>Present text.</p>")

    resp = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "ch1", "title": "h", "body_markdown": "x" * (NOTES_MAX_BODY + 1)},
        csrf=csrf,
    )

    assert resp.status_code == 422, resp.text
    assert notes_client.get("/api/notes").json() == []
    assert notes_client.get(f"/api/sources/{source_id}/highlights").json() == []


def test_capture_highlight_over_cap_body_returns_422(
    notes_client: TestClient, db_conn: Connection
) -> None:
    # The one route where the body cap is checked AFTER anchor resolution: a
    # resolvable selection with an over-cap note body must reject with 422 and
    # persist nothing.
    user_id = _register(notes_client, "hl-toolong@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(
        db_conn,
        source_id,
        anchor="ch1",
        block_html="<p>The quick brown fox jumps over the lazy dog.</p>",
    )

    resp = _post_highlight(
        notes_client,
        source_id,
        {
            "anchor": "ch1",
            "quote_exact": "quick brown fox",
            "title": "highlight",
            "body_markdown": "x" * (NOTES_MAX_BODY + 1),
        },
        csrf=csrf,
    )

    assert resp.status_code == 422, resp.text
    assert notes_client.get("/api/notes").json() == []


def test_capture_highlight_unknown_source_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "hl-nosource@example.com")
    csrf = _csrf(notes_client)
    resp = _post_highlight(
        notes_client,
        uuid4(),
        {"anchor": "ch1", "quote_exact": "x", "title": "h"},
        csrf=csrf,
    )
    assert resp.status_code == 404, resp.text


def test_capture_highlight_unknown_anchor_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "hl-noanchor@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id, anchor="ch1", block_html="<p>Present text.</p>")

    resp = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "does-not-exist", "quote_exact": "Present", "title": "h"},
        csrf=csrf,
    )
    assert resp.status_code == 404, resp.text


def test_capture_highlight_stale_selection_returns_409(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "hl-stale@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id, anchor="ch1", block_html="<p>The present text.</p>")

    # The quote does not resolve in the served section → the evidence is stale.
    resp = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "ch1", "quote_exact": "vanished passage", "title": "h"},
        csrf=csrf,
    )
    assert resp.status_code == 409, resp.text


def test_capture_highlight_missing_csrf_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(notes_client, "hl-csrf@example.com")
    _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    resp = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "ch1", "quote_exact": "x", "title": "h"},
        csrf=None,
    )
    assert resp.status_code == 403, resp.text


def test_capture_highlight_unauthenticated_returns_401(
    notes_client: TestClient, db_conn: Connection
) -> None:
    notes_client.cookies.clear()
    resp = _post_highlight(
        notes_client,
        uuid4(),
        {"anchor": "ch1", "quote_exact": "x", "title": "h"},
        csrf="whatever",
    )
    assert resp.status_code == 401, resp.text


# --- List highlights (RD-28) ---------------------------------------------------


def _capture(client: TestClient, db_conn: Connection, email: str) -> UUID:
    """Register, seed a one-section corpus, capture one highlight; return the source id."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(
        db_conn,
        source_id,
        anchor="ch1",
        block_html="<p>The quick brown fox jumps over the lazy dog.</p>",
    )
    resp = _post_highlight(
        client,
        source_id,
        {"anchor": "ch1", "quote_exact": "quick brown fox", "title": "h"},
        csrf=csrf,
    )
    assert resp.status_code == 201, resp.text
    return source_id


def test_list_source_highlights_returns_owner_highlights(
    notes_client: TestClient, db_conn: Connection
) -> None:
    source_id = _capture(notes_client, db_conn, "hl-list@example.com")

    resp = notes_client.get(f"/api/sources/{source_id}/highlights")

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert set(rows[0]) == {
        "note_id",
        "anchor",
        "quote_exact",
        "quote_prefix",
        "quote_suffix",
        "status",
        "note_title",
        "has_body",
    }
    assert rows[0]["anchor"] == "ch1"
    assert rows[0]["quote_exact"] == "quick brown fox"
    assert rows[0]["status"] == "active"
    UUID(rows[0]["note_id"])


def test_list_source_highlights_carries_note_title_and_body_flag(
    notes_client: TestClient, db_conn: Connection
) -> None:
    # CAP-19: the rail labels each entry from the origin note and tells a bare
    # highlight from an annotated one, without a second request.
    user_id = _register(notes_client, "hl-rail@example.com")
    csrf = _csrf(notes_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(
        db_conn,
        source_id,
        anchor="ch1",
        block_html="<p>The quick brown fox jumps over the lazy dog.</p>",
    )
    bare = _post_highlight(
        notes_client,
        source_id,
        {"anchor": "ch1", "quote_exact": "quick brown", "title": "Bare quote"},
        csrf=csrf,
    )
    annotated = _post_highlight(
        notes_client,
        source_id,
        {
            "anchor": "ch1",
            "quote_exact": "lazy dog",
            "title": "On dogs",
            "body_markdown": "A thought.",
        },
        csrf=csrf,
    )
    assert bare.status_code == 201, bare.text
    assert annotated.status_code == 201, annotated.text

    resp = notes_client.get(f"/api/sources/{source_id}/highlights")

    assert resp.status_code == 200, resp.text
    by_title = {row["note_title"]: row for row in resp.json()}
    assert set(by_title) == {"Bare quote", "On dogs"}
    assert by_title["Bare quote"]["has_body"] is False
    assert by_title["On dogs"]["has_body"] is True


def test_list_source_highlights_non_owner_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    source_id = _capture(notes_client, db_conn, "hl-list-owner@example.com")

    _register(notes_client, "hl-list-intruder@example.com")  # become a different user
    resp = notes_client.get(f"/api/sources/{source_id}/highlights")
    assert resp.status_code == 404, resp.text


def test_list_source_highlights_unknown_source_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "hl-list-404@example.com")
    _csrf(notes_client)
    resp = notes_client.get(f"/api/sources/{uuid4()}/highlights")
    assert resp.status_code == 404, resp.text


def test_list_source_highlights_unauthenticated_returns_401(
    notes_client: TestClient, db_conn: Connection
) -> None:
    notes_client.cookies.clear()
    assert notes_client.get(f"/api/sources/{uuid4()}/highlights").status_code == 401
