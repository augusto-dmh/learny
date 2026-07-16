"""C2 gate — POST /api/sources/{id}/questions router (integration, live test DB).

Exercises the owner-scoped cited-Q&A endpoint end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec's acceptance criteria
at the route level (QA-01..04, 07..11, 13, 17, 22):

- owner + a question a ready source supports → 200 ``answered`` with grounded
  citations carrying the QA-02 anchor fields, ``retrieval`` diagnostics and
  ``model`` (QA-01/02/04);
- a question the source cannot support → 200 ``not_found_in_source`` with empty
  citations, the same diagnostics on the outcome (QA-04/13);
- missing/non-owned source → 404 with identical bodies (QA-07); owned but
  not-ready → 409 (QA-08); blank/whitespace and over-long question → 422, with
  the exactly-max-chars question accepted (QA-09/10 + edge);
- no session → 401, bad CSRF / untrusted Origin → 403 (QA-11);
- the generation port raising → 502 with a generic body, no internal detail
  (QA-17); the questions rate limit → 429 + ``Retry-After`` (QA-22).

Corpus + embedding seeding mirrors ``test_web_retrieval``: the deterministic
embedding adapter embeds both the seeded chunk and the query, so the semantic
arm is reproducible on the shared rolled-back ``db_conn``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.domain.entities import (
    AnswerTextDelta,
    CorpusSectionRecord,
    Evidence,
    GeneratedAnswer,
    ParsedSection,
    QuestionAnswer,
    SectionChunk,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db

_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_MODEL = "local-extractive"


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _ask(
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
    return client.post(f"/api/sources/{source_id}/questions", json=body, headers=headers)


# --- Corpus seeding (single known chunk, mirrors test_web_retrieval) ------------


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


def _seed_photosynthesis_corpus(db_conn: Connection, source_id: UUID) -> None:
    chunk = SectionChunk(
        index=0, text=_PHOTO, section_path=("Biology",), anchor="bio.xhtml#p", page_span=None
    )
    section = CorpusSectionRecord(
        section=ParsedSection(
            position=0,
            title="Biology",
            depth=0,
            section_path=("Biology",),
            anchor="bio.xhtml",
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
    """Register ``email``, seed an owned+embedded one-chunk corpus, return (id, csrf)."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_photosynthesis_corpus(db_conn, source_id)
    _embed_all(db_conn, source_id)
    return str(source_id), csrf


# --- 200 answered (QA-01/02/04) ------------------------------------------------


