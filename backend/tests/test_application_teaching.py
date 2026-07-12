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
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application import teaching as teaching_module
from app.application.errors import (
    InvalidTeachingTarget,
    SourceNotFound,
    SourceNotReady,
    TeachingSessionNotFound,
    TeachingTurnConflict,
)
from app.application.identity import AuthorizeOwnership
from app.application.teaching import (
    ListTeachingSessions,
    ReadTeachingSession,
    StartTeachingSession,
)
from app.domain.entities import (
    CorpusStructure,
    Evidence,
    Source,
    StructureSection,
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)
from tests.fakes import FakeClock, FakeSourceRepository

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
_MODEL = "local-extractive"


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
    """In-memory ``TeachingTurnRepository``: turn_index-asc reads, unique-index guard."""

    def __init__(self) -> None:
        self._turns: list[TeachingTurn] = []

    def add(self, turn: TeachingTurn) -> TeachingTurn:
        if any(
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
