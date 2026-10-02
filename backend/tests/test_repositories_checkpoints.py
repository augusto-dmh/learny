"""Checkpoint repository under real, concurrent transactions (live test DB).

The once-only grade is a conditional UPDATE. Only two genuinely concurrent
transactions show that exactly one of them wins: the loser blocks on the
winner's row lock, re-evaluates ``graded_at IS NULL`` after the commit, and
matches nothing. The test commits its own seed and deletes it afterwards.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, delete

from app.domain.entities import CheckpointAttempt, CheckpointAttemptKind, SectionCheckpoint
from app.infrastructure.db.metadata import users
from app.infrastructure.db.repositories import SqlAlchemyCheckpointRepository
from tests.checkpoint_seed import ANCHOR, TITLE, add_source, add_user
from tests.conftest import requires_db

pytestmark = requires_db

_NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)


def test_concurrent_grade_claim_has_one_winner(db_engine: Engine) -> None:
    attempt_id = uuid4()
    with db_engine.begin() as conn:
        user = add_user(conn)
        source_id = add_source(conn, user.id)
        checkpoint = SectionCheckpoint(
            id=uuid4(),
            user_id=user.id,
            source_id=source_id,
            anchor=ANCHOR,
            section_title=TITLE,
            prediction=None,
            created_at=_NOW,
        )
        repo = SqlAlchemyCheckpointRepository(conn)
        repo.add(
            checkpoint,
            [
                CheckpointAttempt(
                    id=attempt_id,
                    checkpoint_id=checkpoint.id,
                    kind=CheckpointAttemptKind.EXPLAIN,
                    position=0,
                )
            ],
        )
        assert repo.claim_response(
            attempt_id, response="x", confidence=2, feedback=None, feedback_citations=(), now=_NOW
        )

    try:
        first = db_engine.connect()
        second = db_engine.connect()
        first_tx = first.begin()
        second_tx = second.begin()
        try:
            won_first = SqlAlchemyCheckpointRepository(first).claim_grade(attempt_id, _NOW)
            with ThreadPoolExecutor(max_workers=1) as pool:
                # Blocks on the row lock the first claim holds until it commits.
                pending = pool.submit(
                    SqlAlchemyCheckpointRepository(second).claim_grade, attempt_id, _NOW
                )
                first_tx.commit()
                won_second = pending.result(timeout=30)
            second_tx.commit()
        finally:
            first.close()
            second.close()

        assert (won_first, won_second) == (True, False)
    finally:
        with db_engine.begin() as conn:
            conn.execute(delete(users).where(users.c.id == user.id))
