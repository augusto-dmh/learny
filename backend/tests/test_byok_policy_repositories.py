"""The BYOK policy ledgers at rest (live DB): upsert-increments, cascades, round-trips.

The monthly ledger and the per-corpus ledger accumulate by atomic upsert-
increment on their composite keys, so N debits land as one row equal to the
sum. The settings row upserts a budget (``NULL`` clears it). The turn row
round-trips the usage columns, and a deleted user (or source) leaves no orphan
ledger rows. Nothing here prices or refuses anything — that is the policy's
business; this is the write/read of what it reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Connection, delete, select

from app.domain.entities import Conversation, ConversationTurn, Source, User
from app.infrastructure.db.metadata import (
    byok_corpus_prompt_months,
    byok_month_usage,
    sources,
    user_byok_settings,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyByokCorpusRepository,
    SqlAlchemyByokMonthRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationTurnRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserByokSettingsRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db

pytestmark = requires_db

_MONTH = "2026-10"


def _user(db_conn: Connection) -> User:
    user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=datetime.now(UTC))
    SqlAlchemyUserRepository(db_conn).add(user)
    return user


_NOW = datetime.now(UTC)


def _source(db_conn: Connection, user_id: object) -> Source:  # noqa: ANN401
    return SqlAlchemySourceRepository(db_conn).add(
        Source(
            id=uuid4(),
            user_id=user_id,  # type: ignore[arg-type]
            title="A Book",
            filename="a-book.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="d" * 64,
            object_key=f"sources/{user_id}/{uuid4()}.epub",
            status="ready",
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


# --- the monthly ledger ------------------------------------------------------------


def test_monthly_ledger_increments_into_one_row(db_conn: Connection) -> None:
    user = _user(db_conn)
    repo = SqlAlchemyByokMonthRepository(db_conn)

    repo.record(user.id, _MONTH, input_tokens=100, output_tokens=40, cost_usd_micros=900)
    repo.record(user.id, _MONTH, input_tokens=25, output_tokens=10, cost_usd_micros=300)

    row = repo.get_for_month(user.id, _MONTH)
    assert row is not None
    assert (row.input_tokens, row.output_tokens, row.cost_usd_micros) == (125, 50, 1200)
    assert repo.get_for_month(user.id, "2026-11") is None
    assert repo.get_for_month(uuid4(), _MONTH) is None


def test_monthly_ledger_dies_with_its_user(db_conn: Connection) -> None:
    user = _user(db_conn)
    SqlAlchemyByokMonthRepository(db_conn).record(user.id, _MONTH, cost_usd_micros=5)

    SqlAlchemyUserByokSettingsRepository(db_conn).set_budget(user.id, 1_000_000)
    SqlAlchemyUserRepository(db_conn).delete(user.id)

    assert (
        db_conn.execute(
            select(byok_month_usage).where(byok_month_usage.c.user_id == user.id)
        ).first()
        is None
    )
    assert (
        db_conn.execute(
            select(user_byok_settings).where(user_byok_settings.c.user_id == user.id)
        ).first()
        is None
    )


# --- the per-corpus ledger ---------------------------------------------------------


def test_corpus_ledger_scopes_by_user_source_and_month(db_conn: Connection) -> None:
    user, other = _user(db_conn), _user(db_conn)
    source, another = _source(db_conn, user.id), _source(db_conn, user.id)
    repo = SqlAlchemyByokCorpusRepository(db_conn)

    repo.record(user.id, source.id, _MONTH, input_tokens=8000)
    repo.record(user.id, source.id, _MONTH, input_tokens=8000)
    repo.record(other.id, source.id, _MONTH, input_tokens=999)
    repo.record(user.id, another.id, _MONTH, input_tokens=777)

    row = repo.get_for_month(user.id, source.id, _MONTH)
    assert row is not None
    assert row.input_tokens == 16000  # this learner's calls on this book only
    assert repo.get_for_month(user.id, source.id, "2026-09") is None


def test_corpus_ledger_dies_with_its_source(db_conn: Connection) -> None:
    user = _user(db_conn)
    source = _source(db_conn, user.id)
    SqlAlchemyByokCorpusRepository(db_conn).record(user.id, source.id, _MONTH, input_tokens=10)

    db_conn.execute(delete(sources).where(sources.c.id == source.id))

    assert (
        db_conn.execute(
            select(byok_corpus_prompt_months).where(
                byok_corpus_prompt_months.c.source_id == source.id
            )
        ).first()
        is None
    )


# --- the settings row ----------------------------------------------------------------


def test_budget_upsert_sets_and_clears(db_conn: Connection) -> None:
    user = _user(db_conn)
    repo = SqlAlchemyUserByokSettingsRepository(db_conn)

    assert repo.get(user.id) is None  # nothing set yet: not a zero budget, an absent row

    stored = repo.set_budget(user.id, 2_500_000)
    assert stored.monthly_budget_usd_micros == 2_500_000
    assert (
        repo.get(user.id) is not None and repo.get(user.id).monthly_budget_usd_micros == 2_500_000
    )  # type: ignore[union-attr]

    raised = repo.set_budget(user.id, 9_000_000)
    assert raised.monthly_budget_usd_micros == 9_000_000

    cleared = repo.set_budget(user.id, None)
    assert cleared.monthly_budget_usd_micros is None


# --- the turn's usage columns --------------------------------------------------------


def _turn(conversation_id: object, **overrides: object) -> ConversationTurn:  # noqa: ANN401
    fields: dict[str, object] = {
        "id": uuid4(),
        "conversation_id": conversation_id,
        "turn_index": 0,
        "message": "What is this about?",
        "mode": "answer",
        "answer_status": "answered",
        "answer_text": "It is about war.",
        "model": "claude-byok",
        "evidence_count": 0,
        "citations": (),
        "created_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return ConversationTurn(**fields)  # type: ignore[arg-type]


def test_turn_round_trips_usage_columns(db_conn: Connection) -> None:
    user = _user(db_conn)
    source = _source(db_conn, user.id)
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source.id,
            title="Chapter 1",
            scope_anchors=(),
            include_notes=False,
            target_anchor=None,
            target_section_path=None,
            target_title=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    repo = SqlAlchemyConversationTurnRepository(db_conn)

    repo.add(
        _turn(
            conversation.id,
            usage_input_tokens=1234,
            usage_output_tokens=567,
            cost_usd_micros=8910,
            user_keyed=True,
        )
    )
    repo.add(_turn(conversation.id, turn_index=1))  # a house turn: defaults

    turns = {turn.turn_index: turn for turn in repo.list_for_conversation(conversation.id)}
    keyed = turns[0]
    assert (keyed.usage_input_tokens, keyed.usage_output_tokens) == (1234, 567)
    assert keyed.cost_usd_micros == 8910
    assert keyed.user_keyed is True
    house = turns[1]
    assert (house.usage_input_tokens, house.usage_output_tokens) is not None
    assert house.usage_input_tokens is None and house.usage_output_tokens is None
    assert house.cost_usd_micros is None
    assert house.user_keyed is False
