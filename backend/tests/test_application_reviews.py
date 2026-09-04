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
from sqlalchemy import Connection, delete, func, select, update

from app.application.dates import local_day
from app.application.errors import QuizItemNotFound, QuizItemNotReviewable, QuizReviewNotUndoable
from app.application.quiz_qc import content_key
from app.application.reviews import (
    DEFAULT_DUE_LIMIT,
    MAX_DUE_LIMIT,
    FlagCard,
    GetDueQueue,
    ResetSchedule,
    SubmitReview,
    UndoLastReview,
)
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
    UndoableReview,
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
from tests.fakes import FakeClock, FakeStudyDayRepository

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
        self.calls.append({"user_id": user_id, "now": now, "limit": limit, "source_id": source_id})
        return self._result


def _user() -> User:
    return User(id=uuid4(), email="due@example.com", created_at=_NOW)


class _UnusedScheduling:
    """A ``SchedulingPort`` double that fails if preview runs without a snapshot."""

    def preview(self, snapshot, reviewed_at):  # noqa: ANN001, ANN201
        raise AssertionError("preview should not run without a joined snapshot")


class _PreviewScheduling:
    """Returns fixed dues so GetDueQueue's bucket mapping is asserted, not FSRS."""

    def preview(self, snapshot, reviewed_at):  # noqa: ANN001, ANN201
        return {
            1: reviewed_at + timedelta(seconds=30),
            2: reviewed_at + timedelta(minutes=10),
            3: reviewed_at + timedelta(days=1),
            4: reviewed_at + timedelta(days=4),
        }


def test_due_queue_defaults_to_twenty_and_passes_user_and_now() -> None:
    repo = _CapturingItemRepo((0, []))
    user = _user()
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW), scheduling=_UnusedScheduling())

    total, items = service(user=user)

    assert (total, items) == (0, [])
    call = repo.calls[0]
    assert call["limit"] == DEFAULT_DUE_LIMIT == 20
    assert call["user_id"] == user.id
    assert call["now"] == _NOW
    assert call["source_id"] is None


def test_due_queue_uses_injected_session_size_when_limit_is_omitted() -> None:
    repo = _CapturingItemRepo((0, []))
    service = GetDueQueue(
        items=repo, clock=FakeClock(_NOW), scheduling=_UnusedScheduling(), session_size=7
    )

    service(user=_user())

    assert repo.calls[0]["limit"] == 7


def test_due_queue_caps_injected_session_size_at_max() -> None:
    repo = _CapturingItemRepo((0, []))
    service = GetDueQueue(
        items=repo, clock=FakeClock(_NOW), scheduling=_UnusedScheduling(), session_size=1000
    )

    service(user=_user())

    assert repo.calls[0]["limit"] == MAX_DUE_LIMIT == 100


def test_due_queue_caps_limit_at_max() -> None:
    repo = _CapturingItemRepo((0, []))
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW), scheduling=_UnusedScheduling())

    service(user=_user(), limit=1000)

    assert repo.calls[0]["limit"] == MAX_DUE_LIMIT == 100


def test_due_queue_passes_source_filter_and_returns_repo_result() -> None:
    due_item = DueReviewItem(
        item=_item(uuid4()), source_title="Book", due=_NOW - timedelta(hours=1)
    )
    repo = _CapturingItemRepo((1, [due_item]))
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW), scheduling=_UnusedScheduling())
    source_id = uuid4()

    total, items = service(user=_user(), limit=5, source_id=source_id)

    assert total == 1
    assert items == [due_item]
    call = repo.calls[0]
    assert call["limit"] == 5
    assert call["source_id"] == source_id


