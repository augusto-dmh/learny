"""D3 gate — quiz + review routers (integration, live test DB).

Exercises the owner-scoped quiz endpoints end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec ACs at the route level:

- ``POST /api/sources/{id}/quiz/deck`` — owned ready source → 202 job + enqueue
  after commit; second while active → 409; not-ready → 409; missing/non-owned →
  identical 404; no session → 401; missing CSRF / untrusted Origin → 403; rate
  limit → 429; enqueue failure → 502 with the job compensated to ``failed``
  (QUIZ-03/04/18).
- ``GET  /api/sources/{id}/quiz`` — owner → 200 items + counts + due count + latest
  job; missing/non-owned → 404 (QUIZ-14).
- ``GET  /api/reviews/due`` — owner → 200 items + total; over-100 limit → 422;
  ``source_id`` filter honoured; no session → 401 (QUIZ-13).
- ``POST /api/quiz-items/{id}/reviews`` — owner active item → 200 updated
  scheduling + logged; rating ∉ 1..4 → 422; stale/orphaned → 409; missing/non-owned
  → 404; missing CSRF → 403; rate limit → 429 (QUIZ-12/18).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select, update

from app.application.dates import local_day
from app.application.quiz_qc import content_key
from app.domain.entities import (
    Note,
    QuizGenerationJob,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    SchedulingSnapshot,
    Source,
)
from app.infrastructure.db.metadata import review_log, sources, study_days
from app.infrastructure.db.repositories import (
    SqlAlchemyNoteRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.scheduling.fsrs import INTERVAL_LABELS
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db

pytestmark = requires_db

_SCHEDULING_FIELDS = {
    "state",
    "step",
    "stability",
    "difficulty",
    "due",
    "last_review",
    "interval_labels",
}


def _assert_interval_labels(labels: dict) -> None:
    assert {int(k) for k in labels} == {1, 2, 3, 4}
    assert set(labels.values()) <= INTERVAL_LABELS
    assert all(isinstance(value, str) for value in labels.values())


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _post_deck(
    client: TestClient, source_id: object, *, csrf: str | None, origin: str | None = None
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.post(f"/api/sources/{source_id}/quiz/deck", headers=headers)


def _post_starter(
    client: TestClient, source_id: object, *, csrf: str | None, origin: str | None = None
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.post(f"/api/sources/{source_id}/quiz/starter", headers=headers)


def _post_review(
    client: TestClient,
    item_id: object,
    body: dict,
    *,
    csrf: str | None,
    origin: str | None = None,
    client_tz: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    if client_tz is not None:
        headers["X-Client-Timezone"] = client_tz
    return client.post(f"/api/quiz-items/{item_id}/reviews", json=body, headers=headers)


def _post_undo(
    client: TestClient,
    *,
    csrf: str | None,
    origin: str | None = None,
    client_tz: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    if client_tz is not None:
        headers["X-Client-Timezone"] = client_tz
    return client.post("/api/reviews/undo", headers=headers)


def _post_flag(
    client: TestClient,
    item_id: object,
    *,
    flagged: bool,
    csrf: str | None,
    origin: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.post(
        f"/api/quiz-items/{item_id}/flag", json={"flagged": flagged}, headers=headers
    )


# --- Seeding -------------------------------------------------------------------


def _persist_source(
    db_conn: Connection, user_id: str, *, status: str = "ready", title: str = "A Book"
) -> UUID:
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
        status=status,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source).id


def _seed_ready_source(
    client: TestClient, db_conn: Connection, email: str, **kw
) -> tuple[str, str]:
    """Register ``email``, seed an owned ready source, return (source_id, csrf)."""
    user_id = _register(client, email)
    csrf = _csrf(client)
    source_id = _persist_source(db_conn, user_id, **kw)
    return str(source_id), csrf


def _seed_item(
    db_conn: Connection,
    source_id: UUID,
    *,
    status: str = QuizItemStatus.ACTIVE,
    question: str = "What is the powerhouse of the cell?",
    answer: str = "Mitochondria",
    due: datetime | None = None,
    with_scheduling: bool = True,
) -> QuizItem:
    now = datetime.now(UTC)
    item = QuizItem(
        id=uuid4(),
        source_id=source_id,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        source_excerpt="The mitochondria is the powerhouse of the cell.",
        chunk_hash="c" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
        status=status,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    repo.upsert(item, embedding=None)
    if with_scheduling:
        repo.create_scheduling(
            item.id,
            SchedulingSnapshot(
                state=1,
                step=0,
                stability=None,
                difficulty=None,
                due=due or (now - timedelta(hours=1)),
                last_review=None,
            ),
        )
    return item


def _seed_sample_with_templates(
    client: TestClient,
    db_conn: Connection,
    *,
    operator_email: str,
    learner_email: str,
) -> tuple[str, str]:
    """Seed the shared sample with five deck templates; return (sample_id, learner csrf)."""
    db_conn.execute(update(sources).where(sources.c.is_sample.is_(True)).values(is_sample=False))
    operator_id = _register(client, operator_email)
    now = datetime.now(UTC)
    sample = Source(
        id=uuid4(),
        user_id=UUID(operator_id),
        title="The Art of War",
        filename="art-of-war.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{operator_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
        is_sample=True,
    )
    SqlAlchemySourceRepository(db_conn).add(sample)
    for n in range(5):
        _seed_item(
            db_conn,
            sample.id,
            question=f"Question {n}?",
            answer=f"Answer {n}",
        )
    _register(client, learner_email)
    return str(sample.id), _csrf(client)


def _seed_job(
    db_conn: Connection, source_id: UUID, *, status: str = QuizJobStatus.QUEUED
) -> QuizGenerationJob:
    now = datetime.now(UTC)
    job = QuizGenerationJob(
        id=uuid4(),
        source_id=source_id,
        status=status,
        attempts=0,
        generated_count=0,
        discarded_count=0,
        failed_sections=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemyQuizJobRepository(db_conn).add(job)


# --- Deck POST: 202 + enqueue (QUIZ-03) ----------------------------------------


def test_deck_post_returns_202_and_enqueues_after_commit(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "deck-ok@example.com")

    resp = _post_deck(quiz_client, source_id, csrf=csrf)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == QuizJobStatus.QUEUED
    assert body["generated_count"] == 0
    UUID(body["id"])
    # The job row was created and the enqueuer was called with matching ids.
    stored = SqlAlchemyQuizJobRepository(db_conn).get_by_id(UUID(body["id"]))
    assert stored is not None and stored.status == QuizJobStatus.QUEUED
    calls = quiz_client.app.state.quiz_enqueuer.calls
    assert calls == [(UUID(source_id), UUID(body["id"]))]


def test_deck_post_second_while_active_returns_409(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # QUIZ-04: a queued/running job already exists → the second POST is a 409.
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "deck-conflict@example.com")
    _seed_job(db_conn, UUID(source_id), status=QuizJobStatus.RUNNING)

    resp = _post_deck(quiz_client, source_id, csrf=csrf)

    assert resp.status_code == 409, resp.text


def test_deck_post_not_ready_source_returns_409(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(
        quiz_client, db_conn, "deck-notready@example.com", status="uploaded"
    )

    resp = _post_deck(quiz_client, source_id, csrf=csrf)

    assert resp.status_code == 409, resp.text


def test_deck_post_missing_and_non_owned_return_identical_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    owned_id, _ = _seed_ready_source(quiz_client, db_conn, "deck-owner@example.com")

    _register(quiz_client, "deck-intruder@example.com")  # become a different user
    csrf = _csrf(quiz_client)

    non_owned = _post_deck(quiz_client, owned_id, csrf=csrf)
    missing = _post_deck(quiz_client, str(uuid4()), csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_deck_post_unauthenticated_returns_401(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "deck-unauth@example.com")
    quiz_client.cookies.clear()
    resp = _post_deck(quiz_client, source_id, csrf="x")
    assert resp.status_code == 401, resp.text


def test_deck_post_missing_csrf_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "deck-nocsrf@example.com")
    resp = _post_deck(quiz_client, source_id, csrf=None)
    assert resp.status_code == 403, resp.text


def test_deck_post_untrusted_origin_returns_403(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "deck-origin@example.com")
    resp = _post_deck(quiz_client, source_id, csrf=csrf, origin="http://evil.example.com")
    assert resp.status_code == 403, resp.text


def test_starter_post_on_sample_returns_five_items(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    tag = uuid4().hex[:8]
    sample_id, csrf = _seed_sample_with_templates(
        quiz_client,
        db_conn,
        operator_email=f"starter-op-{tag}@example.com",
        learner_email=f"starter-learner-{tag}@example.com",
    )

    resp = _post_starter(quiz_client, sample_id, csrf=csrf)

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 5
    assert {item["status"] for item in items} == {QuizItemStatus.ACTIVE}
    assert {item["question"] for item in items} == {f"Question {n}?" for n in range(5)}
    assert len({item["id"] for item in items}) == 5


def test_starter_post_on_owned_non_sample_returns_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(
        quiz_client, db_conn, f"starter-owned-{uuid4().hex[:8]}@example.com"
    )
    resp = _post_starter(quiz_client, source_id, csrf=csrf)
    missing = _post_starter(quiz_client, uuid4(), csrf=csrf)
    assert resp.status_code == 404, resp.text
    assert missing.status_code == 404, missing.text
    assert resp.json() == missing.json()


def test_starter_post_unauthenticated_returns_401(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    tag = uuid4().hex[:8]
    sample_id, _csrf_token = _seed_sample_with_templates(
        quiz_client,
        db_conn,
        operator_email=f"starter-unauth-op-{tag}@example.com",
        learner_email=f"starter-unauth-learner-{tag}@example.com",
    )
    quiz_client.cookies.clear()
    resp = _post_starter(quiz_client, sample_id, csrf="x")
    assert resp.status_code == 401, resp.text


def test_starter_post_missing_csrf_returns_403(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    tag = uuid4().hex[:8]
    sample_id, _csrf_token = _seed_sample_with_templates(
        quiz_client,
        db_conn,
        operator_email=f"starter-nocsrf-op-{tag}@example.com",
        learner_email=f"starter-nocsrf-learner-{tag}@example.com",
    )
    resp = _post_starter(quiz_client, sample_id, csrf=None)
    assert resp.status_code == 403, resp.text


def test_starter_post_untrusted_origin_returns_403(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    tag = uuid4().hex[:8]
    sample_id, csrf = _seed_sample_with_templates(
        quiz_client,
        db_conn,
        operator_email=f"starter-origin-op-{tag}@example.com",
        learner_email=f"starter-origin-learner-{tag}@example.com",
    )
    resp = _post_starter(quiz_client, sample_id, csrf=csrf, origin="http://evil.example.com")
    assert resp.status_code == 403, resp.text


def test_deck_post_enqueue_failure_returns_502_and_compensates_job(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # An enqueue failure after commit → 502, and the queued job is driven terminal
    # ``failed`` so no phantom job blocks a retry (QUIZ-04 guard stays clear).
    from app.infrastructure.web.dependencies import get_quiz_deck_enqueuer
    from tests.fakes import FakeQuizDeckEnqueuer

    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "deck-502@example.com")
    failing = FakeQuizDeckEnqueuer(error=RuntimeError("broker down"))
    quiz_client.app.dependency_overrides[get_quiz_deck_enqueuer] = lambda: failing
    try:
        resp = _post_deck(quiz_client, source_id, csrf=csrf)
    finally:
        quiz_client.app.dependency_overrides.pop(get_quiz_deck_enqueuer, None)

    assert resp.status_code == 502, resp.text
    assert "broker down" not in resp.text
    # The job was created then compensated to terminal failed (not left queued).
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    latest = jobs.get_latest_for_source(UUID(source_id))
    assert latest is not None
    assert latest.status == QuizJobStatus.FAILED
    assert jobs.get_active_for_source(UUID(source_id)) is None


@pytest.fixture
def throttled_quiz_client(  # noqa: ANN201
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
):
    """Like ``quiz_client`` but with a deliberately tight quiz limiter (3/window)."""
    from contextlib import contextmanager

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import (
        get_db_connection,
        get_quiz_deck_enqueuer,
        get_quiz_uow,
    )
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app
    from tests.fakes import FakeQuizDeckEnqueuer

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))

    app = create_app()

    def _override_conn() -> Iterator[Connection]:
        yield db_conn

    @contextmanager
    def _shared_uow() -> Iterator[Connection]:
        yield db_conn

    enqueuer = FakeQuizDeckEnqueuer()
    app.dependency_overrides[get_db_connection] = _override_conn
    app.dependency_overrides[get_quiz_uow] = lambda: lambda: _shared_uow()
    app.dependency_overrides[get_quiz_deck_enqueuer] = lambda: enqueuer
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous)
    get_settings.cache_clear()


def test_deck_post_rate_limit_returns_429(
    throttled_quiz_client: TestClient, db_conn: Connection
) -> None:
    # The limiter (per-IP+route) trips before the handler: the first POST creates the
    # queued job (202), the next two hit the single-in-flight 409, and the 4th is
    # throttled to 429 regardless — the rate limit is enforced ahead of the conflict.
    source_id, csrf = _seed_ready_source(throttled_quiz_client, db_conn, "deck-rl@example.com")
    for _ in range(3):
        _post_deck(throttled_quiz_client, source_id, csrf=csrf)
    throttled = _post_deck(throttled_quiz_client, source_id, csrf=csrf)
    assert throttled.status_code == 429, throttled.text
    assert "retry-after" in {k.lower() for k in throttled.headers}


# --- Overview GET (QUIZ-14) ----------------------------------------------------


def test_overview_returns_items_counts_due_and_latest_job(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "overview@example.com")
    sid = UUID(source_id)
    now = datetime.now(UTC)
    due_item = _seed_item(db_conn, sid, question="Due one", due=now - timedelta(hours=1))
    _seed_item(db_conn, sid, question="Future", answer="later", due=now + timedelta(days=1))
    _seed_item(db_conn, sid, question="Stale one", answer="x", status=QuizItemStatus.STALE)
    _seed_job(db_conn, sid, status=QuizJobStatus.SUCCEEDED)

    resp = quiz_client.get(f"/api/sources/{source_id}/quiz")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "counts_by_status", "due_count", "latest_job"}
    assert len(body["items"]) == 3
    assert body["counts_by_status"] == {QuizItemStatus.ACTIVE: 2, QuizItemStatus.STALE: 1}
    # Only the active past-due item counts toward due_count (future + stale excluded).
    assert body["due_count"] == 1
    assert body["latest_job"]["status"] == QuizJobStatus.SUCCEEDED
    assert body["latest_job"]["discard_reasons"] == {}
    item_view = next(i for i in body["items"] if i["id"] == str(due_item.id))
    assert set(item_view) == {"id", "item_type", "question", "status", "due"}
    assert item_view["item_type"] == QuizItemType.FREE_RECALL
    assert item_view["question"] == "Due one"
    assert item_view["status"] == QuizItemStatus.ACTIVE


def test_overview_exposes_job_discard_reasons(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "overview-reasons@example.com")
    sid = UUID(source_id)
    jobs = SqlAlchemyQuizJobRepository(db_conn)
    job = _seed_job(db_conn, sid, status=QuizJobStatus.RUNNING)
    jobs.update(
        job.succeeded(
            datetime.now(UTC),
            generated_count=0,
            discarded_count=3,
            failed_sections=0,
            discard_reasons={"generic_stem": 2, "duplicate": 1},
        )
    )

    resp = quiz_client.get(f"/api/sources/{source_id}/quiz")

    assert resp.status_code == 200, resp.text
    reasons = resp.json()["latest_job"]["discard_reasons"]
    assert reasons == {"generic_stem": 2, "duplicate": 1}
    assert sum(reasons.values()) == 3


def test_overview_no_job_returns_null_latest_job(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "overview-nojob@example.com")
    resp = quiz_client.get(f"/api/sources/{source_id}/quiz")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["latest_job"] is None
    assert body["items"] == []
    assert body["due_count"] == 0


def test_overview_missing_and_non_owned_return_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    owned_id, _ = _seed_ready_source(quiz_client, db_conn, "overview-owner@example.com")
    _register(quiz_client, "overview-intruder@example.com")

    non_owned = quiz_client.get(f"/api/sources/{owned_id}/quiz")
    missing = quiz_client.get(f"/api/sources/{uuid4()}/quiz")

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text


def test_overview_unauthenticated_returns_401(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "overview-401@example.com")
    quiz_client.cookies.clear()
    resp = quiz_client.get(f"/api/sources/{source_id}/quiz")
    assert resp.status_code == 401, resp.text


# --- Due queue GET (QUIZ-13) ---------------------------------------------------


def test_due_returns_items_and_total_with_full_card(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "due@example.com", title="Due Book")
    sid = UUID(source_id)
    now = datetime.now(UTC)
    item = _seed_item(db_conn, sid, question="What?", answer="This", due=now - timedelta(hours=2))
    _seed_item(db_conn, sid, question="Later?", answer="No", due=now + timedelta(days=1))

    resp = quiz_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_due"] == 1
    assert len(body["items"]) == 1
    view = body["items"][0]
    assert set(view) == {
        "id",
        "source_id",
        "source_title",
        "item_type",
        "question",
        "answer",
        "citation",
        "provenance",
        "status",
        "due",
        "note_changed",
        "interval_labels",
    }
    assert view["id"] == str(item.id)
    assert view["note_changed"] is False  # a deck card is never note-changed
    assert view["source_title"] == "Due Book"
    assert view["question"] == "What?"
    assert view["answer"] == "This"
    assert view["citation"] == {
        "section_path": ["Chapter 1"],
        "anchor": "ch1.xhtml",
        "source_excerpt": "The mitochondria is the powerhouse of the cell.",
    }
    _assert_interval_labels(view["interval_labels"])


def test_due_deck_card_is_queued_with_null_provenance(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # CAP-16: a whole-deck card has no origin note, so ``provenance`` is present and
    # explicitly null — and the card still appears in the queue like any other.
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "due-deck-prov@example.com")
    item = _seed_item(db_conn, UUID(source_id))

    resp = quiz_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    view = resp.json()["items"][0]
    assert view["id"] == str(item.id)
    assert "provenance" in view
    assert view["provenance"] is None


def test_due_over_max_limit_returns_422(quiz_client: TestClient, db_conn: Connection) -> None:
    _seed_ready_source(quiz_client, db_conn, "due-limit@example.com")
    resp = quiz_client.get("/api/reviews/due", params={"limit": 101})
    assert resp.status_code == 422, resp.text


def test_due_source_filter_scopes_to_one_source(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "due-filter@example.com")
    _csrf(quiz_client)
    source_a = _persist_source(db_conn, user_id, title="A")
    source_b = _persist_source(db_conn, user_id, title="B")
    now = datetime.now(UTC)
    in_a = _seed_item(db_conn, source_a, question="In A", due=now - timedelta(hours=1))
    _seed_item(db_conn, source_b, question="In B", answer="b", due=now - timedelta(hours=1))

    resp = quiz_client.get("/api/reviews/due", params={"source_id": str(source_a)})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_due"] == 1
    assert [i["id"] for i in body["items"]] == [str(in_a.id)]


def test_due_unauthenticated_returns_401(quiz_client: TestClient, db_conn: Connection) -> None:
    quiz_client.cookies.clear()
    resp = quiz_client.get("/api/reviews/due")
    assert resp.status_code == 401, resp.text


def test_due_session_caps_page_and_exposes_session_knobs(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "due-session@example.com")
    sid = UUID(source_id)
    now = datetime.now(UTC)
    for i in range(25):
        _seed_item(
            db_conn,
            sid,
            question=f"Question {i}?",
            answer=f"Answer {i}",
            due=now - timedelta(hours=1),
        )

    resp = quiz_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "total_due", "session_size", "requeue_minutes"}
    assert body["total_due"] == 25
    assert len(body["items"]) == 20
    assert body["session_size"] == 20
    assert body["requeue_minutes"] == 15
    for view in body["items"]:
        _assert_interval_labels(view["interval_labels"])


def test_due_query_limit_overrides_session_page_size(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "due-limit-override@example.com")
    sid = UUID(source_id)
    now = datetime.now(UTC)
    for i in range(10):
        _seed_item(
            db_conn,
            sid,
            question=f"Override {i}?",
            answer=f"A{i}",
            due=now - timedelta(hours=1),
        )

    resp = quiz_client.get("/api/reviews/due", params={"limit": 5})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_due"] == 10
    assert len(body["items"]) == 5
    assert body["session_size"] == 20
    assert body["requeue_minutes"] == 15


def test_due_preview_does_not_write_scheduling_or_review_log(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "due-preview-nowrite@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    repo = SqlAlchemyQuizItemRepository(db_conn)
    before = repo.get_scheduling(item.id)
    logged_before = db_conn.execute(
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()

    resp = quiz_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1
    _assert_interval_labels(resp.json()["items"][0]["interval_labels"])
    assert repo.get_scheduling(item.id) == before
    logged_after = db_conn.execute(
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert logged_after == logged_before == 0


# --- Review POST (QUIZ-12) -----------------------------------------------------


def test_review_advances_scheduling_and_logs(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "review@example.com")
    item = _seed_item(db_conn, UUID(source_id))

    resp = _post_review(quiz_client, item.id, {"rating": 3, "review_duration_ms": 4200}, csrf=csrf)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == _SCHEDULING_FIELDS
    _assert_interval_labels(body["interval_labels"])
    # Good schedules the next review in the future and records last_review.
    assert datetime.fromisoformat(body["due"]) > datetime.now(UTC)
    assert body["last_review"] is not None
    rows = db_conn.execute(
        select(review_log.c.rating, review_log.c.review_duration_ms).where(
            review_log.c.quiz_item_id == item.id
        )
    ).all()
    assert [(r.rating, r.review_duration_ms) for r in rows] == [(3, 4200)]


def test_review_with_client_timezone_credits_a_study_day(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # HOME-07/09: a review with the client-timezone header credits exactly one study day
    # with reviews_count=1 (no reading credit); the header adds no body fields (I-6).
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "review-study@example.com")
    item = _seed_item(db_conn, UUID(source_id))

    resp = _post_review(
        quiz_client, item.id, {"rating": 3}, csrf=csrf, client_tz="America/Sao_Paulo"
    )

    assert resp.status_code == 200, resp.text
    # The additive header leaks no fields into the SchedulingView body (I-6).
    assert set(resp.json()) == _SCHEDULING_FIELDS
    user_id = SqlAlchemySourceRepository(db_conn).get_by_id(UUID(source_id)).user_id
    rows = db_conn.execute(
        select(study_days.c.reviews_count, study_days.c.reading_updates).where(
            study_days.c.user_id == user_id
        )
    ).all()
    assert [(r.reviews_count, r.reading_updates) for r in rows] == [(1, 0)]


def test_review_garbage_timezone_succeeds_and_credits_utc_day(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # HOME-09: a garbage zone must not 4xx/5xx; the review is graded and the study day is
    # credited on the UTC date.
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "review-badtz@example.com")
    item = _seed_item(db_conn, UUID(source_id))

    before = datetime.now(UTC)
    resp = _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf, client_tz="Mars/Olympus")
    after = datetime.now(UTC)

    assert resp.status_code == 200, resp.text
    user_id = SqlAlchemySourceRepository(db_conn).get_by_id(UUID(source_id)).user_id
    row = db_conn.execute(
        select(study_days.c.day, study_days.c.reviews_count).where(study_days.c.user_id == user_id)
    ).one()
    assert row.reviews_count == 1
    assert row.day in {local_day(before, None), local_day(after, None)}


@pytest.mark.parametrize("rating", [0, 5, -1])
def test_review_rating_out_of_range_returns_422(
    quiz_client: TestClient, db_conn: Connection, rating: int
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, f"review-r{rating}@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    resp = _post_review(quiz_client, item.id, {"rating": rating}, csrf=csrf)
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("status", [QuizItemStatus.STALE, QuizItemStatus.ORPHANED])
def test_review_non_active_item_returns_409(
    quiz_client: TestClient, db_conn: Connection, status: str
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, f"review-{status}@example.com")
    item = _seed_item(db_conn, UUID(source_id), status=status)
    resp = _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf)
    assert resp.status_code == 409, resp.text


def test_review_missing_and_non_owned_return_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "review-owner@example.com")
    item = _seed_item(db_conn, UUID(source_id))

    _register(quiz_client, "review-intruder@example.com")  # become a different user
    csrf = _csrf(quiz_client)

    non_owned = _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf)
    missing = _post_review(quiz_client, uuid4(), {"rating": 3}, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_review_missing_csrf_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "review-csrf@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    resp = _post_review(quiz_client, item.id, {"rating": 3}, csrf=None)
    assert resp.status_code == 403, resp.text


def test_review_untrusted_origin_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "review-origin@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    resp = _post_review(
        quiz_client, item.id, {"rating": 3}, csrf=csrf, origin="http://evil.example.com"
    )
    assert resp.status_code == 403, resp.text


def test_review_rate_limit_returns_429(
    throttled_quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(throttled_quiz_client, db_conn, "review-rl@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    for _ in range(3):
        r = _post_review(throttled_quiz_client, item.id, {"rating": 3}, csrf=csrf)
        assert r.status_code == 200
    throttled = _post_review(throttled_quiz_client, item.id, {"rating": 3}, csrf=csrf)
    assert throttled.status_code == 429, throttled.text


# --- Note cards at review: badge + schedule reset (NL-12, NL-13) -----------------


def _seed_note_card(
    db_conn: Connection,
    user_id: str,
    *,
    status: str = QuizItemStatus.ACTIVE,
    due: datetime | None = None,
    flagged_at: datetime | None = None,
    title: str = "My note",
) -> tuple[QuizItem, UUID]:
    """Seed a source-less ``note`` card owned by ``user_id``; return (item, note_id)."""
    now = datetime.now(UTC)
    note = SqlAlchemyNoteRepository(db_conn).add(
        Note(
            id=uuid4(),
            user_id=UUID(user_id),
            title=title,
            body_markdown="a body",
            created_at=now,
            updated_at=now,
        )
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = QuizItem(
        id=uuid4(),
        source_id=None,
        user_id=UUID(user_id),
        origin=QuizItemOrigin.NOTE,
        note_id=note.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What does the note say?",
        answer="A fact.",
        section_path=(title,),
        anchor=f"note:{note.id}",
        source_excerpt="a body",
        chunk_hash="e" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, "What does the note say?", "A fact."),
        status=status,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    repo.upsert(item, embedding=None)
    repo.create_scheduling(
        item.id,
        SchedulingSnapshot(
            state=1,
            step=0,
            stability=None,
            difficulty=None,
            due=due or (now - timedelta(hours=1)),
            last_review=None,
        ),
    )
    if flagged_at is not None:
        repo.flag_note_changed(item.id, flagged_at)
    return item, note.id


def _post_reset(
    client: TestClient,
    item_id: object,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.post(f"/api/quiz-items/{item_id}/schedule-reset", headers=headers)


def test_due_queue_flags_a_changed_note_card_with_provenance(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "due-note-badge@example.com")
    _csrf(quiz_client)
    item, note_id = _seed_note_card(
        db_conn, user_id, flagged_at=datetime.now(UTC) + timedelta(hours=1)
    )

    resp = quiz_client.get("/api/reviews/due")

    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["items"] if r["id"] == str(item.id))
    assert row["note_changed"] is True
    assert row["source_title"] == "Your notes"
    assert row["provenance"]["note_id"] == str(note_id)


def test_due_queue_note_changed_false_for_a_deck_card(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _csrf_token = _seed_ready_source(quiz_client, db_conn, "due-deck-badge@example.com")
    item = _seed_item(db_conn, UUID(source_id))

    resp = quiz_client.get("/api/reviews/due")

    row = next(r for r in resp.json()["items"] if r["id"] == str(item.id))
    assert row["note_changed"] is False


def test_reset_fresh_schedule_and_clears_badge(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "reset-badge@example.com")
    csrf = _csrf(quiz_client)
    item, _note_id = _seed_note_card(
        db_conn, user_id, flagged_at=datetime.now(UTC) + timedelta(hours=1)
    )

    resp = _post_reset(quiz_client, item.id, csrf=csrf)

    assert resp.status_code == 200, resp.text
    # The badge has retired on the next due read.
    due = quiz_client.get("/api/reviews/due")
    row = next(r for r in due.json()["items"] if r["id"] == str(item.id))
    assert row["note_changed"] is False


def test_reset_non_active_item_returns_409(quiz_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(quiz_client, "reset-stale@example.com")
    csrf = _csrf(quiz_client)
    item, _note_id = _seed_note_card(db_conn, user_id, status=QuizItemStatus.STALE)

    resp = _post_reset(quiz_client, item.id, csrf=csrf)

    assert resp.status_code == 409, resp.text


def test_reset_non_owner_returns_404(quiz_client: TestClient, db_conn: Connection) -> None:
    owner_id = _register(quiz_client, "reset-owner@example.com")
    _csrf(quiz_client)
    item, _note_id = _seed_note_card(db_conn, owner_id)

    _register(quiz_client, "reset-intruder@example.com")
    intruder_csrf = _csrf(quiz_client)
    resp = _post_reset(quiz_client, item.id, csrf=intruder_csrf)

    assert resp.status_code == 404, resp.text


def test_reset_missing_csrf_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(quiz_client, "reset-nocsrf@example.com")
    _csrf(quiz_client)
    item, _note_id = _seed_note_card(db_conn, user_id)

    resp = _post_reset(quiz_client, item.id, csrf=None)

    assert resp.status_code == 403, resp.text


def test_reset_without_a_session_returns_401(quiz_client: TestClient, db_conn: Connection) -> None:
    user_id = _register(quiz_client, "reset-unauth@example.com")
    csrf = _csrf(quiz_client)
    item, _note_id = _seed_note_card(db_conn, user_id)
    quiz_client.cookies.clear()

    resp = _post_reset(quiz_client, item.id, csrf=csrf)

    assert resp.status_code == 401, resp.text


# --- Undo last review (REV-22..28) ----------------------------------------------


def test_undo_restores_scheduling_and_keeps_the_log(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "undo-ok@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    repo = SqlAlchemyQuizItemRepository(db_conn)
    before = repo.get_scheduling(item.id)

    graded = _post_review(quiz_client, item.id, {"rating": 4}, csrf=csrf)
    assert graded.status_code == 200, graded.text
    assert datetime.fromisoformat(graded.json()["due"]) != before.due

    resp = _post_undo(quiz_client, csrf=csrf)

    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == _SCHEDULING_FIELDS
    _assert_interval_labels(resp.json()["interval_labels"])
    assert repo.get_scheduling(item.id) == before
    row = db_conn.execute(
        select(review_log.c.rating, review_log.c.undone_at).where(
            review_log.c.quiz_item_id == item.id
        )
    ).one()
    assert row.rating == 4
    assert row.undone_at is not None
    user_id = SqlAlchemySourceRepository(db_conn).get_by_id(UUID(source_id)).user_id
    counts = db_conn.execute(
        select(study_days.c.reviews_count).where(study_days.c.user_id == user_id)
    ).all()
    assert [r.reviews_count for r in counts] == [0]


def test_undo_empty_returns_409(quiz_client: TestClient, db_conn: Connection) -> None:
    _seed_ready_source(quiz_client, db_conn, "undo-empty@example.com")
    csrf = _csrf(quiz_client)
    resp = _post_undo(quiz_client, csrf=csrf)
    assert resp.status_code == 409, resp.text


def test_undo_second_returns_409(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "undo-twice@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    assert _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf).status_code == 200
    assert _post_undo(quiz_client, csrf=csrf).status_code == 200
    resp = _post_undo(quiz_client, csrf=csrf)
    assert resp.status_code == 409, resp.text


def test_undo_does_not_see_another_users_review(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "undo-owner-web@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    assert _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf).status_code == 200

    _register(quiz_client, "undo-intruder-web@example.com")
    csrf = _csrf(quiz_client)
    resp = _post_undo(quiz_client, csrf=csrf)

    assert resp.status_code == 409, resp.text
    undone = db_conn.execute(
        select(review_log.c.undone_at).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert undone is None


def test_undo_missing_csrf_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "undo-csrf@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    csrf = _csrf(quiz_client)
    assert _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf).status_code == 200
    resp = _post_undo(quiz_client, csrf=None)
    assert resp.status_code == 403, resp.text


def test_undo_untrusted_origin_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "undo-origin@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    assert _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf).status_code == 200
    resp = _post_undo(quiz_client, csrf=csrf, origin="http://evil.example.com")
    assert resp.status_code == 403, resp.text


def test_undo_unauthenticated_returns_401(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "undo-unauth@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    assert _post_review(quiz_client, item.id, {"rating": 3}, csrf=csrf).status_code == 200
    quiz_client.cookies.clear()
    resp = _post_undo(quiz_client, csrf=csrf)
    assert resp.status_code == 401, resp.text


def test_undo_rate_limit_returns_429(
    throttled_quiz_client: TestClient, db_conn: Connection
) -> None:
    _seed_ready_source(throttled_quiz_client, db_conn, "undo-rl@example.com")
    csrf = _csrf(throttled_quiz_client)
    for _ in range(3):
        r = _post_undo(throttled_quiz_client, csrf=csrf)
        assert r.status_code == 409
    throttled = _post_undo(throttled_quiz_client, csrf=csrf)
    assert throttled.status_code == 429, throttled.text


# --- Flag out of due (REV-34..36, REV-38) ---------------------------------------


def test_flag_removes_item_from_due_and_unflag_restores(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "flag-due@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    repo = SqlAlchemyQuizItemRepository(db_conn)
    before = repo.get_scheduling(item.id)

    flagged = _post_flag(quiz_client, item.id, flagged=True, csrf=csrf)
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["flagged"] is True
    assert flagged.json()["flagged_at"] is not None
    due = quiz_client.get("/api/reviews/due")
    assert due.status_code == 200, due.text
    assert due.json()["total_due"] == 0
    assert due.json()["items"] == []
    assert repo.get_scheduling(item.id) == before

    unflagged = _post_flag(quiz_client, item.id, flagged=False, csrf=csrf)
    assert unflagged.status_code == 200, unflagged.text
    assert unflagged.json() == {"flagged": False, "flagged_at": None}
    restored = quiz_client.get("/api/reviews/due")
    assert restored.json()["total_due"] == 1
    assert [i["id"] for i in restored.json()["items"]] == [str(item.id)]
    assert repo.get_scheduling(item.id) == before


def test_flag_missing_and_non_owned_return_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "flag-owner-web@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    _register(quiz_client, "flag-intruder-web@example.com")
    csrf = _csrf(quiz_client)

    non_owned = _post_flag(quiz_client, item.id, flagged=True, csrf=csrf)
    missing = _post_flag(quiz_client, uuid4(), flagged=True, csrf=csrf)

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    assert non_owned.json() == missing.json()


def test_flag_unauthenticated_returns_401(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "flag-unauth@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    quiz_client.cookies.clear()
    resp = _post_flag(quiz_client, item.id, flagged=True, csrf=csrf)
    assert resp.status_code == 401, resp.text


def test_flag_rate_limit_returns_429(
    throttled_quiz_client: TestClient, db_conn: Connection
) -> None:
    source_id, csrf = _seed_ready_source(throttled_quiz_client, db_conn, "flag-rl@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    for _ in range(3):
        r = _post_flag(throttled_quiz_client, item.id, flagged=True, csrf=csrf)
        assert r.status_code == 200, r.text
    throttled = _post_flag(throttled_quiz_client, item.id, flagged=True, csrf=csrf)
    assert throttled.status_code == 429, throttled.text


def test_flag_missing_csrf_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, _ = _seed_ready_source(quiz_client, db_conn, "flag-csrf@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    resp = _post_flag(quiz_client, item.id, flagged=True, csrf=None)
    assert resp.status_code == 403, resp.text


def test_flag_untrusted_origin_returns_403(quiz_client: TestClient, db_conn: Connection) -> None:
    source_id, csrf = _seed_ready_source(quiz_client, db_conn, "flag-origin@example.com")
    item = _seed_item(db_conn, UUID(source_id))
    resp = _post_flag(
        quiz_client, item.id, flagged=True, csrf=csrf, origin="http://evil.example.com"
    )
    assert resp.status_code == 403, resp.text
