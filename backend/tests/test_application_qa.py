"""B2 gate (unit) — AskQuestion application service (QA-01..17).

Drives ``AskQuestion`` over fakes (source repo, conversation repos, a
``RetrieveEvidence`` double, an ``AnswerGenerationPort`` double) and the real
``AuthorizeOwnership`` primitive, so the orchestration is asserted in isolation.
Since ADR-0029 an ask *is* a whole-book conversation plus its first answer turn, so
the builder below composes the unified services for real and every criterion is
asserted through the seam the legacy router calls. Each test maps to a
service-level acceptance criterion: ownership-as-404 (QA-07), readiness guard
before retrieval (QA-08), answered result with grounded/rank-ordered/deduped
citations (QA-01/02/03) carrying evidence_count + model (QA-04), the
empty-evidence short-circuit that never invokes the port (QA-13), the
found/blank/grounding not-found guards (QA-14/15/16), port failure →
``AnswerGenerationFailed`` (QA-17), one content-free completion log (QA-12), and
the persistence AD-195 adds: the question is kept as a conversation, and a failed
ask keeps nothing.
"""

from __future__ import annotations

import ast
import inspect
import logging
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application import conversations as conversation_services
from app.application import qa as qa_module
from app.application.errors import (
    AnswerGenerationFailed,
    SourceNotFound,
    SourceNotReady,
)
from app.application.identity import AuthorizeOwnership
from app.application.qa import AskQuestion
from app.application.streaming import StreamAnswer, StreamDelta
from app.domain.entities import (
    AnswerStreamEvent,
    AnswerTextDelta,
    Conversation,
    ConversationTurn,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    QuestionAnswer,
    Source,
    User,
)
from tests.fakes import (
    FakeAnswerGeneration,
    FakeClock,
    FakeCorpusRepository,
    FakeRetrieveEvidence,
    FakeSourceRepository,
)

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
_TOP_K = 8
_HISTORY_TURNS = 6
_MODEL = "local-extractive"


def _user() -> User:
    return User(id=uuid4(), email="owner@example.com", created_at=_NOW)


def _owned_source(user_id: UUID, *, status: str = "ready") -> Source:
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/a-book.epub",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _evidence(source_id: UUID, snippet: str, *, score: float) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=source_id,
        section_path=("Chapter 1", "Core Idea"),
        anchor="ch1.xhtml#core",
        page_span=None,
        snippet=snippet,
        score=score,
    )


class FakeConversationRepository:
    """In-memory ``ConversationRepository`` for the conversation an ask opens."""

    def __init__(self) -> None:
        self.by_id: dict[UUID, Conversation] = {}
        self.touched: list[UUID] = []

    def add(self, conversation: Conversation) -> Conversation:
        self.by_id[conversation.id] = conversation
        return conversation

    def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return self.by_id.get(conversation_id)

    def delete(self, conversation_id: UUID) -> bool:
        return self.by_id.pop(conversation_id, None) is not None

    def touch(self, conversation_id: UUID, now: datetime) -> None:
        self.touched.append(conversation_id)

    def only(self) -> Conversation:
        """The single conversation an ask opened (fails loudly if that is not so)."""
        assert len(self.by_id) == 1, f"expected exactly one conversation, got {len(self.by_id)}"
        return next(iter(self.by_id.values()))


class FakeConversationTurnRepository:
    """In-memory ``ConversationTurnRepository``: turn_index-asc reads."""

    def __init__(self) -> None:
        self.turns: list[ConversationTurn] = []

    def add(self, turn: ConversationTurn) -> ConversationTurn:
        self.turns.append(turn)
        return turn

    def list_for_conversation(self, conversation_id: UUID) -> list[ConversationTurn]:
        return sorted(
            (t for t in self.turns if t.conversation_id == conversation_id),
            key=lambda t: t.turn_index,
        )

    def recent_history(self, conversation_id: UUID, limit: int) -> tuple[int, list[HistoryTurn]]:
        turns = self.list_for_conversation(conversation_id)
        history = [
            HistoryTurn(message=t.message, response_text=t.answer_text) for t in turns[-limit:]
        ]
        return len(turns), history


