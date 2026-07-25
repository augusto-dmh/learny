"""Saving a reading position under real transactions (integration, live test DB).

Two properties of ``SaveReadingPosition`` that only a real connection can show, because
both are about what other transactions can see:

- **A day is credited once per advance.** The reading volume is *derived* from the stored
  position — the distance from it to the new one — so a plain read of that row would let
  two overlapping saves each claim the same distance and leave the counter overstated with
  nothing to recompute it. Two genuinely concurrent savers of the same ``(user, source)``
  must therefore credit the advance once between them.
- **The position and its credit commit together, or not at all.** Both writes are issued
  and *then* the transaction fails; a second connection must see neither. The 404 path
  cannot show this — nothing is written there at all, so it passes however the credit is
  wired.

Both use committed transactions rather than the rolled-back ``db_conn``, so each test
cleans up the user it seeded.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, func, select, text

from app.application.identity import AuthorizeOwnership
from app.application.reading import SaveReadingPosition
from app.domain.entities import (
    CorpusSectionRecord,
    ParsedSection,
    Source,
    User,
)
from app.infrastructure.db.metadata import reading_positions, study_days
from app.infrastructure.db.repositories import (
    SqlAlchemyReadingPositionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyStudyDayRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db
from tests.fakes import (
    FakeClock,
    FakeCorpusRepository,
    FakeSourceRepository,
)

pytestmark = requires_db

_NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)


# --- Seeding -------------------------------------------------------------------


def _record(position: int, depth: int, anchor: str, markdown: str) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=f"Section {position}",
            depth=depth,
            section_path=(f"Section {position}",),
            anchor=anchor,
            blocks=(),
            anchor_aliases=(),
        ),
        markdown=markdown,
        chunks=(),
    )


def _seed_committed(db_engine: Engine, email: str) -> tuple[User, Source]:
    """Insert a user and one owned source in their own committed transaction."""
    user = User(id=uuid4(), email=email, created_at=_NOW)
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
        created_at=_NOW,
        updated_at=_NOW,
    )
    with db_engine.begin() as conn:
        SqlAlchemyUserRepository(conn).add(user)
        SqlAlchemySourceRepository(conn).add(source)
    return user, source


def _book(source_id: UUID) -> FakeCorpusRepository:
    """Two chapters, word counts 3/2/1/4 — ``c1s1`` sits 3 words in, ``c2s1`` 6."""
    corpus = FakeCorpusRepository()
    corpus.replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _record(0, 0, "c1", "a b c"),
            _record(1, 1, "c1s1", "d e"),
            _record(2, 0, "c2", "f"),
            _record(3, 1, "c2s1", "g h i j"),
        ],
    )
    return corpus


def _service(
    conn: Connection,
    *,
    source: Source,
    corpus: FakeCorpusRepository,
    study_days_repo: object | None = None,
) -> SaveReadingPosition:
    sources = FakeSourceRepository()
    sources.add(source)
    return SaveReadingPosition(
        sources=sources,
        corpus=corpus,
        positions=SqlAlchemyReadingPositionRepository(conn),
        authorize=AuthorizeOwnership(),
        clock=FakeClock(_NOW),
        study_days=study_days_repo or SqlAlchemyStudyDayRepository(conn),
    )


def _delete_user(db_engine: Engine, user_id: UUID) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})


# --- The advance is credited once, not once per concurrent saver ----------------


def test_two_concurrent_saves_credit_the_advance_once(db_engine: Engine) -> None:
    """Two overlapping saves of the same ``(user, source)``, from the same baseline to the
    same target, leave the day crediting the 3-word advance once — not 3 words twice. The
    savers meet at a barrier before reading the baseline, so they genuinely overlap: the
    one that gets there second must see the first one's position, not the one they both
    started from."""
    user, source = _seed_committed(db_engine, "reading-concurrent@example.com")
    corpus = _book(source.id)
    barrier = threading.Barrier(2)

    try:
        # The baseline both savers advance from: c1s1, 3 words into the book.
        with db_engine.begin() as conn:
            _service(conn, source=source, corpus=corpus)(
                user=user, source_id=source.id, anchor="c1s1"
            )

        def worker() -> None:
            with db_engine.connect() as conn:
                trans = conn.begin()
                # Reach the baseline read near-simultaneously, so a read that took no
                # lock would hand both savers the same prior anchor.
                barrier.wait(timeout=30)
                _service(conn, source=source, corpus=corpus)(
                    user=user, source_id=source.id, anchor="c2s1"
                )
                trans.commit()

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(worker), pool.submit(worker)]:
                future.result(timeout=30)

        with db_engine.connect() as conn:
            row = conn.execute(
                select(study_days.c.reading_updates, study_days.c.words_advanced).where(
                    study_days.c.user_id == user.id
                )
            ).one()
            anchor = conn.execute(
                select(reading_positions.c.anchor).where(reading_positions.c.user_id == user.id)
            ).scalar_one()
        # Both saves happened (3 position writes in all), and both moved the reader to
        # c2s1 — but the book only ever advanced 3 words, so only 3 are credited.
        assert (row.reading_updates, row.words_advanced) == (3, 3)
        assert anchor == "c2s1"
    finally:
        _delete_user(db_engine, user.id)


# --- The position and the credit commit together (I-PU-6) -----------------------


class _RecordThenFail:
    """A ``StudyDayRepository`` that performs the credit and *then* raises.

    The failure has to land after both writes are issued: a double that refuses to write
    would leave the credit untried, which is the very thing the 404 path already fails to
    distinguish. Here the study-day row and the position row both exist in the
    transaction at the moment it is torn down."""

    def __init__(self, inner: SqlAlchemyStudyDayRepository) -> None:
        self._inner = inner

    def record(self, *args: object, **kwargs: object) -> None:
        self._inner.record(*args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("study-day credit failed")

    def window(self, *args: object, **kwargs: object) -> list[object]:
        return []


def test_a_failure_after_both_writes_leaves_neither_visible(db_engine: Engine) -> None:
    """The position upsert and the study-day credit are issued, then the transaction
    fails. A second connection sees no position and no study day — they share one
    transaction, so neither survives the other's failure (I-PU-6)."""
    user, source = _seed_committed(db_engine, "reading-atomic@example.com")
    corpus = _book(source.id)

    try:
        with db_engine.connect() as conn:
            trans = conn.begin()
            service = _service(
                conn,
                source=source,
                corpus=corpus,
                study_days_repo=_RecordThenFail(SqlAlchemyStudyDayRepository(conn)),
            )
            with pytest.raises(RuntimeError):
                service(user=user, source_id=source.id, anchor="c1s1")
            # Both writes really were issued before the failure — otherwise "neither is
            # visible afterwards" would be satisfied by never having written at all,
            # which is the hole the 404 sensor falls into. The failure is a Python error,
            # so the transaction is still readable on its own connection.
            assert _counts(conn, user.id) == (1, 1)
            trans.rollback()

        # A second connection: nothing the failed transaction wrote is visible.
        with db_engine.connect() as conn:
            assert _counts(conn, user.id) == (0, 0)
    finally:
        _delete_user(db_engine, user.id)


def _counts(conn: Connection, user_id: UUID) -> tuple[int, int]:
    """The user's stored positions and study days, as this connection sees them."""
    positions = conn.execute(
        select(func.count())
        .select_from(reading_positions)
        .where(reading_positions.c.user_id == user_id)
    ).scalar_one()
    days = conn.execute(
        select(func.count()).select_from(study_days).where(study_days.c.user_id == user_id)
    ).scalar_one()
    return positions, days
