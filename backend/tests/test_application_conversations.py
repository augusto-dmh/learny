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

import logging
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.conversations import (
    DEFAULT_PAGE_LIMIT,
    TITLE_MAX_CHARS,
    DeleteConversation,
    ListConversations,
    PostConversationTurn,
    ReadConversation,
    RenameConversation,
    StartConversation,
)
from app.application.errors import (
    AnswerGenerationFailed,
    ConversationNotFound,
    ConversationTargetUnavailable,
    ConversationTurnConflict,
    InvalidConversationMode,
    InvalidConversationScope,
    InvalidConversationTitle,
    SourceNotFound,
    SourceNotReady,
)
from app.application.identity import AuthorizeOwnership
from app.application.streaming import (
    StreamDelta,
    StreamPhase,
    StreamReasoningDelta,
    StreamTurn,
    TurnStreamEvent,
)
from app.domain.entities import (
    MODE_ANSWER,
    MODE_TEACH,
    SENTINEL,
    AnswerCompleted,
    AnswerReasoningDelta,
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
# A page wider than any fixture below, so a test that is about ownership or order
# reads the whole of what it seeded rather than accidentally testing paging.
_PAGE = 50


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
        self.last_turn_modes: dict[UUID, str] = {}
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
            last_turn_mode=self.last_turn_modes.get(conversation.id),
        )

    def list_for_user(
        self,
        user_id: UUID,
        source_id: UUID | None = None,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[ConversationSummary]:
        assert self._sources is not None, "this fake needs a source repository to join through"
        owned = []
        for conversation in self._by_id.values():
            source = self._sources.get_by_id(conversation.source_id)
            if source is None or source.user_id != user_id:
                continue
            if source_id is not None and conversation.source_id != source_id:
                continue
            # The port does not list a conversation with no turn in it (an aborted
            # first message leaves one), so neither does the fake — a double that
            # returned rows the real read filters out would let a caller rely on
            # something no reader can see.
            if not self.turn_counts.get(conversation.id, 0):
                continue
            owned.append(conversation)
        # The id tiebreaker is the real query's, not decoration: without it two
        # conversations sharing an ``updated_at`` have no fixed order and a paging
        # test over this fake would pass while the same walk lost rows in SQL.
        owned.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return [self._summary(conversation) for conversation in owned[offset : offset + limit]]

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
        self.history_calls: list[tuple[UUID, int]] = []

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
        self.history_calls.append((conversation_id, limit))
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


def _recorded(
    message: str,
    mode: str,
    evidence: Sequence[Evidence],
    history: Sequence[HistoryTurn],
    target_section_path: tuple[str, ...] | None,
) -> dict[str, object]:
    """Every argument the converged generation port was handed, in one record."""
    return {
        "message": message,
        "mode": mode,
        "evidence": list(evidence),
        "history": list(history),
        "target_section_path": target_section_path,
    }


class FakeGeneration:
    """``GenerationPort`` double: preset answer or raise, recording every call.

    Records the message, the mode, the evidence, the bounded history, and the target
    section path each call was handed, so a test can assert not just *that* the port
    ran but *how* the turn reached it.

    A ``deltas`` entry that is not a string is streamed as-is, so a case can place
    reasoning events at exact points among the text — including partway through a
    reply the sentinel guard is still holding back.
    """

    def __init__(
        self,
        *,
        answer: GeneratedAnswer | None = None,
        error: Exception | None = None,
        deltas: Sequence[str | AnswerStreamEvent] | None = None,
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
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
    ) -> GeneratedAnswer:
        self.calls.append(_recorded(message, mode, evidence, history, target_section_path))
        if self._error is not None:
            raise self._error
        assert self._answer is not None, "no preset answer configured"
        return self._answer

    def generate_stream(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        self.stream_calls.append(_recorded(message, mode, evidence, history, target_section_path))
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
                yield AnswerTextDelta(text=text) if isinstance(text, str) else text
            yield AnswerCompleted(answer=self._answer)
        finally:
            self.stream_closed = True


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


def test_start_collapses_repeated_scope_anchors_in_the_order_given() -> None:
    # CONV-05: naming a section twice means what naming it once means. The scope is
    # re-resolved on every turn for the conversation's life, so a repeat that
    # survived the start would be paid for forever — and the reader's order still
    # decides the head that becomes the teach target.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(
        _structure(
            _section("ch1.xhtml", ("Chapter 1",), title="Chapter 1"),
            _section("ch2.xhtml", ("Chapter 2",), title="Chapter 2"),
        )
    )
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user,
        source_id=source.id,
        scope_anchors=["ch2.xhtml", "ch1.xhtml", "ch2.xhtml"],
        include_notes=False,
    )

    assert started.scope_anchors == ("ch2.xhtml", "ch1.xhtml")
    assert started.target_anchor == "ch2.xhtml"


def test_start_validates_aliased_scope_anchors_in_batch() -> None:
    # CONV-05 AC1/AC2: a scope of anchors a re-ingest turned into aliases still
    # resolves, and the check does not grow a query per anchor — the head is
    # resolved and the rest are validated together.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(
        _structure(
            _section("ch1.xhtml", ("Chapter 1",), title="Chapter 1"),
            _section("ch2.xhtml", ("Chapter 2",), title="Chapter 2"),
            _section("ch3.xhtml", ("Chapter 3",), title="Chapter 3"),
        ),
        alias_expansions={
            "old1.xhtml": ("ch1.xhtml",),
            "old2.xhtml": ("ch2.xhtml",),
            "old3.xhtml": ("ch3.xhtml",),
            "ch2.xhtml": ("old2.xhtml",),
            "ch3.xhtml": ("old3.xhtml",),
        },
    )
    conversations = FakeConversationRepository(sources)

    started = _start(sources=sources, corpus=corpus, conversations=conversations)(
        user=user,
        source_id=source.id,
        scope_anchors=["old1.xhtml", "old2.xhtml", "old3.xhtml"],
        include_notes=False,
    )

    assert started.target_anchor == "ch1.xhtml"
    # One expansion resolves the head, two validate the remaining anchors.
    assert len(corpus.expand_anchors_calls) == 3


