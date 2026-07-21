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
from app.application.quiz_qc import content_key
from app.application.reviews import (
    DEFAULT_DUE_LIMIT,
    MAX_DUE_LIMIT,
    GetDueQueue,
    ResetSchedule,
    SubmitReview,
)
from app.application.study import local_day
from app.domain.entities import (
    DueReviewItem,
    Note,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    ReviewLogEntry,
    SchedulingSnapshot,
    Source,
    User,
)
from app.infrastructure.db.metadata import review_log, study_days
from app.infrastructure.db.repositories import (
    SqlAlchemyNoteRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyStudyDayRepository,
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
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=FakeClock(now),
        study_days=SqlAlchemyStudyDayRepository(db_conn),
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


# --- SubmitReview study-day rollup (HOME-07/09, I-1) ----------------------------

# A UTC instant late enough that a positive-offset zone is already the next calendar
# day — so a test can tell "used the client zone" from "used UTC".
_NEAR_MIDNIGHT = datetime(2026, 7, 16, 23, 30, 0, tzinfo=UTC)


class _FailingStudyDayRepository:
    """A ``StudyDayRepository`` whose ``record`` always raises — forces the post-write
    failure that the atomicity sensor (I-1) needs."""

    def record(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise RuntimeError("study-day credit failed")

    def window(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        return []


@requires_db
def test_submit_review_credits_a_study_day_in_the_same_transaction(
    db_conn: Connection,
) -> None:
    # HOME-07 / I-1: submitting a review writes the review log AND the study-day credit
    # on the same connection — both visible together, one transaction. The client zone
    # sets the day (Tokyo is already the 17th at 23:30 UTC on the 16th).
    source = _persisted_source(db_conn, "review-study-txn@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)

    _service(db_conn, now=_NEAR_MIDNIGHT)(
        user=user, item_id=item.id, rating=3, client_tz="Asia/Tokyo"
    )

    logged = db_conn.execute(
        select(func.count()).select_from(review_log).where(
            review_log.c.quiz_item_id == item.id
        )
    ).scalar_one()
    assert logged == 1
    rows = db_conn.execute(
        select(
            study_days.c.day, study_days.c.reviews_count, study_days.c.reading_updates
        ).where(study_days.c.user_id == user.id)
    ).all()
    assert [(r.day, r.reviews_count, r.reading_updates) for r in rows] == [
        (local_day(_NEAR_MIDNIGHT, "Asia/Tokyo"), 1, 0)
    ]


@requires_db
def test_submit_review_study_day_falls_back_to_utc_on_garbage_timezone(
    db_conn: Connection,
) -> None:
    # HOME-09: a garbage zone credits the UTC day (the 16th), never the client zone's
    # next day, and never an error.
    source = _persisted_source(db_conn, "review-study-utc@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)

    _service(db_conn, now=_NEAR_MIDNIGHT)(
        user=user, item_id=item.id, rating=3, client_tz="Mars/Olympus"
    )

    day = db_conn.execute(
        select(study_days.c.day).where(study_days.c.user_id == user.id)
    ).scalar_one()
    assert day == _NEAR_MIDNIGHT.date()  # UTC date, 2026-07-16


@requires_db
def test_submit_review_rolls_back_the_review_when_the_study_credit_fails(
    db_conn: Connection,
) -> None:
    # I-1: a failure after the review write (study credit raises) rolls the whole
    # transaction back — no review-log row and no study-day row survive.
    source = _persisted_source(db_conn, "review-study-atomic@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    service = SubmitReview(
        items=SqlAlchemyQuizItemRepository(db_conn),
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=FakeClock(_NOW),
        study_days=_FailingStudyDayRepository(),
    )

    with pytest.raises(RuntimeError), db_conn.begin_nested():
        service(user=user, item_id=item.id, rating=3)

    logged = db_conn.execute(
        select(func.count()).select_from(review_log).where(
            review_log.c.quiz_item_id == item.id
        )
    ).scalar_one()
    assert logged == 0
    days = db_conn.execute(
        select(func.count()).select_from(study_days).where(
            study_days.c.user_id == user.id
        )
    ).scalar_one()
    assert days == 0


# --- Note-card review + ResetSchedule (NL-12) -----------------------------------


def _persisted_note_card(
    db_conn: Connection,
    email: str,
    *,
    status: str = QuizItemStatus.ACTIVE,
    due: datetime | None = None,
    flagged_at: datetime | None = None,
) -> tuple[User, QuizItem]:
    """Seed a source-less ``note`` card owned by a fresh user (AD-148/149)."""
    source = _persisted_source(db_conn, email)  # creates the owning user
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    now = datetime.now(UTC)
    note = SqlAlchemyNoteRepository(db_conn).add(
        Note(
            id=uuid4(),
            user_id=user.id,
            title="My note",
            body_markdown="a body",
            created_at=now,
            updated_at=now,
        )
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = QuizItem(
        id=uuid4(),
        source_id=None,
        user_id=user.id,
        origin=QuizItemOrigin.NOTE,
        note_id=note.id,
        item_type=QuizItemType.FREE_RECALL,
        question="What does the note say?",
        answer="A fact.",
        section_path=("My note",),
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
            state=1, step=0, stability=None, difficulty=None,
            due=due or (now - timedelta(hours=1)), last_review=None,
        ),
    )
    if flagged_at is not None:
        repo.flag_note_changed(item.id, flagged_at)
    return user, repo.get_by_id(item.id)


def _reset_service(db_conn: Connection) -> ResetSchedule:
    return ResetSchedule(
        items=SqlAlchemyQuizItemRepository(db_conn),
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
    )


@requires_db
def test_submit_review_advances_a_source_less_note_card(db_conn: Connection) -> None:
    # AD-149: a note card has no source, but authorization is its own user_id, so it is
    # reviewable like any other card.
    user, item = _persisted_note_card(db_conn, "review-note@example.com")

    advanced = _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)

    assert advanced.due > _NOW
    assert SqlAlchemyQuizItemRepository(db_conn).get_scheduling(item.id) == advanced


@requires_db
def test_submit_review_note_card_non_owner_is_404(db_conn: Connection) -> None:
    user, item = _persisted_note_card(db_conn, "review-note-owner@example.com")
    intruder_source = _persisted_source(db_conn, "review-note-intruder@example.com")
    intruder = SqlAlchemyUserRepository(db_conn).get_by_id(intruder_source.user_id)

    with pytest.raises(QuizItemNotFound):
        _service(db_conn, now=_NOW)(user=intruder, item_id=item.id, rating=3)


@requires_db
def test_reset_returns_fresh_state_clears_badge_and_preserves_log(
    db_conn: Connection,
) -> None:
    user, item = _persisted_note_card(
        db_conn,
        "reset-ok@example.com",
        flagged_at=datetime.now(UTC) + timedelta(hours=1),
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    # Give the card a review history and an advanced schedule to reset away from.
    repo.append_log(
        item.id, ReviewLogEntry(rating=3, reviewed_at=_NOW, review_duration_ms=800)
    )
    repo.update_scheduling(
        item.id,
        SchedulingSnapshot(
            state=2, step=1, stability=9.0, difficulty=5.0,
            due=_NOW + timedelta(days=5), last_review=_NOW,
        ),
    )
    log_before = db_conn.execute(
        select(review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms)
        .where(review_log.c.quiz_item_id == item.id)
    ).all()

    before = datetime.now(UTC)
    fresh = _reset_service(db_conn)(user=user, item_id=item.id)
    after = datetime.now(UTC)

    # Fresh state: the learning shape a new card receives (no hand-rolled literal), and
    # the stored snapshot is exactly what was returned.
    reference = FsrsSchedulingAdapter(fuzzing=False).initial()
    assert fresh.state == reference.state
    assert fresh.stability == reference.stability
    assert fresh.difficulty == reference.difficulty
    assert fresh.last_review is None
    # Due is minted "now" (Learning), bounded by the call window — the advanced
    # schedule is gone. Bounding against the real clock keeps this date-proof.
    assert before <= fresh.due <= after
    assert repo.get_scheduling(item.id) == fresh
    # Badge cleared, review log untouched.
    assert repo.get_by_id(item.id).note_changed_at is None
    log_after = db_conn.execute(
        select(review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms)
        .where(review_log.c.quiz_item_id == item.id)
    ).all()
    assert log_after == log_before
    assert len(log_after) == 1


@requires_db
@pytest.mark.parametrize("status", [QuizItemStatus.STALE, QuizItemStatus.ORPHANED])
def test_reset_rejects_a_non_active_item(db_conn: Connection, status: str) -> None:
    user, item = _persisted_note_card(db_conn, f"reset-{status}@example.com", status=status)

    with pytest.raises(QuizItemNotReviewable):
        _reset_service(db_conn)(user=user, item_id=item.id)


@requires_db
def test_reset_non_owner_is_404(db_conn: Connection) -> None:
    _user, item = _persisted_note_card(db_conn, "reset-owner@example.com")
    intruder_source = _persisted_source(db_conn, "reset-intruder@example.com")
    intruder = SqlAlchemyUserRepository(db_conn).get_by_id(intruder_source.user_id)

    with pytest.raises(QuizItemNotFound):
        _reset_service(db_conn)(user=intruder, item_id=item.id)


@requires_db
def test_reset_missing_item_is_404(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "reset-missing@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)

    with pytest.raises(QuizItemNotFound):
        _reset_service(db_conn)(user=user, item_id=uuid4())
