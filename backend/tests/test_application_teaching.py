"""C-phase gate (unit) — teaching-session application services.

Drives ``StartTeachingSession`` / ``ReadTeachingSession`` / ``ListTeachingSessions``
(and, below, ``PostTeachingTurn``) over in-memory fakes and the real
``AuthorizeOwnership`` primitive, so the orchestration is asserted in isolation.
The teaching fakes live here rather than in ``tests/fakes.py`` because the turn
path needs a retrieval double that records the ``anchors`` scope, which the Q&A
fake deliberately does not (its ``calls`` shape is asserted verbatim by the Q&A
suite). Each test maps to a TEACH acceptance criterion.
"""

from __future__ import annotations

import ast
import inspect
import logging
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application import teaching as teaching_module
from app.application.errors import (
    AnswerGenerationFailed,
    InvalidTeachingTarget,
    SourceNotFound,
    SourceNotReady,
    TeachingSessionNotFound,
    TeachingTargetGone,
    TeachingTurnConflict,
)
from app.application.identity import AuthorizeOwnership
from app.application.teaching import (
    ListTeachingSessions,
    PostTeachingTurn,
    ReadTeachingSession,
    StartTeachingSession,
)
from app.domain.entities import (
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    CorpusStructure,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    Source,
    StructureSection,
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)
from app.domain.ports import TeachingGenerationPort
from tests.fakes import FakeClock, FakeSourceRepository

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
_MODEL = "local-extractive"
_TOP_K = 8
_HISTORY_TURNS = 6


# --- builders ------------------------------------------------------------------


def _user() -> User:
    return User(id=uuid4(), email="owner@example.com", created_at=_NOW)


def _owned_source(user_id: UUID, *, status: str = "ready") -> Source:
    source_id = uuid4()
    return Source(
        id=source_id,
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{source_id}.epub",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _section(
    anchor: str,
    section_path: tuple[str, ...],
    *,
    title: str = "Section",
    depth: int = 0,
    position: int = 0,
) -> StructureSection:
    return StructureSection(
        position=position,
        title=title,
        depth=depth,
        section_path=section_path,
        anchor=anchor,
    )


def _structure(*sections: StructureSection) -> CorpusStructure:
    return CorpusStructure(
        title="A Book", authors=(), language=None, sections=tuple(sections)
    )


def _evidence(
    source_id: UUID,
    snippet: str,
    *,
    anchor: str,
    section_path: tuple[str, ...] = ("Chapter 1",),
    score: float,
) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=source_id,
        section_path=section_path,
        anchor=anchor,
        page_span=None,
        snippet=snippet,
        score=score,
    )


def _session(
    source_id: UUID,
    *,
    session_id: UUID | None = None,
    target_anchor: str = "ch1.xhtml#core",
    target_section_path: tuple[str, ...] = ("Chapter 1",),
    created_at: datetime = _NOW,
) -> TeachingSession:
    return TeachingSession(
        id=session_id or uuid4(),
        source_id=source_id,
        target_anchor=target_anchor,
        target_section_path=target_section_path,
        target_title="Chapter 1",
        created_at=created_at,
        updated_at=created_at,
    )


def _turn(
    session_id: UUID,
    turn_index: int,
    *,
    status: str = "answered",
    text: str = "answer",
    citations: tuple[Evidence, ...] = (),
) -> TeachingTurn:
    return TeachingTurn(
        id=uuid4(),
        session_id=session_id,
        turn_index=turn_index,
        message=f"message {turn_index}",
        answer_status=status,
        answer_text=text,
        model=_MODEL,
        evidence_count=len(citations),
        citations=citations,
        created_at=_NOW,
    )


# --- fakes ---------------------------------------------------------------------


class FakeCorpus:
    """``CorpusRepository`` read double: returns a preset structure, records reads."""

    def __init__(self, structure: CorpusStructure | None = None) -> None:
        self._structure = structure
        self.get_structure_calls = 0

    def get_structure(self, source_id: UUID) -> CorpusStructure | None:
        self.get_structure_calls += 1
        return self._structure