class _TeachingPortMustNotRun:
    """Teaching port double: an ask is an answer-mode turn and never reaches it."""

    model = "teaching-port-must-not-run"

    def generate(self, **kwargs: object) -> GeneratedAnswer:
        raise AssertionError("the answer path must not reach the teaching port")

    def generate_stream(self, **kwargs: object) -> Iterator[AnswerStreamEvent]:
        raise AssertionError("the answer path must not reach the teaching port")


def _ask(
    *,
    sources: FakeSourceRepository,
    retrieve: FakeRetrieveEvidence,
    generation: FakeAnswerGeneration,
    top_k: int = _TOP_K,
    conversations: FakeConversationRepository | None = None,
    turns: FakeConversationTurnRepository | None = None,
) -> AskQuestion:
    conversations = conversations if conversations is not None else FakeConversationRepository()
    turns = turns if turns is not None else FakeConversationTurnRepository()
    corpus = FakeCorpusRepository()
    return AskQuestion(
        start=conversation_services.StartConversation(
            sources=sources,
            corpus=corpus,
            conversations=conversations,
            authorize=AuthorizeOwnership(),
            clock=FakeClock(_NOW),
            ids=uuid4,
        ),
        post=conversation_services.PostConversationTurn(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=retrieve,
            answer_generation=generation,
            teaching_generation=_TeachingPortMustNotRun(),
            authorize=AuthorizeOwnership(),
            clock=FakeClock(_NOW),
            ids=uuid4,
            evidence_top_k=top_k,
            history_turns=_HISTORY_TURNS,
        ),
        conversations=conversations,
    )


def test_ask_missing_source_raises_source_not_found() -> None:
    # QA-07: missing source → 404-collapse; nothing downstream runs.
    sources = FakeSourceRepository()
    retrieve = FakeRetrieveEvidence()
    generation = FakeAnswerGeneration()
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    with pytest.raises(SourceNotFound):
        service(user=_user(), source_id=uuid4(), question="anything")

    assert retrieve.calls == []
    assert generation.calls == []


def test_ask_non_owner_raises_source_not_found() -> None:
    # QA-07: a non-owner is collapsed to not-found (existence never disclosed).
    owner, other = _user(), _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieve = FakeRetrieveEvidence()
    generation = FakeAnswerGeneration()
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    with pytest.raises(SourceNotFound):
        service(user=other, source_id=source.id, question="anything")

    assert retrieve.calls == []
    assert generation.calls == []


def test_ask_not_ready_raises_without_retrieval_or_generation() -> None:
    # QA-08: status != "ready" → SourceNotReady before retrieval or generation.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id, status="processing")
    sources.add(source)
    retrieve = FakeRetrieveEvidence()
    generation = FakeAnswerGeneration()
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    with pytest.raises(SourceNotReady):
        service(user=owner, source_id=source.id, question="anything")

    assert retrieve.calls == []
    assert generation.calls == []


def test_ask_answered_grounds_orders_and_dedupes_citations() -> None:
    # QA-01/02/03: answered with citations that are grounded (out-of-evidence and
    # unretrieved ids dropped), in evidence-rank order, and deduped.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "first passage", score=0.9)
    e1 = _evidence(source.id, "second passage", score=0.5)
    e2 = _evidence(source.id, "third passage", score=0.1)
    retrieve = FakeRetrieveEvidence(results=[e0, e1, e2])
    # Adapter cites e2 then e0 (out of rank order), e0 again (dup), plus a chunk id
    # that was never retrieved; e1 is not cited.
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="the composed answer",
            cited_chunk_ids=(e2.chunk_id, e0.chunk_id, e0.chunk_id, uuid4()),
            model=_MODEL,
            found=True,
        )
    )
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    result = service(user=owner, source_id=source.id, question="what is it?")

    assert result.status == "answered"
    assert result.text == "the composed answer"
    # Evidence-rank order (e0 before e2), deduped (e0 once), grounded (e1 excluded
    # since uncited, the invalid id excluded since unretrieved).
    assert result.citations == (e0, e2)
    chunk_ids = [c.chunk_id for c in result.citations]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert all(c in {e0, e1, e2} for c in result.citations)


def test_ask_answered_carries_evidence_count_and_model() -> None:
    # QA-04: diagnostics present on the answered outcome.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, f"snippet-{i}", score=1.0 - i / 10) for i in range(3)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="answer",
            cited_chunk_ids=(evidence[0].chunk_id,),
            model=_MODEL,
            found=True,
        )
    )
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=generation,
    )

    result = service(user=owner, source_id=source.id, question="q")

    assert result.evidence_count == 3
    assert result.model == _MODEL


