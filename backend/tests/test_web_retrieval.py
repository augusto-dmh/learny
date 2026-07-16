"""T10 gate — /api/sources/{id}/retrieve router (integration, live test DB).

Exercises the owner-scoped hybrid retrieval endpoint end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec's P1 "Owner-scoped
retrieval endpoint" acceptance criteria (RET-18..22):

- owner + matching query over an embedded corpus → 200 with citation-ready
  evidence carrying anchor/section_path/snippet/score/chunk_id and NO internal
  storage fields (RET-18);
- empty/whitespace query, or ``top_k`` outside ``1..retrieval_max_top_k`` → 422
  without running retrieval (RET-19);
- another user's / a missing source → 404, existence never disclosed (RET-20);
- missing/invalid CSRF or an untrusted Origin → rejected (403), and no session
  → 401, before retrieval (RET-21);
- a query matching nothing → 200 with ``results: []`` (RET-22).

The user + session are created via the auth API; the source, its canonical
corpus, and (for the both-arm happy path) its chunk embeddings are seeded on the
shared rolled-back ``db_conn`` before the request, mirroring the ingestion web
tests. The deterministic embedding adapter embeds both the seeded chunks and the
query, so the semantic arm is reproducible.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.config import get_settings
from app.domain.entities import (
    CorpusSectionRecord,
    ParsedSection,
    SectionChunk,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import TEST_PASSWORD, requires_db

pytestmark = requires_db


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _retrieve(
    client: TestClient,
    source_id: str,
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
    return client.post(f"/api/sources/{source_id}/retrieve", json=body, headers=headers)


# --- Corpus seeding (mirrors tests/test_retrieval.py) --------------------------

_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_OCEAN = "ocean currents redistribute heat across the planet over time"
_QUANTUM = "quantum entanglement links distant particles instantly"


def _persist_source(db_conn: Connection, user_id: str) -> UUID:
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
    return SqlAlchemySourceRepository(db_conn).add(source).id


def _chunk(text: str, *, title: str, anchor: str) -> SectionChunk:
    return SectionChunk(
        index=0,
        text=text,
        section_path=(title,),
        anchor=anchor,
        page_span=None,
    )


def _section(position: int, title: str, anchor: str, chunk: SectionChunk) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=0,
            section_path=(title,),
            anchor=anchor,
            blocks=(),
        ),
        markdown="",
        chunks=(chunk,),
    )


def _seed_three_topic_corpus(db_conn: Connection, source_id: UUID) -> None:
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            _section(
                0, "Biology", "bio.xhtml", _chunk(_PHOTO, title="Biology", anchor="bio.xhtml#p")
            ),
            _section(
                1, "Geography", "geo.xhtml", _chunk(_OCEAN, title="Geography", anchor="geo.xhtml#o")
            ),
            _section(
                2, "Physics", "phys.xhtml", _chunk(_QUANTUM, title="Physics", anchor="phys.xhtml#q")
            ),
        ),
    )


def _embed_all(db_conn: Connection, source_id: UUID) -> None:
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source_id)
    vectors = adapter.embed_documents([c.text for c in chunks])
    index.set_embeddings(
        list(zip((c.id for c in chunks), vectors, strict=True)), model=adapter.model
    )


def _seed_owned_embedded_source(
    client: TestClient, db_conn: Connection, email: str
) -> tuple[str, str]:
    """Register ``email``, seed an owned corpus + embeddings, return (source_id, csrf)."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_three_topic_corpus(db_conn, source_id)
    _embed_all(db_conn, source_id)
    return str(source_id), csrf


# --- 200 happy path (RET-18) ---------------------------------------------------


