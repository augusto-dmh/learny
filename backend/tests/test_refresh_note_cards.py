"""Phase C gate — the refresh_note_cards worker task (integration, live DB).

Drives the ``refresh_note_cards`` task *function* directly against the migrated test
engine (no Redis, no eager mode), mirroring ``test_embed_note``: the task commits
through its own engine, so each test seeds a committed user + note + promoted note card
and the fixture deletes the user afterwards (FK cascade). The deterministic local
adapters make the regenerated suggestions and their embeddings reproducible in-test.

Covers NL-10 (a matched card's text is rewritten in place while its scheduling and
review-log rows stay byte-equal — the cycle's core invariant, driven end-to-end through
the real repository) and the deleted-note no-op (AD-145).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy import delete as sa_delete

from app.application.quiz_qc import content_key
from app.core.config import get_settings
from app.domain.entities import (
    Note,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    ReviewLogEntry,
    SchedulingSnapshot,
)
from app.infrastructure.db.metadata import quiz_items, review_log, users
from app.infrastructure.db.repositories import (
    SqlAlchemyNoteRepository,
    SqlAlchemyQuizItemRepository,
)
from app.infrastructure.embeddings import build_embedding_adapter
from app.infrastructure.quiz import build_quiz_adapter
from app.worker.tasks import refresh_note_cards
from tests.conftest import requires_db

pytestmark = requires_db

# The raw (unbound) task function, driven with a stand-in ``self`` (the body ignores it).
_refresh = refresh_note_cards.run.__func__

_BODY = "Spaced repetition schedules reviews at expanding intervals. It aids recall."


def _free_recall_suggestion():  # noqa: ANN202
    """The free-recall candidate the local adapter regenerates from :data:`_BODY`."""
    settings = get_settings()
    candidates = build_quiz_adapter(settings).suggest_note_cards(
        _BODY, "", settings.quiz_max_suggestions
    )
    return next(c for c in candidates if c.item_type == QuizItemType.FREE_RECALL)


def _embedding_of(question: str, answer: str) -> list[float]:
    return build_embedding_adapter(get_settings()).embed_documents(
        [f"{question}\n{answer}"]
    )[0]


@pytest.fixture
def refresh_env(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the task's engine at the test DB and return a committed-scenario seeder.

    The seeder commits an owner + one note + one promoted note card whose stored
    embedding matches the regenerated free-recall suggestion (so the refresh pairs them)
    but whose text differs (so the pairing is a rewrite), plus a scheduling row and one
    review-log entry — the memory history the refresh must not disturb.
    """
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created_users: list[UUID] = []

    def _seed(*, body: str = _BODY, card_question: str, card_answer: str) -> tuple:
        user_id = uuid4()
        item_id = uuid4()
        now = datetime.now(UTC)
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (id, email) VALUES (:id, :email)"),
                {"id": user_id, "email": f"{user_id}@example.com"},
            )
            note = SqlAlchemyNoteRepository(conn).add(
                Note(
                    id=uuid4(),
                    user_id=user_id,
                    title="Memory",
                    body_markdown=body,
                    created_at=now,
                    updated_at=now,
                )
            )
            repo = SqlAlchemyQuizItemRepository(conn)
            item = QuizItem(
                id=item_id,
                source_id=None,
                user_id=user_id,
                origin=QuizItemOrigin.NOTE,
                note_id=note.id,
                item_type=QuizItemType.FREE_RECALL,
                question=card_question,
                answer=card_answer,
                section_path=("Memory",),
                anchor=f"note:{note.id}",
                source_excerpt=body,
                chunk_hash="e" * 64,
                content_key=content_key(
                    QuizItemType.FREE_RECALL, card_question, card_answer
                ),
                status=QuizItemStatus.ACTIVE,
                generation_meta={},
                created_at=now,
                updated_at=now,
            )
            # Store the *suggestion's* embedding so the greedy match pairs them, while the
            # card's text stays stale — the rewrite path.
            target = _free_recall_suggestion()
            repo.upsert(
                item, embedding=_embedding_of(target.question, target.answer)
            )
            repo.create_scheduling(
                item_id,
                SchedulingSnapshot(
                    state=2,
                    step=1,
                    stability=7.25,
                    difficulty=4.5,
                    due=now + timedelta(days=3),
                    last_review=now - timedelta(days=1),
                ),
            )
            repo.append_log(
                item_id,
                ReviewLogEntry(
                    rating=3, reviewed_at=now - timedelta(days=1), review_duration_ms=900
                ),
            )
        created_users.append(user_id)
        return note.id, item_id, target

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created_users:
            conn.execute(sa_delete(users).where(users.c.id == user_id))


def _scheduling_row(engine: Engine, item_id: UUID):  # noqa: ANN202
    with engine.connect() as conn:
        return SqlAlchemyQuizItemRepository(conn).get_scheduling(item_id)


def _log_rows(engine: Engine, item_id: UUID):  # noqa: ANN202
    with engine.connect() as conn:
        return conn.execute(
            select(
                review_log.c.rating,
                review_log.c.reviewed_at,
                review_log.c.review_duration_ms,
            ).where(review_log.c.quiz_item_id == item_id)
        ).all()


def _card_row(engine: Engine, item_id: UUID):  # noqa: ANN202
    with engine.connect() as conn:
        return conn.execute(
            select(
                quiz_items.c.question,
                quiz_items.c.answer,
                quiz_items.c.note_changed_at,
            ).where(quiz_items.c.id == item_id)
        ).one()


def test_refresh_rewrites_matched_card_and_preserves_memory(
    refresh_env, db_engine: Engine
) -> None:
    # The card's text is stale but its embedding matches the regenerated suggestion.
    note_id, item_id, target = refresh_env(
        card_question="A stale question?", card_answer="A stale answer"
    )
    before_sched = _scheduling_row(db_engine, item_id)
    before_log = _log_rows(db_engine, item_id)

    _refresh(None, str(note_id))

    card = _card_row(db_engine, item_id)
    # Rewritten in place to the regenerated free-recall text and flagged (NL-10/11).
    assert card.question == target.question
    assert card.answer == target.answer
    assert card.note_changed_at is not None
    # The memory history is byte-identical (the core invariant).
    assert _scheduling_row(db_engine, item_id) == before_sched
    assert _log_rows(db_engine, item_id) == before_log


def test_refresh_missing_note_is_a_noop(refresh_env, db_engine: Engine) -> None:
    # A note deleted before the task runs is a no-op (its cards survive, AD-145).
    _refresh(None, str(uuid4()))  # must not raise
