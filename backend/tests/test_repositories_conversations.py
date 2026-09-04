"""Conversation repository — tutor-ladder columns (TUTOR-16, TUTOR-26).

Integration proofs that the conversation row is the home of ladder state: a
conversation written without tutor kwargs reads as a null phase (pre-cycle /
Answer), a full ladder round-trips, ``update_tutor_state`` is the write path
(there is no generic save), and the all-or-nothing CHECK refuses a half-set pair.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Conversation, Source, User
from app.infrastructure.db.repositories import (
    SqlAlchemyConversationRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _new_user(email: str) -> User:
    return User(id=uuid4(), email=email, created_at=_NOW)


def _new_source(user_id: UUID) -> Source:
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="uploaded",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _persisted_source(db_conn: Connection, email: str) -> Source:
    user = _new_user(email)
    SqlAlchemyUserRepository(db_conn).add(user)
    return SqlAlchemySourceRepository(db_conn).add(_new_source(user.id))


def _conversation(source_id: UUID, **overrides: object) -> Conversation:
    fields: dict[str, object] = {
        "id": uuid4(),
        "source_id": source_id,
        "title": "Chapter 1",
        "scope_anchors": ("ch1.xhtml",),
        "include_notes": False,
        "target_anchor": "ch1.xhtml",
        "target_section_path": ("Chapter 1",),
        "target_title": "Chapter 1",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    fields.update(overrides)
    return Conversation(**fields)  # type: ignore[arg-type]


def test_conversation_add_reads_pre_cycle_tutor_state_as_null_phase(db_conn: Connection) -> None:
    # TUTOR-26: a conversation constructed the way StartConversation still does
    # (no tutor kwargs) stores a null phase. Pre-cycle teach threads and Answer
    # threads share that spelling.
    source = _persisted_source(db_conn, "tutor-null-phase@example.com")
    repo = SqlAlchemyConversationRepository(db_conn)
    stored = repo.add(_conversation(source.id))

    fetched = repo.get_by_id(stored.id)

    assert fetched is not None
    assert (fetched.tutor_phase, fetched.hint_level) == (None, None)
    assert (fetched.tutor_ordinary_turns, fetched.tutor_scaffold_misses) == (0, 0)
    assert fetched.tutor_check_text is None


def test_conversation_round_trips_tutor_ladder_state(db_conn: Connection) -> None:
    # TUTOR-16: opening stores phase=open and hint=pump. The repository is the
    # write/read of that pair, not the policy that chooses it.
    source = _persisted_source(db_conn, "tutor-round-trip@example.com")
    repo = SqlAlchemyConversationRepository(db_conn)
    stored = repo.add(
        _conversation(
            source.id,
            tutor_phase="open",
            hint_level="pump",
            tutor_ordinary_turns=2,
            tutor_scaffold_misses=1,
            tutor_check_text=None,
        )
    )

    fetched = repo.get_by_id(stored.id)

    assert fetched == stored
    assert (fetched.tutor_phase, fetched.hint_level) == ("open", "pump")
    assert (fetched.tutor_ordinary_turns, fetched.tutor_scaffold_misses) == (2, 1)
    assert fetched.tutor_check_text is None


def test_conversation_update_tutor_state_writes_ladder_columns(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "tutor-update@example.com")
    repo = SqlAlchemyConversationRepository(db_conn)
    created = repo.add(_conversation(source.id))
    later = _NOW + timedelta(minutes=1)
    advanced = _conversation(
        source.id,
        id=created.id,
        created_at=created.created_at,
        updated_at=later,
        tutor_phase="check",
        hint_level="assert",
        tutor_ordinary_turns=3,
        tutor_scaffold_misses=2,
        tutor_check_text="Photosynthesis stores sunlight as sugar.",
    )

    written = repo.update_tutor_state(advanced)
    fetched = repo.get_by_id(created.id)

    assert written == advanced
    assert fetched == advanced
    assert fetched.tutor_phase == "check"
    assert fetched.hint_level == "assert"
    assert fetched.tutor_ordinary_turns == 3
    assert fetched.tutor_scaffold_misses == 2
    assert fetched.tutor_check_text == "Photosynthesis stores sunlight as sugar."
    assert repo.update_tutor_state(_conversation(source.id)) is None


def test_conversation_check_refuses_phase_without_hint(db_conn: Connection) -> None:
    # Sensor: the pair is all-or-nothing. A row with a phase and a null hint is
    # not a state the policy can recover from, so the database refuses it.
    source = _persisted_source(db_conn, "tutor-check-phase@example.com")
    repo = SqlAlchemyConversationRepository(db_conn)

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            repo.add(_conversation(source.id, tutor_phase="open"))


def test_conversation_check_refuses_hint_without_phase(db_conn: Connection) -> None:
    source = _persisted_source(db_conn, "tutor-check-hint@example.com")
    repo = SqlAlchemyConversationRepository(db_conn)

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            repo.add(_conversation(source.id, hint_level="pump"))


def test_conversation_sql_defaults_match_entity_defaults(db_conn: Connection) -> None:
    # A raw INSERT that omits the tutor columns (the shape a pre-cycle writer
    # used) still reads as a null phase with zero counters.
    source = _persisted_source(db_conn, "tutor-sql-default@example.com")
    conversation_id = uuid4()
    db_conn.execute(
        text(
            "INSERT INTO conversations "
            "(id, source_id, title, scope_anchors, include_notes, "
            " target_anchor, target_section_path, target_title) "
            "VALUES (:id, :sid, 'Chapter 1', '[\"ch1.xhtml\"]'::jsonb, false, "
            "        'ch1.xhtml', '[\"Chapter 1\"]'::jsonb, 'Chapter 1')"
        ),
        {"id": conversation_id, "sid": source.id},
    )

    fetched = SqlAlchemyConversationRepository(db_conn).get_by_id(conversation_id)

    assert fetched is not None
    assert (fetched.tutor_phase, fetched.hint_level) == (None, None)
    assert (fetched.tutor_ordinary_turns, fetched.tutor_scaffold_misses) == (0, 0)
    assert fetched.tutor_check_text is None
