"""T6 gate — notes + highlights router (integration, live test DB).

Exercises the owner-scoped notes endpoints end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec ACs at the route level:

- ``POST   /api/notes`` — owner → 201 note detail; over-cap body → 422; no session
  → 401; missing CSRF / untrusted Origin → 403; rate limit → 429 (NF-05/09).
- ``GET    /api/notes`` — owner → 200 summaries newest-first; ``?tag=`` filters
  case-insensitively; no session → 401 (NF-13).
- ``GET    /api/notes/{id}`` — owner → 200 detail; missing/non-owned → identical
  404; no session → 401 (NF-05/10).
- ``PATCH  /api/notes/{id}`` — owner → 200 rewritten; over-cap body → 422;
  missing/non-owned → 404; missing CSRF → 403 (NF-05).
- ``DELETE /api/notes/{id}`` — owner → 204; missing/non-owned → 404; missing CSRF →
  403 (NF-05).
- ``GET    /api/notes/{id}/backlinks`` — owner → 200 inbound links; unknown → 404
  (NF-10).
- ``POST   /api/sources/{id}/highlights`` — owned ready source → 201 note + anchor
  jump-back fields; unknown source / unknown anchor → 404; stale selection → 409;
  missing CSRF → 403 (NF-06/10).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import (
    CorpusSectionRecord,
    ParsedBlock,
    ParsedSection,
    SectionChunk,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemySourceRepository,
)
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db

# A tight body cap so the over-cap 422 path is exercised cheaply; every note body
# in this module stays well under it.
NOTES_MAX_BODY = 50


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def notes_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the notes routers, isolated to a rolled-back txn.

    Mirrors ``sources_client`` (shared ``db_conn``, non-Secure cookie, trusted
    Origin, generous limiter) but pins ``notes_max_body_chars`` to
    :data:`NOTES_MAX_BODY` so the over-cap reject stays cheap. Every note path is one
    atomic request, so no UoW-factory override is needed.
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
    monkeypatch.setenv("LEARNY_NOTES_MAX_BODY_CHARS", str(NOTES_MAX_BODY))
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
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
    separate buckets and never eat into the note-write budget — the 4th ``POST
    /api/notes`` trips ``rate_limit_notes`` deterministically (NF-09).
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

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _post_note(
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
    return client.post("/api/notes", json=body, headers=headers)


def _patch_note(
    client: TestClient, note_id: object, body: dict, *, csrf: str | None
):
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
    client: TestClient, source_id: object, body: dict, *, csrf: str | None
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return client.post(f"/api/sources/{source_id}/highlights", json=body, headers=headers)


def _created_note(client: TestClient, csrf: str, **fields) -> dict:
    """Create a note through the API and return its detail body."""
    body = {"title": "Untitled", "body_markdown": "", "tags": []}
    body.update(fields)
    resp = _post_note(client, body, csrf=csrf)
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


# --- Create (NF-05/09) ---------------------------------------------------------


def test_create_note_returns_201_with_detail(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-create@example.com")
    csrf = _csrf(notes_client)

    resp = _post_note(
        notes_client,
        {"title": "First", "body_markdown": "hello", "tags": ["Python", "python"]},
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {
        "id",
        "title",
        "body_markdown",
        "tags",
        "anchors",
        "created_at",
        "updated_at",
    }
    assert body["title"] == "First"
    assert body["body_markdown"] == "hello"
    # Tags are normalized (lowercased + deduped) by the use case.
    assert body["tags"] == ["python"]
    assert body["anchors"] == []
    UUID(body["id"])


def test_create_note_over_cap_body_returns_422(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-toolong@example.com")
    csrf = _csrf(notes_client)
    resp = _post_note(
        notes_client,
        {"title": "Big", "body_markdown": "x" * (NOTES_MAX_BODY + 1)},
        csrf=csrf,
    )
    assert resp.status_code == 422, resp.text


def test_create_note_unauthenticated_returns_401(
    notes_client: TestClient, db_conn: Connection
) -> None:
    notes_client.cookies.clear()
    resp = _post_note(notes_client, {"title": "X"}, csrf="whatever")
    assert resp.status_code == 401, resp.text


def test_create_note_missing_csrf_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-nocsrf@example.com")
    resp = _post_note(notes_client, {"title": "X"}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_create_note_untrusted_origin_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-origin@example.com")
    csrf = _csrf(notes_client)
    resp = _post_note(
        notes_client, {"title": "X"}, csrf=csrf, origin="http://evil.example.com"
    )
    assert resp.status_code == 403, resp.text


def test_create_note_rate_limit_returns_429(
    throttled_notes_client: TestClient, db_conn: Connection
) -> None:
    _register(throttled_notes_client, "note-rl@example.com")
    csrf = _csrf(throttled_notes_client)
    for _ in range(3):
        resp = _post_note(throttled_notes_client, {"title": "X"}, csrf=csrf)
        assert resp.status_code == 201, resp.text
    throttled = _post_note(throttled_notes_client, {"title": "X"}, csrf=csrf)
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


# --- List (NF-13) --------------------------------------------------------------


def test_list_notes_newest_edited_first_and_owner_scoped(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-list@example.com")
    csrf = _csrf(notes_client)
    _created_note(notes_client, csrf, title="First")
    _created_note(notes_client, csrf, title="Second")

    resp = notes_client.get("/api/notes")

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["title"] for r in rows] == ["Second", "First"]
    assert set(rows[0]) == {
        "id",
        "title",
        "tags",
        "anchor_statuses",
        "created_at",
        "updated_at",
    }


def test_list_notes_filters_by_tag_case_insensitively(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-tagfilter@example.com")
    csrf = _csrf(notes_client)
    _created_note(notes_client, csrf, title="Tagged", tags=["python"])
    _created_note(notes_client, csrf, title="Untagged")

    resp = notes_client.get("/api/notes", params={"tag": "PYTHON"})

    assert resp.status_code == 200, resp.text
    assert [r["title"] for r in resp.json()] == ["Tagged"]


def test_list_notes_unauthenticated_returns_401(
    notes_client: TestClient, db_conn: Connection
) -> None:
    notes_client.cookies.clear()
    assert notes_client.get("/api/notes").status_code == 401


# --- Get (NF-05/10) ------------------------------------------------------------


def test_get_note_returns_200_detail(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-get@example.com")
    csrf = _csrf(notes_client)
    note = _created_note(notes_client, csrf, title="Readable", body_markdown="body")

    resp = notes_client.get(f"/api/notes/{note['id']}")

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Readable"
    assert resp.json()["body_markdown"] == "body"


def test_get_note_missing_and_non_owned_return_identical_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-get-owner@example.com")
    note = _created_note(notes_client, _csrf(notes_client), title="Owned")

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
    _register(notes_client, "note-update@example.com")
    csrf = _csrf(notes_client)
    note = _created_note(notes_client, csrf, title="Old", tags=["old"])

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
    _register(notes_client, "note-update-cap@example.com")
    csrf = _csrf(notes_client)
    note = _created_note(notes_client, csrf, title="X")
    resp = _patch_note(
        notes_client,
        note["id"],
        {"title": "X", "body_markdown": "x" * (NOTES_MAX_BODY + 1)},
        csrf=csrf,
    )
    assert resp.status_code == 422, resp.text


def test_update_note_non_owned_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-update-owner@example.com")
    note = _created_note(notes_client, _csrf(notes_client), title="Owned")

    _register(notes_client, "note-update-intruder@example.com")
    csrf = _csrf(notes_client)
    resp = _patch_note(notes_client, note["id"], {"title": "Hijack"}, csrf=csrf)
    assert resp.status_code == 404, resp.text


def test_update_note_missing_csrf_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-update-csrf@example.com")
    csrf = _csrf(notes_client)
    note = _created_note(notes_client, csrf, title="X")
    resp = _patch_note(notes_client, note["id"], {"title": "Y"}, csrf=None)
    assert resp.status_code == 403, resp.text


# --- Delete (NF-05) ------------------------------------------------------------


def test_delete_note_returns_204_then_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-delete@example.com")
    csrf = _csrf(notes_client)
    note = _created_note(notes_client, csrf, title="Doomed")

    resp = _delete_note(notes_client, note["id"], csrf=csrf)
    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    # It is gone afterwards.
    assert notes_client.get(f"/api/notes/{note['id']}").status_code == 404


def test_delete_note_non_owned_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-delete-owner@example.com")
    note = _created_note(notes_client, _csrf(notes_client), title="Owned")

    _register(notes_client, "note-delete-intruder@example.com")
    csrf = _csrf(notes_client)
    resp = _delete_note(notes_client, note["id"], csrf=csrf)
    assert resp.status_code == 404, resp.text


def test_delete_note_missing_csrf_returns_403(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-delete-csrf@example.com")
    csrf = _csrf(notes_client)
    note = _created_note(notes_client, csrf, title="X")
    resp = _delete_note(notes_client, note["id"], csrf=None)
    assert resp.status_code == 403, resp.text


# --- Backlinks (NF-10) ---------------------------------------------------------


def test_backlinks_returns_inbound_links(
    notes_client: TestClient, db_conn: Connection
) -> None:
    _register(notes_client, "note-backlinks@example.com")
    csrf = _csrf(notes_client)
    target = _created_note(notes_client, csrf, title="Target")
    linker = _created_note(notes_client, csrf, title="Link", body_markdown="[[Target]]")

    resp = notes_client.get(f"/api/notes/{target['id']}/backlinks")

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert [r["note_id"] for r in rows] == [linker["id"]]
    assert rows[0]["title"] == "Link"


def test_backlinks_unknown_note_returns_404(
    notes_client: TestClient, db_conn: Connection
) -> None:
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