def test_retrieve_owner_matching_query_returns_200_with_evidence(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # RET-18 / AC1: an authenticated owner POSTing a matching query for a
    # processed source gets 200 with the fused evidence list, each item carrying
    # citation anchors (chunk_id, source_id, section_path, anchor, page_span,
    # snippet) and a score.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "own@example.com")

    resp = _retrieve(auth_client, source_id, {"query": "photosynthesis sunlight energy"}, csrf=csrf)

    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results, "expected at least one evidence item for a matching query"

    hit = next((r for r in results if r["anchor"] == "bio.xhtml#p"), None)
    assert hit is not None, "expected the known Biology chunk in the results"
    assert hit["source_id"] == source_id
    assert hit["section_path"] == ["Biology"]
    assert hit["snippet"] == _PHOTO
    assert hit["page_span"] is None
    assert isinstance(hit["score"], (int, float)) and hit["score"] > 0
    UUID(hit["chunk_id"])  # a real chunk id is projected

    # The public view exposes ONLY citation fields — no internal storage columns.
    assert set(hit) == {
        "chunk_id",
        "source_id",
        "section_path",
        "anchor",
        "page_span",
        "snippet",
        "score",
    }
    assert "object_key" not in hit and "checksum" not in hit


# --- 422 validation (RET-19) ---------------------------------------------------


def test_retrieve_empty_query_returns_422(auth_client: TestClient, db_conn: Connection) -> None:
    # RET-19 / AC2: an empty query is rejected with 422 before retrieval runs.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "empty@example.com")
    resp = _retrieve(auth_client, source_id, {"query": ""}, csrf=csrf)
    assert resp.status_code == 422, resp.text
    assert "results" not in resp.json()  # retrieval never produced a body


def test_retrieve_whitespace_query_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # RET-19 / AC2: a whitespace-only query is rejected with 422 (not treated as
    # a real query) before retrieval runs.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "ws@example.com")
    resp = _retrieve(auth_client, source_id, {"query": "   "}, csrf=csrf)
    assert resp.status_code == 422, resp.text
    assert "results" not in resp.json()


def test_retrieve_top_k_zero_returns_422(auth_client: TestClient, db_conn: Connection) -> None:
    # RET-19 / AC2: top_k below the 1..MAX range is rejected with 422.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "tk0@example.com")
    resp = _retrieve(auth_client, source_id, {"query": "photosynthesis", "top_k": 0}, csrf=csrf)
    assert resp.status_code == 422, resp.text


def test_retrieve_top_k_over_max_returns_422(auth_client: TestClient, db_conn: Connection) -> None:
    # RET-19 / AC2: top_k above LEARNY_RETRIEVAL_MAX_TOP_K is rejected (not clamped).
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "tkmax@example.com")
    over = get_settings().retrieval_max_top_k + 1
    resp = _retrieve(auth_client, source_id, {"query": "photosynthesis", "top_k": over}, csrf=csrf)
    assert resp.status_code == 422, resp.text


# --- 404 ownership (RET-20) ----------------------------------------------------


def test_retrieve_non_owner_source_returns_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # RET-20 / AC3: another user's source returns 404 — existence not disclosed.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "owner@example.com")

    _register(auth_client, "intruder@example.com")  # become a different user
    csrf = _csrf(auth_client)
    resp = _retrieve(auth_client, source_id, {"query": "photosynthesis"}, csrf=csrf)

    assert resp.status_code == 404, resp.text


def test_retrieve_missing_source_returns_404(auth_client: TestClient) -> None:
    # RET-20 / AC3: a source that does not exist returns 404.
    _register(auth_client, "nosrc@example.com")
    csrf = _csrf(auth_client)
    resp = _retrieve(auth_client, str(uuid4()), {"query": "photosynthesis"}, csrf=csrf)
    assert resp.status_code == 404, resp.text


# --- 401 / 403 auth + CSRF (RET-21) --------------------------------------------


def test_retrieve_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    # RET-21 / AC4: no session → 401 before retrieval.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "unauth@example.com")
    auth_client.cookies.clear()
    resp = _retrieve(auth_client, source_id, {"query": "photosynthesis"}, csrf="whatever")
    assert resp.status_code == 401, resp.text


def test_retrieve_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    # RET-21 / AC4: a state-changing POST without the CSRF token → 403.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "nocsrf@example.com")
    resp = _retrieve(auth_client, source_id, {"query": "photosynthesis"}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_retrieve_invalid_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    # RET-21 / AC4: a wrong CSRF token → 403.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "badcsrf@example.com")
    resp = _retrieve(
        auth_client, source_id, {"query": "photosynthesis"}, csrf="not-the-session-token"
    )
    assert resp.status_code == 403, resp.text


def test_retrieve_untrusted_origin_returns_403(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # RET-21 / AC4: an untrusted Origin on a state-changing POST → 403.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "origin@example.com")
    resp = _retrieve(
        auth_client,
        source_id,
        {"query": "photosynthesis"},
        csrf=csrf,
        origin="http://evil.example.com",
    )
    assert resp.status_code == 403, resp.text


# --- 200 empty (RET-22) --------------------------------------------------------


def test_retrieve_nonsense_query_returns_200_empty(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # RET-22 / AC5: a query matching nothing returns 200 with an empty list, not
    # an error. Embeddings are left NULL so the semantic arm contributes nothing
    # and a non-lexical-matching query yields no results.
    user_id = _register(auth_client, "none@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_three_topic_corpus(db_conn, source_id)  # corpus present, NOT embedded

    resp = _retrieve(
        auth_client,
        str(source_id),
        {"query": "zzzqqq nonsensical unmatchable token"},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"results": []}