def test_ask_answered_returns_200_with_grounded_citations_and_diagnostics(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-01/02/04: a question the ready source supports → 200 answered, non-empty
    # answer, grounded citations carrying exactly the anchor fields, and the
    # retrieval + model diagnostics.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "own@example.com")

    resp = _ask(auth_client, source_id, {"question": "photosynthesis sunlight energy"}, csrf=csrf)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer_status"] == "answered"
    assert body["answer"] == _PHOTO  # extractive answer is the one chunk's snippet
    assert body["model"] == _MODEL
    assert body["retrieval"] == {"strategy": "hybrid", "evidence_count": 1}

    assert len(body["citations"]) == 1, "the single grounded chunk is cited exactly once"
    citation = body["citations"][0]
    assert set(citation) == {
        "chunk_id",
        "source_id",
        "section_path",
        "anchor",
        "page_span",
        "snippet",
        "score",
    }
    assert citation["source_id"] == source_id
    assert citation["section_path"] == ["Biology"]
    assert citation["anchor"] == "bio.xhtml#p"
    assert citation["snippet"] == _PHOTO
    assert citation["page_span"] is None
    UUID(citation["chunk_id"])  # a real chunk id is projected

    # No duplicate chunk ids in the citation set (QA-02).
    chunk_ids = [c["chunk_id"] for c in body["citations"]]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_ask_trims_question_before_calling_service(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-01 normalization: the validator strips the question and passes the
    # TRIMMED value to the service (asserted by spying on the wired service).
    from app.infrastructure.web.dependencies import get_ask_question

    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "trim@example.com")

    captured: dict[str, str] = {}

    class _SpyService:
        def __call__(self, *, user, source_id, question) -> QuestionAnswer:  # noqa: ANN001
            captured["question"] = question
            return QuestionAnswer(
                status="not_found_in_source",
                text="",
                citations=(),
                evidence_count=0,
                model=_MODEL,
            )

    auth_client.app.dependency_overrides[get_ask_question] = lambda: _SpyService()
    try:
        resp = _ask(auth_client, source_id, {"question": "  photosynthesis  "}, csrf=csrf)
    finally:
        auth_client.app.dependency_overrides.pop(get_ask_question, None)

    assert resp.status_code == 200, resp.text
    assert captured["question"] == "photosynthesis"


# --- 200 not found (QA-04/13) --------------------------------------------------


def test_ask_no_supporting_evidence_returns_200_not_found(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-13: a question with no supporting evidence → 200 not_found_in_source,
    # empty citations, empty answer, diagnostics still present (evidence_count 0).
    user_id = _register(auth_client, "none@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_photosynthesis_corpus(db_conn, source_id)  # corpus present, NOT embedded

    resp = _ask(
        auth_client,
        str(source_id),
        {"question": "zzzqqq nonsensical unmatchable token"},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer_status"] == "not_found_in_source"
    assert body["answer"] == ""
    assert body["citations"] == []
    assert body["model"] == _MODEL
    assert body["retrieval"] == {"strategy": "hybrid", "evidence_count": 0}


# --- 401 / 403 auth + CSRF (QA-11) ---------------------------------------------


def test_ask_unauthenticated_returns_401(auth_client: TestClient, db_conn: Connection) -> None:
    # QA-11: no session → 401.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "unauth@example.com")
    auth_client.cookies.clear()
    resp = _ask(auth_client, source_id, {"question": "photosynthesis"}, csrf="whatever")
    assert resp.status_code == 401, resp.text


def test_ask_missing_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    # QA-11: a state-changing POST without the CSRF token → 403.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "nocsrf@example.com")
    resp = _ask(auth_client, source_id, {"question": "photosynthesis"}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_ask_invalid_csrf_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    # QA-11: a wrong CSRF token → 403.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "badcsrf@example.com")
    resp = _ask(auth_client, source_id, {"question": "photosynthesis"}, csrf="not-the-token")
    assert resp.status_code == 403, resp.text


def test_ask_untrusted_origin_returns_403(auth_client: TestClient, db_conn: Connection) -> None:
    # QA-11: an untrusted Origin on a state-changing POST → 403.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "origin@example.com")
    resp = _ask(
        auth_client,
        source_id,
        {"question": "photosynthesis"},
        csrf=csrf,
        origin="http://evil.example.com",
    )
    assert resp.status_code == 403, resp.text


# --- 404 ownership, identical bodies (QA-07) -----------------------------------


def test_ask_missing_and_non_owned_source_return_identical_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-07: a missing source and another user's source both → 404 with the exact
    # same body — existence is never disclosed.
    owned_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "owner@example.com")

    _register(auth_client, "intruder@example.com")  # become a different user
    csrf = _csrf(auth_client)

    non_owned = _ask(auth_client, owned_id, {"question": "photosynthesis"}, csrf=csrf)
    missing = _ask(auth_client, str(uuid4()), {"question": "photosynthesis"}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


# --- 409 readiness (QA-08) -----------------------------------------------------


def test_ask_not_ready_source_returns_409(auth_client: TestClient, db_conn: Connection) -> None:
    # QA-08: an owned source whose status != "ready" → 409, naming the state.
    user_id = _register(auth_client, "notready@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id, status="uploaded")

    resp = _ask(auth_client, str(source_id), {"question": "photosynthesis"}, csrf=csrf)

    assert resp.status_code == 409, resp.text
    assert resp.json() == {"detail": "Source is not ready for questions."}


# --- 422 validation (QA-09/10 + edge) ------------------------------------------


def test_ask_blank_question_returns_422(auth_client: TestClient, db_conn: Connection) -> None:
    # QA-09: an empty question is rejected with 422 before the service runs.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "blank@example.com")
    resp = _ask(auth_client, source_id, {"question": ""}, csrf=csrf)
    assert resp.status_code == 422, resp.text
    assert "answer_status" not in resp.json()


def test_ask_missing_question_field_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-09: a body without the question key is rejected with 422 before the
    # service runs.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "missing@example.com")
    resp = _ask(auth_client, source_id, {}, csrf=csrf)
    assert resp.status_code == 422, resp.text
    assert "answer_status" not in resp.json()


def test_ask_whitespace_question_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-09: a whitespace-only question is rejected with 422 (trimmed → empty).
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "ws@example.com")
    resp = _ask(auth_client, source_id, {"question": "   "}, csrf=csrf)
    assert resp.status_code == 422, resp.text


def test_ask_over_long_question_returns_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-10: a trimmed question longer than LEARNY_QA_QUESTION_MAX_CHARS → 422.
    from app.core.config import get_settings

    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "long@example.com")
    over = "a" * (get_settings().qa_question_max_chars + 1)
    resp = _ask(auth_client, source_id, {"question": over}, csrf=csrf)
    assert resp.status_code == 422, resp.text


def test_ask_exactly_max_chars_is_accepted(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # Edge case: a trimmed question of exactly LEARNY_QA_QUESTION_MAX_CHARS chars
    # is accepted (bound is inclusive) — reaches the service (200), not 422.
    from app.core.config import get_settings

    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "max@example.com")
    exact = "a" * get_settings().qa_question_max_chars
    resp = _ask(auth_client, source_id, {"question": exact}, csrf=csrf)
    assert resp.status_code == 200, resp.text


# --- 502 generation failure, generic body (QA-17) ------------------------------


def test_ask_generation_failure_returns_502_generic(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # QA-17: the generation port raising → 502 with a generic body that leaks no
    # provider/internal detail (the raised message must not appear in the body).
    from app.infrastructure.web.dependencies import get_answer_generation

    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "boom@example.com")

    class _RaisingAdapter:
        model = _MODEL

        def generate(self, *, question: str, evidence: Sequence[Evidence]) -> GeneratedAnswer:
            raise RuntimeError("provider-secret-internal-detail")

    auth_client.app.dependency_overrides[get_answer_generation] = lambda: _RaisingAdapter()
    try:
        resp = _ask(auth_client, source_id, {"question": "photosynthesis sunlight"}, csrf=csrf)
    finally:
        auth_client.app.dependency_overrides.pop(get_answer_generation, None)

    assert resp.status_code == 502, resp.text
    assert resp.json() == {"detail": "Answer generation failed. Please try again."}
    assert "provider-secret-internal-detail" not in resp.text


# --- 429 rate limit (QA-22) ----------------------------------------------------


@pytest.fixture
def throttled_questions_client(  # noqa: ANN201
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
):
    """Like ``auth_client`` but with a deliberately tight questions limiter.

    Mirrors ``throttled_client``: 3 attempts per long window so the 4th
    ``POST /api/sources/{id}/questions`` trips the ``rate_limit_questions`` 429
    branch deterministically (QA-22). The per-IP+route key means the register/csrf
    setup calls consume separate buckets and never eat the questions budget.
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


def test_ask_rate_limit_returns_429_with_retry_after(
    throttled_questions_client: TestClient, db_conn: Connection
) -> None:
    # QA-22: once the window is exceeded, the endpoint returns 429 + Retry-After.
    source_id, csrf = _seed_owned_embedded_source(
        throttled_questions_client, db_conn, "rl@example.com"
    )
    # First 3 questions pass the limiter (200 answered).
    for _ in range(3):
        resp = _ask(
            throttled_questions_client, source_id, {"question": "photosynthesis"}, csrf=csrf
        )
        assert resp.status_code == 200, resp.text
    # The 4th is throttled before reaching the service.
    throttled = _ask(
        throttled_questions_client, source_id, {"question": "photosynthesis"}, csrf=csrf
    )
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


# --- POST /questions/stream (SSE, GEN-14..17) ----------------------------------
#
# Derived from the P2 SSE ACs (GEN-14..17) at the route level: the deterministic
# provider streams the UI Message Stream v1 frame sequence with its header; the
# pre-stream guards surface as the same plain HTTP errors as the JSON sibling
# (404/409/422/429, plus the CSRF 403 dependency); a mid-stream provider failure is
# rendered as a protocol ``error`` part (headers already sent); and the not-found
# outcome emits the status part with no text.


def _ask_stream(
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
    return client.post(
        f"/api/sources/{source_id}/questions/stream", json=body, headers=headers
    )


def _parse_ui_stream(text: str) -> list:
    """Parse an SSE ``text/event-stream`` body into its UI Message Stream parts.

    Each part is the JSON of a ``data:`` line (comment/keepalive lines ignored); the
    terminal ``data: [DONE]`` marker is kept verbatim as the string ``"[DONE]"``.
    """
    parts: list = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: ") :]
            parts.append(payload if payload == "[DONE]" else json.loads(payload))
    return parts


def _part_types(parts: list) -> list[str]:
    return [p["type"] if isinstance(p, dict) else p for p in parts]


def test_ask_stream_emits_full_frame_sequence_and_header(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-14: the answered stream emits start → text-start → text-delta → text-end →
    # data-citations → data-answer-status → finish → [DONE] under the header.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "sstream@example.com")

    resp = _ask_stream(
        auth_client, source_id, {"question": "photosynthesis sunlight energy"}, csrf=csrf
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert resp.headers["content-type"].startswith("text/event-stream")

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
    delta = next(p for p in parts if p["type"] == "text-delta" if isinstance(p, dict))
    assert delta["delta"] == _PHOTO
    citations = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-citations")
    assert len(citations["data"]) == 1
    citation = citations["data"][0]
    assert set(citation) == {
        "chunk_id",
        "source_id",
        "section_path",
        "anchor",
        "page_span",
        "snippet",
        "score",
    }
    assert citation["source_id"] == source_id
    assert citation["anchor"] == "bio.xhtml#p"
    assert citation["snippet"] == _PHOTO
    UUID(citation["chunk_id"])
    status = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-answer-status")
    assert status["data"] == {"status": "answered"}


def test_ask_stream_not_found_emits_status_part_without_text(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-16 (not-found stream): no supporting evidence → no text-delta, empty
    # data-citations, and a not_found_in_source status part.
    user_id = _register(auth_client, "sstream-nf@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_photosynthesis_corpus(db_conn, source_id)  # corpus present, NOT embedded

    resp = _ask_stream(
        auth_client, str(source_id), {"question": "zzzqqq unmatchable token"}, csrf=csrf
    )

    assert resp.status_code == 200, resp.text
    parts = _parse_ui_stream(resp.text)
    assert _part_types(parts) == [
        "start",
        "text-start",
        "text-end",
        "data-citations",
        "data-answer-status",
        "finish",
        "[DONE]",
    ]
    citations = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-citations")
    assert citations["data"] == []
    status = next(p for p in parts if isinstance(p, dict) and p["type"] == "data-answer-status")
    assert status["data"] == {"status": "not_found_in_source"}


def test_ask_stream_missing_and_non_owned_source_return_plain_404(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-16: pre-stream ownership failure is a plain HTTP 404 (not SSE), identical
    # for a missing and a non-owned source.
    owned_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "s404-owner@example.com")
    _register(auth_client, "s404-intruder@example.com")
    csrf = _csrf(auth_client)

    non_owned = _ask_stream(auth_client, owned_id, {"question": "photosynthesis"}, csrf=csrf)
    missing = _ask_stream(auth_client, str(uuid4()), {"question": "photosynthesis"}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()  # plain JSON body, never SSE


def test_ask_stream_not_ready_returns_plain_409(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-16: pre-stream readiness failure is a plain HTTP 409.
    user_id = _register(auth_client, "s409@example.com")
    csrf = _csrf(auth_client)
    source_id = _persist_source(db_conn, user_id, status="uploaded")

    resp = _ask_stream(auth_client, str(source_id), {"question": "photosynthesis"}, csrf=csrf)

    assert resp.status_code == 409, resp.text
    assert resp.json() == {"detail": "Source is not ready for questions."}


def test_ask_stream_blank_question_returns_plain_422(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-16: pre-stream validation failure is a plain HTTP 422.
    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "s422@example.com")
    resp = _ask_stream(auth_client, source_id, {"question": "   "}, csrf=csrf)
    assert resp.status_code == 422, resp.text
    assert "start" not in resp.text


def test_ask_stream_missing_csrf_returns_403(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-14: the stream endpoint carries the same CSRF/Origin dependencies — a
    # state-changing POST without the token → 403 before any SSE byte.
    source_id, _ = _seed_owned_embedded_source(auth_client, db_conn, "s403@example.com")
    resp = _ask_stream(auth_client, source_id, {"question": "photosynthesis"}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_ask_stream_rate_limit_returns_429(
    throttled_questions_client: TestClient, db_conn: Connection
) -> None:
    # GEN-14: the stream endpoint shares the questions rate limiter — the 4th call
    # in the window is throttled with 429 before streaming.
    source_id, csrf = _seed_owned_embedded_source(
        throttled_questions_client, db_conn, "s429@example.com"
    )
    for _ in range(3):
        resp = _ask_stream(
            throttled_questions_client, source_id, {"question": "photosynthesis"}, csrf=csrf
        )
        assert resp.status_code == 200, resp.text
    throttled = _ask_stream(
        throttled_questions_client, source_id, {"question": "photosynthesis"}, csrf=csrf
    )
    assert throttled.status_code == 429, throttled.text


def test_ask_stream_mid_stream_failure_emits_error_part(
    auth_client: TestClient, db_conn: Connection
) -> None:
    # GEN-16: a provider failure after the first delta (headers already sent) is
    # rendered as a protocol error part with the generic message, then terminates —
    # no data-citations/finish, and no internal detail leaks.
    from app.infrastructure.web.dependencies import get_answer_generation

    source_id, csrf = _seed_owned_embedded_source(auth_client, db_conn, "s-mid@example.com")

    class _MidStreamRaisingAdapter:
        model = _MODEL

        def generate(self, *, question: str, evidence: Sequence[Evidence]) -> GeneratedAnswer:
            raise AssertionError("stream path must not call generate")

        def generate_stream(self, *, question: str, evidence: Sequence[Evidence]):
            yield AnswerTextDelta(text="partial ")
            raise RuntimeError("provider-secret-internal-detail")

    auth_client.app.dependency_overrides[get_answer_generation] = (
        lambda: _MidStreamRaisingAdapter()
    )
    try:
        resp = _ask_stream(
            auth_client, source_id, {"question": "photosynthesis sunlight"}, csrf=csrf
        )
    finally:
        auth_client.app.dependency_overrides.pop(get_answer_generation, None)

    assert resp.status_code == 200, resp.text
    parts = _parse_ui_stream(resp.text)
    types = _part_types(parts)
    assert "error" in types
    assert "data-citations" not in types
    assert "finish" not in types
    error_part = next(p for p in parts if isinstance(p, dict) and p["type"] == "error")
    assert error_part["errorText"] == "Answer generation failed. Please try again."
    assert "provider-secret-internal-detail" not in resp.text
    # The partial delta that streamed before the failure is present.
    assert any(
        isinstance(p, dict) and p["type"] == "text-delta" and p["delta"] == "partial "
        for p in parts
    )
