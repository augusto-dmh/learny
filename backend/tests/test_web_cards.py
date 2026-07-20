"""C1 gate — cards router (integration, live test DB).

Exercises the owner-scoped card endpoints end-to-end through FastAPI's ``TestClient``
against a real Postgres, asserting the spec ACs at the route level:

- ``POST  /api/sources/{id}/cards/suggestions`` — owner → 200 grounded candidates;
  a passage the corpus no longer holds → 409; another user's / another source's
  anchor → identical 404; no session → 401; missing CSRF / untrusted Origin → 403
  (CAP-01, CAP-08, CAP-09).
- ``POST  /api/sources/{id}/cards`` — owner → 201 card + scheduling due now; the same
  text from the same highlight again → 200 with the same id and still one row; edited
  text persisted as sent; empty/over-long text → 422; non-owned anchor → 404; missing
  CSRF / untrusted Origin → 403 (CAP-05..07, CAP-09).
- ``PATCH /api/quiz-items/{id}`` — owner's highlight card → 200 with its id, ``due``,
  and review log untouched; a deck-origin card → 409; missing/non-owned → identical
  404; empty text → 422; missing CSRF / untrusted Origin → 403 (CAP-12).
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
    ParsedBlock,
    ParsedSection,
    QuizItem,
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

# A tight card-text cap so the over-cap 422 path is exercised cheaply; every card
# in this module stays well under it.
CARDS_MAX_CHARS = 60

# The passage every highlight in this module is taken from.
BLOCK_HTML = "<p>The quick brown fox jumps over the lazy dog.</p>"
QUOTE = "quick brown fox"


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def cards_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the cards router, isolated to a rolled-back txn.

    Mirrors ``notes_client`` (shared ``db_conn``, non-Secure cookie, trusted Origin,
    generous limiter) and pins ``quiz_max_card_chars`` so the over-cap reject stays
    cheap. The generation/embedding providers are pinned to the deterministic local
    adapters so the suggestion route never reaches a network provider.
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
    monkeypatch.setenv("LEARNY_QUIZ_MAX_CARD_CHARS", str(CARDS_MAX_CHARS))
    monkeypatch.setenv("LEARNY_GENERATION_PROVIDER", "local")
    monkeypatch.setenv("LEARNY_EMBEDDING_PROVIDER", "local")
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


def _headers(csrf: str | None, origin: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return headers


def _post_suggestions(
    client: TestClient,
    source_id: object,
    anchor_id: object,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.post(
        f"/api/sources/{source_id}/cards/suggestions",
        json={"note_anchor_id": str(anchor_id)},
        headers=_headers(csrf, origin),
    )


def _post_card(
    client: TestClient,
    source_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.post(
        f"/api/sources/{source_id}/cards", json=body, headers=_headers(csrf, origin)
    )


def _patch_card(
    client: TestClient,
    item_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.patch(
        f"/api/quiz-items/{item_id}", json=body, headers=_headers(csrf, origin)
    )


# --- Seeding -------------------------------------------------------------------


def _persist_source(db_conn: Connection, user_id: str, *, title: str = "A Book") -> UUID:
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


def _seed_corpus(
    db_conn: Connection, source_id: UUID, *, anchor: str = "ch1", block_html: str = BLOCK_HTML
) -> None:
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


def _capture_note(
    client: TestClient, source_id: UUID, csrf: str, *, title: str = "highlight"
) -> tuple[UUID, UUID]:
    """Capture a highlight over :data:`QUOTE`; return (note_id, note_anchor_id)."""
    resp = client.post(
        f"/api/sources/{source_id}/highlights",
        json={
            "anchor": "ch1",
            "quote_exact": QUOTE,
            "title": title,
            "body_markdown": "",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return UUID(body["id"]), UUID(body["anchors"][0]["id"])


def _capture(client: TestClient, source_id: UUID, csrf: str, *, title: str = "highlight") -> UUID:
    """Capture a highlight over :data:`QUOTE` and return its note-anchor id."""
    return _capture_note(client, source_id, csrf, title=title)[1]


def _seed_highlighted_source(
    client: TestClient, db_conn: Connection, email: str
) -> tuple[UUID, UUID, str]:
    """Register ``email``, seed a corpus + highlight; return (source_id, anchor_id, csrf)."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id)
    return source_id, _capture(client, source_id, csrf), csrf