def test_due_queue_attaches_interval_labels_from_the_joined_snapshot() -> None:
    snapshot = SchedulingSnapshot(
        state=1,
        step=0,
        stability=None,
        difficulty=None,
        due=_NOW - timedelta(hours=1),
        last_review=None,
    )
    due_item = DueReviewItem(
        item=_item(uuid4()),
        source_title="Book",
        due=snapshot.due,
        snapshot=snapshot,
    )
    repo = _CapturingItemRepo((1, [due_item]))
    service = GetDueQueue(items=repo, clock=FakeClock(_NOW), scheduling=_PreviewScheduling())

    _total, items = service(user=_user())

    assert items[0].interval_labels == {1: "~1m", 2: "~10m", 3: "~1d", 4: "~4d"}
    assert items[0].snapshot == snapshot
    assert not hasattr(repo, "get_scheduling")


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
    question: str = "What is the powerhouse of the cell?",
    answer: str = "Mitochondria",
) -> QuizItem:
    repo = SqlAlchemyQuizItemRepository(db_conn)
    item = _item(source_id, status=status, question=question, answer=answer)
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
    assert advanced.snapshot.due > _NOW
    assert repo.get_scheduling(item.id) == advanced.snapshot
    assert set(advanced.interval_labels) == {1, 2, 3, 4}
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
        select(review_log.c.review_duration_ms).where(review_log.c.quiz_item_id == item.id)
    ).all()
    assert [r.review_duration_ms for r in rows] == [None]