def test_ask_forwards_trimmed_question_and_settings_top_k() -> None:
    # QA-05: the trimmed question and the server-controlled top_k reach retrieval,
    # and the same question + retrieved evidence reach the generation port.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.7)]
    retrieve = FakeRetrieveEvidence(results=evidence)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="answer", cited_chunk_ids=(evidence[0].chunk_id,), model=_MODEL, found=True
        )
    )
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    service(user=owner, source_id=source.id, question="photosynthesis")

    assert retrieve.calls == [
        {"user": owner, "source_id": source.id, "query": "photosynthesis", "top_k": _TOP_K}
    ]
    assert generation.calls == [{"question": "photosynthesis", "evidence": evidence}]


def test_ask_forwards_include_notes_to_retrieve() -> None:
    # NL-04: the include_notes decision reaches retrieval verbatim on the buffered
    # path — True when opted in, False when not — so the notes arms are gated by it.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.7)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="answer", cited_chunk_ids=(evidence[0].chunk_id,), model=_MODEL, found=True
        )
    )

    retrieve = FakeRetrieveEvidence(results=evidence)
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)
    service(user=owner, source_id=source.id, question="q", include_notes=True)
    service(user=owner, source_id=source.id, question="q", include_notes=False)

    assert retrieve.include_notes_calls == [True, False]


def test_stream_forwards_include_notes_to_retrieve() -> None:
    # NL-04: the streaming path forwards the flag identically (retrieval runs eagerly
    # when the stream is opened, before any delta).
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="answer", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )

    retrieve = FakeRetrieveEvidence(results=[e0])
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)
    service.stream(user=owner, source_id=source.id, question="q", include_notes=True)

    assert retrieve.include_notes_calls == [True]


def test_ask_empty_evidence_is_not_found_without_invoking_port() -> None:
    # QA-13 (+ zero-chunk edge): zero evidence → not-found, port never invoked;
    # model comes from the port's stable identity, evidence_count is 0.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    retrieve = FakeRetrieveEvidence(results=[])
    generation = FakeAnswerGeneration(model=_MODEL)
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    result = service(user=owner, source_id=source.id, question="nonsense token")

    assert generation.calls == []
    assert result.status == "not_found_in_source"
    assert result.text == ""
    assert result.citations == ()
    assert result.evidence_count == 0
    assert result.model == _MODEL


def test_ask_found_false_is_not_found() -> None:
    # QA-14: the port reports found == false → not-found, citations empty.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.6)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(text="", cited_chunk_ids=(), model=_MODEL, found=False)
    )
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=generation,
    )

    result = service(user=owner, source_id=source.id, question="q")

    assert result.status == "not_found_in_source"
    assert result.citations == ()
    # Diagnostics still reflect that one evidence item was retrieved (QA-04).
    assert result.evidence_count == 1
    assert result.model == _MODEL


def test_ask_all_citations_out_of_evidence_is_not_found() -> None:
    # QA-15: found == true but every cited id is outside the retrieved set → all
    # discarded, none remain → not-found.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.6)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="an ungrounded answer",
            cited_chunk_ids=(uuid4(), uuid4()),
            model=_MODEL,
            found=True,
        )
    )
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=generation,
    )

    result = service(user=owner, source_id=source.id, question="q")

    assert result.status == "not_found_in_source"
    assert result.citations == ()


def test_ask_blank_answer_text_is_not_found() -> None:
    # QA-16: found == true with whitespace-only text → not-found, even with a
    # grounded citation.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.6)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="   \n\t",
            cited_chunk_ids=(evidence[0].chunk_id,),
            model=_MODEL,
            found=True,
        )
    )
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=generation,
    )

    result = service(user=owner, source_id=source.id, question="q")

    assert result.status == "not_found_in_source"
    assert result.citations == ()


def test_ask_port_failure_wraps_answer_generation_failed() -> None:
    # QA-17: any exception from the port becomes AnswerGenerationFailed, chained.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.6)]
    boom = RuntimeError("provider exploded")
    generation = FakeAnswerGeneration(error=boom)
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=generation,
    )

    with pytest.raises(AnswerGenerationFailed) as excinfo:
        service(user=owner, source_id=source.id, question="q")

    assert excinfo.value.__cause__ is boom