def test_start_rejects_a_scope_whose_later_anchor_resolves_to_nothing() -> None:
    # CONV-05 AC2: the batched check is the per-anchor verdict — an anchor past the
    # head that addresses nothing still fails the whole start, even when its
    # neighbours resolve.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(
        _structure(_section("ch1.xhtml", ("Chapter 1",))),
        alias_expansions={"old1.xhtml": ("ch1.xhtml",), "ch1.xhtml": ("old1.xhtml",)},
    )
    conversations = FakeConversationRepository(sources)

    with pytest.raises(InvalidConversationScope):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=user,
            source_id=source.id,
            scope_anchors=["ch1.xhtml", "old1.xhtml", "ghost.xhtml"],
            include_notes=False,
        )

    assert conversations.list_for_user(user.id, limit=_PAGE) == []


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

    assert conversations.list_for_user(user.id, limit=_PAGE) == []


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

    assert conversations.list_for_user(user.id, limit=_PAGE) == []


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

    assert conversations.list_for_user(owner.id, limit=_PAGE) == []


def test_start_against_a_not_ready_source_creates_nothing() -> None:
    user, source, sources = _owned_world(status="processing")
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)

    with pytest.raises(SourceNotReady):
        _start(sources=sources, corpus=corpus, conversations=conversations)(
            user=user, source_id=source.id, scope_anchors=["ch1.xhtml"], include_notes=False
        )

    assert conversations.list_for_user(user.id, limit=_PAGE) == []
    assert corpus.get_structure_calls == 0


# --- List (CONV-06) -------------------------------------------------------------


def _with_a_turn(
    conversations: FakeConversationRepository, conversation: Conversation
) -> Conversation:
    """Store a conversation the list will return — one with a turn in it."""
    stored = conversations.add(conversation)
    conversations.turn_counts[stored.id] = 1
    return stored


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
    conversations.turn_counts[stale.id] = 1
    conversations.turn_counts[fresh.id] = 3

    rows = _list(conversations=conversations)(user=user)

    assert [row.conversation.id for row in rows] == [fresh.id, stale.id]
    assert [row.source_title for row in rows] == ["Book Two", "Book One"]
    assert [row.turn_count for row in rows] == [3, 1]


def test_list_filters_by_source_when_asked() -> None:
    user = _user()
    sources = FakeSourceRepository()
    kept = _owned_source(user.id, title="Book One")
    other = _owned_source(user.id, title="Book Two")
    sources.add(kept)
    sources.add(other)
    conversations = FakeConversationRepository(sources)
    mine = _with_a_turn(conversations, _whole_book_conversation(kept.id))
    _with_a_turn(conversations, _whole_book_conversation(other.id))

    rows = _list(conversations=conversations)(user=user, source_id=kept.id)

    assert [row.conversation.id for row in rows] == [mine.id]


def test_list_pages_the_callers_history_and_bounds_it_by_default() -> None:
    # CONV-06: the service is public — the router is not its only caller — so it
    # bounds an unnamed page itself rather than trusting every caller to, and the
    # window a caller does name is the window it gets.
    user = _user()
    sources = FakeSourceRepository()
    source = _owned_source(user.id, title="Book One")
    sources.add(source)
    conversations = FakeConversationRepository(sources)
    seeded = [
        _with_a_turn(
            conversations,
            _whole_book_conversation(source.id, updated_at=_NOW - timedelta(minutes=i)),
        )
        for i in range(DEFAULT_PAGE_LIMIT + 2)
    ]
    service = _list(conversations=conversations)

    default_page = service(user=user)
    window = service(user=user, limit=2, offset=1)

    assert [row.conversation.id for row in default_page] == [
        c.id for c in seeded[:DEFAULT_PAGE_LIMIT]
    ]
    assert [row.conversation.id for row in window] == [c.id for c in seeded[1:3]]


def test_list_never_returns_another_users_conversations() -> None:
    # CONV-07 / I-CM-6: ownership is a join, so a stranger's list is simply empty.
    owner, source, sources = _owned_world()
    intruder = _user()
    conversations = FakeConversationRepository(sources)
    _with_a_turn(conversations, _whole_book_conversation(source.id))

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


# --- Turn path: scope enforcement (CONV-10, CONV-11, I-CM-3) --------------------


def _post(
    *,
    conversations,
    turns,
    sources,
    corpus,
    retrieve,
    generation=None,
    clock=None,
    ids=uuid4,
) -> PostConversationTurn:
    return PostConversationTurn(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
        generation=generation or FakeGeneration(),
        authorize=AuthorizeOwnership(),
        clock=clock or FakeClock(_NOW),
        ids=ids,
        evidence_top_k=_TOP_K,
        history_turns=_HISTORY_TURNS,
    )


def _answered(*evidence: Evidence, text: str = "grounded answer") -> GeneratedAnswer:
    return GeneratedAnswer(
        text=text,
        cited_chunk_ids=tuple(item.chunk_id for item in evidence),
        model=_MODEL,
        found=True,
    )


def _turn_fields(turn: ConversationTurn) -> dict[str, object]:
    """Every persisted field but the surrogate id (which is generated per call)."""
    return {
        "conversation_id": turn.conversation_id,
        "turn_index": turn.turn_index,
        "message": turn.message,
        "mode": turn.mode,
        "answer_status": turn.answer_status,
        "answer_text": turn.answer_text,
        "model": turn.model,
        "evidence_count": turn.evidence_count,
        "citations": turn.citations,
        "created_at": turn.created_at,
    }