def _accept_body(**overrides) -> dict:
    body = {
        "note_anchor_id": "",
        "item_type": QuizItemType.FREE_RECALL,
        "question": "What animal jumps?",
        "answer": "The fox",
    }
    body.update(overrides)
    return body


def _seed_deck_item(db_conn: Connection, source_id: UUID) -> QuizItem:
    """Persist a ``deck``-origin item directly — the identity-by-content-hash kind."""
    now = datetime.now(UTC)
    question = "What is the powerhouse of the cell?"
    answer = "Mitochondria"
    item = QuizItem(
        id=uuid4(),
        source_id=source_id,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        section_path=("Chapter 1",),
        anchor="ch1",
        source_excerpt=QUOTE,
        chunk_hash="c" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
        status=QuizItemStatus.ACTIVE,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    SqlAlchemyQuizItemRepository(db_conn).upsert(item, embedding=None)
    return item


# --- Suggestions (CAP-01, CAP-08, CAP-09) --------------------------------------


def test_suggestions_returns_grounded_candidates_for_own_highlight(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "sugg-ok@example.com"
    )

    resp = _post_suggestions(cards_client, source_id, anchor_id, csrf=csrf)

    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    assert suggestions, "the highlighted passage should yield at least one candidate"
    for suggestion in suggestions:
        assert suggestion["item_type"] in {QuizItemType.FREE_RECALL, QuizItemType.CLOZE}
        assert suggestion["question"] and suggestion["answer"]
        # CAP-03: every returned candidate is quoted verbatim from the passage.
        assert suggestion["anchor_quote"] in BLOCK_HTML


def test_suggestions_are_capped_at_the_configured_maximum(
    cards_client: TestClient, db_conn: Connection
) -> None:
    from app.core.config import get_settings

    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "sugg-cap@example.com"
    )

    resp = _post_suggestions(cards_client, source_id, anchor_id, csrf=csrf)

    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    # Non-empty first: a bare `<= cap` passes on an empty response, so the cap would
    # read as enforced even if the route had stopped generating anything at all.
    assert suggestions
    assert len(suggestions) <= get_settings().quiz_max_suggestions


def test_suggestions_persist_nothing(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # CAP-A2/AD-134: suggestions are ephemeral — only acceptance writes a row.
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "sugg-ephemeral@example.com"
    )

    assert _post_suggestions(cards_client, source_id, anchor_id, csrf=csrf).status_code == 200

    assert SqlAlchemyQuizItemRepository(db_conn).list_for_source(source_id) == []


def test_suggestions_for_a_vanished_passage_returns_409(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # The section the highlight was taken from is gone after a re-ingest: the student
    # is told to reload rather than shown a fabricated card.
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "sugg-stale@example.com"
    )
    _seed_corpus(db_conn, source_id, anchor="ch9", block_html="<p>Something else.</p>")

    resp = _post_suggestions(cards_client, source_id, anchor_id, csrf=csrf)

    assert resp.status_code == 409, resp.text