def test_ask_persists_the_question_as_a_whole_book_conversation_with_turn_zero() -> None:
    # CONV-24/25 (AD-195): each ask opens one whole-book conversation named after the
    # question, and the answer is its ``answer``-mode turn 0 — so a reload loses
    # nothing that was asked.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.7)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="answer", cited_chunk_ids=(evidence[0].chunk_id,), model=_MODEL, found=True
        )
    )
    conversations = FakeConversationRepository()
    turns = FakeConversationTurnRepository()
    retrieve = FakeRetrieveEvidence(results=evidence)
    service = _ask(
        sources=sources,
        retrieve=retrieve,
        generation=generation,
        conversations=conversations,
        turns=turns,
    )

    service(user=owner, source_id=source.id, question="what is photosynthesis", include_notes=True)

    conversation = conversations.only()
    assert conversation.source_id == source.id
    assert conversation.scope_anchors == ()  # the whole book, never a scope
    assert conversation.title == "what is photosynthesis"
    assert conversation.include_notes is True  # the reader's choice is stored
    assert conversation.target_anchor is None  # nothing to teach — not a session

    assert len(turns.turns) == 1
    turn = turns.turns[0]
    assert turn.conversation_id == conversation.id
    assert turn.turn_index == 0
    assert turn.mode == "answer"
    assert turn.message == "what is photosynthesis"
    assert turn.answer_status == "answered"
    # A whole-book conversation is the only thing that searches the whole source.
    assert retrieve.anchor_calls == [None]


def test_ask_titles_the_conversation_with_the_first_80_characters() -> None:
    # AD-195: the title is a plain 80-character cut of the question — no word
    # boundary, no ellipsis, nothing to surprise a reader with.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    question = "w" * 100
    conversations = FakeConversationRepository()
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=[]),
        generation=FakeAnswerGeneration(),
        conversations=conversations,
    )

    service(user=owner, source_id=source.id, question=question)

    assert conversations.only().title == question[:80]
    assert len(conversations.only().title) == 80


def test_ask_generation_failure_leaves_no_conversation_behind() -> None:
    # The pre-cycle ask persisted nothing when generation failed; persisting the
    # question must not change that — a failed ask leaves no empty conversation in
    # the reader's list.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.7)]
    conversations = FakeConversationRepository()
    turns = FakeConversationTurnRepository()
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=FakeAnswerGeneration(error=RuntimeError("provider down")),
        conversations=conversations,
        turns=turns,
    )

    with pytest.raises(AnswerGenerationFailed):
        service(user=owner, source_id=source.id, question="q")

    assert conversations.by_id == {}
    assert turns.turns == []


def test_stream_mid_stream_failure_leaves_no_conversation_behind() -> None:
    # The streaming half of the same promise: a provider failure after the headers
    # went out still leaves nothing behind.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    conversations = FakeConversationRepository()
    turns = FakeConversationTurnRepository()
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=[e0]),
        generation=FakeAnswerGeneration(error=RuntimeError("provider down")),
        conversations=conversations,
        turns=turns,
    )

    with pytest.raises(AnswerGenerationFailed):
        list(service.stream(user=owner, source_id=source.id, question="q"))

    assert conversations.by_id == {}
    assert turns.turns == []


def test_stream_consumer_disconnect_leaves_no_conversation_behind() -> None:
    # A reader who navigates away mid-answer has asked nothing they can return to:
    # the turn was never persisted, so neither is the conversation.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    conversations = FakeConversationRepository()
    turns = FakeConversationTurnRepository()
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="one two", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        ),
        deltas=["one ", "two"],
    )
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=[e0]),
        generation=generation,
        conversations=conversations,
        turns=turns,
    )

    stream = service.stream(user=owner, source_id=source.id, question="q")
    next(stream)  # consume the first delta, then walk away
    stream.close()

    assert conversations.by_id == {}
    assert turns.turns == []