def _scoped_world(*, include_notes: bool = False, alias_expansions=None):
    """A ready owned source with a two-level corpus and a conversation scoped to ch1."""
    user, source, sources = _owned_world()
    parent = _section("ch1.xhtml", ("Chapter 1",), title="Chapter 1")
    child = _section("ch1.xhtml#core", ("Chapter 1", "Core"), title="Core", depth=1, position=1)
    sibling = _section("ch2.xhtml", ("Chapter 2",), title="Chapter 2", position=2)
    corpus = FakeCorpus(_structure(parent, child, sibling), alias_expansions=alias_expansions)
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(
        _conversation(
            source.id,
            title="Chapter 1",
            scope_anchors=("ch1.xhtml",),
            include_notes=include_notes,
            target_anchor="ch1.xhtml",
            target_section_path=("Chapter 1",),
            target_title="Chapter 1",
        )
    )
    return user, source, sources, corpus, conversations, conversation


def test_scoped_turn_retrieves_through_the_expanded_scope_subtree() -> None:
    # CONV-10/CONV-11 AC1: the scope is expanded per turn to the section, its
    # descendants, and the anchors normalization merged away, and those anchors are
    # what retrieval sees — along with the raw message and the conversation's notes
    # choice.
    user, source, sources, corpus, conversations, conversation = _scoped_world(
        alias_expansions={"ch1.xhtml": ("ch1-old.xhtml",)}
    )
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    retrieve = FakeScopedRetrieveEvidence(evidence)
    generation = FakeGeneration(answer=_answered(*evidence))

    _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="what is anchoring?", mode=MODE_ANSWER)

    assert retrieve.calls == [
        {
            "user": user,
            "source_id": source.id,
            "query": "what is anchoring?",
            "top_k": _TOP_K,
            "anchors": ["ch1.xhtml", "ch1.xhtml#core", "ch1-old.xhtml"],
            "include_notes": False,
        }
    ]
    # The sibling chapter is outside the scope and never reaches retrieval.
    assert "ch2.xhtml" not in retrieve.calls[0]["anchors"]


def test_whole_book_turn_is_the_only_one_that_searches_the_whole_source() -> None:
    # CONV-11 AC1: only an empty scope yields ``anchors=None`` (the whole source).
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_whole_book_conversation(source.id))
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    retrieve = FakeScopedRetrieveEvidence(evidence)

    _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
        generation=FakeGeneration(answer=_answered(*evidence)),
    )(user=user, conversation_id=conversation.id, message="what is anchoring?", mode=MODE_ANSWER)

    assert retrieve.calls[0]["anchors"] is None
    assert corpus.expand_anchors_calls == []
    # CONV-11: neither the scope expansion nor the teach target can use the table of
    # contents on a whole-book answer turn, so it is never loaded — every legacy ask
    # takes this path.
    assert corpus.get_structure_calls == 0


def test_scope_is_expanded_again_on_every_turn() -> None:
    # CONV-10 AC1: expansion is per turn, so a corpus that changed between turns is
    # picked up rather than a stale anchor set being reused.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    retrieve = FakeScopedRetrieveEvidence(evidence)
    post = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
        generation=FakeGeneration(answer=_answered(*evidence)),
    )

    post(user=user, conversation_id=conversation.id, message="first", mode=MODE_ANSWER)
    post(user=user, conversation_id=conversation.id, message="second", mode=MODE_ANSWER)

    assert corpus.expand_anchors_calls == [
        ["ch1.xhtml", "ch1.xhtml#core"],
        ["ch1.xhtml", "ch1.xhtml#core"],
    ]


def test_multi_anchor_scope_unions_every_subtree_in_the_given_order() -> None:
    user, source, sources, corpus, conversations, _ = _scoped_world()
    conversation = conversations.add(
        _conversation(
            source.id,
            scope_anchors=("ch2.xhtml", "ch1.xhtml", "ch2.xhtml"),
            target_anchor="ch2.xhtml",
        )
    )
    retrieve = FakeScopedRetrieveEvidence([])

    _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    # Given order, subtrees expanded, the repeated anchor deduped.
    assert retrieve.calls[0]["anchors"] == ["ch2.xhtml", "ch1.xhtml", "ch1.xhtml#core"]


def test_an_aliased_scope_costs_one_expansion_per_turn_not_one_per_anchor() -> None:
    # CONV-10: after a re-ingest merged sections away, every stored anchor is an
    # alias — the case the fallback exists for is also its worst case. The misses are
    # expanded together, so a turn's expansion count does not grow with the scope.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(
        _structure(
            _section("ch1.xhtml", ("Chapter 1",)),
            _section("ch2.xhtml", ("Chapter 2",)),
            _section("ch3.xhtml", ("Chapter 3",)),
        ),
        alias_expansions={
            "old1.xhtml": ("ch1.xhtml",),
            "old2.xhtml": ("ch2.xhtml",),
            "old3.xhtml": ("ch3.xhtml",),
        },
    )
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(
        _conversation(
            source.id,
            scope_anchors=("old1.xhtml", "old2.xhtml", "old3.xhtml"),
            target_anchor="old1.xhtml",
        )
    )
    retrieve = FakeScopedRetrieveEvidence([])

    _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    # One expansion for all three misses, then the closing expansion of the result.
    assert len(corpus.expand_anchors_calls) == 2
    assert corpus.expand_anchors_calls[0] == ["old1.xhtml", "old2.xhtml", "old3.xhtml"]
    # Every aliased anchor's live section is in scope, and the sibling that no scope
    # anchor addresses is not.
    assert set(retrieve.calls[0]["anchors"]) == {
        "old1.xhtml",
        "old2.xhtml",
        "old3.xhtml",
        "ch1.xhtml",
        "ch2.xhtml",
        "ch3.xhtml",
    }


def test_a_scoped_turn_never_widens_when_its_section_disappeared() -> None:
    # I-CM-3 sensor: a corpus replace dropped the scoped section. The turn must still
    # be scoped (to an anchor that now matches nothing) — never ``None``, which would
    # silently search the whole book.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch9.xhtml", ("Chapter 9",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(
        _conversation(source.id, scope_anchors=("gone.xhtml",), target_anchor="gone.xhtml")
    )
    retrieve = FakeScopedRetrieveEvidence([])
    turns = FakeConversationTurnRepository()

    turn = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert retrieve.calls[0]["anchors"] == ["gone.xhtml"]
    assert turn.answer_status == "not_found_in_scope"


