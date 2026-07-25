"""B-phase gate (unit) — unified conversation application services.

Drives ``StartConversation`` / ``ListConversations`` / ``ReadConversation`` /
``RenameConversation`` / ``DeleteConversation`` (and, below, the turn path) over
in-memory fakes and the real ``AuthorizeOwnership`` primitive, so the
orchestration is asserted in isolation. Each test maps to a CONV acceptance
criterion or an invariant sensor (I-CM-2/3/5/6/7).

The fakes live here rather than in ``tests/fakes.py`` because the conversation
repository double needs the management methods (``list_for_user``, ``rename``,
``delete``, ``touch``) the teaching suite's double deliberately does not have, and
the retrieval double must record the ``anchors`` scope every turn is called with.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.conversations import (
    TITLE_MAX_CHARS,
    DeleteConversation,
    ListConversations,
    ReadConversation,
    RenameConversation,
    StartConversation,
)
from app.application.errors import (
    ConversationNotFound,
    ConversationTurnConflict,
    InvalidConversationScope,
    InvalidConversationTitle,
    SourceNotFound,
    SourceNotReady,
)
from app.application.identity import AuthorizeOwnership
from app.domain.entities import (
    MODE_ANSWER,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    Conversation,
    ConversationSummary,
    ConversationTurn,
    CorpusStructure,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    Source,
    StructureSection,
    User,
)
from tests.fakes import FakeClock, FakeSourceRepository

_NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)
_MODEL = "local-extractive"
_TOP_K = 8
_HISTORY_TURNS = 6


# --- builders ------------------------------------------------------------------


def _user() -> User:
    return User(id=uuid4(), email="owner@example.com", created_at=_NOW)


def _owned_source(user_id: UUID, *, status: str = "ready", title: str = "A Book") -> Source:
    source_id = uuid4()
    return Source(
        id=source_id,
        user_id=user_id,
        title=title,
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
    return CorpusStructure(title="A Book", authors=(), language=None, sections=tuple(sections))


def _evidence(
    source_id: UUID,
    snippet: str,
    *,
    anchor: str,
    section_path: tuple[str, ...] = ("Chapter 1",),
    score: float = 0.9,
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


def _conversation(
    source_id: UUID,
    *,
    conversation_id: UUID | None = None,
    title: str = "Chapter 1",
    scope_anchors: tuple[str, ...] = ("ch1.xhtml#core",),
    include_notes: bool = False,
    target_anchor: str | None = "ch1.xhtml#core",
    target_section_path: tuple[str, ...] | None = ("Chapter 1",),
    target_title: str | None = "Chapter 1",
    created_at: datetime = _NOW,
    updated_at: datetime | None = None,
) -> Conversation:
    return Conversation(
        id=conversation_id or uuid4(),
        source_id=source_id,
        title=title,
        scope_anchors=scope_anchors,
        include_notes=include_notes,
        target_anchor=target_anchor,
        target_section_path=target_section_path,
        target_title=target_title,
        created_at=created_at,
        updated_at=updated_at or created_at,
    )


def _whole_book_conversation(source_id: UUID, **kwargs: object) -> Conversation:
    defaults: dict[str, object] = {
        "title": "A Book",
        "scope_anchors": (),
        "target_anchor": None,
        "target_section_path": None,
        "target_title": None,
    }
    defaults.update(kwargs)
    return _conversation(source_id, **defaults)  # type: ignore[arg-type]


# --- fakes ---------------------------------------------------------------------


class FakeCorpus:
    """``CorpusRepository`` read double: a preset structure plus alias expansion.

    ``expand_anchors`` defaults to the identity (input returned unchanged, order
    preserved). ``alias_expansions`` maps an input anchor to the extra anchors that
    normalization merged into its section, so both scope resolution and per-turn
    expansion can be driven through the alias path (AD-085).
    """

    def __init__(
        self,
        structure: CorpusStructure | None = None,
        *,
        alias_expansions: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._structure = structure
        self._alias_expansions = alias_expansions or {}
        self.get_structure_calls = 0
        self.expand_anchors_calls: list[list[str]] = []

    def get_structure(self, source_id: UUID) -> CorpusStructure | None:
        self.get_structure_calls += 1
        return self._structure

    def expand_anchors(self, source_id: UUID, anchors: Sequence[str]) -> tuple[str, ...]:
        self.expand_anchors_calls.append(list(anchors))
        expanded = list(anchors)
        seen = set(expanded)
        for anchor in anchors:
            for extra in self._alias_expansions.get(anchor, ()):
                if extra not in seen:
                    seen.add(extra)
                    expanded.append(extra)
        return tuple(expanded)


class FakeConversationRepository:
    """In-memory ``ConversationRepository`` with the management methods.

    ``list_for_user`` emulates the real join through ``sources``: it reads
    ownership from the source repository it is given, so a conversation whose
    parent source is another user's is unreachable, not filtered afterwards.
    """

    def __init__(self, sources: FakeSourceRepository | None = None) -> None:
        self._by_id: dict[UUID, Conversation] = {}
        self._sources = sources
        self.turn_counts: dict[UUID, int] = {}
        self.touch_calls: list[tuple[UUID, datetime]] = []

    def add(self, conversation: Conversation) -> Conversation:
        self._by_id[conversation.id] = conversation
        return conversation

    def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return self._by_id.get(conversation_id)

    def _summary(self, conversation: Conversation) -> ConversationSummary:
        source = self._sources.get_by_id(conversation.source_id) if self._sources else None
        return ConversationSummary(
            conversation=conversation,
            turn_count=self.turn_counts.get(conversation.id, 0),
            source_title=source.title if source is not None else "Book",
        )

    def list_for_user(
        self, user_id: UUID, source_id: UUID | None = None
    ) -> list[ConversationSummary]:
        assert self._sources is not None, "this fake needs a source repository to join through"
        owned = []
        for conversation in self._by_id.values():
            source = self._sources.get_by_id(conversation.source_id)
            if source is None or source.user_id != user_id:
                continue
            if source_id is not None and conversation.source_id != source_id:
                continue
            owned.append(conversation)
        owned.sort(key=lambda c: c.updated_at, reverse=True)
        return [self._summary(conversation) for conversation in owned]

    def list_for_source_with_target(self, source_id: UUID) -> list[ConversationSummary]:
        owned = [
            c
            for c in self._by_id.values()
            if c.source_id == source_id and c.target_anchor is not None
        ]
        owned.sort(key=lambda c: c.created_at, reverse=True)
        return [self._summary(conversation) for conversation in owned]

    def rename(self, conversation_id: UUID, title: str, now: datetime) -> Conversation | None:
        conversation = self._by_id.get(conversation_id)
        if conversation is None:
            return None
        renamed = replace_conversation(conversation, title=title, updated_at=now)
        self._by_id[conversation_id] = renamed
        return renamed

    def delete(self, conversation_id: UUID) -> bool:
        return self._by_id.pop(conversation_id, None) is not None

    def touch(self, conversation_id: UUID, now: datetime) -> None:
        self.touch_calls.append((conversation_id, now))
        conversation = self._by_id.get(conversation_id)
        if conversation is not None:
            self._by_id[conversation_id] = replace_conversation(conversation, updated_at=now)


def replace_conversation(
    conversation: Conversation, *, title: str | None = None, updated_at: datetime | None = None
) -> Conversation:
    """Return a copy of ``conversation`` with the given fields replaced (frozen entity)."""
    return Conversation(
        id=conversation.id,
        source_id=conversation.source_id,
        title=conversation.title if title is None else title,
        scope_anchors=conversation.scope_anchors,
        include_notes=conversation.include_notes,
        target_anchor=conversation.target_anchor,
        target_section_path=conversation.target_section_path,
        target_title=conversation.target_title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at if updated_at is None else updated_at,
    )


class FakeConversationTurnRepository:
    """In-memory ``ConversationTurnRepository``: turn_index-asc reads, unique guard.

    ``fail_add`` injects a ``ConversationTurnConflict`` on the next ``add``
    regardless of contents, modelling the turn-index race loser where a concurrent
    writer already took the computed index after this caller's read (I-CM-2) — a
    consistent in-memory fake cannot otherwise reproduce the race.
    """

    def __init__(self, *, fail_add: bool = False) -> None:
        self._turns: list[ConversationTurn] = []
        self._fail_add = fail_add
        self.add_calls = 0

    def add(self, turn: ConversationTurn) -> ConversationTurn:
        self.add_calls += 1
        if self._fail_add or any(
            t.conversation_id == turn.conversation_id and t.turn_index == turn.turn_index
            for t in self._turns
        ):
            raise ConversationTurnConflict("Another turn was just added; retry.")
        self._turns.append(turn)
        return turn

    def list_for_conversation(self, conversation_id: UUID) -> list[ConversationTurn]:
        return sorted(
            (t for t in self._turns if t.conversation_id == conversation_id),
            key=lambda t: t.turn_index,
        )

    def recent_history(self, conversation_id: UUID, limit: int) -> tuple[int, list[HistoryTurn]]:
        turns = self.list_for_conversation(conversation_id)
        history = [
            HistoryTurn(message=t.message, response_text=t.answer_text) for t in turns[-limit:]
        ]
        return len(turns), history


class FakeScopedRetrieveEvidence:
    """``RetrieveEvidence`` double recording the ``anchors`` scope of every call."""

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
        include_notes: bool = False,
    ) -> list[Evidence]:
        self.calls.append(
            {
                "user": user,
                "source_id": source_id,
                "query": query,
                "top_k": top_k,
                "anchors": None if anchors is None else list(anchors),
                "include_notes": include_notes,
            }
        )
        if self._error is not None:
            raise self._error
        return self.results


class FakeAnswerGenerationWithHistory:
    """``AnswerGenerationPort`` double recording the history it was called with."""

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

    def generate(
        self,
        *,
        question: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
    ) -> GeneratedAnswer:
        self.calls.append(
            {"question": question, "evidence": list(evidence), "history": list(history)}
        )
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        return self._answer

    def generate_stream(
        self,
        *,
        question: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
    ) -> Iterator[AnswerStreamEvent]:
        self.stream_calls.append(
            {"question": question, "evidence": list(evidence), "history": list(history)}
        )
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        texts = (
            list(self._deltas)
            if self._deltas is not None
            else ([self._answer.text] if self._answer.text else [])
        )
        for text in texts:
            yield AnswerTextDelta(text=text)
        yield AnswerCompleted(answer=self._answer)


class FakeTeachingGeneration:
    """``TeachingGenerationPort`` double: preset answer or raise, records calls."""

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
        for text in texts:
            yield AnswerTextDelta(text=text)
        yield AnswerCompleted(answer=self._answer)


# --- service builders ----------------------------------------------------------


def _start(*, sources, corpus, conversations, ids=uuid4, clock=None) -> StartConversation:
    return StartConversation(
        sources=sources,
        corpus=corpus,
        conversations=conversations,
        authorize=AuthorizeOwnership(),
        clock=clock or FakeClock(_NOW),
        ids=ids,
    )


def _read(*, conversations, turns, sources) -> ReadConversation:
    return ReadConversation(
        conversations=conversations,
        turns=turns,
        sources=sources,
        authorize=AuthorizeOwnership(),
    )


def _list(*, conversations) -> ListConversations:
    return ListConversations(conversations=conversations)


def _rename(*, conversations, sources, clock=None) -> RenameConversation:
    return RenameConversation(
        conversations=conversations,
        sources=sources,
        authorize=AuthorizeOwnership(),
        clock=clock or FakeClock(_NOW),
    )


def _delete(*, conversations, sources) -> DeleteConversation:
    return DeleteConversation(
        conversations=conversations,
        sources=sources,
        authorize=AuthorizeOwnership(),
    )


def _owned_world(*, status: str = "ready", title: str = "A Book"):
    """Return ``(user, source, sources)`` for an owned source in the given state."""
    user = _user()
    source = _owned_source(user.id, status=status, title=title)
    sources = FakeSourceRepository()
    sources.add(source)
    return user, source, sources


# --- Start: scope, target snapshot, title (CONV-05) -----------------------------


def test_start_scoped_snapshots_the_scope_head_as_the_target() -> None:
    # CONV-05 AC1: a scoped conversation stores the scope as given and snapshots the
    # target trio from the *head* anchor, so it can teach without re-reading the corpus.
    user, source, sources = _owned_world()
    head = _section("ch1.xhtml#core", ("Chapter 1", "Core"), title="Core Ideas", depth=1)
    other = _section("ch2.xhtml", ("Chapter 2",), title="Chapter 2", position=1)
    corpus = FakeCorpus(_structure(head, other))
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user,
        source_id=source.id,
        scope_anchors=["ch1.xhtml#core", "ch2.xhtml"],
        include_notes=False,
    )

    assert started.scope_anchors == ("ch1.xhtml#core", "ch2.xhtml")
    assert started.target_anchor == "ch1.xhtml#core"
    assert started.target_section_path == ("Chapter 1", "Core")
    assert started.target_title == "Core Ideas"
    assert started.title == "Core Ideas"
    assert conversations.get_by_id(started.id) == started


def test_start_whole_book_has_no_target_and_is_named_after_the_book() -> None:
    # CONV-05 AC1: the empty scope is the single spelling of "the whole book" — no
    # target trio, and the title defaults to the source's own title.
    user, source, sources = _owned_world(title="Thinking, Fast and Slow")
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user, source_id=source.id, include_notes=True
    )

    assert started.scope_anchors == ()
    assert (started.target_anchor, started.target_section_path, started.target_title) == (
        None,
        None,
        None,
    )
    assert started.title == "Thinking, Fast and Slow"
    assert started.include_notes is True
    # A whole-book start never needs the corpus at all.
    assert corpus.get_structure_calls == 0


def test_start_stores_the_explicit_notes_choice_when_off() -> None:
    # CONV-05 AC1 / ADR-0029: ``include_notes`` is always the caller's explicit
    # choice, stored as given — never inferred from the scope.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user, source_id=source.id, scope_anchors=["ch1.xhtml"], include_notes=False
    )

    assert started.include_notes is False


def test_start_resolves_a_scope_anchor_through_its_alias() -> None:
    # CONV-05 AC1: an anchor normalization merged away still resolves (alias-aware),
    # and the snapshot carries the surviving section's canonical identity (AD-085).
    user, source, sources = _owned_world()
    surviving = _section("ch1.xhtml#merged", ("Chapter 1",), title="Chapter 1")
    corpus = FakeCorpus(
        _structure(surviving), alias_expansions={"ch1.xhtml#old": ("ch1.xhtml#merged",)}
    )
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user, source_id=source.id, scope_anchors=["ch1.xhtml#old"], include_notes=False
    )

    # The reader's anchor is stored as given; the target snapshot is canonical.
    assert started.scope_anchors == ("ch1.xhtml#old",)
    assert started.target_anchor == "ch1.xhtml#merged"
    assert started.target_title == "Chapter 1"


def test_start_rejects_an_unresolvable_scope_anchor_and_creates_nothing() -> None:
    # CONV-05 AC2: any anchor that resolves to no section fails the whole start with
    # the 422-mapped error — a conversation must never silently drop part of its scope.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    with pytest.raises(InvalidConversationScope):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=user,
            source_id=source.id,
            scope_anchors=["ch1.xhtml", "ghost.xhtml"],
            include_notes=False,
        )

    assert conversations.list_for_user(user.id) == []


def test_start_without_a_corpus_rejects_any_scope() -> None:
    # Edge: a ready source whose corpus is missing resolves no section at all.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(None)
    conversations = FakeConversationRepository(sources)

    with pytest.raises(InvalidConversationScope):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=user, source_id=source.id, scope_anchors=["ch1.xhtml"], include_notes=False
        )


def test_start_uses_and_trims_an_explicit_title() -> None:
    # CONV-05 AC1: a given title wins over the default and is stored trimmed.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",), title="Chapter 1")))
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user,
        source_id=source.id,
        scope_anchors=["ch1.xhtml"],
        include_notes=False,
        title="  Anchoring bias  ",
    )

    assert started.title == "Anchoring bias"


def test_start_falls_back_to_the_default_title_when_the_given_one_is_blank() -> None:
    user, source, sources = _owned_world(title="A Book")
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user, source_id=source.id, include_notes=False, title="   "
    )

    assert started.title == "A Book"


def test_start_rejects_an_oversize_title_and_creates_nothing() -> None:
    # CONV-08's bound applies at creation too: nothing is stored over the limit.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    with pytest.raises(InvalidConversationTitle):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=user,
            source_id=source.id,
            include_notes=False,
            title="x" * (TITLE_MAX_CHARS + 1),
        )

    assert conversations.list_for_user(user.id) == []


def test_start_on_an_unowned_source_reports_the_source_missing() -> None:
    # Edge: the unified start against another user's source is a 404, not a 422.
    owner, source, sources = _owned_world()
    intruder = _user()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    with pytest.raises(SourceNotFound):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=intruder, source_id=source.id, include_notes=False
        )

    assert conversations.list_for_user(owner.id) == []


def test_start_against_a_not_ready_source_creates_nothing() -> None:
    user, source, sources = _owned_world(status="processing")
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    with pytest.raises(SourceNotReady):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=user, source_id=source.id, scope_anchors=["ch1.xhtml"], include_notes=False
        )

    assert conversations.list_for_user(user.id) == []
    assert corpus.get_structure_calls == 0


# --- List (CONV-06) -------------------------------------------------------------


def test_list_returns_the_callers_conversations_newest_activity_first() -> None:
    # CONV-06 AC3: the global list spans every source the caller owns, ordered by
    # ``updated_at`` desc, each row carrying its source title and turn count.
    user = _user()
    sources = FakeSourceRepository()
    first_source = _owned_source(user.id, title="Book One")
    second_source = _owned_source(user.id, title="Book Two")
    sources.add(first_source)
    sources.add(second_source)
    conversations = FakeConversationRepository(sources)
    stale = conversations.add(
        _whole_book_conversation(first_source.id, updated_at=_NOW - timedelta(hours=2))
    )
    fresh = conversations.add(_whole_book_conversation(second_source.id, updated_at=_NOW))
    conversations.turn_counts[fresh.id] = 3

    rows = _list(conversations=conversations)(user=user)

    assert [row.conversation.id for row in rows] == [fresh.id, stale.id]
    assert [row.source_title for row in rows] == ["Book Two", "Book One"]
    assert [row.turn_count for row in rows] == [3, 0]


def test_list_filters_by_source_when_asked() -> None:
    user = _user()
    sources = FakeSourceRepository()
    kept = _owned_source(user.id, title="Book One")
    other = _owned_source(user.id, title="Book Two")
    sources.add(kept)
    sources.add(other)
    conversations = FakeConversationRepository(sources)
    mine = conversations.add(_whole_book_conversation(kept.id))
    conversations.add(_whole_book_conversation(other.id))

    rows = _list(conversations=conversations)(user=user, source_id=kept.id)

    assert [row.conversation.id for row in rows] == [mine.id]


def test_list_never_returns_another_users_conversations() -> None:
    # CONV-07 / I-CM-6: ownership is a join, so a stranger's list is simply empty.
    owner, source, sources = _owned_world()
    intruder = _user()
    conversations = FakeConversationRepository(sources)
    conversations.add(_whole_book_conversation(source.id))

    assert _list(conversations=conversations)(user=intruder) == []
    assert len(_list(conversations=conversations)(user=owner)) == 1


# --- Read (CONV-07, I-CM-6) -----------------------------------------------------


def test_read_returns_the_conversation_with_its_ordered_turns() -> None:
    user, source, sources = _owned_world()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id))
    turns = FakeConversationTurnRepository()
    for index in (0, 1):
        turns.add(
            ConversationTurn(
                id=uuid4(),
                conversation_id=conversation.id,
                turn_index=index,
                message=f"message {index}",
                mode=MODE_ANSWER,
                answer_status="answered",
                answer_text="text",
                model=_MODEL,
                evidence_count=1,
                citations=(),
                created_at=_NOW,
            )
        )

    read, read_turns = _read(conversations=conversations, turns=turns, sources=sources)(
        user=user, conversation_id=conversation.id
    )

    assert read == conversation
    assert [turn.turn_index for turn in read_turns] == [0, 1]


def test_read_of_an_unowned_conversation_is_indistinguishable_from_absence() -> None:
    # I-CM-6: the unowned read and the missing read raise the same error with the
    # same message, so a conversation's existence is never disclosed.
    owner, source, sources = _owned_world()
    intruder = _user()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id))
    turns = FakeConversationTurnRepository()
    read = _read(conversations=conversations, turns=turns, sources=sources)

    with pytest.raises(ConversationNotFound) as unowned:
        read(user=intruder, conversation_id=conversation.id)
    with pytest.raises(ConversationNotFound) as missing:
        read(user=owner, conversation_id=uuid4())

    assert str(unowned.value) == str(missing.value)


# --- Rename (CONV-08) -----------------------------------------------------------


def test_rename_changes_the_title_and_bumps_updated_at() -> None:
    user, source, sources = _owned_world()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id, title="Chapter 1"))
    later = _NOW + timedelta(minutes=5)

    renamed = _rename(conversations=conversations, sources=sources, clock=FakeClock(later))(
        user=user, conversation_id=conversation.id, title="  Loss aversion  "
    )

    assert renamed.title == "Loss aversion"
    assert renamed.updated_at == later
    assert conversations.get_by_id(conversation.id).title == "Loss aversion"


@pytest.mark.parametrize("title", ["", "   ", "x" * (TITLE_MAX_CHARS + 1)])
def test_rename_rejects_blank_and_oversize_titles_leaving_the_stored_title(title: str) -> None:
    # CONV-08 AC4: an empty or oversize title is rejected and nothing is written.
    user, source, sources = _owned_world()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id, title="Chapter 1"))

    with pytest.raises(InvalidConversationTitle):
        _rename(conversations=conversations, sources=sources)(
            user=user, conversation_id=conversation.id, title=title
        )

    assert conversations.get_by_id(conversation.id).title == "Chapter 1"


def test_rename_accepts_a_title_at_the_maximum_length() -> None:
    user, source, sources = _owned_world()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id))

    renamed = _rename(conversations=conversations, sources=sources)(
        user=user, conversation_id=conversation.id, title="x" * TITLE_MAX_CHARS
    )

    assert renamed.title == "x" * TITLE_MAX_CHARS


def test_rename_of_an_unowned_conversation_is_indistinguishable_from_absence() -> None:
    # I-CM-6, and the stored title is untouched by the rejected write.
    owner, source, sources = _owned_world()
    intruder = _user()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id, title="Chapter 1"))
    rename = _rename(conversations=conversations, sources=sources)

    with pytest.raises(ConversationNotFound) as unowned:
        rename(user=intruder, conversation_id=conversation.id, title="Mine now")
    with pytest.raises(ConversationNotFound) as missing:
        rename(user=owner, conversation_id=uuid4(), title="Mine now")

    assert str(unowned.value) == str(missing.value)
    assert conversations.get_by_id(conversation.id).title == "Chapter 1"


# --- Delete (CONV-09) -----------------------------------------------------------


def test_delete_removes_the_conversation_and_a_second_delete_reports_absence() -> None:
    # CONV-09 AC5: the delete succeeds once; the repeat is a plain not-found.
    user, source, sources = _owned_world()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id))
    delete = _delete(conversations=conversations, sources=sources)

    delete(user=user, conversation_id=conversation.id)

    assert conversations.get_by_id(conversation.id) is None
    with pytest.raises(ConversationNotFound):
        delete(user=user, conversation_id=conversation.id)


def test_delete_of_an_unowned_conversation_deletes_nothing() -> None:
    # I-CM-6: a stranger's delete is refused as absence, and the row survives.
    owner, source, sources = _owned_world()
    intruder = _user()
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_conversation(source.id))
    delete = _delete(conversations=conversations, sources=sources)

    with pytest.raises(ConversationNotFound) as unowned:
        delete(user=intruder, conversation_id=conversation.id)
    with pytest.raises(ConversationNotFound) as missing:
        delete(user=owner, conversation_id=uuid4())

    assert str(unowned.value) == str(missing.value)
    assert conversations.get_by_id(conversation.id) is not None