@requires_db
def test_submit_review_allows_early_review_of_future_due_item(db_conn: Connection) -> None:
    # A-4: reviewing an active item that is not yet due is allowed (cramming).
    source = _persisted_source(db_conn, "review-early@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id, due=_NOW + timedelta(days=3))

    advanced = _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)

    assert advanced.snapshot.due > _NOW


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
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
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
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
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
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert logged == 1
    rows = db_conn.execute(
        select(study_days.c.day, study_days.c.reviews_count, study_days.c.reading_updates).where(
            study_days.c.user_id == user.id
        )
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
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert logged == 0
    days = db_conn.execute(
        select(func.count()).select_from(study_days).where(study_days.c.user_id == user.id)
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
    return user, repo.get_by_id(item.id)


def _reset_service(db_conn: Connection) -> ResetSchedule:
    return ResetSchedule(
        items=SqlAlchemyQuizItemRepository(db_conn),
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=FakeClock(_NOW),
    )


@requires_db
def test_submit_review_advances_a_source_less_note_card(db_conn: Connection) -> None:
    # AD-149: a note card has no source, but authorization is its own user_id, so it is
    # reviewable like any other card.
    user, item = _persisted_note_card(db_conn, "review-note@example.com")

    advanced = _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)

    assert advanced.snapshot.due > _NOW
    assert SqlAlchemyQuizItemRepository(db_conn).get_scheduling(item.id) == advanced.snapshot


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
    repo.append_log(item.id, ReviewLogEntry(rating=3, reviewed_at=_NOW, review_duration_ms=800))
    repo.update_scheduling(
        item.id,
        SchedulingSnapshot(
            state=2,
            step=1,
            stability=9.0,
            difficulty=5.0,
            due=_NOW + timedelta(days=5),
            last_review=_NOW,
        ),
    )
    log_before = db_conn.execute(
        select(
            review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms
        ).where(review_log.c.quiz_item_id == item.id)
    ).all()

    before = datetime.now(UTC)
    fresh = _reset_service(db_conn)(user=user, item_id=item.id)
    after = datetime.now(UTC)

    # Fresh state: the learning shape a new card receives (no hand-rolled literal), and
    # the stored snapshot is exactly what was returned.
    reference = FsrsSchedulingAdapter(fuzzing=False).initial()
    assert fresh.snapshot.state == reference.state
    assert fresh.snapshot.stability == reference.stability
    assert fresh.snapshot.difficulty == reference.difficulty
    assert fresh.snapshot.last_review is None
    # Due is minted "now" (Learning), bounded by the call window — the advanced
    # schedule is gone. Bounding against the real clock keeps this date-proof.
    assert before <= fresh.snapshot.due <= after
    assert repo.get_scheduling(item.id) == fresh.snapshot
    # Badge cleared, review log untouched.
    assert repo.get_by_id(item.id).note_changed_at is None
    log_after = db_conn.execute(
        select(
            review_log.c.rating, review_log.c.reviewed_at, review_log.c.review_duration_ms
        ).where(review_log.c.quiz_item_id == item.id)
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


# --- UndoLastReview (REV-22..28) ------------------------------------------------


def _undo_service(db_conn: Connection, *, now: datetime) -> UndoLastReview:
    return UndoLastReview(
        items=SqlAlchemyQuizItemRepository(db_conn),
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=FakeClock(now),
        study_days=SqlAlchemyStudyDayRepository(db_conn),
    )


@requires_db
def test_submit_review_stores_the_pre_grade_snapshot_on_the_log(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "review-prev@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    before = repo.get_scheduling(item.id)

    _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)

    row = db_conn.execute(
        select(
            review_log.c.prev_state,
            review_log.c.prev_step,
            review_log.c.prev_stability,
            review_log.c.prev_difficulty,
            review_log.c.prev_due,
            review_log.c.prev_last_review,
        ).where(review_log.c.quiz_item_id == item.id)
    ).one()
    assert row.prev_state == before.state
    assert row.prev_step == before.step
    assert row.prev_stability == before.stability
    assert row.prev_difficulty == before.difficulty
    assert row.prev_due == before.due
    assert row.prev_last_review == before.last_review


@requires_db
def test_undo_restores_scheduling_and_keeps_the_log_row(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-restore@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    repo = SqlAlchemyQuizItemRepository(db_conn)
    before = repo.get_scheduling(item.id)
    question, answer, key = item.question, item.answer, item.content_key

    clock = FakeClock(_NOW)
    SubmitReview(
        items=repo,
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=clock,
        study_days=SqlAlchemyStudyDayRepository(db_conn),
    )(user=user, item_id=item.id, rating=4)
    assert repo.get_scheduling(item.id) != before

    clock.advance(timedelta(seconds=5))
    restored = UndoLastReview(
        items=repo,
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=clock,
        study_days=SqlAlchemyStudyDayRepository(db_conn),
    )(user=user)

    assert restored.snapshot == before
    assert repo.get_scheduling(item.id) == before
    rows = db_conn.execute(
        select(review_log.c.rating, review_log.c.undone_at).where(
            review_log.c.quiz_item_id == item.id
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].rating == 4
    assert rows[0].undone_at == _NOW + timedelta(seconds=5)
    stored = repo.get_by_id(item.id)
    assert stored.question == question
    assert stored.answer == answer
    assert stored.content_key == key


@requires_db
def test_second_undo_is_not_undoable(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-twice@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)
    undo = _undo_service(db_conn, now=_NOW)
    undo(user=user)

    with pytest.raises(QuizReviewNotUndoable):
        undo(user=user)


@requires_db
def test_legacy_null_snapshot_is_not_undoable(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-legacy@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    SqlAlchemyQuizItemRepository(db_conn).append_log(
        item.id, ReviewLogEntry(rating=3, reviewed_at=_NOW)
    )

    with pytest.raises(QuizReviewNotUndoable):
        _undo_service(db_conn, now=_NOW)(user=user)


@requires_db
def test_undo_with_no_reviews_is_not_undoable(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-empty@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)

    with pytest.raises(QuizReviewNotUndoable):
        _undo_service(db_conn, now=_NOW)(user=user)


@requires_db
def test_undo_decrements_the_credited_study_day(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-study@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    _service(db_conn, now=_NEAR_MIDNIGHT)(
        user=user, item_id=item.id, rating=3, client_tz="Asia/Tokyo"
    )

    _undo_service(db_conn, now=_NEAR_MIDNIGHT)(user=user, client_tz="Asia/Tokyo")

    rows = db_conn.execute(
        select(study_days.c.day, study_days.c.reviews_count).where(study_days.c.user_id == user.id)
    ).all()
    assert [(r.day, r.reviews_count) for r in rows] == [
        (local_day(_NEAR_MIDNIGHT, "Asia/Tokyo"), 0)
    ]


@requires_db
def test_undo_floors_reviews_count_at_zero(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-floor@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)
    db_conn.execute(
        update(study_days).where(study_days.c.user_id == user.id).values(reviews_count=0)
    )

    _undo_service(db_conn, now=_NOW)(user=user)

    count = db_conn.execute(
        select(study_days.c.reviews_count).where(study_days.c.user_id == user.id)
    ).scalar_one()
    assert count == 0


@requires_db
def test_undo_does_not_insert_a_study_day_row(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-noinsert@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id)
    _service(db_conn, now=_NOW)(user=user, item_id=item.id, rating=3)
    db_conn.execute(delete(study_days).where(study_days.c.user_id == user.id))

    _undo_service(db_conn, now=_NOW)(user=user)

    remaining = db_conn.execute(
        select(func.count()).select_from(study_days).where(study_days.c.user_id == user.id)
    ).scalar_one()
    assert remaining == 0


@requires_db
def test_undo_targets_the_callers_latest_review_across_items(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "undo-latest@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    first = _seed_active_item(db_conn, source.id, question="First?", answer="A")
    second = _seed_active_item(db_conn, source.id, question="Second?", answer="B")
    repo = SqlAlchemyQuizItemRepository(db_conn)
    second_before = repo.get_scheduling(second.id)
    clock = FakeClock(_NOW)
    submit = SubmitReview(
        items=repo,
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=clock,
        study_days=SqlAlchemyStudyDayRepository(db_conn),
    )
    submit(user=user, item_id=first.id, rating=3)
    first_after = repo.get_scheduling(first.id)
    clock.advance(timedelta(minutes=1))
    submit(user=user, item_id=second.id, rating=4)

    UndoLastReview(
        items=repo,
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=clock,
        study_days=SqlAlchemyStudyDayRepository(db_conn),
    )(user=user)

    assert repo.get_scheduling(second.id) == second_before
    assert repo.get_scheduling(first.id) == first_after
    first_log = db_conn.execute(
        select(review_log.c.undone_at).where(review_log.c.quiz_item_id == first.id)
    ).scalar_one()
    second_log = db_conn.execute(
        select(review_log.c.undone_at).where(review_log.c.quiz_item_id == second.id)
    ).scalar_one()
    assert first_log is None
    assert second_log is not None


@requires_db
def test_undo_does_not_see_another_users_review(db_conn: Connection) -> None:
    owner_source = _persisted_source(db_conn, "undo-owner@example.com")
    owner = SqlAlchemyUserRepository(db_conn).get_by_id(owner_source.user_id)
    item = _seed_active_item(db_conn, owner_source.id)
    _service(db_conn, now=_NOW)(user=owner, item_id=item.id, rating=3)
    intruder_source = _persisted_source(db_conn, "undo-intruder@example.com")
    intruder = SqlAlchemyUserRepository(db_conn).get_by_id(intruder_source.user_id)

    with pytest.raises(QuizReviewNotUndoable):
        _undo_service(db_conn, now=_NOW)(user=intruder)

    undone = db_conn.execute(
        select(review_log.c.undone_at).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert undone is None


def test_undo_vanished_item_is_not_found() -> None:
    row = UndoableReview(
        log_id=uuid4(),
        quiz_item_id=uuid4(),
        reviewed_at=_NOW,
        previous=SchedulingSnapshot(
            state=1,
            step=0,
            stability=None,
            difficulty=None,
            due=_NOW,
            last_review=None,
        ),
    )

    class _VanishedItemRepo:
        def latest_undoable_review(self, user_id):  # noqa: ANN001
            return row

        def get_by_id(self, item_id):  # noqa: ANN001
            return None

        def update_scheduling(self, quiz_item_id, snapshot) -> None:  # noqa: ANN001
            raise AssertionError("must not restore a vanished item")

        def mark_log_undone(self, log_id, undone_at) -> None:  # noqa: ANN001
            raise AssertionError("must not stamp a vanished item")

    with pytest.raises(QuizItemNotFound):
        UndoLastReview(
            items=_VanishedItemRepo(),
            scheduling=FsrsSchedulingAdapter(fuzzing=False),
            clock=FakeClock(_NOW),
            study_days=FakeStudyDayRepository(),
        )(user=_user())


# --- FlagCard (REV-34..36, REV-38) ----------------------------------------------


def _flag_service(db_conn: Connection, *, now: datetime) -> FlagCard:
    return FlagCard(items=SqlAlchemyQuizItemRepository(db_conn), clock=FakeClock(now))


@requires_db
def test_flag_hides_past_due_item_without_touching_schedule_or_log(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "flag-hide@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id, due=_NOW - timedelta(hours=1))
    repo = SqlAlchemyQuizItemRepository(db_conn)
    repo.append_log(item.id, ReviewLogEntry(rating=3, reviewed_at=_NOW))
    before = repo.get_scheduling(item.id)
    logged_before = db_conn.execute(
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()

    flagged = _flag_service(db_conn, now=_NOW)(user=user, item_id=item.id, flagged=True)

    assert flagged.flagged_at == _NOW
    assert repo.get_by_id(item.id).flagged_at == _NOW
    assert repo.get_scheduling(item.id) == before
    logged_after = db_conn.execute(
        select(func.count()).select_from(review_log).where(review_log.c.quiz_item_id == item.id)
    ).scalar_one()
    assert logged_after == logged_before
    total, due = repo.due_for_user(user.id, now=_NOW, limit=20)
    assert total == 0
    assert due == []


@requires_db
def test_unflag_restores_due_membership_of_an_active_past_due_item(
    db_conn: Connection,
) -> None:
    source = _persisted_source(db_conn, "flag-unflag@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(db_conn, source.id, due=_NOW - timedelta(hours=1))
    repo = SqlAlchemyQuizItemRepository(db_conn)
    flag = _flag_service(db_conn, now=_NOW)
    flag(user=user, item_id=item.id, flagged=True)

    restored = flag(user=user, item_id=item.id, flagged=False)

    assert restored.flagged_at is None
    total, due = repo.due_for_user(user.id, now=_NOW, limit=20)
    assert total == 1
    assert [d.item.id for d in due] == [item.id]


@requires_db
def test_unflag_of_stale_item_stays_out_of_due(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "flag-stale@example.com")
    user = SqlAlchemyUserRepository(db_conn).get_by_id(source.user_id)
    item = _seed_active_item(
        db_conn, source.id, status=QuizItemStatus.STALE, due=_NOW - timedelta(hours=1)
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    flag = _flag_service(db_conn, now=_NOW)
    flag(user=user, item_id=item.id, flagged=True)
    flag(user=user, item_id=item.id, flagged=False)

    total, due = repo.due_for_user(user.id, now=_NOW, limit=20)
    assert total == 0
    assert due == []
    assert repo.get_by_id(item.id).status == QuizItemStatus.STALE
    assert repo.get_by_id(item.id).flagged_at is None


@requires_db
def test_flag_missing_and_non_owned_raise_not_found(db_conn: Connection) -> None:
    owner_source = _persisted_source(db_conn, "flag-owner@example.com")
    owner = SqlAlchemyUserRepository(db_conn).get_by_id(owner_source.user_id)
    item = _seed_active_item(db_conn, owner_source.id)
    intruder_source = _persisted_source(db_conn, "flag-intruder@example.com")
    intruder = SqlAlchemyUserRepository(db_conn).get_by_id(intruder_source.user_id)
    flag = _flag_service(db_conn, now=_NOW)

    with pytest.raises(QuizItemNotFound):
        flag(user=intruder, item_id=item.id, flagged=True)
    with pytest.raises(QuizItemNotFound):
        flag(user=owner, item_id=uuid4(), flagged=True)
    assert SqlAlchemyQuizItemRepository(db_conn).get_by_id(item.id).flagged_at is None