def test_the_conversations_notes_choice_gates_the_notes_arms() -> None:
    user, source, sources, corpus, conversations, conversation = _scoped_world(include_notes=True)
    retrieve = FakeScopedRetrieveEvidence([])

    _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert retrieve.calls[0]["include_notes"] is True


def test_every_turn_takes_the_notes_choice_from_the_conversation() -> None:
    # ADR-0029: the choice is the conversation's, made once when it is started. No
    # turn carries one of its own, so a thread cannot answer from notes on one
    # message and without them on the next.
    user, source, sources, corpus, conversations, conversation = _scoped_world(include_notes=False)
    retrieve = FakeScopedRetrieveEvidence([])
    post = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
    )

    post(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    post(user=user, conversation_id=conversation.id, message="q2", mode=MODE_ANSWER)

    assert [call["include_notes"] for call in retrieve.calls] == [False, False]


# --- Turn path: statuses by scope (CONV-11, I-CM-3) -----------------------------


def test_scoped_turn_without_evidence_is_not_found_in_scope_and_skips_generation() -> None:
    # CONV-11 AC3: the reader's own selection came up short — a distinct verdict from
    # the whole-book one, and the generation port is never invoked.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository()
    generation = FakeGeneration()

    turn = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([]),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.answer_status == "not_found_in_scope"
    assert (turn.answer_text, turn.citations, turn.evidence_count) == ("", (), 0)
    assert turn.model == _MODEL
    assert generation.calls == []
    assert turns.list_for_conversation(conversation.id) == [turn]


def test_the_one_generator_supplies_the_model_identity_in_either_mode() -> None:
    # CONV-11: the service holds a single generation collaborator, so the identity a
    # turn records is that generator's whatever the mode. This path never invokes
    # generation, so the identity can only have been read off the injected port —
    # which is the read that used to force a union of two port types.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    generation = FakeGeneration(model="the-only-generator")
    post = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([]),
        generation=generation,
    )

    answered = post(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    taught = post(user=user, conversation_id=conversation.id, message="q", mode=MODE_TEACH)

    assert (answered.model, taught.model) == ("the-only-generator", "the-only-generator")
    assert generation.calls == []


def test_whole_book_turn_without_evidence_stays_not_found_in_source() -> None:
    # CONV-11 AC3: with no scope there is nothing to widen to, so the verdict is the
    # whole-book one.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_whole_book_conversation(source.id))

    turn = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([]),
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.answer_status == "not_found_in_source"


def test_scoped_turn_that_fails_grounding_is_not_found_in_scope() -> None:
    # CONV-11 AC3: a reply the evidence cannot support is the same verdict as no
    # evidence at all, and it is still persisted with empty text and no citations.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    ungrounded = GeneratedAnswer(text="", cited_chunk_ids=(), model=_MODEL, found=False)

    turn = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=FakeGeneration(answer=ungrounded),
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.answer_status == "not_found_in_scope"
    assert (turn.answer_text, turn.citations, turn.evidence_count) == ("", (), 1)


def test_a_turn_cites_only_the_evidence_the_generator_referenced() -> None:
    # AD-027: grounding keeps the cited *subset* and nothing else. Retrieval put three
    # passages in front of the generator and it referenced two of them, so the turn
    # attributes those two — a turn that cited the passage the generator never used
    # would credit the book for something it did not say.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    top = _evidence(source.id, "top", anchor="ch1.xhtml", score=0.9)
    unused = _evidence(source.id, "unused", anchor="ch1.xhtml#core", score=0.6)
    last = _evidence(source.id, "last", anchor="ch1.xhtml#core", score=0.2)
    generation = FakeGeneration(
        answer=GeneratedAnswer(
            text="grounded",
            # Out of rank order, and with one id that was never retrieved at all.
            cited_chunk_ids=(last.chunk_id, uuid4(), top.chunk_id),
            model=_MODEL,
            found=True,
        )
    )

    turn = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([top, unused, last]),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.answer_status == "answered"
    # Exactly the cited subset, back in evidence-rank order; the retrieved-but-uncited
    # passage and the unretrieved id are both absent.
    assert turn.citations == (top, last)
    # The count still reports everything retrieval offered, cited or not.
    assert turn.evidence_count == 3


@pytest.mark.parametrize("text", ["", "   \n\t"])
def test_a_turn_whose_answer_text_is_blank_is_not_found_despite_its_citations(text: str) -> None:
    # AD-027: a reply with citations but nothing to read is not an answer. Without the
    # blank-text guard the turn persists as answered with empty text and citations
    # attached, which a reader sees as a blank answer over real passages.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    turns = FakeConversationTurnRepository()
    generation = FakeGeneration(
        answer=GeneratedAnswer(
            text=text,
            cited_chunk_ids=(evidence[0].chunk_id,),
            model=_MODEL,
            found=True,
        )
    )

    turn = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.answer_status == "not_found_in_scope"
    assert (turn.answer_text, turn.citations) == ("", ())
    assert turns.list_for_conversation(conversation.id) == [turn]


# --- Turn path: mode dispatch (CONV-10 AC2, CONV-14) ----------------------------


def test_answer_mode_sends_the_bounded_history_to_the_answer_port() -> None:
    # CONV-10 AC2 / CONV-14: an answer turn reaches the answer port with the raw
    # message and the conversation's recent history, bounded by the settings value.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository()
    for index in range(2):
        turns.add(
            ConversationTurn(
                id=uuid4(),
                conversation_id=conversation.id,
                turn_index=index,
                message=f"message {index}",
                mode=MODE_ANSWER,
                answer_status="answered",
                answer_text=f"answer {index}",
                model=_MODEL,
                evidence_count=1,
                citations=(),
                created_at=_NOW,
            )
        )
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence))

    _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="and now?", mode=MODE_ANSWER)

    assert turns.history_calls[-1] == (conversation.id, _HISTORY_TURNS)
    assert generation.calls == [
        {
            "message": "and now?",
            "mode": MODE_ANSWER,
            "evidence": evidence,
            "history": [
                HistoryTurn(message="message 0", response_text="answer 0"),
                HistoryTurn(message="message 1", response_text="answer 1"),
            ],
            "target_section_path": None,
        }
    ]


