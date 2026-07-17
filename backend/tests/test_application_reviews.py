"""D2 gate — review services (unit + integration, live test DB).

``GetDueQueue`` is exercised with a capturing fake repository to pin the
limit/default/cap and pass-through semantics (QUIZ-13, A-6). ``SubmitReview`` runs
against Postgres with the real FSRS adapter so the atomic scheduling-update +
log-append and the ownership/status branches are asserted on persisted state
(QUIZ-12): an active item advances and logs (early review allowed, A-4); a
stale/orphaned item is rejected (409 semantics); a missing or non-owned item is
indistinguishable (404 semantics, no disclosure).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, select

from app.application.errors import QuizItemNotFound, QuizItemNotReviewable
from app.application.identity import AuthorizeOwnership
from app.application.quiz_qc import content_key
from app.application.reviews import (
    DEFAULT_DUE_LIMIT,
    MAX_DUE_LIMIT,
    GetDueQueue,
    SubmitReview,
)
from app.domain.entities import (
    DueReviewItem,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    SchedulingSnapshot,
    Source,
    User,
)
from app.infrastructure.db.metadata import review_log
from app.infrastructure.db.repositories import (
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.scheduling.fsrs import FsrsSchedulingAdapter
from tests.conftest import requires_db
from tests.fakes import FakeClock

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)


# --- GetDueQueue (unit) ---------------------------------------------------------


class _CapturingItemRepo:
    """A ``QuizItemRepository`` double recording the ``due_for_user`` call args."""

    def __init__(self, result: tuple[int, list[DueReviewItem]]) -> None:
        self._result = result
        self.calls: list[dict] = []

    def due_for_user(
        self, user_id, *, now, limit, source_id=None
    ) -> tuple[int, list[DueReviewItem]]:  # noqa: ANN001
        self.calls.append(
            {"user_id": user_id, "now": now, "limit": limit, "source_id": source_id}
        )
        return self._result


def _user() -> User:
    return User(id=uuid4(), email="due@example.com", created_at=_NOW)


def test_due_queue_defaults_to_twenty_and_passes_user_and_now() -> None:
    repo = _CapturingItemRepo((0, []))
    user = _user()
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW))

    total, items = service(user=user)

    assert (total, items) == (0, [])
    call = repo.calls[0]
    assert call["limit"] == DEFAULT_DUE_LIMIT == 20
    assert call["user_id"] == user.id
    assert call["now"] == _NOW
    assert call["source_id"] is None


def test_due_queue_caps_limit_at_max() -> None:
    repo = _CapturingItemRepo((0, []))
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW))

    service(user=_user(), limit=1000)

    assert repo.calls[0]["limit"] == MAX_DUE_LIMIT == 100


def test_due_queue_passes_source_filter_and_returns_repo_result() -> None:
    due_item = DueReviewItem(
        item=_item(uuid4()), source_title="Book", due=_NOW - timedelta(hours=1)
    )
    repo = _CapturingItemRepo((1, [due_item]))
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW))
    source_id = uuid4()

    total, items = service(user=_user(), limit=5, source_id=source_id)

    assert total == 1
    assert items == [due_item]
    call = repo.calls[0]
    assert call["limit"] == 5
    assert call["source_id"] == source_id


# --- SubmitReview (integration) -------------------------------------------------


def _item(
    source_id: UUID,
    *,
    status: str = QuizItemStatus.ACTIVE,
    question: str = "What is the powerhouse of the cell?",
    answer: str = "Mitochondria",
) -> QuizItem:
    now = datetime.now(UTC)
    return QuizItem(
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


def _persisted_source(db_conn: Connection, email: str) -> Source:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    now = datetime.now(UTC)
    user = User(id=uuid4(), email=email, created_at=now)
    users.add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return sources.add(source)


def _seed_active_item(
    db_conn: Connection,
    source_id: UUID,
    *,
    status: str = QuizItemStatus.ACTIVE,
    due: datetime | None = None,
) -> QuizItem:
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source_id, status=status)
    repo.upsert(item, embedding=None)
    repo.create_scheduling(
        item.id,
        SchedulingSnapshot(
            state=1,
            step=0,
            stability=None,
            difficulty=None,
            due=due or (datetime.now(UTC) - timedelta(hours=1)),
            last_review=None,
        ),
    )
    return item


def _service(db_conn: Connection, *, now: datetime) -> SubmitReview:
    return SubmitReview(
        items=SqlAlchemyQuizItemRepository(db_conn),
        sources=SqlAlchemySourceRepository(db_conn),
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        authorize=AuthorizeOwnership(),
        clock=FakeClock(now),
    )


@requires_db
def test_submit_review_advances_scheduling_and_appends_log(db_conn: Connection) -> None:
    # QUIZ-12: a Good on an active due item moves the due date forward and appends a
    # review-log row carrying the rating and the client-supplied duration.
    source = _persisted_source(db_conn, "review-ok@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)

    advanced = _service(db_conn, now=_NOW)(
        user=user, item_id=item.id, rating=3, review_duration_ms=4200
    )

    # Good schedules the next review after now — the due date advanced.
    assert advanced.due > _NOW
    assert repo.get_scheduling(item.id) == advanced
    rows = db_conn.execute(
        select(review_log.c.rating, review_log.c.review_duration_ms).where(
            review_log.c.quiz_item_id == item.id
        )
    ).all()
    assert [(r.rating, r.review_duration_ms) for r in rows] == [(3, 4200)]


@requires_db
def test_submit_review_without_duration_logs_null(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "review-nodur@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)

    _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=2)

    rows = db_conn.execute(
        select(review_log.c.review_duration_ms).where(
            review_log.c.quiz_item_id == item.id
        )
    ).all()
    assert [r.review_duration_ms for r in rows] == [None]


@requires_db
def test_submit_review_allows_early_review_of_future_due_item(db_conn: Connection) -> None:
    # A-4: reviewing an active item that is not yet due is allowed (cramming).
    source = _persisted_source(db_conn, "review-early@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id, due=_NOW + timedelta(days=3))

    advanced = _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)

    assert advanced.due > _NOW


@requires_db
@pytest.mark.parametrize("status", [QuizItemStatus.STALE, QuizItemStatus.ORPHANED])
def test_submit_review_rejects_non_active_item(db_conn: Connection, status: str) -> None:
    # QUIZ-12: a stale/orphaned item is not reviewable (→ 409); nothing is logged.
    source = _persisted_source(db_conn, f"review-{status}@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id, status=status)

    with pytest.raises(QuizItemNotReviewable):
        _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)

    logged = db_conn.execute(
        select(func.count()).select_from(review_log).where(
            review_log.c.quiz_item_id == item.id
        )
    ).scalar_one()
    assert logged == 0


@requires_db
def test_submit_review_missing_item_raises_not_found(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "review-missing@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)

    with pytest.raises(QuizItemNotFound):
        _service(db_conn, now=_NOW)(user=user, item_id=uuid4(), rating=3)


@requires_db
def test_submit_review_non_owner_raises_not_found(db_conn: Connection) -> None:
    # QUIZ-18: another user's item is indistinguishable from a missing one (404).
    owner_source = _persisted_source(db_conn, "review-owner@example.com")
    intruder_source = _persisted_source(db_conn, "review-intruder@example.com")
    intruder = SqlAlchemyUserRepository(db_conn).get_by_id(intruder_source.user_id)
    item = _seed_active_item(db_conn, owner_source.id)

    with pytest.raises(QuizItemNotFound):
        _service(db_conn, now=_NOW)(user=intruder, item_id=item.id, rating=3)

    logged = db_conn.execute(
        select(func.count()).select_from(review_log).where(
            review_log.c.quiz_item_id == item.id
        )
    ).scalar_one()
    assert logged == 0
