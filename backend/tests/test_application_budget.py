"""Daily AI spend ledger and budget service (integration, live test DB).

The RFC-0007 Cycle F spend-cap specs at the layer the Test Coverage Matrix pins for
budget/kill integration behaviour:

- The ``ai_spend_days`` ledger accumulates same-day increments atomically — two
  increments never lose one, USD micros and the integer counters each sum, and
  different UTC days are separate rows.
- The daily USD cap refuses a turn or deck POST with the honest 429 copy *before*
  the provider port is touched (the ordering is the observable: a recording
  generation double must stay call-free), and a successful call debits the usage it
  actually reported. An FSRS review never touches the ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from app.application.budget import (
    EXHAUSTED_COPY,
    KIND_ASK,
    PAUSED_COPY,
    DailyBudget,
    TokenPrices,
)
from app.application.conversations import PostConversationTurn
from app.application.errors import AiPaused, DailyBudgetExhausted
from app.application.identity import AuthorizeOwnership
from app.application.quiz_qc import content_key
from app.application.reviews import SubmitReview
from app.domain.entities import (
    ANSWERED,
    MODE_ANSWER,
    MODE_TEACH,
    TUTOR_OPENING_MESSAGE,
    AiSpendDay,
    AnswerCompleted,
    AnswerTextDelta,
    ChunkToEmbed,
    Conversation,
    ConversationTurn,
    CorpusSectionRecord,
    Evidence,
    GeneratedAnswer,
    IngestionJob,
    ParsedSection,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    SchedulingSnapshot,
    SectionChunk,
    Source,
    TokenUsage,
    User,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyAiSpendDayRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationTurnRepository,
    SqlAlchemyCorpusRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyStudyDayRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.scheduling import FsrsSchedulingAdapter
from app.infrastructure.web.dependencies import get_generation
from tests.conftest import TEST_ORIGIN, TEST_PASSWORD, requires_db
from tests.fakes import (
    FakeAiSpendDayRepository,
    FakeClock,
    FakeEmbeddingIndexRepository,
    FakeEmbeddingPort,
    FakeIngestionEventRepository,
)

pytestmark = requires_db

_NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
_DAY = _NOW.date()

#: The web composition budgets on the real system clock, so the tests that drive
#: HTTP endpoints seed the LIVE UTC day — a frozen seed date goes stale at UTC
#: midnight and the cap silently stops firing (the seed would pay "yesterday").
_LIVE_DAY = datetime.now(UTC).date()

#: $1 per million input tokens, $2 per million output tokens — round numbers so a
#: debit's expected micros are hand-checkable.
_PRICES = TokenPrices(
    input_micros_per_million=1_000_000,
    output_micros_per_million=2_000_000,
    embed_micros_per_million=0,
)
_CAP_MICROS = 1_000_000


def _add_user(db_conn: Connection, email: str) -> User:
    return SqlAlchemyUserRepository(db_conn).add(
        User(id=uuid4(), email=email, created_at=datetime.now(UTC))
    )


def _ledger(db_conn: Connection) -> SqlAlchemyAiSpendDayRepository:
    return SqlAlchemyAiSpendDayRepository(db_conn)


def _budget(
    db_conn: Connection,
    *,
    cap_micros: int = _CAP_MICROS,
    ask_cap: int = 8,
    teach_start_cap: int = 1,
) -> DailyBudget:
    return DailyBudget(
        repo=_ledger(db_conn),
        clock=FakeClock(_NOW),
        daily_cap_micros=cap_micros,
        prices=_PRICES,
        ask_daily_cap=ask_cap,
        teach_start_daily_cap=teach_start_cap,
    )


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
    repo.record(user.id, _DAY - timedelta(days=1), usd_micros=1)

    today = repo.get_for_day(user.id, _DAY)
    assert today is not None
    assert today.usd_micros == 9_999_999


# --- Turn-path doubles -----------------------------------------------------------


class _StubRetrieve:
    """``RetrieveEvidence`` double: returns the preset evidence, records the call."""

    def __init__(self, evidence: list[Evidence]) -> None:
        self._evidence = evidence
        self.calls: list[UUID] = []

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID,
        query: str,
        top_k: int | None = None,
        anchors: Sequence[str] | None = None,
        include_notes: bool = False,
    ) -> list[Evidence]:
        self.calls.append(source_id)
        return list(self._evidence)


class _RecordingGeneration:
    """``GenerationPort`` double: preset answer, records every call it gets.

    The zero-calls sensor for the assert-before-provider ordering: a refused turn
    must leave ``calls`` and ``stream_calls`` empty.
    """

    def __init__(self, answer: GeneratedAnswer) -> None:
        self._answer = answer
        self.model = answer.model
        self.calls = 0
        self.stream_calls = 0

    def generate(self, **_kwargs) -> GeneratedAnswer:  # noqa: ANN003 — port kwargs
        self.calls += 1
        return self._answer

    def generate_stream(self, **_kwargs):  # noqa: ANN003, ANN202 — port kwargs
        self.stream_calls += 1

        def _stream():
            if self._answer.text:
                yield AnswerTextDelta(text=self._answer.text)
            yield AnswerCompleted(answer=self._answer)

        return _stream()


def _declining_answer(*, usage: TokenUsage | None) -> GeneratedAnswer:
    """A successful provider reply that declines to answer (evidence can't support it).

    Debit happens on port success, before grounding, so a decline is exactly the
    cheapest successful call to assert the ledger against.
    """
    return GeneratedAnswer(
        text="",
        cited_chunk_ids=(),
        model="test-model",
        found=False,
        usage=usage,
    )


def _evidence(source_id: UUID) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=source_id,
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        page_span=None,
        snippet="Some grounded text.",
        score=0.5,
    )


def _seed_turn_world(db_conn: Connection, email: str) -> tuple[User, Source, Conversation]:
    """A user with an owned ready source and a whole-book conversation on it."""
    user = _add_user(db_conn, email)
    now = datetime.now(UTC)
    source = SqlAlchemySourceRepository(db_conn).add(
        Source(
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
    )
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source.id,
            title="A Book",
            scope_anchors=(),
            include_notes=False,
            target_anchor=None,
            target_section_path=None,
            target_title=None,
            tutor_phase=None,
            hint_level=None,
            tutor_check_text=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    return user, source, conversation


def _turn_service(
    db_conn: Connection,
    *,
    generation: _RecordingGeneration,
    retrieve: _StubRetrieve,
    budget: DailyBudget | None,
) -> PostConversationTurn:
    return PostConversationTurn(
        conversations=SqlAlchemyConversationRepository(db_conn),
        turns=SqlAlchemyConversationTurnRepository(db_conn),
        sources=SqlAlchemySourceRepository(db_conn),
        corpus=SqlAlchemyCorpusRepository(db_conn),
        retrieve=retrieve,
        generation=generation,
        authorize=AuthorizeOwnership(),
        clock=FakeClock(_NOW),
        ids=uuid4,
        evidence_top_k=8,
        history_turns=6,
        tutor_check_after_turns=3,
        budget=budget,
    )


# --- USD cap: refuse before the provider, debit after success (DOOR-08/09/14) -----


def test_exhausted_usd_day_refuses_the_ask_before_the_provider(
    db_conn: Connection,
) -> None:
    user, source, conversation = _seed_turn_world(db_conn, "budget-cap@example.com")
    _ledger(db_conn).record(user.id, _DAY, usd_micros=_CAP_MICROS)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    with pytest.raises(DailyBudgetExhausted) as refused:
        service(user=user, conversation_id=conversation.id, message="Why?", mode=MODE_ANSWER)

    # Honest copy, and the ordering observable: neither retrieval nor the provider
    # ever ran past the guard, so the refusal cannot have cost anything.
    assert EXHAUSTED_COPY in str(refused.value)
    assert generation.calls == 0
    assert retrieve.calls == []
    # Nothing was written: the day's row still says exactly what it said.
    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.usd_micros == _CAP_MICROS
    turns = SqlAlchemyConversationTurnRepository(db_conn).list_for_conversation(conversation.id)
    assert turns == []


def test_successful_ask_debits_the_usage_it_actually_used(db_conn: Connection) -> None:
    # DOOR-09: a successful call adds its USD — adapter usage × the price catalog —
    # to the day's ledger. (1500 in × $1/M) + (250 out × $2/M) = 2000 micros.
    user, source, conversation = _seed_turn_world(db_conn, "budget-debit@example.com")
    generation = _RecordingGeneration(
        _declining_answer(usage=TokenUsage(input_tokens=1500, output_tokens=250))
    )
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    service(user=user, conversation_id=conversation.id, message="Why?", mode=MODE_ANSWER)

    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.usd_micros == 2000
    assert generation.calls == 1


def test_generation_without_reported_usage_debits_nothing(db_conn: Connection) -> None:
    # DOOR-14: the deterministic local adapters report no usage, so no USD is
    # recorded — but the free-tier Ask counter still counts the call (DOOR-10),
    # because the integer caps are call counts, not amounts.
    user, source, conversation = _seed_turn_world(db_conn, "budget-local@example.com")
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    service(user=user, conversation_id=conversation.id, message="Why?", mode=MODE_ANSWER)

    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None
    assert (row.usd_micros, row.ask_count, row.teach_starts) == (0, 1, 0)
    assert generation.calls == 1  # the call ran; it simply cost nothing recorded


def test_stream_refusal_happens_before_any_provider_call(db_conn: Connection) -> None:
    user, source, conversation = _seed_turn_world(db_conn, "budget-stream-cap@example.com")
    _ledger(db_conn).record(user.id, _DAY, usd_micros=_CAP_MICROS)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    with pytest.raises(DailyBudgetExhausted):
        service.stream(user=user, conversation_id=conversation.id, message="Why?", mode=MODE_ANSWER)

    assert generation.calls == 0
    assert generation.stream_calls == 0


def test_stream_turn_debits_when_the_stream_completes(db_conn: Connection) -> None:
    user, source, conversation = _seed_turn_world(db_conn, "budget-stream@example.com")
    generation = _RecordingGeneration(
        _declining_answer(usage=TokenUsage(input_tokens=1500, output_tokens=250))
    )
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    events = list(
        service.stream(user=user, conversation_id=conversation.id, message="Why?", mode=MODE_ANSWER)
    )

    assert events, "the stream must complete for the debit to be earned"
    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.usd_micros == 2000


def _seed_committed_turn_world(db_engine, email: str) -> tuple[User, Source]:
    """Seed a user + ready source on their OWN committed connection.

    ``_record_deck_spend`` resolves the owner through a fresh worker connection, so
    the rows it reads must be committed — the per-test ``db_conn`` transaction is
    invisible to it. Rows are deleted by the caller so nothing leaks into the shared
    test database.
    """
    user_id = uuid4()
    now = datetime.now(UTC)
    with db_engine.begin() as conn:
        SqlAlchemyUserRepository(conn).add(User(id=user_id, email=email, created_at=now))
        source = SqlAlchemySourceRepository(conn).add(
            Source(
                id=uuid4(),
                user_id=user_id,
                title="A Book",
                filename="a-book.epub",
                content_type="application/epub+zip",
                byte_size=1024,
                checksum="d" * 64,
                object_key=f"sources/{user_id}/{uuid4()}.epub",
                status="ready",
                created_at=now,
                updated_at=now,
            )
        )
    return User(id=user_id, email=email, created_at=now), source


def _committed_spend(db_engine, user_id: UUID) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM ai_spend_days WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM sources WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})


def test_deck_worker_debits_the_pass_usage_to_its_owner(
    db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # DOOR-09 on the worker-side deck pass: the debit uses the same ledger, priced
    # from the usage the adapter attached to the result.
    from app.worker import tasks as deck_tasks

    monkeypatch.setattr(deck_tasks, "get_engine", lambda: db_engine)
    user, source = _seed_committed_turn_world(db_engine, "budget-deck@example.com")
    try:

        class _Result:
            candidates = ()
            errors = ()
            usage = TokenUsage(input_tokens=2000, output_tokens=1000)

        deck_tasks._record_deck_spend(source.id, _Result())

        # Priced with the operator's default catalog ($3/M in, $15/M out):
        # 2000 in + 1000 out = 21_000 micros.
        with db_engine.connect() as conn:
            row = SqlAlchemyAiSpendDayRepository(conn).get_for_day(
                user.id, datetime.now(UTC).date()
            )
        assert row is not None and row.usd_micros == 21_000
    finally:
        _committed_spend(db_engine, user.id)


def test_deck_worker_local_result_debits_nothing(
    db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.worker import tasks as deck_tasks

    monkeypatch.setattr(deck_tasks, "get_engine", lambda: db_engine)
    user, source = _seed_committed_turn_world(db_engine, "budget-deck-local@example.com")
    try:

        class _LocalResult:
            candidates = ()
            errors = ()
            usage = None

        deck_tasks._record_deck_spend(source.id, _LocalResult())

        with db_engine.connect() as conn:
            assert (
                SqlAlchemyAiSpendDayRepository(conn).get_for_day(user.id, datetime.now(UTC).date())
                is None
            )
    finally:
        _committed_spend(db_engine, user.id)


# --- Reviews are $0 (DOOR-13) ----------------------------------------------------


def test_review_submit_leaves_the_ledger_untouched(db_conn: Connection) -> None:
    user, source, _conversation = _seed_turn_world(db_conn, "budget-review@example.com")
    _ledger(db_conn).record(user.id, _DAY, usd_micros=4321)
    now = datetime.now(UTC)
    item_repo = SqlAlchemyQuizItemRepository(db_conn)
    question, answer = "What is the powerhouse of the cell?", "Mitochondria"
    item = QuizItem(
        id=uuid4(),
        source_id=source.id,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        source_excerpt="powerhouse",
        chunk_hash="c" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
        status=QuizItemStatus.ACTIVE,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    item_repo.upsert(item, embedding=None)
    item_repo.create_scheduling(
        item.id,
        SchedulingSnapshot(
            state=1,
            step=0,
            stability=None,
            difficulty=None,
            due=now - timedelta(hours=1),
            last_review=None,
        ),
    )

    SubmitReview(
        items=item_repo,
        scheduling=FsrsSchedulingAdapter(fuzzing=False),
        clock=FakeClock(_NOW),
        study_days=SqlAlchemyStudyDayRepository(db_conn),
    )(user=user, item_id=item.id, rating=3)

    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None
    assert (row.usd_micros, row.ask_count, row.teach_starts) == (4321, 0, 0)


# --- Ask and Teach daily integers (DOOR-10/11) -----------------------------------


def _seed_corpus(db_conn: Connection, source_id: UUID) -> None:
    chunk = SectionChunk(
        index=0,
        text="Grounded text.",
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        page_span=None,
    )
    record = CorpusSectionRecord(
        section=ParsedSection(
            position=0,
            title="Chapter 1",
            depth=0,
            section_path=("Chapter 1",),
            anchor="ch1.xhtml",
            blocks=(),
        ),
        markdown="",
        chunks=(chunk,),
    )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(record,),
    )


def _seed_scoped_conversation(db_conn: Connection, source_id: UUID) -> Conversation:
    """A chapter-scoped conversation with a live target — teachable."""
    return SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source_id,
            title="Chapter 1",
            scope_anchors=("ch1.xhtml",),
            include_notes=False,
            target_anchor="ch1.xhtml",
            target_section_path=("Chapter 1",),
            target_title="Chapter 1",
            tutor_phase=None,
            hint_level=None,
            tutor_check_text=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def _seed_prior_turn(
    db_conn: Connection,
    conversation_id: UUID,
    *,
    turn_index: int,
    mode: str,
    answer_status: str,
) -> None:
    SqlAlchemyConversationTurnRepository(db_conn).add(
        ConversationTurn(
            id=uuid4(),
            conversation_id=conversation_id,
            turn_index=turn_index,
            message="earlier",
            mode=mode,
            answer_status=answer_status,
            answer_text="earlier answer",
            model="test-model",
            evidence_count=0,
            citations=(),
            created_at=_NOW,
        )
    )


def test_ninth_ask_is_refused_and_the_thread_survives(db_conn: Connection) -> None:
    # DOOR-10: 8 Asks used, so the ninth refuses with the honest copy and zero
    # provider work — and nothing about the conversation is taken away.
    user, source, conversation = _seed_turn_world(db_conn, "ask-cap@example.com")
    _ledger(db_conn).record(user.id, _DAY, asks=8)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    with pytest.raises(DailyBudgetExhausted) as refused:
        service(user=user, conversation_id=conversation.id, message="Nine?", mode=MODE_ANSWER)

    assert EXHAUSTED_COPY in str(refused.value)
    assert generation.calls == 0
    turns = SqlAlchemyConversationTurnRepository(db_conn).list_for_conversation(conversation.id)
    assert turns == []
    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.ask_count == 8


def test_the_eighth_ask_still_runs_and_bumps_the_counter(db_conn: Connection) -> None:
    # The cap counts *used* asks: seven used means the eighth runs — and its success
    # is what writes the eighth count.
    user, source, conversation = _seed_turn_world(db_conn, "ask-eighth@example.com")
    _ledger(db_conn).record(user.id, _DAY, asks=7)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    service(user=user, conversation_id=conversation.id, message="Eight?", mode=MODE_ANSWER)

    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.ask_count == 8


def test_second_teach_start_same_day_is_refused(db_conn: Connection) -> None:
    # DOOR-11: one Teach session start per UTC day. A teach turn at index 0 *is*
    # the session start, so a second one refuses before any provider work.
    user, source, _ = _seed_turn_world(db_conn, "teach-cap@example.com")
    _seed_corpus(db_conn, source.id)
    conversation = _seed_scoped_conversation(db_conn, source.id)
    _ledger(db_conn).record(user.id, _DAY, teach_starts=1)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    with pytest.raises(DailyBudgetExhausted):
        service(
            user=user,
            conversation_id=conversation.id,
            message=TUTOR_OPENING_MESSAGE,
            mode=MODE_TEACH,
        )

    assert generation.calls == 0


def test_first_teach_start_of_a_day_runs_and_counts(db_conn: Connection) -> None:
    user, source, _ = _seed_turn_world(db_conn, "teach-first@example.com")
    _seed_corpus(db_conn, source.id)
    conversation = _seed_scoped_conversation(db_conn, source.id)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    service(
        user=user,
        conversation_id=conversation.id,
        message=TUTOR_OPENING_MESSAGE,
        mode=MODE_TEACH,
    )

    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.teach_starts == 1


def test_teach_continuation_is_not_charged_as_a_session_start(db_conn: Connection) -> None:
    # A teach turn past index 0 continues the session that already spent its one
    # start: it rides the USD cap (kind ``generation``), never the starts counter.
    user, source, _ = _seed_turn_world(db_conn, "teach-cont@example.com")
    _seed_corpus(db_conn, source.id)
    conversation = _seed_scoped_conversation(db_conn, source.id)
    _seed_prior_turn(
        db_conn, conversation.id, turn_index=0, mode=MODE_TEACH, answer_status=ANSWERED
    )
    _ledger(db_conn).record(user.id, _DAY, teach_starts=1)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    service(user=user, conversation_id=conversation.id, message="Go on…", mode=MODE_TEACH)

    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None
    assert (row.teach_starts, row.ask_count) == (1, 0)
    assert generation.calls == 1


def test_ask_cap_does_not_gate_a_teach_start_and_vice_versa(db_conn: Connection) -> None:
    # The meters are separate: a used-up Ask budget leaves the Teach start, and a
    # spent Teach start leaves the asks — only the USD cap is shared.
    user, source, conversation = _seed_turn_world(db_conn, "caps-separate@example.com")
    _ledger(db_conn).record(user.id, _DAY, asks=8)
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )

    with pytest.raises(DailyBudgetExhausted):
        service(user=user, conversation_id=conversation.id, message="Nine?", mode=MODE_ANSWER)

    # Same exhausted-ask day, but a teach start is not an ask.
    _seed_corpus(db_conn, source.id)
    teach_conversation = _seed_scoped_conversation(db_conn, source.id)
    service = _turn_service(
        db_conn, generation=generation, retrieve=retrieve, budget=_budget(db_conn)
    )
    service(
        user=user,
        conversation_id=teach_conversation.id,
        message=TUTOR_OPENING_MESSAGE,
        mode=MODE_TEACH,
    )
    row = _ledger(db_conn).get_for_day(user.id, _DAY)
    assert row is not None and row.teach_starts == 1


# --- Route level: the honest 429 at the real wiring ------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _seed_web_source(db_conn: Connection, user_id: str, *, status: str = "ready") -> UUID:
    now = datetime.now(UTC)
    return (
        SqlAlchemySourceRepository(db_conn)
        .add(
            Source(
                id=uuid4(),
                user_id=UUID(user_id),
                title="A Book",
                filename="a-book.epub",
                content_type="application/epub+zip",
                byte_size=1024,
                checksum="d" * 64,
                object_key=f"sources/{user_id}/{uuid4()}.epub",
                status=status,
                created_at=now,
                updated_at=now,
            )
        )
        .id
    )


def test_ask_turn_past_the_usd_cap_is_429_and_keeps_the_thread(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # DOOR-08 at the real wiring: the daily cap refuses the POST with the honest
    # copy and the generation adapter is never constructed into a call; the
    # conversation row and its history survive the refusal.
    user_id = _register(auth_client, "budget-web@example.com")
    csrf = _csrf(auth_client)
    source_id = _seed_web_source(db_conn, user_id)
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source_id,
            title="A Book",
            scope_anchors=(),
            include_notes=False,
            target_anchor=None,
            target_section_path=None,
            target_title=None,
            tutor_phase=None,
            hint_level=None,
            tutor_check_text=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    _ledger(db_conn).record(UUID(user_id), _LIVE_DAY, usd_micros=500_000)

    class _NeverCalled:
        model = "never"

        def generate(self, **_kwargs):  # noqa: ANN003
            raise AssertionError("provider must not be called past the cap")

        def generate_stream(self, **_kwargs):  # noqa: ANN003
            raise AssertionError("provider must not be called past the cap")

    auth_client.app.dependency_overrides[get_generation] = lambda: _NeverCalled()
    try:
        resp = auth_client.post(
            f"/api/conversations/{conversation.id}/turns",
            json={"message": "Why?", "mode": MODE_ANSWER},
            headers={"X-CSRF-Token": csrf, "Origin": TEST_ORIGIN},
        )
    finally:
        auth_client.app.dependency_overrides.pop(get_generation, None)

    assert resp.status_code == 429, resp.text
    assert "00:00 UTC" in resp.json()["detail"]
    # The thread remains: the refusal costs the reader nothing but the wait.
    still_there = auth_client.get(
        f"/api/conversations/{conversation.id}", headers={"X-CSRF-Token": csrf}
    )
    assert still_there.status_code == 200, still_there.text
    assert still_there.json()["turns"] == []


def test_ninth_ask_at_the_route_is_429_and_keeps_the_conversation(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # DOOR-10's independent test, at the real wiring: the ninth Ask of the UTC day
    # is a 429 with the honest copy, the provider is never invoked, and the
    # conversation row (with its history) remains.
    user_id = _register(auth_client, "ask-cap-web@example.com")
    csrf = _csrf(auth_client)
    source_id = _seed_web_source(db_conn, user_id)
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source_id,
            title="A Book",
            scope_anchors=(),
            include_notes=False,
            target_anchor=None,
            target_section_path=None,
            target_title=None,
            tutor_phase=None,
            hint_level=None,
            tutor_check_text=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    SqlAlchemyConversationTurnRepository(db_conn).add(
        ConversationTurn(
            id=uuid4(),
            conversation_id=conversation.id,
            turn_index=0,
            message="earlier",
            mode=MODE_ANSWER,
            answer_status=ANSWERED,
            answer_text="earlier answer",
            model="test-model",
            evidence_count=0,
            citations=(),
            created_at=_NOW,
        )
    )
    _ledger(db_conn).record(UUID(user_id), _LIVE_DAY, asks=8)

    class _NeverCalled:
        model = "never"

        def generate(self, **_kwargs):  # noqa: ANN003
            raise AssertionError("provider must not be called past the ask cap")

        def generate_stream(self, **_kwargs):  # noqa: ANN003
            raise AssertionError("provider must not be called past the ask cap")

    auth_client.app.dependency_overrides[get_generation] = lambda: _NeverCalled()
    try:
        resp = auth_client.post(
            f"/api/conversations/{conversation.id}/turns",
            json={"message": "Nine?", "mode": MODE_ANSWER},
            headers={"X-CSRF-Token": csrf, "Origin": TEST_ORIGIN},
        )
    finally:
        auth_client.app.dependency_overrides.pop(get_generation, None)

    assert resp.status_code == 429, resp.text
    assert "00:00 UTC" in resp.json()["detail"]
    # The thread remains: its history is exactly what it was before the refusal.
    still_there = auth_client.get(
        f"/api/conversations/{conversation.id}", headers={"X-CSRF-Token": csrf}
    )
    assert still_there.status_code == 200, still_there.text
    assert [t["turn_index"] for t in still_there.json()["turns"]] == [0]


def test_deck_post_past_the_usd_cap_is_429_and_starts_nothing(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "budget-deck-web@example.com")
    csrf = _csrf(quiz_client)
    source_id = _seed_web_source(db_conn, user_id)
    _ledger(db_conn).record(UUID(user_id), _LIVE_DAY, usd_micros=500_000)

    resp = quiz_client.post(
        f"/api/sources/{source_id}/quiz/deck",
        headers={"X-CSRF-Token": csrf, "Origin": TEST_ORIGIN},
    )

    assert resp.status_code == 429, resp.text
    assert "00:00 UTC" in resp.json()["detail"]
    # No queued job, no enqueue: the refusal happened before the plan committed.
    assert quiz_client.app.state.quiz_enqueuer.calls == []
    from sqlalchemy import select

    from app.infrastructure.db.metadata import quiz_generation_jobs

    rows = db_conn.execute(select(quiz_generation_jobs)).all()
    assert rows == []


# --- Operator kill switch (DOOR-12/13) -------------------------------------------


def test_kill_switch_refuses_the_turn_before_the_provider(db_conn: Connection) -> None:
    user, source, conversation = _seed_turn_world(db_conn, "pause-turn@example.com")
    generation = _RecordingGeneration(_declining_answer(usage=None))
    retrieve = _StubRetrieve([_evidence(source.id)])
    paused = DailyBudget(
        repo=_ledger(db_conn),
        clock=FakeClock(_NOW),
        daily_cap_micros=_CAP_MICROS,
        prices=_PRICES,
        ask_daily_cap=8,
        teach_start_daily_cap=1,
        ai_paused=True,
    )
    guarded = _turn_service(db_conn, generation=generation, retrieve=retrieve, budget=paused)

    with pytest.raises(AiPaused) as paused_exc:
        guarded(user=user, conversation_id=conversation.id, message="Why?", mode=MODE_ANSWER)

    assert PAUSED_COPY in str(paused_exc.value)
    assert generation.calls == 0
    # The pause is checked before the ledger: even a fresh day refuses.
    assert _ledger(db_conn).get_for_day(user.id, _DAY) is None


def test_kill_switch_beats_the_budget_ledger(db_conn: Connection) -> None:
    # The operator's pause wins whichever way the meters read — a paused process
    # answers with the pause copy, never a spend figure.
    paused = DailyBudget(
        repo=FakeAiSpendDayRepository(),
        clock=FakeClock(_NOW),
        daily_cap_micros=0,
        prices=_PRICES,
        ask_daily_cap=8,
        teach_start_daily_cap=1,
        ai_paused=True,
    )
    with pytest.raises(AiPaused):
        paused.assert_generation(uuid4(), kind=KIND_ASK)


def test_kill_switch_stops_the_embed_step_before_the_provider(db_conn: Connection) -> None:
    # DOOR-12's embedding-producing ingest step: with the switch on, the embed step
    # raises before the embedding port is touched — no SDK, no batches.
    from app.application.retrieval import EmbedCorpus

    user = _add_user(db_conn, "pause-embed@example.com")
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        status="processing",
        created_at=now,
        updated_at=now,
    )
    job = IngestionJob(
        id=uuid4(),
        source_id=source.id,
        status="running",
        attempts=1,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    embeddings = FakeEmbeddingPort()
    chunks = ChunkToEmbed(id=uuid4(), text="some text")
    paused = DailyBudget(
        repo=FakeAiSpendDayRepository(),
        clock=FakeClock(_NOW),
        daily_cap_micros=_CAP_MICROS,
        prices=_PRICES,
        ask_daily_cap=8,
        teach_start_daily_cap=1,
        ai_paused=True,
    )
    embed = EmbedCorpus(
        embeddings=embeddings,
        index=FakeEmbeddingIndexRepository({source.id: [chunks]}),
        events=FakeIngestionEventRepository(),
        clock=FakeClock(_NOW),
        ids=uuid4,
        batch_size=8,
        budget=paused,
    )

    with pytest.raises(AiPaused):
        embed(source=source, job=job)

    assert embeddings.document_batches == []


def test_embed_step_runs_when_the_switch_is_off(db_conn: Connection) -> None:
    # The budget guard composes in without changing the unpaused behaviour: chunks
    # still embed, vectors still persist.
    from app.application.retrieval import EmbedCorpus

    user = _add_user(db_conn, "unpaused-embed@example.com")
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        status="processing",
        created_at=now,
        updated_at=now,
    )
    job = IngestionJob(
        id=uuid4(),
        source_id=source.id,
        status="running",
        attempts=1,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    embeddings = FakeEmbeddingPort()
    chunk = ChunkToEmbed(id=uuid4(), text="some text")
    index = FakeEmbeddingIndexRepository({source.id: [chunk]})
    embed = EmbedCorpus(
        embeddings=embeddings,
        index=index,
        events=FakeIngestionEventRepository(),
        clock=FakeClock(_NOW),
        ids=uuid4,
        batch_size=8,
        budget=_budget(db_conn),
    )

    embed(source=source, job=job)

    assert embeddings.document_batches == [["some text"]]
    assert chunk.id in index.persisted


def _pause_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the kill switch on for this request cycle (env + fresh settings)."""
    from app.core.config import get_settings

    monkeypatch.setenv("LEARNY_AI_KILL_SWITCH", "true")
    get_settings.cache_clear()


def test_kill_switch_ask_turn_is_503_with_the_pause_copy(
    auth_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _register(auth_client, "pause-web@example.com")
    csrf = _csrf(auth_client)
    source_id = _seed_web_source(db_conn, user_id)
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source_id,
            title="A Book",
            scope_anchors=(),
            include_notes=False,
            target_anchor=None,
            target_section_path=None,
            target_title=None,
            tutor_phase=None,
            hint_level=None,
            tutor_check_text=None,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    _pause_switch(monkeypatch)

    class _NeverCalled:
        model = "never"

        def generate(self, **_kwargs):  # noqa: ANN003
            raise AssertionError("provider must not be called while paused")

        def generate_stream(self, **_kwargs):  # noqa: ANN003
            raise AssertionError("provider must not be called while paused")

    auth_client.app.dependency_overrides[get_generation] = lambda: _NeverCalled()
    try:
        resp = auth_client.post(
            f"/api/conversations/{conversation.id}/turns",
            json={"message": "Why?", "mode": MODE_ANSWER},
            headers={"X-CSRF-Token": csrf, "Origin": TEST_ORIGIN},
        )
    finally:
        auth_client.app.dependency_overrides.pop(get_generation, None)

    assert resp.status_code == 503, resp.text
    assert "paused" in resp.json()["detail"]
    assert "still work" in resp.json()["detail"]


def test_kill_switch_deck_post_is_503_and_starts_nothing(
    quiz_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _register(quiz_client, "pause-deck@example.com")
    csrf = _csrf(quiz_client)
    source_id = _seed_web_source(db_conn, user_id)
    _pause_switch(monkeypatch)

    resp = quiz_client.post(
        f"/api/sources/{source_id}/quiz/deck",
        headers={"X-CSRF-Token": csrf, "Origin": TEST_ORIGIN},
    )

    assert resp.status_code == 503, resp.text
    assert "paused" in resp.json()["detail"]
    assert quiz_client.app.state.quiz_enqueuer.calls == []
    from sqlalchemy import select

    from app.infrastructure.db.metadata import quiz_generation_jobs

    assert db_conn.execute(select(quiz_generation_jobs)).all() == []


def test_kill_switch_review_submit_still_grades(
    quiz_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # DOOR-13's independent test: reviews never touch a provider, so the pause
    # never reaches them — a card still grades to 200 under the switch.
    from app.domain.entities import (
        QuizItem,
        QuizItemStatus,
        QuizItemType,
        SchedulingSnapshot,
    )

    user_id = _register(quiz_client, "pause-review@example.com")
    csrf = _csrf(quiz_client)
    source_id = _seed_web_source(db_conn, user_id)
    now = datetime.now(UTC)
    question, answer = "What is the powerhouse of the cell?", "Mitochondria"
    item = QuizItem(
        id=uuid4(),
        source_id=source_id,
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        source_excerpt="powerhouse",
        chunk_hash="c" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
        status=QuizItemStatus.ACTIVE,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    repo = SqlAlchemyQuizItemRepository(db_conn)
    repo.upsert(item, embedding=None)
    repo.create_scheduling(
        item.id,
        SchedulingSnapshot(
            state=1,
            step=0,
            stability=None,
            difficulty=None,
            due=now - timedelta(hours=1),
            last_review=None,
        ),
    )
    _pause_switch(monkeypatch)

    resp = quiz_client.post(
        f"/api/quiz-items/{item.id}/reviews",
        json={"rating": 3},
        headers={"X-CSRF-Token": csrf, "Origin": TEST_ORIGIN},
    )

    assert resp.status_code == 200, resp.text


def test_kill_switch_leaves_reads_working(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spec edge: while paused, reads (the library) still succeed.
    _register(auth_client, "pause-reads@example.com")
    _pause_switch(monkeypatch)

    resp = auth_client.get("/api/sources")

    assert resp.status_code == 200, resp.text