def test_history_keeps_not_found_turns_with_an_empty_response() -> None:
    # A turn the source could not answer is still part of the conversation, so it
    # reaches the port with an empty response rather than being filtered out.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository()
    turns.add(
        ConversationTurn(
            id=uuid4(),
            conversation_id=conversation.id,
            turn_index=0,
            message="unanswerable",
            mode=MODE_ANSWER,
            answer_status="not_found_in_scope",
            answer_text="",
            model=_MODEL,
            evidence_count=0,
            citations=(),
            created_at=_NOW,
        )
    )
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence))

    _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="retry", mode=MODE_ANSWER)

    assert generation.calls[0]["history"] == [HistoryTurn(message="unanswerable", response_text="")]


def test_scoped_answer_turn_generates_as_an_answer_despite_its_target_snapshot() -> None:
    # CONV-10 AC2: a conversation scoped to a chapter snapshots that chapter as its
    # target whatever its mode (AD-194), so target-presence cannot stand in for the
    # mode. An answer turn in such a conversation must reach the port as an answer,
    # with no target section path, or the reader silently gets taught instead.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    assert conversation.target_anchor is not None  # the precondition this pins
    assert conversation.target_section_path == ("Chapter 1",)
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence))

    turn = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="what is anchoring?", mode=MODE_ANSWER)

    assert generation.calls == [
        {
            "message": "what is anchoring?",
            "mode": MODE_ANSWER,
            "evidence": evidence,
            "history": [],
            "target_section_path": None,
        }
    ]
    assert turn.mode == MODE_ANSWER


def test_scoped_answer_stream_generates_as_an_answer_despite_its_target_snapshot() -> None:
    # The streaming half of the same trap: the stream assembles its own call to the
    # port, so it can drift from the buffered path's mode and target.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence))

    list(
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert generation.stream_calls[0]["mode"] == MODE_ANSWER
    assert generation.stream_calls[0]["target_section_path"] is None


def test_teach_mode_sends_the_mode_target_section_path_and_history_to_the_port() -> None:
    # CONV-10 AC2: a teach turn reaches the one generation port carrying the teach
    # mode and the re-resolved target's section path, exactly what the teaching path
    # sent when it had a port of its own.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence))

    turn = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="teach me", mode="teach")

    assert generation.calls == [
        {
            "message": "teach me",
            "mode": MODE_TEACH,
            "evidence": evidence,
            "history": [],
            "target_section_path": ("Chapter 1",),
        }
    ]
    assert turn.mode == "teach"


def test_an_unknown_mode_is_rejected_from_the_published_error_vocabulary() -> None:
    # CONV-20: the turn service is public — the router is not its only caller — so a
    # mode it does not know is a named 422-mapped error rather than a bare ValueError
    # escaping as a 500, and nothing is retrieved or persisted for it.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_whole_book_conversation(source.id))
    retrieve = FakeScopedRetrieveEvidence([])
    turns = FakeConversationTurnRepository()

    with pytest.raises(InvalidConversationMode):
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=retrieve,
        )(user=user, conversation_id=conversation.id, message="q", mode="shout")

    assert retrieve.calls == []
    assert turns.add_calls == 0


def test_teach_turn_on_a_whole_book_conversation_is_a_state_conflict() -> None:
    # I-CM-7 / CONV-12 AC4: nothing to teach, so the turn is refused before any
    # retrieval and nothing is persisted.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_whole_book_conversation(source.id))
    retrieve = FakeScopedRetrieveEvidence([])
    turns = FakeConversationTurnRepository()

    with pytest.raises(ConversationTargetUnavailable):
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=retrieve,
        )(user=user, conversation_id=conversation.id, message="teach me", mode="teach")

    assert retrieve.calls == []
    assert turns.add_calls == 0