def test_ask_emits_one_content_free_completion_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # QA-12: exactly one lifecycle log per completion, carrying source_id/outcome/
    # evidence_count/model and never the question or answer text.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    evidence = [_evidence(source.id, "passage", score=0.6)]
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="the secret answer body",
            cited_chunk_ids=(evidence[0].chunk_id,),
            model=_MODEL,
            found=True,
        )
    )
    conversations = FakeConversationRepository()
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=evidence),
        generation=generation,
        conversations=conversations,
    )

    with caplog.at_level(logging.INFO, logger="app.application.conversations"):
        service(user=owner, source_id=source.id, question="my private question text")

    records = [r for r in caplog.records if r.name == "app.application.conversations"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "outcome=answered" in message
    assert f"conversation_id={conversations.only().id}" in message
    assert "evidence_count=1" in message
    assert f"model={_MODEL}" in message
    assert "my private question text" not in message
    assert "the secret answer body" not in message


def test_ask_emits_one_content_free_completion_log_on_not_found(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # QA-12 covers "answered or not found": the not-found completion also logs
    # exactly once, content-free, with the not-found outcome.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    generation = FakeAnswerGeneration()
    conversations = FakeConversationRepository()
    service = _ask(
        sources=sources,
        retrieve=FakeRetrieveEvidence(results=[]),
        generation=generation,
        conversations=conversations,
    )

    with caplog.at_level(logging.INFO, logger="app.application.conversations"):
        service(user=owner, source_id=source.id, question="my private question text")

    records = [r for r in caplog.records if r.name == "app.application.conversations"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "outcome=not_found_in_source" in message
    assert f"conversation_id={conversations.only().id}" in message
    assert "evidence_count=0" in message
    assert f"model={_MODEL}" in message
    assert "my private question text" not in message


# --- AskQuestion.stream (GEN-13, streaming half) -------------------------------
#
# Derived from the C3 Done-when: guards raise before any yield; the sentinel
# hold-back suppresses a whole-reply sentinel and flushes a divergent (or genuine
# short) prefix; not-found surfaces via the sentinel and via grounding; a port
# failure wraps to AnswerGenerationFailed; and closing the consumer closes the
# port stream.


def test_stream_missing_source_raises_before_any_yield() -> None:
    # Guards run eagerly: .stream() raises before returning an iterator; retrieval
    # and the generation stream are never touched.
    sources = FakeSourceRepository()
    retrieve = FakeRetrieveEvidence()
    generation = FakeAnswerGeneration()
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    with pytest.raises(SourceNotFound):
        service.stream(user=_user(), source_id=uuid4(), question="anything")

    assert retrieve.calls == []
    assert generation.stream_calls == []


def test_stream_not_ready_raises_before_any_yield() -> None:
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id, status="processing")
    sources.add(source)
    retrieve = FakeRetrieveEvidence()
    generation = FakeAnswerGeneration()
    service = _ask(sources=sources, retrieve=retrieve, generation=generation)

    with pytest.raises(SourceNotReady):
        service.stream(user=owner, source_id=source.id, question="anything")

    assert retrieve.calls == []
    assert generation.stream_calls == []


def test_stream_answered_streams_deltas_and_yields_grounded_terminal() -> None:
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="the answer", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        ),
        deltas=["the ", "answer"],
    )
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    events = list(service.stream(user=owner, source_id=source.id, question="q"))

    deltas = [e for e in events if isinstance(e, StreamDelta)]
    assert [d.text for d in deltas] == ["the ", "answer"]
    terminal = events[-1]
    assert isinstance(terminal, StreamAnswer)
    assert terminal.result.status == "answered"
    assert terminal.result.text == "the answer"
    assert terminal.result.citations == (e0,)
    assert terminal.result.evidence_count == 1
    assert terminal.result.model == _MODEL


def test_stream_empty_evidence_is_not_found_without_invoking_port() -> None:
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    generation = FakeAnswerGeneration(model=_MODEL)
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[]), generation=generation
    )

    events = list(service.stream(user=owner, source_id=source.id, question="q"))

    assert generation.stream_calls == []
    assert [e for e in events if isinstance(e, StreamDelta)] == []
    assert events == [
        StreamAnswer(
            QuestionAnswer(
                status="not_found_in_source",
                text="",
                citations=(),
                evidence_count=0,
                model=_MODEL,
            )
        )
    ]


def test_stream_whole_reply_sentinel_suppresses_deltas_and_is_not_found() -> None:
    # Hold-back: the sentinel is streamed split across deltas but never presented;
    # the completed found=False collapses to the not-found terminal.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(text="", cited_chunk_ids=(), model=_MODEL, found=False),
        deltas=["NOT_FOUND", "_IN_SOURCE"],
    )
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    events = list(service.stream(user=owner, source_id=source.id, question="q"))

    assert [e for e in events if isinstance(e, StreamDelta)] == []
    terminal = events[-1]
    assert isinstance(terminal, StreamAnswer)
    assert terminal.result.status == "not_found_in_source"
    assert terminal.result.text == ""
    assert terminal.result.citations == ()


