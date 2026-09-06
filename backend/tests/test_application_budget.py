"""Daily AI spend ledger and budget service (integration, live test DB).

The RFC-0007 Cycle F spend-cap specs at the layer the Test Coverage Matrix pins for
budget/kill integration behaviour:

- The ``ai_spend_days`` ledger accumulates same-day increments atomically — two
  increments never lose one, USD micros and the integer counters each sum, and
  different UTC days are separate rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Connection

from app.domain.entities import AiSpendDay, User
from app.infrastructure.db.repositories import (
    SqlAlchemyAiSpendDayRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db

pytestmark = requires_db

_DAY = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC).date()


def _add_user(db_conn: Connection, email: str) -> User:
    return SqlAlchemyUserRepository(db_conn).add(
        User(id=uuid4(), email=email, created_at=datetime.now(UTC))
    )


def _ledger(db_conn: Connection) -> SqlAlchemyAiSpendDayRepository:
    return SqlAlchemyAiSpendDayRepository(db_conn)


# --- Ledger: same-day accumulation -----------------------------------------------


def test_record_inserts_the_first_debit_of_a_day(db_conn: Connection) -> None:
    user = _add_user(db_conn, "budget-first@example.com")
    repo = _ledger(db_conn)

    repo.record(user.id, _DAY, usd_micros=2500, asks=1)

    assert repo.get_for_day(user.id, _DAY) == AiSpendDay(
        user_id=user.id, day_utc=_DAY, usd_micros=2500, ask_count=1, teach_starts=0
    )


def test_two_same_day_increments_accumulate_into_one_row(db_conn: Connection) -> None:
    # DOOR-07 / spec edge: two overlapping debits are both persisted — the atomic
    # upsert-increment never loses one, whatever order they land in.
    user = _add_user(db_conn, "budget-accumulate@example.com")
    repo = _ledger(db_conn)

    repo.record(user.id, _DAY, usd_micros=1000, asks=1)
    repo.record(user.id, _DAY, usd_micros=2500, asks=1)

    row = repo.get_for_day(user.id, _DAY)
    assert row is not None
    assert row.usd_micros == 3500
    assert row.ask_count == 2
    assert row.teach_starts == 0


def test_counters_accumulate_independently_of_the_usd_total(db_conn: Connection) -> None:
    # A local-adapter debit is 0 USD (DOOR-14) but the free-tier integer counters
    # still count the calls, so a 0-micros day can still exhaust the Ask cap.
    user = _add_user(db_conn, "budget-counters@example.com")
    repo = _ledger(db_conn)

    repo.record(user.id, _DAY, asks=1)
    repo.record(user.id, _DAY, usd_micros=700, teach_starts=1)

    row = repo.get_for_day(user.id, _DAY)
    assert row is not None
    assert (row.usd_micros, row.ask_count, row.teach_starts) == (700, 1, 1)


def test_different_utc_days_are_separate_rows(db_conn: Connection) -> None:
    # The cap is per UTC day: yesterday's spend never gates today's first call.
    user = _add_user(db_conn, "budget-days@example.com")
    repo = _ledger(db_conn)

    repo.record(user.id, _DAY, usd_micros=9_999_999)
    repo.record(user.id, _DAY.replace(day=_DAY.day - 1), usd_micros=1)

    today = repo.get_for_day(user.id, _DAY)
    assert today is not None
    assert today.usd_micros == 9_999_999