def test_teach_turn_whose_target_section_disappeared_is_a_state_conflict() -> None:
    # I-CM-7 / CONV-12 AC4: re-ingestion dropped the target; the turn is refused with
    # nothing retrieved and nothing persisted.
    user, source, sources = _owned_world()
    corpus = FakeCorpus(_structure(_section("ch9.xhtml", ("Chapter 9",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(
        _conversation(source.id, scope_anchors=("gone.xhtml",), target_anchor="gone.xhtml")
    )
    retrieve = FakeScopedRetrieveEvidence([])
    turns = FakeConversationTurnRepository()

    with pytest.raises(ConversationTargetUnavailable):
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=retrieve,
        )(user=user, conversation_id=conversation.id, message="teach me", mode="teach")

    assert retrieve.calls == []
    assert turns.add_calls == 0


def test_answer_turn_proceeds_when_a_scoped_section_disappeared() -> None:
    # Edge case: only teach mode needs a live target — an answer turn goes ahead
    # against whatever of its scope survives.
    user, source, sources = _owned_world()
    surviving = _section("ch1.xhtml", ("Chapter 1",))
    corpus = FakeCorpus(_structure(surviving))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(
        _conversation(
            source.id, scope_anchors=("ch1.xhtml", "gone.xhtml"), target_anchor="gone.xhtml"
        )
    )
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]

    turn = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=FakeGeneration(answer=_answered(*evidence)),
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.answer_status == "answered"


# --- Turn path: persistence (CONV-10 AC5, CONV-13, I-CM-2) ----------------------


def test_answered_turn_is_persisted_with_the_next_index_and_ranked_citations() -> None:
    # CONV-10 AC5: the turn takes the next index, carries its mode, and snapshots the
    # grounded citations in evidence-rank order.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository()
    turns.add(
        ConversationTurn(
            id=uuid4(),
            conversation_id=conversation.id,
            turn_index=0,
            message="earlier",
            mode=MODE_ANSWER,
            answer_status="answered",
            answer_text="earlier answer",
            model=_MODEL,
            evidence_count=1,
            citations=(),
            created_at=_NOW,
        )
    )
    top = _evidence(source.id, "top", anchor="ch1.xhtml", score=0.9)
    second = _evidence(source.id, "second", anchor="ch1.xhtml#core", score=0.4)
    generation = FakeGeneration(
        answer=GeneratedAnswer(
            text="grounded",
            # Cited out of rank order: grounding restores evidence rank.
            cited_chunk_ids=(second.chunk_id, top.chunk_id),
            model="claude-test",
            found=True,
        )
    )

    turn = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([top, second]),
        generation=generation,
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turn.turn_index == 1
    assert turn.mode == MODE_ANSWER
    assert turn.answer_status == "answered"
    assert turn.answer_text == "grounded"
    assert turn.citations == (top, second)
    assert (turn.evidence_count, turn.model) == (2, "claude-test")
    assert [t.turn_index for t in turns.list_for_conversation(conversation.id)] == [0, 1]


def test_a_persisted_turn_bumps_the_conversations_activity() -> None:
    # CONV-13: the conversation rises in the list the moment a turn lands in it.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    later = _NOW + timedelta(minutes=9)

    _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([]),
        clock=FakeClock(later),
    )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert conversations.touch_calls == [(conversation.id, later)]
    assert conversations.get_by_id(conversation.id).updated_at == later


def test_a_turn_index_race_surfaces_as_a_conflict() -> None:
    # I-CM-2: the unique index is the arbiter; the losing writer gets the conflict
    # rather than a gap or a duplicate, and the activity bump does not happen.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository(fail_add=True)
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]

    with pytest.raises(ConversationTurnConflict):
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=FakeGeneration(answer=_answered(*evidence)),
        )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert conversations.touch_calls == []


def test_a_turn_index_race_surfaces_as_a_conflict_while_streaming() -> None:
    # I-CM-2 on the streaming path: the conflict surfaces as the stream completes.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository(fail_add=True)
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    post = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=FakeGeneration(answer=_answered(*evidence)),
    )

    with pytest.raises(ConversationTurnConflict):
        list(post.stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER))


def test_generation_failure_persists_nothing() -> None:
    # A port failure maps to the generic generation error (502) with no turn written.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]

    with pytest.raises(AnswerGenerationFailed):
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=FakeGeneration(error=RuntimeError("provider down")),
        )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert turns.add_calls == 0
    assert conversations.touch_calls == []


# --- Turn path: the completion log (CONV-13) ------------------------------------

_LOGGER = "app.application.conversations"
_PRIVATE_MESSAGE = "why does the narrator resent his brother?"
_PRIVATE_ANSWER = "because the will left the orchard to the younger son"


def _completion_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == _LOGGER]


def test_an_answered_turn_logs_once_carrying_ids_and_counts_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A completed turn leaves exactly one operational record — outcome, ids, counts,
    # model — and never the reader's question or the book's prose. Logs are read,
    # shipped, and retained far from the reader who wrote the question.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence, text=_PRIVATE_ANSWER))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        )(user=user, conversation_id=conversation.id, message=_PRIVATE_MESSAGE, mode=MODE_ANSWER)

    records = _completion_records(caplog)
    assert len(records) == 1
    line = records[0]
    assert "outcome=answered" in line
    assert f"conversation_id={conversation.id}" in line
    assert f"source_id={source.id}" in line
    assert f"mode={MODE_ANSWER}" in line
    assert "evidence_count=1" in line
    assert f"model={_MODEL}" in line
    assert _PRIVATE_MESSAGE not in line
    assert _PRIVATE_ANSWER not in line


def test_a_not_found_turn_logs_once_and_still_carries_no_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The outcome differs; the privacy property does not. A turn that found nothing
    # still logs once and still keeps the reader's question out of the record.
    user, source, sources, corpus, conversations, conversation = _scoped_world()

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence([]),
        )(user=user, conversation_id=conversation.id, message=_PRIVATE_MESSAGE, mode=MODE_ANSWER)

    records = _completion_records(caplog)
    assert len(records) == 1
    line = records[0]
    assert "outcome=not_found_in_scope" in line
    assert f"conversation_id={conversation.id}" in line
    assert "evidence_count=0" in line
    assert _PRIVATE_MESSAGE not in line


def test_a_streamed_turn_logs_the_same_single_content_free_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The streaming path persists through the same writer, so it owes the same one
    # record — and the deltas it already sent the reader must not reappear in it.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence, text=_PRIVATE_ANSWER))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        list(
            _post(
                conversations=conversations,
                turns=FakeConversationTurnRepository(),
                sources=sources,
                corpus=corpus,
                retrieve=FakeScopedRetrieveEvidence(evidence),
                generation=generation,
            ).stream(
                user=user,
                conversation_id=conversation.id,
                message=_PRIVATE_MESSAGE,
                mode=MODE_ANSWER,
            )
        )

    records = _completion_records(caplog)
    assert len(records) == 1
    assert "outcome=answered" in records[0]
    assert _PRIVATE_MESSAGE not in records[0]
    assert _PRIVATE_ANSWER not in records[0]


# --- Turn path: streaming (CONV-10 AC6, I-CM-5) ---------------------------------