def test_suggestions_cross_owner_and_wrong_source_anchors_return_identical_404(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # CAP-09: another user's highlight, an anchor on a different source, and an
    # unknown anchor are indistinguishable — no existence is disclosed, and never 403.
    owner_source, owner_anchor, _ = _seed_highlighted_source(
        cards_client, db_conn, "sugg-owner@example.com"
    )

    intruder_id = _register(cards_client, "sugg-intruder@example.com")
    csrf = _csrf(cards_client)
    other_source = _persist_source(db_conn, intruder_id, title="Another Book")
    _seed_corpus(db_conn, other_source)
    own_anchor = _capture(cards_client, other_source, csrf)
    second_source = _persist_source(db_conn, intruder_id, title="A Third Book")
    _seed_corpus(db_conn, second_source)

    cross_owner = _post_suggestions(cards_client, other_source, owner_anchor, csrf=csrf)
    wrong_source = _post_suggestions(cards_client, second_source, own_anchor, csrf=csrf)
    unknown = _post_suggestions(cards_client, other_source, uuid4(), csrf=csrf)
    non_owned_source = _post_suggestions(cards_client, owner_source, owner_anchor, csrf=csrf)

    assert cross_owner.status_code == 404, cross_owner.text
    assert wrong_source.status_code == 404, wrong_source.text
    assert unknown.status_code == 404, unknown.text
    # Never 403: a 403 would confirm the resource exists (CAP-09).
    assert non_owned_source.status_code == 404, non_owned_source.text
    # The three anchor-resolution failures are byte-identical to each other.
    assert cross_owner.json() == unknown.json()
    assert wrong_source.json() == unknown.json()


def test_suggestions_unauthenticated_returns_401(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, _ = _seed_highlighted_source(
        cards_client, db_conn, "sugg-unauth@example.com"
    )
    cards_client.cookies.clear()

    resp = _post_suggestions(cards_client, source_id, anchor_id, csrf="x")

    assert resp.status_code == 401, resp.text


def test_suggestions_missing_csrf_returns_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, _ = _seed_highlighted_source(
        cards_client, db_conn, "sugg-nocsrf@example.com"
    )

    resp = _post_suggestions(cards_client, source_id, anchor_id, csrf=None)

    assert resp.status_code == 403, resp.text


def test_suggestions_untrusted_origin_returns_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "sugg-origin@example.com"
    )

    resp = _post_suggestions(
        cards_client, source_id, anchor_id, csrf=csrf, origin="http://evil.example.com"
    )

    assert resp.status_code == 403, resp.text


# --- Accept (CAP-05..07, CAP-09) -----------------------------------------------


def test_accept_returns_201_with_provenance_and_schedules_the_card(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-ok@example.com"
    )

    resp = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["origin"] == "highlight"
    assert body["note_anchor_id"] == str(anchor_id)
    assert body["question"] == "What animal jumps?"
    assert body["citation"]["anchor"] == "ch1"
    assert body["citation"]["source_excerpt"] == QUOTE
    # CAP-05: exactly one row, scheduled and already due.
    repo = SqlAlchemyQuizItemRepository(db_conn)
    assert len(repo.list_for_source(source_id)) == 1
    scheduling = repo.get_scheduling(UUID(body["id"]))
    assert scheduling is not None
    assert scheduling.due <= datetime.now(UTC) + timedelta(seconds=1)


def test_accept_persists_the_edited_text_as_submitted(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # CAP-06: text the student reworded before accepting is stored verbatim.
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-edited@example.com"
    )

    resp = _post_card(
        cards_client,
        source_id,
        _accept_body(
            note_anchor_id=str(anchor_id),
            question="Which animal is quick?",
            answer="The brown fox",
        ),
        csrf=csrf,
    )

    assert resp.status_code == 201, resp.text
    stored = SqlAlchemyQuizItemRepository(db_conn).get_by_id(UUID(resp.json()["id"]))
    assert stored is not None
    assert stored.question == "Which animal is quick?"
    assert stored.answer == "The brown fox"


def test_reaccepting_the_same_card_returns_200_with_the_same_id(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # Double-submit edge case: the first accept creates (201), the second returns the
    # existing card (200) and no duplicate row appears.
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-idempotent@example.com"
    )
    body = _accept_body(note_anchor_id=str(anchor_id))

    first = _post_card(cards_client, source_id, body, csrf=csrf)
    second = _post_card(cards_client, source_id, body, csrf=csrf)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert len(SqlAlchemyQuizItemRepository(db_conn).list_for_source(source_id)) == 1


def test_accept_empty_question_or_answer_returns_422(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-empty@example.com"
    )

    blank_question = _post_card(
        cards_client,
        source_id,
        _accept_body(note_anchor_id=str(anchor_id), question="   "),
        csrf=csrf,
    )
    blank_answer = _post_card(
        cards_client,
        source_id,
        _accept_body(note_anchor_id=str(anchor_id), answer=""),
        csrf=csrf,
    )

    assert blank_question.status_code == 422, blank_question.text
    assert blank_answer.status_code == 422, blank_answer.text
    assert SqlAlchemyQuizItemRepository(db_conn).list_for_source(source_id) == []


def test_accept_over_long_text_returns_422(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-toolong@example.com"
    )

    resp = _post_card(
        cards_client,
        source_id,
        _accept_body(note_anchor_id=str(anchor_id), answer="x" * (CARDS_MAX_CHARS + 1)),
        csrf=csrf,
    )

    assert resp.status_code == 422, resp.text
    assert SqlAlchemyQuizItemRepository(db_conn).list_for_source(source_id) == []


def test_accept_cross_owner_anchor_returns_404_and_writes_nothing(
    cards_client: TestClient, db_conn: Connection
) -> None:
    owner_source, owner_anchor, _ = _seed_highlighted_source(
        cards_client, db_conn, "accept-owner@example.com"
    )

    intruder_id = _register(cards_client, "accept-intruder@example.com")
    csrf = _csrf(cards_client)
    other_source = _persist_source(db_conn, intruder_id, title="Another Book")
    _seed_corpus(db_conn, other_source)

    cross_owner = _post_card(
        cards_client, other_source, _accept_body(note_anchor_id=str(owner_anchor)), csrf=csrf
    )
    unknown = _post_card(
        cards_client, other_source, _accept_body(note_anchor_id=str(uuid4())), csrf=csrf
    )

    assert cross_owner.status_code == 404, cross_owner.text
    assert unknown.status_code == 404, unknown.text
    assert cross_owner.json() == unknown.json()
    assert SqlAlchemyQuizItemRepository(db_conn).list_for_source(owner_source) == []
    assert SqlAlchemyQuizItemRepository(db_conn).list_for_source(other_source) == []


def test_accept_missing_csrf_returns_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, _ = _seed_highlighted_source(
        cards_client, db_conn, "accept-nocsrf@example.com"
    )

    resp = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=None
    )

    assert resp.status_code == 403, resp.text