def test_stream_flushes_a_divergent_prefix_as_one_delta() -> None:
    # A run that starts as a sentinel prefix but diverges is flushed (buffered
    # prefix + the diverging text) as a single delta, then passes through.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="NOT_FOUNDX real answer", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        ),
        deltas=["NOT_FOUND", "X real answer"],
    )
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    events = list(service.stream(user=owner, source_id=source.id, question="q"))

    deltas = [e for e in events if isinstance(e, StreamDelta)]
    assert [d.text for d in deltas] == ["NOT_FOUNDX real answer"]
    assert events[-1].result.status == "answered"


def test_stream_flushes_short_answer_that_looked_like_a_sentinel_prefix() -> None:
    # A genuine short answer whose text is a strict prefix of the sentinel is held
    # through completion, then flushed once (so the client sees the answer text).
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="NOT", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        ),
        deltas=["NOT"],
    )
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    events = list(service.stream(user=owner, source_id=source.id, question="q"))

    deltas = [e for e in events if isinstance(e, StreamDelta)]
    assert [d.text for d in deltas] == ["NOT"]
    assert events[-1].result.status == "answered"
    assert events[-1].result.text == "NOT"


def test_stream_zero_grounded_citations_is_not_found_via_grounding() -> None:
    # found=true prose whose citations are all outside the evidence → grounding
    # collapses to not-found even though the prose already streamed.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="ungrounded prose", cited_chunk_ids=(uuid4(),), model=_MODEL, found=True
        ),
        deltas=["ungrounded prose"],
    )
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    events = list(service.stream(user=owner, source_id=source.id, question="q"))

    assert [d.text for d in events if isinstance(d, StreamDelta)] == ["ungrounded prose"]
    terminal = events[-1]
    assert terminal.result.status == "not_found_in_source"
    assert terminal.result.text == ""
    assert terminal.result.citations == ()


def test_stream_port_failure_wraps_answer_generation_failed() -> None:
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    boom = RuntimeError("provider exploded")
    generation = FakeAnswerGeneration(error=boom)
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    with pytest.raises(AnswerGenerationFailed) as excinfo:
        list(service.stream(user=owner, source_id=source.id, question="q"))

    assert excinfo.value.__cause__ is boom


def test_stream_ending_without_completed_event_raises() -> None:
    # Contract violation: a port stream must end with exactly one AnswerCompleted.
    # A stream that yields only deltas and ends surfaces as a generation failure,
    # never as a silently empty answer.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)

    class _CompletedlessGeneration(FakeAnswerGeneration):
        def generate_stream(
            self, *, question: str, evidence: object, history: Sequence[HistoryTurn] = ()
        ) -> Iterator[AnswerStreamEvent]:
            yield AnswerTextDelta(text="partial ")
            yield AnswerTextDelta(text="answer")

    generation = _CompletedlessGeneration(model=_MODEL)
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    with pytest.raises(AnswerGenerationFailed):
        list(service.stream(user=owner, source_id=source.id, question="q"))


def test_stream_consumer_close_closes_the_port_stream() -> None:
    # Closing the consumer generator mid-stream closes the underlying port stream
    # (no leaked provider generation on client disconnect).
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    e0 = _evidence(source.id, "passage", score=0.9)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="hello world", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        ),
        deltas=["hello world"],
    )
    service = _ask(
        sources=sources, retrieve=FakeRetrieveEvidence(results=[e0]), generation=generation
    )

    gen = service.stream(user=owner, source_id=source.id, question="q")
    first = next(gen)
    assert isinstance(first, StreamDelta)
    assert generation.stream_closed is False

    gen.close()

    assert generation.stream_closed is True


def test_qa_module_imports_no_web_or_provider_sdk() -> None:
    # Done-when / ADR-0007/0009: no FastAPI/SQLAlchemy/SDK type crosses this layer.
    tree = ast.parse(inspect.getsource(qa_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    for forbidden in ("fastapi", "sqlalchemy", "celery", "openai", "anthropic"):
        assert forbidden not in imported
