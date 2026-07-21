"""Study-day rollup repository (integration, live test DB).

Exercises ``SqlAlchemyStudyDayRepository`` against Postgres:

- ``record`` inserts a new ``(user_id, day)`` row and, on a repeat, takes the atomic
  ON CONFLICT increment path — N same-day events leave exactly one row whose counters
  equal the totals (HOME-10 / I-2), including under two genuinely concurrent sessions.
- ``window`` returns the caller's rows in an inclusive day range, day-ordered, and never
  another user's rows (HOME-15 / I-5).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, select, text

from app.domain.entities import StudyDay, User
from app.infrastructure.db.metadata import study_days
from app.infrastructure.db.repositories import (
    SqlAlchemyStudyDayRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db

pytestmark = requires_db


def _add_user(db_conn: Connection, email: str) -> UUID:
    user = User(id=uuid4(), email=email, created_at=datetime.now(UTC))
    return SqlAlchemyUserRepository(db_conn).add(user).id


# --- record: insert + upsert-increment (HOME-07/08/10, I-2) --------------------


def test_record_inserts_a_new_day_row_with_the_passed_counters(
    db_conn: Connection,
) -> None:
    user_id = _add_user(db_conn, "study-insert@example.com")
    repo = SqlAlchemyStudyDayRepository(db_conn)
    day = date(2026, 7, 21)

    repo.record(user_id, day, reviews=1)

    rows = repo.window(user_id, start=day, end=day)
    assert rows == [
        StudyDay(user_id=user_id, day=day, reviews_count=1, reading_updates=0)
    ]


def test_record_same_day_events_sum_into_one_row(db_conn: Connection) -> None:
    # HOME-10 / spec independent test: 2 reviews + 1 position save on one local day →
    # exactly one row, reviews_count=2, reading_updates=1.
    user_id = _add_user(db_conn, "study-sum@example.com")
    repo = SqlAlchemyStudyDayRepository(db_conn)
    day = date(2026, 7, 21)

    repo.record(user_id, day, reviews=1)
    repo.record(user_id, day, reviews=1)
    repo.record(user_id, day, reading_updates=1)

    rows = repo.window(user_id, start=day, end=day)
    assert rows == [
        StudyDay(user_id=user_id, day=day, reviews_count=2, reading_updates=1)
    ]


def test_record_different_days_are_separate_rows(db_conn: Connection) -> None:
    user_id = _add_user(db_conn, "study-days@example.com")
    repo = SqlAlchemyStudyDayRepository(db_conn)

    repo.record(user_id, date(2026, 7, 20), reviews=1)
    repo.record(user_id, date(2026, 7, 21), reading_updates=1)

    rows = repo.window(user_id, start=date(2026, 7, 1), end=date(2026, 7, 31))
    assert rows == [
        StudyDay(user_id=user_id, day=date(2026, 7, 20), reviews_count=1, reading_updates=0),
        StudyDay(user_id=user_id, day=date(2026, 7, 21), reviews_count=0, reading_updates=1),
    ]


# --- window: range, ordering, user-scoping (HOME-11 repo half, HOME-15/I-5) -----


def test_window_returns_only_in_range_rows_day_ordered(db_conn: Connection) -> None:
    user_id = _add_user(db_conn, "study-window@example.com")
    repo = SqlAlchemyStudyDayRepository(db_conn)
    # Seed out of order to prove the query orders by day, and outside the window to
    # prove the inclusive bounds exclude the edges beyond [start, end].
    repo.record(user_id, date(2026, 7, 20), reviews=1)
    repo.record(user_id, date(2026, 7, 10), reviews=1)
    repo.record(user_id, date(2026, 7, 15), reviews=1)
    repo.record(user_id, date(2026, 7, 5), reviews=1)  # before window
    repo.record(user_id, date(2026, 7, 25), reviews=1)  # after window

    rows = repo.window(user_id, start=date(2026, 7, 10), end=date(2026, 7, 20))

    assert [row.day for row in rows] == [
        date(2026, 7, 10),
        date(2026, 7, 15),
        date(2026, 7, 20),
    ]


def test_window_is_scoped_to_the_caller_in_sql(db_conn: Connection) -> None:
    # HOME-15 / I-5: another user's study days are unreachable, not filtered post-hoc.
    caller = _add_user(db_conn, "study-scope-caller@example.com")
    other = _add_user(db_conn, "study-scope-other@example.com")
    repo = SqlAlchemyStudyDayRepository(db_conn)
    day = date(2026, 7, 21)
    repo.record(caller, day, reviews=1)
    repo.record(other, day, reviews=9)

    rows = repo.window(caller, start=day, end=day)

    assert rows == [
        StudyDay(user_id=caller, day=day, reviews_count=1, reading_updates=0)
    ]


# --- concurrency: two sessions on the same (user, day) (HOME-10, I-2) -----------


def _add_user_committed(db_engine: Engine, email: str) -> UUID:
    user_id = uuid4()
    with db_engine.begin() as conn:
        SqlAlchemyUserRepository(conn).add(
            User(id=user_id, email=email, created_at=datetime.now(UTC))
        )
    return user_id


def test_record_two_concurrent_sessions_increment_exactly_once(
    db_engine: Engine,
) -> None:
    """Two independent sessions recording the same ``(user, day)`` concurrently leave
    one row with ``reviews_count == 2`` — the ON CONFLICT increment serializes the
    second commit onto the first (HOME-10 / I-2). Uses committed transactions (real
    concurrency), so the seeded user is cleaned up afterward."""
    user_id = _add_user_committed(db_engine, "study-concurrent@example.com")
    day = date(2026, 7, 21)
    barrier = threading.Barrier(2)

    def worker() -> None:
        with db_engine.connect() as conn:
            trans = conn.begin()
            # Reach the write near-simultaneously so the second commit takes the
            # genuine ON CONFLICT path against a locked/committed row.
            barrier.wait(timeout=30)
            SqlAlchemyStudyDayRepository(conn).record(user_id, day, reviews=1)
            trans.commit()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(worker), pool.submit(worker)]:
                future.result(timeout=30)

        with db_engine.connect() as conn:
            row = conn.execute(
                select(
                    study_days.c.reviews_count, study_days.c.reading_updates
                ).where(study_days.c.user_id == user_id)
            ).one()
        assert (row.reviews_count, row.reading_updates) == (2, 0)
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
