"""Structure + section read endpoints (integration, live test DB).

Exercises ``GET /api/sources/{id}/structure`` and ``GET /api/sources/{id}/section``
through FastAPI's ``TestClient`` against a real Postgres: the owner reads the nested
section tree (200 with the exact nested shape and values — titles, depths, section
paths, anchors, and child nesting built from the flat depth-ordered sections) and one
section's content by anchor (200 with the anchor round-tripped through the query
param), an unauthenticated caller gets 401, a missing source, another user's source,
and an owned source with no corpus all return 404 (A-7), an unknown anchor returns
404, and an empty/missing anchor returns 422. The GET carries no CSRF header and must
not be rejected.

Owned sources are created through the real upload flow (shared rolled-back
connection); corpus rows are seeded via ``SqlAlchemyCorpusRepository`` on that same
connection, mirroring how the ingestion read tests drive real services on ``db_conn``.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import CorpusSectionRecord, ParsedSection
from app.infrastructure.db.repositories import SqlAlchemyCorpusRepository
from tests.conftest import TEST_PASSWORD, requires_db

pytestmark = requires_db

EPUB_BYTES = b"PK\x03\x04-fake-but-nonempty-epub-payload"
EPUB_TYPE = "application/epub+zip"


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


def _create_source(client: TestClient, csrf: str, *, title: str = "My Book") -> str:
    resp = client.post(
        "/api/sources",
        data={"title": title},
        files={"file": ("book.epub", EPUB_BYTES, EPUB_TYPE)},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _section(
    *,
    position: int,
    title: str,
    depth: int,
    section_path: tuple[str, ...],
    anchor: str,
    markdown: str = "",
) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=depth,
            section_path=section_path,
            anchor=anchor,
            blocks=(),
        ),
        markdown=markdown,
        chunks=(),
    )


def _seed_corpus(conn: Connection, source_id: str) -> None:
    """Persist a two-level corpus (a depth-1 child under a depth-0 parent)."""
    SqlAlchemyCorpusRepository(conn).replace(
        UUID(source_id),
        title="The Test Book",
        authors=("Ada", "Alan"),
        language="en",
        schema_version=1,
        sections=(
            _section(
                position=0,
                title="Chapter 1",
                depth=0,
                section_path=("Chapter 1",),
                anchor="chapter01.xhtml",
            ),
            _section(
                position=1,
                title="Section 1.1",
                depth=1,
                section_path=("Chapter 1", "Section 1.1"),
                anchor="chapter01.xhtml#s11",
            ),
            _section(
                position=2,
                title="Chapter 2",
                depth=0,
                section_path=("Chapter 2",),
                anchor="chapter02.xhtml",
            ),
        ),
    )


def test_structure_returns_200_with_nested_tree_and_values(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "owner@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)
    _seed_corpus(db_conn, source_id)

    resp = sources_client.get(f"/api/sources/{source_id}/structure")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "The Test Book"
    assert body["authors"] == ["Ada", "Alan"]
    assert body["language"] == "en"

    # Two top-level sections; the depth-1 section nests under the preceding depth-0.
    sections = body["sections"]
    assert len(sections) == 2

    chapter1 = sections[0]
    assert chapter1["title"] == "Chapter 1"
    assert chapter1["depth"] == 0
    assert chapter1["section_path"] == ["Chapter 1"]
    assert chapter1["anchor"] == "chapter01.xhtml"
    assert len(chapter1["children"]) == 1

    child = chapter1["children"][0]
    assert child["title"] == "Section 1.1"
    assert child["depth"] == 1
    assert child["section_path"] == ["Chapter 1", "Section 1.1"]
    assert child["anchor"] == "chapter01.xhtml#s11"
    assert child["children"] == []

    chapter2 = sections[1]
    assert chapter2["title"] == "Chapter 2"
    assert chapter2["depth"] == 0
    assert chapter2["children"] == []


def test_structure_get_requires_no_csrf(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "nocsrf@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)
    _seed_corpus(db_conn, source_id)

    # No X-CSRF-Token header on the read — a GET must not be CSRF-gated.
    resp = sources_client.get(f"/api/sources/{source_id}/structure")

    assert resp.status_code != 403
    assert resp.status_code == 200, resp.text


def test_structure_unauthenticated_returns_401(sources_client: TestClient) -> None:
    _register(sources_client, "unauth@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)

    sources_client.cookies.clear()
    resp = sources_client.get(f"/api/sources/{source_id}/structure")
    assert resp.status_code == 401, resp.text


def test_structure_missing_source_returns_404(sources_client: TestClient) -> None:
    _register(sources_client, "missing@example.com")
    resp = sources_client.get(f"/api/sources/{uuid4()}/structure")
    assert resp.status_code == 404, resp.text


def test_structure_non_owner_source_returns_404(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "a@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)
    _seed_corpus(db_conn, source_id)

    _register(sources_client, "b@example.com")  # become another user
    resp = sources_client.get(f"/api/sources/{source_id}/structure")
    assert resp.status_code == 404, resp.text  # no existence disclosure


def test_structure_owned_source_without_corpus_returns_404(
    sources_client: TestClient,
) -> None:
    _register(sources_client, "nocorpus@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)

    # Source exists and is owned, but no corpus has been built yet (A-7).
    resp = sources_client.get(f"/api/sources/{source_id}/structure")
    assert resp.status_code == 404, resp.text


# ---- GET /api/sources/{id}/section (FE-14) --------------------------------

# An anchor bearing both ``/`` (href path) and ``#`` (fragment) — the reserved
# characters that must survive query-param round-tripping to the backend.
SECTION_ANCHOR = "text/ch1.xhtml#s2"


def _seed_section_corpus(conn: Connection, source_id: str) -> None:
    """Persist a corpus whose section carries markdown at ``SECTION_ANCHOR``."""
    SqlAlchemyCorpusRepository(conn).replace(
        UUID(source_id),
        title="The Test Book",
        authors=("Ada",),
        language="en",
        schema_version=1,
        sections=(
            _section(
                position=0,
                title="Section Two",
                depth=1,
                section_path=("Chapter 1", "Section Two"),
                anchor=SECTION_ANCHOR,
                markdown="## Section Two\n\nBody text.",
            ),
        ),
    )


def test_section_returns_200_with_content_round_tripping_the_anchor(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "sec-owner@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)
    _seed_section_corpus(db_conn, source_id)

    # The anchor carries ``/`` and ``#``; passing it via ``params`` proves the
    # encoded query param decodes back to the exact anchor server-side.
    resp = sources_client.get(
        f"/api/sources/{source_id}/section", params={"anchor": SECTION_ANCHOR}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["anchor"] == SECTION_ANCHOR
    assert body["title"] == "Section Two"
    assert body["section_path"] == ["Chapter 1", "Section Two"]
    assert body["markdown"] == "## Section Two\n\nBody text."


def test_section_unknown_anchor_returns_404(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "sec-unknown@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)
    _seed_section_corpus(db_conn, source_id)

    resp = sources_client.get(
        f"/api/sources/{source_id}/section", params={"anchor": "text/ch1.xhtml#nope"}
    )
    assert resp.status_code == 404, resp.text


def test_section_unauthenticated_returns_401(sources_client: TestClient) -> None:
    _register(sources_client, "sec-unauth@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)

    sources_client.cookies.clear()
    resp = sources_client.get(
        f"/api/sources/{source_id}/section", params={"anchor": SECTION_ANCHOR}
    )
    assert resp.status_code == 401, resp.text


def test_section_missing_source_returns_404(sources_client: TestClient) -> None:
    _register(sources_client, "sec-missing@example.com")
    resp = sources_client.get(
        f"/api/sources/{uuid4()}/section", params={"anchor": SECTION_ANCHOR}
    )
    assert resp.status_code == 404, resp.text


def test_section_non_owner_source_returns_404(
    sources_client: TestClient, db_conn: Connection
) -> None:
    _register(sources_client, "sec-a@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)
    _seed_section_corpus(db_conn, source_id)

    _register(sources_client, "sec-b@example.com")  # become another user
    resp = sources_client.get(
        f"/api/sources/{source_id}/section", params={"anchor": SECTION_ANCHOR}
    )
    assert resp.status_code == 404, resp.text  # no existence disclosure


def test_section_owned_source_without_corpus_returns_404(
    sources_client: TestClient,
) -> None:
    _register(sources_client, "sec-nocorpus@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)

    # Owned source, but no corpus built yet — indistinguishable from unknown anchor.
    resp = sources_client.get(
        f"/api/sources/{source_id}/section", params={"anchor": SECTION_ANCHOR}
    )
    assert resp.status_code == 404, resp.text


def test_section_empty_or_missing_anchor_returns_422(
    sources_client: TestClient,
) -> None:
    _register(sources_client, "sec-422@example.com")
    csrf = _csrf(sources_client)
    source_id = _create_source(sources_client, csrf)

    empty = sources_client.get(
        f"/api/sources/{source_id}/section", params={"anchor": ""}
    )
    assert empty.status_code == 422, empty.text

    missing = sources_client.get(f"/api/sources/{source_id}/section")
    assert missing.status_code == 422, missing.text