def test_accept_untrusted_origin_returns_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-origin@example.com"
    )

    resp = _post_card(
        cards_client,
        source_id,
        _accept_body(note_anchor_id=str(anchor_id)),
        csrf=csrf,
        origin="http://evil.example.com",
    )

    assert resp.status_code == 403, resp.text


# --- Edit (CAP-12) -------------------------------------------------------------


def test_patch_rewrites_text_and_leaves_identity_and_scheduling_untouched(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "patch-ok@example.com"
    )
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text
    item_id = UUID(created.json()["id"])
    repo = SqlAlchemyQuizItemRepository(db_conn)
    due_before = repo.get_scheduling(item_id)

    resp = _patch_card(
        cards_client,
        item_id,
        {"question": "Which animal jumps?", "answer": "A fox"},
        csrf=csrf,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(item_id)
    assert resp.json()["question"] == "Which animal jumps?"
    assert repo.get_scheduling(item_id) == due_before


def test_patch_of_a_deck_origin_card_returns_409(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # A deck card's identity *is* its content hash, so its text is not rewritable.
    user_id = _register(cards_client, "patch-deck@example.com")
    csrf = _csrf(cards_client)
    source_id = _persist_source(db_conn, user_id)
    item = _seed_deck_item(db_conn, source_id)

    resp = _patch_card(
        cards_client, item.id, {"question": "Reworded?", "answer": "No"}, csrf=csrf
    )

    assert resp.status_code == 409, resp.text
    stored = SqlAlchemyQuizItemRepository(db_conn).get_by_id(item.id)
    assert stored is not None and stored.question == item.question


def test_patch_missing_and_non_owned_return_identical_404(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "patch-owner@example.com"
    )
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    _register(cards_client, "patch-intruder@example.com")
    intruder_csrf = _csrf(cards_client)

    non_owned = _patch_card(
        cards_client, item_id, {"question": "Mine now", "answer": "No"}, csrf=intruder_csrf
    )
    missing = _patch_card(
        cards_client, uuid4(), {"question": "Mine now", "answer": "No"}, csrf=intruder_csrf
    )

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_patch_empty_text_returns_422(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "patch-empty@example.com"
    )
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text

    resp = _patch_card(
        cards_client, created.json()["id"], {"question": "  ", "answer": "A fox"}, csrf=csrf
    )

    assert resp.status_code == 422, resp.text


def test_patch_missing_csrf_and_untrusted_origin_return_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "patch-csrf@example.com"
    )
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    body = {"question": "Which animal jumps?", "answer": "A fox"}

    no_csrf = _patch_card(cards_client, item_id, body, csrf=None)
    bad_origin = _patch_card(
        cards_client, item_id, body, csrf=csrf, origin="http://evil.example.com"
    )

    assert no_csrf.status_code == 403, no_csrf.text
    assert bad_origin.status_code == 403, bad_origin.text


def test_accepted_card_appears_in_the_due_queue(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # The capture loop closes: a card accepted at the passage is reviewable at once.
    source_id, anchor_id, csrf = _seed_highlighted_source(
        cards_client, db_conn, "accept-due@example.com"
    )
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text

    resp = cards_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    assert [i["id"] for i in resp.json()["items"]] == [created.json()["id"]]


# --- Provenance at review (CAP-15, CAP-16) -------------------------------------


def test_due_queue_shows_the_origin_note_title_for_a_highlight_card(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "prov-title@example.com")
    csrf = _csrf(cards_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id)
    note_id, anchor_id = _capture_note(cards_client, source_id, csrf, title="On foxes")
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text

    resp = cards_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    view = resp.json()["items"][0]
    assert view["provenance"] == {"note_id": str(note_id), "note_title": "On foxes"}


def test_deleting_the_origin_note_leaves_the_card_due_with_null_provenance(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # CAP-15: nothing in the notes aggregate may destroy a card. The link is severed,
    # the card stays reviewable from its own citation snapshot, and ``provenance`` is
    # explicitly null rather than absent or an error.
    user_id = _register(cards_client, "prov-deleted@example.com")
    csrf = _csrf(cards_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_corpus(db_conn, source_id)
    note_id, anchor_id = _capture_note(cards_client, source_id, csrf, title="On foxes")
    created = _post_card(
        cards_client, source_id, _accept_body(note_anchor_id=str(anchor_id)), csrf=csrf
    )
    assert created.status_code == 201, created.text

    deleted = cards_client.delete(
        f"/api/notes/{note_id}", headers={"X-CSRF-Token": csrf}
    )
    assert deleted.status_code == 204, deleted.text

    resp = cards_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    view = resp.json()["items"][0]
    assert view["id"] == created.json()["id"]
    assert view["provenance"] is None
    assert view["citation"]["source_excerpt"] == QUOTE


# --- Rate limiting (spec edge case: throttled on the quiz limiter) --------------


@pytest.fixture
def throttled_cards_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """``cards_client`` with a 3-attempt limiter so the 4th call trips.

    The card routes are the app's first synchronous LLM call inside a request
    handler, and ``rate_limit_quiz`` is what bounds that exposure. Without a test
    the dependency can be deleted from every route with the suite still green.
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
    monkeypatch.setenv("LEARNY_QUIZ_MAX_CARD_CHARS", str(CARDS_MAX_CHARS))
    monkeypatch.setenv("LEARNY_GENERATION_PROVIDER", "local")
    monkeypatch.setenv("LEARNY_EMBEDDING_PROVIDER", "local")
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


def test_suggestions_are_throttled_on_the_quiz_limiter(
    throttled_cards_client: TestClient, db_conn: Connection
) -> None:
    # Generation is the expensive leg — the limiter must trip regardless of outcome.
    source_id, anchor_id, csrf = _seed_highlighted_source(
        throttled_cards_client, db_conn, "suggest-rl@example.com"
    )
    for _ in range(3):
        _post_suggestions(throttled_cards_client, source_id, anchor_id, csrf=csrf)
    throttled = _post_suggestions(
        throttled_cards_client, source_id, anchor_id, csrf=csrf
    )
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


def test_accept_is_throttled_on_the_quiz_limiter(
    throttled_cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        throttled_cards_client, db_conn, "accept-rl@example.com"
    )
    body = _accept_body(note_anchor_id=str(anchor_id))
    for _ in range(3):
        _post_card(throttled_cards_client, source_id, body, csrf=csrf)
    throttled = _post_card(throttled_cards_client, source_id, body, csrf=csrf)
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


def test_patch_is_throttled_on_the_quiz_limiter(
    throttled_cards_client: TestClient, db_conn: Connection
) -> None:
    source_id, anchor_id, csrf = _seed_highlighted_source(
        throttled_cards_client, db_conn, "patch-rl@example.com"
    )
    created = _post_card(
        throttled_cards_client,
        source_id,
        _accept_body(note_anchor_id=str(anchor_id)),
        csrf=csrf,
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    edit = {"question": "Reworded?", "answer": "Yes"}
    # The limiter buckets per route, so the accept above spends nothing here.
    for _ in range(3):
        _patch_card(throttled_cards_client, item_id, edit, csrf=csrf)
    throttled = _patch_card(throttled_cards_client, item_id, edit, csrf=csrf)
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}




# --- Note promotion (NL-08, NL-09, NL-15) --------------------------------------

# A note body whose leading sentence has a maskable word, so the deterministic adapter
# derives a grounded free_recall + cloze pair from it.
NOTE_BODY = "Spaced repetition schedules reviews at expanding intervals."


def _persist_note(
    db_conn: Connection,
    user_id: str,
    *,
    title: str = "Memory",
    body: str = NOTE_BODY,
) -> UUID:
    """Seed a note directly on the test connection (the `/api/notes` UoW isn't overridden).

    The cards fixture only overrides the cards router's connection, so a note is seeded
    on ``db_conn`` the same way sources are — no dependency on the notes router's separate
    unit of work.
    """
    now = datetime.now(UTC)
    note = Note(
        id=uuid4(),
        user_id=UUID(user_id),
        title=title,
        body_markdown=body,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemyNoteRepository(db_conn).add(note).id


def _post_note_suggest(
    client: TestClient,
    note_id: object,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.post(
        f"/api/notes/{note_id}/cards/suggest", headers=_headers(csrf, origin)
    )


def _post_note_card(
    client: TestClient,
    note_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    return client.post(
        f"/api/notes/{note_id}/cards", json=body, headers=_headers(csrf, origin)
    )


def _note_accept_body(**overrides) -> dict:
    body = {
        "item_type": QuizItemType.FREE_RECALL,
        "question": "What schedules reviews?",
        "answer": "Spaced repetition",
    }
    body.update(overrides)
    return body


def test_note_suggest_returns_grounded_candidates(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-suggest@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)

    resp = _post_note_suggest(cards_client, note_id, csrf=csrf)

    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    assert suggestions
    for s in suggestions:
        assert s["item_type"] in {QuizItemType.FREE_RECALL, QuizItemType.CLOZE}
        # Grounded verbatim in the note body (the note IS the source, NL-08).
        assert s["anchor_quote"] in NOTE_BODY


def test_note_suggest_empty_body_returns_an_empty_list(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-empty@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id, body="")

    resp = _post_note_suggest(cards_client, note_id, csrf=csrf)

    assert resp.status_code == 200, resp.text
    assert resp.json()["suggestions"] == []


def test_note_promote_roundtrips_into_the_due_queue(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-promote@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)

    accepted = _post_note_card(cards_client, note_id, _note_accept_body(), csrf=csrf)
    assert accepted.status_code == 201, accepted.text
    card = accepted.json()
    assert card["origin"] == "note"
    assert card["source_id"] is None
    assert card["note_id"] == str(note_id)

    # The promoted card is due now and shows in the review queue as a note card.
    due = cards_client.get("/api/reviews/due")
    assert due.status_code == 200, due.text
    rows = {r["id"]: r for r in due.json()["items"]}
    assert card["id"] in rows
    assert rows[card["id"]]["source_title"] == "Your notes"
    assert rows[card["id"]]["source_id"] is None


def test_note_re_promote_is_idempotent(
    cards_client: TestClient, db_conn: Connection
) -> None:
    # NL-15: promoting the same text from one note twice returns the existing card.
    user_id = _register(cards_client, "owner-note-idem@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)

    first = _post_note_card(cards_client, note_id, _note_accept_body(), csrf=csrf)
    second = _post_note_card(cards_client, note_id, _note_accept_body(), csrf=csrf)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    # Exactly one card is due — no duplicate row.
    due = cards_client.get("/api/reviews/due")
    assert sum(1 for r in due.json()["items"] if r["id"] == first.json()["id"]) == 1


def test_note_promote_persists_edited_text(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-edit@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)

    body = _note_accept_body(question="My own wording?", answer="Spaced repetition")
    resp = _post_note_card(cards_client, note_id, body, csrf=csrf)

    assert resp.status_code == 201, resp.text
    assert resp.json()["question"] == "My own wording?"


def test_note_suggest_for_another_users_note_is_404(
    cards_client: TestClient, db_conn: Connection
) -> None:
    owner_id = _register(cards_client, "owner-note-a@example.com")
    _csrf(cards_client)
    note_id = _persist_note(db_conn, owner_id)

    _register(cards_client, "stranger-note-a@example.com")
    stranger_csrf = _csrf(cards_client)
    resp = _post_note_suggest(cards_client, note_id, csrf=stranger_csrf)

    assert resp.status_code == 404, resp.text


def test_note_promote_for_another_users_note_is_404(
    cards_client: TestClient, db_conn: Connection
) -> None:
    owner_id = _register(cards_client, "owner-note-b@example.com")
    _csrf(cards_client)
    note_id = _persist_note(db_conn, owner_id)

    _register(cards_client, "stranger-note-b@example.com")
    stranger_csrf = _csrf(cards_client)
    resp = _post_note_card(cards_client, note_id, _note_accept_body(), csrf=stranger_csrf)

    assert resp.status_code == 404, resp.text


def test_note_suggest_for_an_unknown_note_is_404(cards_client: TestClient) -> None:
    _register(cards_client, "owner-note-unknown@example.com")
    csrf = _csrf(cards_client)
    resp = _post_note_suggest(cards_client, uuid4(), csrf=csrf)
    assert resp.status_code == 404, resp.text


def test_note_promote_rejects_over_long_text(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-long@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)

    body = _note_accept_body(answer="y" * (CARDS_MAX_CHARS + 1))
    resp = _post_note_card(cards_client, note_id, body, csrf=csrf)

    assert resp.status_code == 422, resp.text


def test_note_suggest_without_a_session_is_401(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-unauth@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)
    cards_client.cookies.clear()

    resp = _post_note_suggest(cards_client, note_id, csrf=csrf)
    assert resp.status_code == 401, resp.text


def test_note_suggest_without_csrf_is_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-csrf1@example.com")
    _csrf(cards_client)  # establish the CSRF cookie; the request omits the header
    note_id = _persist_note(db_conn, user_id)

    resp = _post_note_suggest(cards_client, note_id, csrf=None)
    assert resp.status_code == 403, resp.text


def test_note_promote_with_untrusted_origin_is_403(
    cards_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(cards_client, "owner-note-csrf2@example.com")
    csrf = _csrf(cards_client)
    note_id = _persist_note(db_conn, user_id)

    resp = _post_note_card(
        cards_client,
        note_id,
        _note_accept_body(),
        csrf=csrf,
        origin="https://evil.example.com",
    )
    assert resp.status_code == 403, resp.text