class FakeTeachingSessionRepository:
    """In-memory ``TeachingSessionRepository``: newest-first list with turn counts."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, TeachingSession] = {}
        self.turn_counts: dict[UUID, int] = {}

    def add(self, session: TeachingSession) -> TeachingSession:
        self._by_id[session.id] = session
        return session

    def get_by_id(self, session_id: UUID) -> TeachingSession | None:
        return self._by_id.get(session_id)

    def list_for_source(self, source_id: UUID) -> list[TeachingSessionSummary]:
        owned = [s for s in self._by_id.values() if s.source_id == source_id]
        owned.sort(key=lambda s: s.created_at, reverse=True)
        return [
            TeachingSessionSummary(
                session=s, turn_count=self.turn_counts.get(s.id, 0)
            )
            for s in owned
        ]


class FakeTeachingTurnRepository:
    """In-memory ``TeachingTurnRepository``: turn_index-asc reads, unique-index guard.

    ``fail_add`` injects a ``TeachingTurnConflict`` on the next ``add`` regardless
    of contents, modelling the turn-index race loser where a concurrent writer
    already took the computed index after this caller's ``list_for_session`` read
    (TEACH-17) — a consistent in-memory fake cannot otherwise reproduce the race.
    """

    def __init__(self, *, fail_add: bool = False) -> None:
        self._turns: list[TeachingTurn] = []
        self._fail_add = fail_add
        self.add_calls = 0

    def add(self, turn: TeachingTurn) -> TeachingTurn:
        self.add_calls += 1
        if self._fail_add or any(
            t.session_id == turn.session_id and t.turn_index == turn.turn_index
            for t in self._turns
        ):
            raise TeachingTurnConflict("Another turn was just added; retry.")
        self._turns.append(turn)
        return turn

    def list_for_session(self, session_id: UUID) -> list[TeachingTurn]:
        return sorted(
            (t for t in self._turns if t.session_id == session_id),
            key=lambda t: t.turn_index,
        )

    def recent_history(
        self, session_id: UUID, limit: int
    ) -> tuple[int, list[HistoryTurn]]:
        turns = self.list_for_session(session_id)
        history = [
            HistoryTurn(message=t.message, response_text=t.answer_text)
            for t in turns[-limit:]
        ]
        return len(turns), history


class FakeScopedRetrieveEvidence:
    """``RetrieveEvidence`` double that records the ``anchors`` scope per call.

    Distinct from ``tests.fakes.FakeRetrieveEvidence`` (whose recorded ``calls``
    shape is asserted verbatim by the Q&A suite and omits ``anchors``): the turn
    path must prove the target-subtree anchors reach retrieval (TEACH-09).
    """

    def __init__(
        self, results: list[Evidence] | None = None, *, error: Exception | None = None
    ) -> None:
        self.results = results if results is not None else []
        self._error = error
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID,
        query: str,
        top_k: int | None = None,
        anchors: Sequence[str] | None = None,
    ) -> list[Evidence]:
        self.calls.append(
            {
                "user": user,
                "source_id": source_id,
                "query": query,
                "top_k": top_k,
                "anchors": None if anchors is None else list(anchors),
            }
        )
        if self._error is not None:
            raise self._error
        return self.results


class FakeTeachingGeneration:
    """``TeachingGenerationPort`` double: preset answer or raise, records calls.

    ``generate_stream`` mirrors ``generate`` and yields the text deltas (``deltas``
    when given, else the preset answer's text as one delta) then exactly one
    ``AnswerCompleted``; a configured ``error`` raises on first iteration and the
    ``try/finally`` sets ``stream_closed`` so cancellation is observable.
    """

    def __init__(
        self,
        *,
        answer: GeneratedAnswer | None = None,
        error: Exception | None = None,
        deltas: Sequence[str] | None = None,
        model: str = _MODEL,
    ) -> None:
        self._answer = answer
        self._error = error
        self._deltas = deltas
        self.model = model
        self.calls: list[dict[str, object]] = []
        self.stream_calls: list[dict[str, object]] = []
        self.stream_closed = False

    def generate(
        self,
        *,
        message: str,
        target_section_path: tuple[str, ...],
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
    ) -> GeneratedAnswer:
        self.calls.append(
            {
                "message": message,
                "target_section_path": target_section_path,
                "history": list(history),
                "evidence": list(evidence),
            }
        )
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        return self._answer

    def generate_stream(
        self,
        *,
        message: str,
        target_section_path: tuple[str, ...],
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
    ) -> Iterator[AnswerStreamEvent]:
        self.stream_calls.append(
            {
                "message": message,
                "target_section_path": target_section_path,
                "history": list(history),
                "evidence": list(evidence),
            }
        )
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        texts = (
            list(self._deltas)
            if self._deltas is not None
            else ([self._answer.text] if self._answer.text else [])
        )
        try:
            for text in texts:
                yield AnswerTextDelta(text=text)
            yield AnswerCompleted(answer=self._answer)
        finally:
            self.stream_closed = True


# --- service builders ----------------------------------------------------------


def _start(
    *, sources, corpus, sessions, ids=uuid4, clock: FakeClock | None = None
) -> StartTeachingSession:
    return StartTeachingSession(
        sources=sources,
        corpus=corpus,
        sessions=sessions,
        authorize=AuthorizeOwnership(),
        clock=clock or FakeClock(_NOW),
        ids=ids,
    )


def _read(*, sessions, turns, sources) -> ReadTeachingSession:
    return ReadTeachingSession(
        sessions=sessions,
        turns=turns,
        sources=sources,
        authorize=AuthorizeOwnership(),
    )


def _list(*, sources, sessions) -> ListTeachingSessions:
    return ListTeachingSessions(
        sources=sources, sessions=sessions, authorize=AuthorizeOwnership()
    )


def _post(
    *,
    sessions,
    turns,
    sources,
    corpus,
    retrieve,
    generation,
    ids=uuid4,
    clock: FakeClock | None = None,
    evidence_top_k: int = _TOP_K,
    history_turns: int = _HISTORY_TURNS,
) -> PostTeachingTurn:
    return PostTeachingTurn(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
        generation=generation,
        authorize=AuthorizeOwnership(),
        clock=clock or FakeClock(_NOW),
        ids=ids,
        evidence_top_k=evidence_top_k,
        history_turns=history_turns,
    )


# --- StartTeachingSession (TEACH-01..04) ---------------------------------------


def test_start_creates_session_with_target_snapshot() -> None:
    # TEACH-01: create returns the session with the resolved target snapshot
    # (anchor, section_path, title) and persists it.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    target = _section(
        "ch1.xhtml#core", ("Chapter 1", "Core Idea"), title="Core Idea"
    )
    corpus = FakeCorpus(
        _structure(target, _section("ch2.xhtml", ("Chapter 2",), title="Chapter 2"))
    )
    sessions = FakeTeachingSessionRepository()
    session_id = uuid4()
    service = _start(
        sources=sources, corpus=corpus, sessions=sessions, ids=lambda: session_id
    )

    result = service(
        user=owner, source_id=source.id, target_anchor="ch1.xhtml#core"
    )

    assert result.id == session_id
    assert result.source_id == source.id
    assert result.target_anchor == "ch1.xhtml#core"
    assert result.target_section_path == ("Chapter 1", "Core Idea")
    assert result.target_title == "Core Idea"
    assert result.created_at == _NOW
    assert sessions.get_by_id(session_id) == result


def test_start_missing_source_raises_source_not_found() -> None:
    # TEACH-02: a missing source collapses to 404 (no session created).
    sources = FakeSourceRepository()
    sessions = FakeTeachingSessionRepository()
    service = _start(
        sources=sources, corpus=FakeCorpus(_structure()), sessions=sessions
    )

    with pytest.raises(SourceNotFound):
        service(user=_user(), source_id=uuid4(), target_anchor="ch1.xhtml#core")

    assert sessions.list_for_source(uuid4()) == []


def test_start_non_owner_raises_source_not_found() -> None:
    # TEACH-02: a non-owner is collapsed to 404 (existence never disclosed).
    owner, other = _user(), _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    service = _start(
        sources=sources,
        corpus=FakeCorpus(_structure(_section("ch1.xhtml#core", ("Chapter 1",)))),
        sessions=FakeTeachingSessionRepository(),
    )

    with pytest.raises(SourceNotFound):
        service(user=other, source_id=source.id, target_anchor="ch1.xhtml#core")


def test_start_not_ready_raises_before_reading_corpus() -> None:
    # TEACH-03: status != "ready" → SourceNotReady before the corpus is read.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id, status="processing")
    sources.add(source)
    corpus = FakeCorpus(_structure(_section("ch1.xhtml#core", ("Chapter 1",))))
    service = _start(
        sources=sources, corpus=corpus, sessions=FakeTeachingSessionRepository()
    )

    with pytest.raises(SourceNotReady):
        service(user=owner, source_id=source.id, target_anchor="ch1.xhtml#core")

    assert corpus.get_structure_calls == 0


def test_start_unknown_anchor_raises_invalid_target() -> None:
    # TEACH-04: an anchor matching no section → InvalidTeachingTarget (422).
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    corpus = FakeCorpus(_structure(_section("ch1.xhtml#core", ("Chapter 1",))))
    service = _start(
        sources=sources, corpus=corpus, sessions=FakeTeachingSessionRepository()
    )

    with pytest.raises(InvalidTeachingTarget):
        service(user=owner, source_id=source.id, target_anchor="does-not-exist")


def test_start_no_corpus_raises_invalid_target() -> None:
    # Edge: a ready source without a corpus resolves no section → InvalidTeachingTarget.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    service = _start(
        sources=sources,
        corpus=FakeCorpus(None),
        sessions=FakeTeachingSessionRepository(),
    )

    with pytest.raises(InvalidTeachingTarget):
        service(user=owner, source_id=source.id, target_anchor="ch1.xhtml#core")


# --- ReadTeachingSession (TEACH-05, 06) ----------------------------------------


def test_read_returns_session_and_turns_ordered_with_citations() -> None:
    # TEACH-05: returns the session and all turns in turn_index-asc order, each
    # carrying its citation snapshots.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    session = _session(source.id)
    sessions = FakeTeachingSessionRepository()
    sessions.add(session)
    cite = _evidence(source.id, "cited passage", anchor="ch1.xhtml#core", score=0.9)
    t0 = _turn(session.id, 0, citations=(cite,))
    t1 = _turn(session.id, 1)
    t2 = _turn(session.id, 2)
    turns = FakeTeachingTurnRepository()
    turns.add(t2)
    turns.add(t0)
    turns.add(t1)
    service = _read(sessions=sessions, turns=turns, sources=sources)

    got_session, got_turns = service(user=owner, session_id=session.id)

    assert got_session == session
    assert [t.turn_index for t in got_turns] == [0, 1, 2]
    assert got_turns == [t0, t1, t2]
    assert got_turns[0].citations == (cite,)


def test_read_missing_session_raises_not_found() -> None:
    # TEACH-06: an unknown session id → TeachingSessionNotFound (404).
    owner = _user()
    sources = FakeSourceRepository()
    service = _read(
        sessions=FakeTeachingSessionRepository(),
        turns=FakeTeachingTurnRepository(),
        sources=sources,
    )

    with pytest.raises(TeachingSessionNotFound):
        service(user=owner, session_id=uuid4())


def test_read_non_owner_raises_not_found() -> None:
    # TEACH-06: a session whose source is another user's → 404 (no disclosure).
    owner, other = _user(), _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    session = _session(source.id)
    sessions = FakeTeachingSessionRepository()
    sessions.add(session)
    service = _read(
        sessions=sessions, turns=FakeTeachingTurnRepository(), sources=sources
    )

    with pytest.raises(TeachingSessionNotFound):
        service(user=other, session_id=session.id)


# --- ListTeachingSessions (TEACH-21, TEACH-02 semantics) -----------------------


def test_list_returns_only_owner_sessions_newest_first_with_counts() -> None:
    # TEACH-21: the source's sessions, newest first, each with its turn count;
    # sessions on other sources are excluded.
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    other_source = _owned_source(owner.id)
    sources.add(source)
    sources.add(other_source)
    sessions = FakeTeachingSessionRepository()
    older = _session(source.id, created_at=_NOW)
    newer = _session(source.id, created_at=_NOW + timedelta(hours=1))
    elsewhere = _session(other_source.id, created_at=_NOW + timedelta(hours=2))
    sessions.add(older)
    sessions.add(newer)
    sessions.add(elsewhere)
    sessions.turn_counts[older.id] = 2
    sessions.turn_counts[newer.id] = 5
    service = _list(sources=sources, sessions=sessions)

    result = service(user=owner, source_id=source.id)

    assert [s.session for s in result] == [newer, older]
    assert [s.turn_count for s in result] == [5, 2]


def test_list_missing_source_raises_source_not_found() -> None:
    # TEACH-02 semantics: a missing source → 404.
    service = _list(
        sources=FakeSourceRepository(), sessions=FakeTeachingSessionRepository()
    )

    with pytest.raises(SourceNotFound):
        service(user=_user(), source_id=uuid4())


def test_list_non_owner_raises_source_not_found() -> None:
    # TEACH-02 semantics: a non-owned source → 404.
    owner, other = _user(), _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id)
    sources.add(source)
    service = _list(sources=sources, sessions=FakeTeachingSessionRepository())

    with pytest.raises(SourceNotFound):
        service(user=other, source_id=source.id)


# --- PostTeachingTurn (TEACH-07, 09..17, 19, 24) -------------------------------


def _seeded(*, target: StructureSection, status: str = "ready"):
    """Owner + ready source + a session anchored to ``target``, all persisted."""
    owner = _user()
    sources = FakeSourceRepository()
    source = _owned_source(owner.id, status=status)
    sources.add(source)
    session = _session(
        source.id,
        target_anchor=target.anchor,
        target_section_path=target.section_path,
    )
    sessions = FakeTeachingSessionRepository()
    sessions.add(session)
    return owner, source, session, sessions, sources


def test_turn_answered_returns_grounded_cited_turn() -> None:
    # TEACH-07 / TEACH-24: an answered turn persists and returns turn_index,
    # message, status, grounded citations, evidence_count, and the port's model.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "first", anchor="ch1.xhtml#core", score=0.9)
    e1 = _evidence(source.id, "second", anchor="ch1.xhtml#core", score=0.5)
    retrieve = FakeScopedRetrieveEvidence([e0, e1])
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="the answer", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )
    turns = FakeTeachingTurnRepository()
    turn_id = uuid4()
    service = _post(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=retrieve,
        generation=generation,
        ids=lambda: turn_id,
    )

    result = service(user=owner, session_id=session.id, message="explain")

    assert result.id == turn_id
    assert result.turn_index == 0
    assert result.message == "explain"
    assert result.answer_status == "answered"
    assert result.answer_text == "the answer"
    assert result.citations == (e0,)  # e1 uncited → dropped by grounding
    assert result.evidence_count == 2
    assert result.model == _MODEL
    assert result.created_at == _NOW
    assert turns.list_for_session(session.id) == [result]


def test_turn_scopes_retrieval_to_target_and_descendants() -> None:
    # TEACH-09: retrieval anchors = the target section plus its descendants
    # (section_path prefix), excluding sibling sections.
    target = _section("ch1.xhtml", ("Chapter 1",), position=0, depth=0)
    descendant = _section(
        "ch1.xhtml#sec-a", ("Chapter 1", "Section A"), position=1, depth=1
    )
    sibling = _section("ch2.xhtml", ("Chapter 2",), position=2, depth=0)
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml", score=0.9)
    retrieve = FakeScopedRetrieveEvidence([e0])
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="a", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(target, descendant, sibling)),
        retrieve=retrieve,
        generation=generation,
    )

    service(user=owner, session_id=session.id, message="q")

    assert len(retrieve.calls) == 1
    call = retrieve.calls[0]
    assert call["anchors"] == ["ch1.xhtml", "ch1.xhtml#sec-a"]
    assert call["source_id"] == source.id
    assert call["query"] == "q"
    assert call["top_k"] == _TOP_K


def test_turn_passes_bounded_history_last_n() -> None:
    # TEACH-12: the port receives at most the last history_turns prior turns as
    # (message, response_text) pairs — response empty for a not-found turn.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    turns = FakeTeachingTurnRepository()
    turns.add(_turn(session.id, 0, text="r0"))
    turns.add(_turn(session.id, 1, status="not_found_in_source", text=""))
    turns.add(_turn(session.id, 2, text="r2"))
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="a", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )
    service = _post(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
        history_turns=2,
    )

    result = service(user=owner, session_id=session.id, message="q")

    assert len(generation.calls) == 1
    assert generation.calls[0]["history"] == [
        HistoryTurn(message="message 1", response_text=""),
        HistoryTurn(message="message 2", response_text="r2"),
    ]
    assert generation.calls[0]["target_section_path"] == ("Chapter 1",)
    assert result.turn_index == 3


def test_turn_history_bound_exceeds_stored_passes_all() -> None:
    # TEACH-12 edge: history_turns > stored turns → all prior turns passed.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    turns = FakeTeachingTurnRepository()
    turns.add(_turn(session.id, 0, text="r0"))
    turns.add(_turn(session.id, 1, text="r1"))
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="a", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )
    service = _post(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
        history_turns=6,
    )

    service(user=owner, session_id=session.id, message="q")

    assert generation.calls[0]["history"] == [
        HistoryTurn(message="message 0", response_text="r0"),
        HistoryTurn(message="message 1", response_text="r1"),
    ]


def test_turn_empty_evidence_not_found_without_invoking_port() -> None:
    # TEACH-11 / TEACH-14 / TEACH-24: no scoped evidence → not-found persisted with
    # empty text/citations, the port never invoked, model from the port attribute.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    generation = FakeTeachingGeneration(model=_MODEL)
    turns = FakeTeachingTurnRepository()
    service = _post(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([]),
        generation=generation,
    )

    result = service(user=owner, session_id=session.id, message="q")

    assert generation.calls == []
    assert result.answer_status == "not_found_in_source"
    assert result.answer_text == ""
    assert result.citations == ()
    assert result.evidence_count == 0
    assert result.model == _MODEL
    assert result.turn_index == 0
    assert turns.list_for_session(session.id) == [result]


def test_turn_ungrounded_citations_not_found_persisted() -> None:
    # TEACH-10: found=true but every cited id is outside the retrieved evidence →
    # not-found, still persisted with empty text and no citations (TEACH-14).
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="ungrounded", cited_chunk_ids=(uuid4(),), model=_MODEL, found=True
        )
    )
    turns = FakeTeachingTurnRepository()
    service = _post(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
    )

    result = service(user=owner, session_id=session.id, message="q")

    assert result.answer_status == "not_found_in_source"
    assert result.answer_text == ""
    assert result.citations == ()
    assert result.evidence_count == 1
    assert turns.list_for_session(session.id)[0].citations == ()


def test_turn_found_false_not_found() -> None:
    # TEACH-10: the port reporting found=false → not-found outcome.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="", cited_chunk_ids=(), model=_MODEL, found=False
        )
    )
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
    )

    result = service(user=owner, session_id=session.id, message="q")

    assert result.answer_status == "not_found_in_source"
    assert result.citations == ()


def test_turn_blank_text_not_found() -> None:
    # TEACH-10: found=true with whitespace-only text → not-found even though a
    # cited chunk is grounded.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="  \n\t", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
    )

    result = service(user=owner, session_id=session.id, message="q")

    assert result.answer_status == "not_found_in_source"
    assert result.citations == ()


def test_turn_port_raise_maps_to_502_and_persists_nothing() -> None:
    # TEACH-13: any port raise → AnswerGenerationFailed (chained) and no turn row.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    boom = RuntimeError("provider exploded")
    turns = FakeTeachingTurnRepository()
    service = _post(
        sessions=sessions,
        turns=turns,
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=FakeTeachingGeneration(error=boom),
    )

    with pytest.raises(AnswerGenerationFailed) as excinfo:
        service(user=owner, session_id=session.id, message="q")

    assert excinfo.value.__cause__ is boom
    assert turns.add_calls == 0
    assert turns.list_for_session(session.id) == []


def test_turn_source_not_ready_raises_before_retrieval() -> None:
    # TEACH-15: the session's source no longer ready → SourceNotReady, no retrieval.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(
        target=target, status="processing"
    )
    retrieve = FakeScopedRetrieveEvidence([])
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=retrieve,
        generation=FakeTeachingGeneration(),
    )

    with pytest.raises(SourceNotReady):
        service(user=owner, session_id=session.id, message="q")

    assert retrieve.calls == []


def test_turn_target_gone_raises_before_retrieval() -> None:
    # TEACH-16: the stored target_anchor no longer resolves in the current corpus
    # → TeachingTargetGone, no retrieval.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    retrieve = FakeScopedRetrieveEvidence([])
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(_section("ch9.xhtml", ("Chapter 9",)))),
        retrieve=retrieve,
        generation=FakeTeachingGeneration(),
    )

    with pytest.raises(TeachingTargetGone):
        service(user=owner, session_id=session.id, message="q")

    assert retrieve.calls == []


def test_turn_index_conflict_propagates() -> None:
    # TEACH-17: the repository's unique-index conflict (race loser) propagates.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="a", cited_chunk_ids=(e0.chunk_id,), model=_MODEL, found=True
        )
    )
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(fail_add=True),
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
    )

    with pytest.raises(TeachingTurnConflict):
        service(user=owner, session_id=session.id, message="q")


def test_turn_missing_session_raises_not_found() -> None:
    # Turn-path ownership resolution: an unknown session id → 404 (no disclosure).
    service = _post(
        sessions=FakeTeachingSessionRepository(),
        turns=FakeTeachingTurnRepository(),
        sources=FakeSourceRepository(),
        corpus=FakeCorpus(_structure()),
        retrieve=FakeScopedRetrieveEvidence([]),
        generation=FakeTeachingGeneration(),
    )

    with pytest.raises(TeachingSessionNotFound):
        service(user=_user(), session_id=uuid4(), message="q")


def test_turn_non_owner_raises_not_found() -> None:
    # Turn-path ownership resolution: another user's session → 404 (no disclosure).
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    other = _user()
    retrieve = FakeScopedRetrieveEvidence([])
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=retrieve,
        generation=FakeTeachingGeneration(),
    )

    with pytest.raises(TeachingSessionNotFound):
        service(user=other, session_id=session.id, message="q")

    assert retrieve.calls == []


def test_turn_emits_one_content_free_completion_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # TEACH-19: exactly one lifecycle log per completed turn carrying outcome,
    # session id, evidence count, and model — never the message or answer text.
    target = _section("ch1.xhtml#core", ("Chapter 1",))
    owner, source, session, sessions, sources = _seeded(target=target)
    e0 = _evidence(source.id, "s", anchor="ch1.xhtml#core", score=0.9)
    generation = FakeTeachingGeneration(
        answer=GeneratedAnswer(
            text="the secret answer body",
            cited_chunk_ids=(e0.chunk_id,),
            model=_MODEL,
            found=True,
        )
    )
    service = _post(
        sessions=sessions,
        turns=FakeTeachingTurnRepository(),
        sources=sources,
        corpus=FakeCorpus(_structure(target)),
        retrieve=FakeScopedRetrieveEvidence([e0]),
        generation=generation,
    )

    with caplog.at_level(logging.INFO, logger="app.application.teaching"):
        service(
            user=owner, session_id=session.id, message="my private message text"
        )

    records = [r for r in caplog.records if r.name == "app.application.teaching"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "outcome=answered" in message
    assert f"session_id={session.id}" in message
    assert "evidence_count=1" in message
    assert f"model={_MODEL}" in message
    assert "my private message text" not in message
    assert "the secret answer body" not in message


def test_teaching_fake_conforms_to_the_teaching_port_protocol() -> None:
    # GEN-12: the runtime-checkable teaching port now includes ``generate_stream``;
    # the local teaching fake satisfies it structurally.
    assert isinstance(FakeTeachingGeneration(), TeachingGenerationPort)


def test_teaching_module_imports_no_web_or_provider_sdk() -> None:
    # ADR-0007/0009: no FastAPI/SQLAlchemy/provider-SDK type crosses this layer.
    tree = ast.parse(inspect.getsource(teaching_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    for forbidden in ("fastapi", "sqlalchemy", "celery", "openai", "anthropic"):
        assert forbidden not in imported