def test_stream_yields_the_deltas_then_the_persisted_turn() -> None:
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence, text="one two"), deltas=["one ", "two"])
    turns = FakeConversationTurnRepository()

    events = list(
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert events[0] == StreamPhase(phase="searching")
    assert [e.text for e in events[1:-1]] == ["one ", "two"]
    assert isinstance(events[-1], StreamTurn)
    assert events[-1].turn.answer_text == "one two"
    assert turns.list_for_conversation(conversation.id) == [events[-1].turn]


def test_stream_and_buffered_paths_persist_identical_turns() -> None:
    # I-CM-5: same inputs, same persisted turn and terminal status on both paths.
    def run(streamed: bool) -> ConversationTurn:
        user, source, sources, corpus, conversations, conversation = _scoped_world()
        evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
        # Both paths see the same conversation id and evidence ids.
        generation = FakeGeneration(answer=_answered(*evidence, text="reply"))
        turns = FakeConversationTurnRepository()
        post = _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        )
        if streamed:
            events = list(
                post.stream(
                    user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER
                )
            )
            return events[-1].turn
        return post(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    buffered_turn = run(streamed=False)
    streamed_turn = run(streamed=True)

    comparable = {
        "turn_index",
        "message",
        "mode",
        "answer_status",
        "answer_text",
        "model",
        "evidence_count",
        "created_at",
    }
    buffered = {k: v for k, v in _turn_fields(buffered_turn).items() if k in comparable}
    streamed = {k: v for k, v in _turn_fields(streamed_turn).items() if k in comparable}
    assert buffered == streamed
    assert [c.snippet for c in buffered_turn.citations] == [
        c.snippet for c in streamed_turn.citations
    ]


def test_stream_cancelled_before_completion_persists_nothing() -> None:
    # I-CM-5: the turn is written only after grounding, so a consumer disconnect
    # mid-stream leaves no turn and no activity bump behind.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(answer=_answered(*evidence, text="one two"), deltas=["one ", "two"])
    turns = FakeConversationTurnRepository()

    stream = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence(evidence),
        generation=generation,
    ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    assert next(stream) == StreamPhase(phase="searching")
    assert next(stream) == StreamDelta(text="one ")  # generation is now under way
    stream.close()

    assert turns.add_calls == 0
    assert conversations.touch_calls == []
    assert generation.stream_closed is True


def test_stream_without_evidence_persists_the_scoped_not_found_turn() -> None:
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    generation = FakeGeneration()
    turns = FakeConversationTurnRepository()

    events = list(
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence([]),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    # The phase, then straight to the verdict: nothing was found to answer from, so
    # there is no reasoning and no text between them.
    assert events[0] == StreamPhase(phase="searching")
    assert len(events) == 2
    assert events[-1].turn.answer_status == "not_found_in_scope"
    assert generation.stream_calls == []
    assert turns.list_for_conversation(conversation.id) == [events[-1].turn]


# --- Turn path: streamed phases and reasoning (ANSW-01, ANSW-02, ANSW-03) -------
#
# Derived from the phases ACs: a turn announces that it is searching *before* it
# searches, so the slowest silent stretch of a turn is accounted for; reasoning the
# provider streams reaches the reader as it arrives, including while the sentinel
# guard is still holding answer text back; a turn that finds nothing goes from the
# phase straight to its verdict; and a retrieval that fails now that the response
# has already begun is reported as the same generation failure as any other
# mid-stream break, since a status code is no longer available to say it.


def test_the_searching_phase_is_yielded_before_retrieval_runs() -> None:
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    retrieve = FakeScopedRetrieveEvidence(evidence)
    stream = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
        generation=FakeGeneration(answer=_answered(*evidence, text="reply")),
    ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    first = next(stream)

    assert first == StreamPhase(phase="searching")
    # The frame is out while the search has not started — the point of moving it.
    assert retrieve.calls == []
    next(stream)
    assert len(retrieve.calls) == 1
    stream.close()


def test_reasoning_streams_through_while_answer_text_is_still_held_back() -> None:
    # The sentinel guard buffers text that might still be the not-found signal.
    # Reasoning is not answer text, so it must not queue behind that buffer — and
    # the buffered text must still be released exactly as it was: one flush, whole.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    tail = " is the phrase this chapter uses."
    generation = FakeGeneration(
        answer=_answered(*evidence, text=SENTINEL + tail),
        deltas=[
            SENTINEL[:9],
            AnswerReasoningDelta(text="Checking the second passage"),
            SENTINEL[9:] + tail,
        ],
    )

    events = list(
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert events[0] == StreamPhase(phase="searching")
    # The reasoning left while the text it arrived between was still held.
    assert events[1] == StreamReasoningDelta(text="Checking the second passage")
    assert _deltas(events) == [SENTINEL + tail]
    assert events[-1].turn.answer_status == "answered"


def test_a_sentinel_only_turn_leaks_no_text_and_nothing_after_the_verdict() -> None:
    # Reasoning may stream during a turn that then finds nothing; it must not leave a
    # trailing frame after the verdict, and none of the sentinel may reach the reader.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(
        answer=GeneratedAnswer(text="", cited_chunk_ids=(), model=_MODEL, found=False),
        deltas=[
            AnswerReasoningDelta(text="No passage covers this."),
            SENTINEL[:9],
            SENTINEL[9:],
        ],
    )

    events = list(
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert events[0] == StreamPhase(phase="searching")
    assert events[1] == StreamReasoningDelta(text="No passage covers this.")
    assert _deltas(events) == []
    # The verdict is last: nothing — reasoning included — follows it.
    assert isinstance(events[-1], StreamTurn)
    assert len(events) == 3
    assert events[-1].turn.answer_status == "not_found_in_scope"
    assert events[-1].turn.answer_text == ""


def test_retrieval_failing_inside_the_stream_becomes_the_generation_failure() -> None:
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    turns = FakeConversationTurnRepository()
    generation = FakeGeneration()
    stream = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([], error=RuntimeError("index unavailable")),
        generation=generation,
    ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert next(stream) == StreamPhase(phase="searching")
    with pytest.raises(AnswerGenerationFailed):
        next(stream)

    # The failure replaces the answer, it does not half-write a turn.
    assert generation.stream_calls == []
    assert turns.add_calls == 0
    assert conversations.touch_calls == []


# --- Turn path: the streaming sentinel hold-back (design §6) --------------------
#
# The provider signals "I cannot ground this" by emitting the sentinel as its whole
# reply. Deltas arrive before that verdict is known, so the hold-back buffers any run
# that is still a prefix of the sentinel and only releases it once the reply proves to
# be something else. The three cases below are the three ways that resolves.


def _deltas(events: list[TurnStreamEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, StreamDelta)]


def test_stream_never_shows_a_reader_the_whole_reply_sentinel() -> None:
    # The sentinel arrives split across deltas and none of it reaches the reader; the
    # turn lands as the not-found verdict rather than as an answer reading
    # "NOT_FOUND_IN_SOURCE".
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    generation = FakeGeneration(
        answer=GeneratedAnswer(text="", cited_chunk_ids=(), model=_MODEL, found=False),
        deltas=[SENTINEL[:9], SENTINEL[9:]],
    )

    events = list(
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert _deltas(events) == []
    assert events[-1].turn.answer_status == "not_found_in_scope"
    assert events[-1].turn.answer_text == ""


def test_stream_flushes_a_divergent_sentinel_prefix_as_one_delta() -> None:
    # A reply that opens like the sentinel and then turns out to be prose: the buffered
    # run is released as a *single* delta — not re-split into the chunks the provider
    # happened to send — and everything after it passes straight through.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    text = SENTINEL[:9] + " markers appear until"
    generation = FakeGeneration(
        answer=_answered(*evidence, text=text + " the third chapter"),
        deltas=[SENTINEL[:9], " markers appear until", " the third chapter"],
    )

    events = list(
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert _deltas(events) == [text, " the third chapter"]
    assert events[-1].turn.answer_status == "answered"


def test_stream_flushes_a_short_answer_that_merely_looked_like_the_sentinel() -> None:
    # A genuine answer short enough to be a proper prefix of the sentinel is held to
    # the end — nothing later proves it is not the sentinel — and flushed once on
    # completion. Without that flush the reader is shown an empty answered turn.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    short = SENTINEL[:3]
    generation = FakeGeneration(answer=_answered(*evidence, text=short), deltas=[short])

    events = list(
        _post(
            conversations=conversations,
            turns=FakeConversationTurnRepository(),
            sources=sources,
            corpus=corpus,
            retrieve=FakeScopedRetrieveEvidence(evidence),
            generation=generation,
        ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    )

    assert _deltas(events) == [short]
    assert events[-1].turn.answer_status == "answered"
    assert events[-1].turn.answer_text == short


def test_stream_that_ends_without_a_completed_event_is_a_generation_failure() -> None:
    # Port contract: a generation stream ends with exactly one completed event. One
    # that just stops surfaces as a generation failure with nothing persisted, never
    # as a silently empty answer built from the deltas already sent.
    user, source, sources, corpus, conversations, conversation = _scoped_world()
    evidence = [_evidence(source.id, "snippet", anchor="ch1.xhtml")]
    turns = FakeConversationTurnRepository()

    class _NeverCompletes(FakeGeneration):
        def generate_stream(
            self,
            *,
            message: str,
            mode: str,
            evidence: Sequence[Evidence],
            history: Sequence[HistoryTurn] = (),
            target_section_path: tuple[str, ...] | None = None,
        ) -> Iterator[AnswerStreamEvent]:
            yield AnswerTextDelta(text="partial ")
            yield AnswerTextDelta(text="answer")

    with pytest.raises(AnswerGenerationFailed):
        list(
            _post(
                conversations=conversations,
                turns=turns,
                sources=sources,
                corpus=corpus,
                retrieve=FakeScopedRetrieveEvidence(evidence),
                generation=_NeverCompletes(),
            ).stream(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
        )

    assert turns.add_calls == 0
    assert conversations.touch_calls == []


# --- Turn path: ownership and readiness (I-CM-6) --------------------------------


def test_turn_on_an_unowned_conversation_is_indistinguishable_from_absence() -> None:
    owner, source, sources, corpus, conversations, conversation = _scoped_world()
    intruder = _user()
    retrieve = FakeScopedRetrieveEvidence([])
    turns = FakeConversationTurnRepository()
    post = _post(
        conversations=conversations,
        turns=turns,
        sources=sources,
        corpus=corpus,
        retrieve=retrieve,
    )

    with pytest.raises(ConversationNotFound) as unowned:
        post(user=intruder, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)
    with pytest.raises(ConversationNotFound) as missing:
        post(user=owner, conversation_id=uuid4(), message="q", mode=MODE_ANSWER)

    assert str(unowned.value) == str(missing.value)
    assert retrieve.calls == []
    assert turns.add_calls == 0


def test_stream_guards_raise_before_any_event_is_yielded() -> None:
    # The stream's guards run eagerly, so a 404 surfaces before any SSE byte.
    owner, source, sources, corpus, conversations, conversation = _scoped_world()
    intruder = _user()
    post = _post(
        conversations=conversations,
        turns=FakeConversationTurnRepository(),
        sources=sources,
        corpus=corpus,
        retrieve=FakeScopedRetrieveEvidence([]),
    )

    with pytest.raises(ConversationNotFound):
        post.stream(user=intruder, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)


def test_turn_against_a_source_that_is_no_longer_ready_persists_nothing() -> None:
    user = _user()
    source = _owned_source(user.id, status="processing")
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpus(_structure(_section("ch1.xhtml", ("Chapter 1",))))
    conversations = FakeConversationRepository(sources)
    conversation = conversations.add(_whole_book_conversation(source.id))
    turns = FakeConversationTurnRepository()
    retrieve = FakeScopedRetrieveEvidence([])

    with pytest.raises(SourceNotReady):
        _post(
            conversations=conversations,
            turns=turns,
            sources=sources,
            corpus=corpus,
            retrieve=retrieve,
        )(user=user, conversation_id=conversation.id, message="q", mode=MODE_ANSWER)

    assert retrieve.calls == []
    assert turns.add_calls == 0
