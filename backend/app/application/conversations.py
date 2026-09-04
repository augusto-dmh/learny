"""Unified grounded-conversation use-case services (ADR-0029).

One conversation is one grounded exchange about a book, defined by two axes: its
*scope* (the section anchors retrieval may see — empty means the whole book) and
each turn's *mode* (``answer`` replies as cited Q&A, ``teach`` as structured
teaching against the conversation's target section). These services generalize the
mechanics the separate ask and teaching paths each proved out before them:
ownership collapses missing and unowned to one error, the scope is re-expanded per
turn against the live corpus, and a turn is persisted only after grounding.

Ownership is source-mediated (AD-014): the aggregate carries no ``user_id``, so
every conversation-rooted service resolves the parent source and collapses a
missing conversation, a missing source, and a non-owner to
``ConversationNotFound`` — existence is never disclosed. No FastAPI / SQLAlchemy /
provider-SDK type crosses this boundary (ADR-0007/0009).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from app.application.errors import (
    AnswerGenerationFailed,
    ConversationClosed,
    ConversationNotFound,
    ConversationTargetUnavailable,
    InvalidConversationMode,
    InvalidConversationScope,
    InvalidConversationTitle,
    NotAuthorized,
    SourceNotReady,
)
from app.application.grounding import ground, ground_spans
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import SOURCE_STATUS_READY, authorized_source
from app.application.retrieval import RetrieveEvidence
from app.application.streaming import (
    PHASE_SEARCHING,
    StreamPhase,
    StreamTurn,
    TurnStreamEvent,
    hold_back_deltas,
)
from app.application.teaching_policy import TeachingPolicy, TutorState
from app.domain.entities import (
    ANSWERED,
    FAILED,
    MODE_ANSWER,
    MODE_TEACH,
    NOT_FOUND_IN_SCOPE,
    NOT_FOUND_IN_SOURCE,
    TUTOR_OPENING_MESSAGE,
    AnswerStreamEvent,
    CitedSpan,
    Conversation,
    ConversationSummary,
    ConversationTurn,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    Source,
    StructureSection,
    User,
)
from app.domain.ports import (
    Clock,
    ConversationRepository,
    ConversationTurnRepository,
    CorpusRepository,
    GenerationPort,
    SourceRepository,
)

logger = logging.getLogger(__name__)

# The longest title a conversation may carry (CONV-08). Titles are trimmed first,
# so trailing whitespace never costs a reader their title. The web layer declares
# the same bound on its request models; this is the enforcement.
TITLE_MAX_CHARS = 200

# How much conversation history one unparameterized list read returns, and the most
# any read may ask for (CONV-06). The shipped list convention — the due-review queue
# uses the same pair — kept in one place so the endpoint's default and the service's
# cannot drift apart.
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


def authorized_conversation(
    *,
    user: User,
    conversation_id: UUID,
    conversations: ConversationRepository,
    sources: SourceRepository,
    authorize: AuthorizeOwnership,
) -> tuple[Conversation, Source]:
    """Resolve a conversation the caller owns, or raise ``ConversationNotFound``.

    The single home of the ownership collapse (CONV-07, I-CM-6): a missing
    conversation, a missing parent source, and a non-owner all raise the same error
    with the same message, so a conversation's existence is never disclosed.
    Services never re-implement it.
    """
    conversation = conversations.get_by_id(conversation_id)
    if conversation is None:
        raise ConversationNotFound("Conversation not found.")
    source = sources.get_by_id(conversation.source_id)
    if source is None:
        raise ConversationNotFound("Conversation not found.")
    try:
        authorize(user=user, owner_id=source.user_id)
    except NotAuthorized as exc:
        raise ConversationNotFound("Conversation not found.") from exc
    return conversation, source


def normalize_title(title: str | None) -> str | None:
    """Trim a caller-supplied title, or return ``None`` when none was given.

    A title that is blank once trimmed counts as "not given" on the start path
    (the default applies) and is rejected on the rename path, where the caller
    asked for a specific title. Anything longer than :data:`TITLE_MAX_CHARS`
    raises ``InvalidConversationTitle`` (CONV-08).
    """
    if title is None:
        return None
    trimmed = title.strip()
    if not trimmed:
        return None
    if len(trimmed) > TITLE_MAX_CHARS:
        raise InvalidConversationTitle(f"Title must be at most {TITLE_MAX_CHARS} characters.")
    return trimmed


def resolve_section(
    anchor: str,
    *,
    by_anchor: dict[str, StructureSection],
    corpus: CorpusRepository,
    source_id: UUID,
) -> StructureSection | None:
    """Resolve one anchor to a live section, canonical first then by alias (AD-085).

    Normalization can merge a section away and leave its old anchor behind as an
    alias, so an anchor a reader scoped days ago may no longer be canonical. The
    canonical map answers the common case without a query; only an anchor that
    misses it pays one ``expand_anchors`` call, whose expansion carries the
    canonical anchor of whichever section adopted it. ``None`` means the anchor
    addresses nothing in the current corpus.
    """
    section = by_anchor.get(anchor)
    if section is not None:
        return section
    for candidate in corpus.expand_anchors(source_id, [anchor]):
        section = by_anchor.get(candidate)
        if section is not None:
            return section
    return None


class StartConversation:
    """Create a conversation over an owned, ready source (CONV-05).

    Ownership is enforced first via ``authorized_source`` (missing + non-owner →
    ``SourceNotFound``, 404); a source whose ``status != "ready"`` raises
    ``SourceNotReady`` before the corpus is read. Every given scope anchor must
    resolve to a live section (alias-aware) or the whole start fails with
    ``InvalidConversationScope`` (422) having created nothing — a conversation that
    silently dropped part of its scope would promise a reader something it does not
    enforce. The scope is stored in the order given, with repeats collapsed to their
    first appearance: naming a section twice means the same thing as naming it once,
    and the duplicate would otherwise be re-resolved on every turn forever.
    Expansion is a per-turn concern.

    The teach target is snapshotted from the *scope head* — the first anchor the
    reader gave — so a scoped conversation can teach without re-reading the corpus
    (it is still re-resolved per turn). A whole-book conversation has no target and
    teaches nothing in particular. The title defaults to the target's title when
    scoped and the book's title otherwise; ``include_notes`` is always the caller's
    explicit choice (ADR-0029), never inferred.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        corpus: CorpusRepository,
        conversations: ConversationRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._conversations = conversations
        self._authorize = authorize
        self._clock = clock
        self._ids = ids

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID,
        scope_anchors: Sequence[str] = (),
        include_notes: bool,
        title: str | None = None,
    ) -> Conversation:
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        if source.status != SOURCE_STATUS_READY:
            # Guard before touching the corpus so a not-ready source starts nothing.
            raise SourceNotReady("Source is not ready for conversations.")

        given_title = normalize_title(title)
        # ``dict.fromkeys`` keeps the reader's order while collapsing repeats, so the
        # per-turn expansion is linear in the sections asked for rather than in what
        # the client happened to send.
        scope = tuple(dict.fromkeys(scope_anchors))
        head = self._resolve_head(source_id, scope)

        now = self._clock.now()
        conversation = Conversation(
            id=self._ids(),
            source_id=source_id,
            title=given_title or self._default_title(head, source),
            scope_anchors=scope,
            include_notes=include_notes,
            target_anchor=head.anchor if head is not None else None,
            target_section_path=head.section_path if head is not None else None,
            target_title=head.title if head is not None else None,
            created_at=now,
            updated_at=now,
        )
        return self._conversations.add(conversation)

    def _resolve_head(self, source_id: UUID, scope: tuple[str, ...]) -> StructureSection | None:
        """Validate every scope anchor and return the section the head resolves to."""
        if not scope:
            return None
        structure = self._corpus.get_structure(source_id)
        sections = structure.sections if structure is not None else ()
        by_anchor = {section.anchor: section for section in sections}
        # Only the head needs to be resolved to a section (it becomes the target
        # snapshot); the rest only need to exist, which is a batched question.
        head = resolve_section(
            scope[0], by_anchor=by_anchor, corpus=self._corpus, source_id=source_id
        )
        if head is None:
            raise InvalidConversationScope("Scope does not exist in this source.")
        self._reject_unresolvable(source_id, scope[1:], by_anchor)
        return head

    def _reject_unresolvable(
        self, source_id: UUID, anchors: tuple[str, ...], by_anchor: dict[str, StructureSection]
    ) -> None:
        """Fail the start unless every anchor addresses a live section (CONV-05).

        Asked in batch rather than once per anchor. One expansion over the anchors
        the canonical map missed reaches exactly the sections those anchors can
        address — a live section comes back precisely when it carries one of them as
        an alias — and a second expansion over those sections yields every alias they
        answer to. An anchor resolves if and only if it appears there, so the verdict
        is the same one :func:`resolve_section` gives per anchor, at two queries for
        the whole scope instead of one per anchor.
        """
        misses = [anchor for anchor in anchors if anchor not in by_anchor]
        if not misses:
            return
        reached = [c for c in self._corpus.expand_anchors(source_id, misses) if c in by_anchor]
        aliases = set(self._corpus.expand_anchors(source_id, reached)) if reached else set()
        if not set(misses) <= aliases:
            raise InvalidConversationScope("Scope does not exist in this source.")

    @staticmethod
    def _default_title(head: StructureSection | None, source: Source) -> str:
        """Name a conversation after what it is about: its section, else the book."""
        if head is not None and head.title:
            return head.title
        return source.title


class ListConversations:
    """Return a page of the caller's conversations, newest activity first (CONV-06).

    Spans every source the caller owns unless ``source_id`` narrows it. Ownership
    is the repository's join through ``sources`` (AD-014), so another user's
    conversations are unreachable rather than filtered afterwards — narrowing by a
    source the caller does not own yields an empty list, disclosing nothing.

    The list is always a page: a reader who has been at this for months should not
    pay for their whole history to draw a dock. Callers that name no page take
    :data:`DEFAULT_PAGE_LIMIT`, and there is no way to ask for an unbounded one.
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
    ) -> None:
        self._conversations = conversations

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> list[ConversationSummary]:
        return self._conversations.list_for_user(user.id, source_id, limit=limit, offset=offset)


class ReadConversation:
    """Return an owned conversation with its full ordered turns (CONV-07).

    Turns come back ``turn_index``-ascending with their citation snapshots (the
    repository's contract), so re-ingestion never breaks history (I-CM-1).
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        turns: ConversationTurnRepository,
        sources: SourceRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._conversations = conversations
        self._turns = turns
        self._sources = sources
        self._authorize = authorize

    def __call__(
        self, *, user: User, conversation_id: UUID
    ) -> tuple[Conversation, list[ConversationTurn]]:
        conversation, _ = authorized_conversation(
            user=user,
            conversation_id=conversation_id,
            conversations=self._conversations,
            sources=self._sources,
            authorize=self._authorize,
        )
        return conversation, self._turns.list_for_conversation(conversation_id)


class RenameConversation:
    """Retitle an owned conversation and bump its activity (CONV-08).

    The title is trimmed and bounded by :data:`TITLE_MAX_CHARS`; blank or oversize
    raises ``InvalidConversationTitle`` (422) with the stored title untouched. A
    conversation that vanished between the ownership read and the write reports
    absence like any other missing conversation.
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        sources: SourceRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
    ) -> None:
        self._conversations = conversations
        self._sources = sources
        self._authorize = authorize
        self._clock = clock

    def __call__(self, *, user: User, conversation_id: UUID, title: str) -> Conversation:
        authorized_conversation(
            user=user,
            conversation_id=conversation_id,
            conversations=self._conversations,
            sources=self._sources,
            authorize=self._authorize,
        )
        trimmed = normalize_title(title)
        if trimmed is None:
            raise InvalidConversationTitle("Title must not be empty.")
        renamed = self._conversations.rename(conversation_id, trimmed, self._clock.now())
        if renamed is None:
            raise ConversationNotFound("Conversation not found.")
        return renamed


class DeleteConversation:
    """Delete an owned conversation with its turns and citations (CONV-09).

    The repository's cascade removes the child rows, so a second delete reports
    absence rather than leaving orphans behind — and an unowned delete is
    indistinguishable from that absence (I-CM-6).
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        sources: SourceRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._conversations = conversations
        self._sources = sources
        self._authorize = authorize

    def __call__(self, *, user: User, conversation_id: UUID) -> None:
        authorized_conversation(
            user=user,
            conversation_id=conversation_id,
            conversations=self._conversations,
            sources=self._sources,
            authorize=self._authorize,
        )
        if not self._conversations.delete(conversation_id):
            raise ConversationNotFound("Conversation not found.")


def _with_spans(citations: list[Evidence], spans: Sequence[CitedSpan]) -> tuple[Evidence, ...]:
    """Snapshot each citation with the first claim-level quote reported for its chunk.

    One quote per citation rather than per reported span: the reader sees one ``[^n]``
    per passage (AD-222), so the hover behind that mark has one sentence to show.
    Later spans into the same chunk are dropped instead of concatenated — the passage
    region still carries the whole snippet, which is where a second claim is read. A
    citation nothing was reported for keeps its empty span and behaves exactly as it
    did before spans existed (ASK-17).
    """
    first: dict[UUID, CitedSpan] = {}
    for span in spans:
        first.setdefault(span.chunk_id, span)
    snapshots: list[Evidence] = []
    for citation in citations:
        span = first.get(citation.chunk_id)
        snapshots.append(
            citation
            if span is None
            else replace(
                citation,
                quoted_text=span.quote,
                start_char=span.start,
                end_char=span.end,
            )
        )
    return tuple(snapshots)


@dataclass(frozen=True)
class _TurnPrep:
    """What the guards resolved for one turn, before anything is searched for.

    The half of the preflight that decides whether the turn may run at all, so both
    paths can settle every error outcome — a 404, a 409, a bad mode — before a
    streaming response has committed to a status code. ``anchors`` is the expanded
    scope retrieval will be given (``None`` = the whole source).
    """

    conversation: Conversation
    target: StructureSection | None
    history: list[HistoryTurn]
    turn_index: int
    anchors: tuple[str, ...] | None
    tutor_state: TutorState


@dataclass(frozen=True)
class _TurnPlan:
    """Everything the guards resolved for one turn, before any generation runs.

    A :class:`_TurnPrep` plus the evidence retrieval found for it, so the buffered
    and streaming paths run byte-identical guards, retrieval, and history (I-CM-5).
    ``target`` is the resolved teach target on a teach turn and ``None`` on an
    answer turn; ``turn_index`` is the count of prior turns, the index this turn
    claims.
    """

    conversation: Conversation
    target: StructureSection | None
    history: list[HistoryTurn]
    evidence: list[Evidence]
    turn_index: int
    tutor_state: TutorState


def _is_closing_restatement(prep: _TurnPrep) -> bool:
    """True when this learner message is the unaided check that closes the session."""
    return prep.tutor_state.phase == "close" and prep.conversation.tutor_phase == "check"


class PostConversationTurn:
    """Run one grounded turn in an owned conversation (CONV-10..14).

    The conversation's *scope* decides what retrieval may see and the turn's *mode*
    decides how the reply behaves, so one service covers both product shapes. The
    guards are the teaching path's, generalized: ownership collapses to
    ``ConversationNotFound`` (404), a source that is no longer ``ready`` raises
    ``SourceNotReady`` (409), and a teach turn without a resolvable target raises
    ``ConversationTargetUnavailable`` (409) before anything is retrieved or written.

    Scope is a promise (ADR-0029). It is re-expanded **per turn** against the live
    corpus — each scoped anchor to its section's subtree, then through
    ``expand_anchors`` for the anchors normalization merged away — and a scoped turn
    passes those anchors to retrieval every time. A scope anchor whose section a
    re-ingest dropped keeps its raw anchor in the set rather than being discarded, so
    a scoped turn can return nothing but can never silently widen to the whole book
    (I-CM-3). Whole-book conversations pass ``anchors=None``, which is the only way
    the whole source is searched. Notes are never anchor-filtered (engine semantics):
    the conversation's own stored ``include_notes`` gates them, for every turn — the
    choice is the conversation's, made once when it is started (ADR-0029), and no
    request can bend it for one turn.

    Generation goes to the one :class:`~app.domain.ports.GenerationPort` with the
    mode, the bounded prior history, and — for ``teach`` — the target's section
    path. There is no port to choose and so no branch that chooses one, and the
    model identity a turn records has a single type. The port's answer passes
    through the shared grounding guard (AD-027), any port raise becomes
    ``AnswerGenerationFailed`` — after a turn recording the question and no answer is
    written at ``failed`` (AD-262), so a provider outage costs the reader an answer
    and never the question — and the turn — answered or
    not-found — is persisted **only after grounding** with the next ``turn_index``,
    its citations in evidence-rank order (I-CM-5). The not-found verdict follows the
    scope: a scoped conversation reports ``not_found_in_scope`` (the reader's own
    selection came up short, which a client can offer to widen), a whole-book one
    ``not_found_in_source``. The ``(conversation_id, turn_index)`` unique is the race
    arbiter — the loser's ``ConversationTurnConflict`` propagates (I-CM-2) — and a
    persisted turn bumps the conversation's ``updated_at`` (CONV-13). Exactly one
    content-free log line records each completed turn. Framework-free (ADR-0007/0009).
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
        turns: ConversationTurnRepository,
        sources: SourceRepository,
        corpus: CorpusRepository,
        retrieve: RetrieveEvidence,
        generation: GenerationPort,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
        evidence_top_k: int,
        history_turns: int,
        tutor_check_after_turns: int,
    ) -> None:
        self._conversations = conversations
        self._turns = turns
        self._sources = sources
        self._corpus = corpus
        self._retrieve = retrieve
        self._generation = generation
        self._authorize = authorize
        self._clock = clock
        self._ids = ids
        self._evidence_top_k = evidence_top_k
        self._history_turns = history_turns
        self._tutor_check_after_turns = tutor_check_after_turns

    def __call__(
        self,
        *,
        user: User,
        conversation_id: UUID,
        message: str,
        mode: str,
    ) -> ConversationTurn:
        prep = self._preflight(
            user=user, conversation_id=conversation_id, mode=mode, message=message
        )
        if _is_closing_restatement(prep):
            return self._persist(
                self._unsearched_plan(prep),
                self._restatement_turn(prep, message, mode),
                mode,
            )
        plan = self._retrieve_evidence(user=user, prep=prep, message=message, mode=mode)

        if not plan.evidence:
            # Nothing in scope to answer from → not-found; the port is never invoked,
            # so the model identity comes from the port attribute.
            turn = self._not_found_turn(plan, message, mode, 0, self._generation.model)
        else:
            try:
                generated = self._generate(mode=mode, message=message, plan=plan)
            except Exception as exc:  # any port failure maps to 502
                self._persist_failed(plan, message, mode)
                raise AnswerGenerationFailed("Answer generation failed.") from exc

            turn = self._turn_from_generated(
                plan=plan, message=message, mode=mode, generated=generated
            )

        return self._persist(plan, turn, mode)

    def stream(
        self,
        *,
        user: User,
        conversation_id: UUID,
        message: str,
        mode: str,
    ) -> Iterator[TurnStreamEvent]:
        """Run one turn incrementally, persisting only on stream completion.

        The shared guards run **eagerly** (before this returns), so the turn's HTTP
        error outcomes (404/409/422) surface before any SSE bytes. Retrieval does
        not: it is the first slow thing a turn does, so it runs inside the stream,
        behind an immediately-yielded ``searching`` phase — the wait for evidence is
        the part of the turn a reader would otherwise spend staring at nothing.
        Failing there can no longer be an HTTP status (the response has begun), so
        it becomes the same generation-failure the reader is shown for any other
        mid-stream break.

        The generation stream then drives the sentinel hold-back and the same
        grounding guard, and the turn is persisted and yielded as the terminal
        :class:`~app.application.streaming.StreamTurn` only after grounding completes
        — so a consumer disconnect mid-stream persists nothing, and the persisted turn
        is identical to the buffered path's (I-CM-5). A break the reader did not ask
        for is the exception: retrieval or the provider failing writes the ``failed``
        turn before the error reaches the wire, so reloading after an error still
        shows the question that was asked (AD-262).
        """
        prep = self._preflight(
            user=user, conversation_id=conversation_id, mode=mode, message=message
        )
        return self._turn_stream(user=user, prep=prep, message=message, mode=mode)

    def _turn_stream(
        self, *, user: User, prep: _TurnPrep, message: str, mode: str
    ) -> Iterator[TurnStreamEvent]:
        if _is_closing_restatement(prep):
            yield self._stream_turn(
                self._unsearched_plan(prep),
                self._restatement_turn(prep, message, mode),
                mode,
            )
            return
        yield StreamPhase(phase=PHASE_SEARCHING)
        try:
            plan = self._retrieve_evidence(user=user, prep=prep, message=message, mode=mode)
        except Exception as exc:  # retrieval can no longer answer with a status code
            # The reader is told only that generation failed, so this line is the
            # sole record of *why*: without it an index outage and a programming
            # error both leave nothing behind but a generic frame.
            logger.exception(
                "conversation turn retrieval failed conversation_id=%s source_id=%s mode=%s",
                prep.conversation.id,
                prep.conversation.source_id,
                mode,
            )
            self._persist_failed(self._unsearched_plan(prep), message, mode)
            raise AnswerGenerationFailed("Answer generation failed.") from exc

        if not plan.evidence:
            turn = self._not_found_turn(plan, message, mode, 0, self._generation.model)
            yield self._stream_turn(plan, turn, mode)
            return

        stream = self._generate_stream(mode=mode, message=message, plan=plan)
        # Hold-back yields presentable deltas and returns the authoritative answer;
        # no *answered* turn is persisted until it completes (so cancellation persists
        # nothing), but a provider break writes the failed turn before it propagates.
        try:
            answer = yield from hold_back_deltas(stream)
        except AnswerGenerationFailed:
            self._persist_failed(plan, message, mode)
            raise
        # SPEC_DEVIATION: a reader who stops the stream still persists nothing; only a
        # failure the reader did not ask for writes the ``failed`` turn.
        # Reason: cancellation arrives as ``GeneratorExit`` while this generator is
        # closing, and writing to the database there runs after the request's response
        # is done — a different transaction lifetime than any other write on this path.
        # ASK-04 (the conversation survives a stop) is met on the client, which no
        # longer deletes it; keeping the stopped question is not an acceptance
        # criterion and is left to the retry cycle.

        turn = self._turn_from_generated(plan=plan, message=message, mode=mode, generated=answer)
        yield self._stream_turn(plan, turn, mode)

    def _preflight(
        self,
        *,
        user: User,
        conversation_id: UUID,
        mode: str,
        message: str,
    ) -> _TurnPrep:
        """Run the shared turn guards, scope expansion, and history.

        Both the buffered and the streaming path run this identically, and both run
        it eagerly, so the same error outcomes surface — for the stream, before any
        SSE bytes, which is what keeps a rejected turn an HTTP status rather than a
        200 that carries bad news. Retrieval is deliberately *not* here: see
        :meth:`_retrieve_evidence`.
        """
        if mode not in (MODE_ANSWER, MODE_TEACH):
            # A named error rather than a bare ValueError: this is a public service
            # with callers beyond the router, so a bad mode is the 422 the boundary
            # already publishes rather than an unhandled 500.
            raise InvalidConversationMode(f"Unknown conversation mode: {mode!r}")

        conversation, source = authorized_conversation(
            user=user,
            conversation_id=conversation_id,
            conversations=self._conversations,
            sources=self._sources,
            authorize=self._authorize,
        )
        if conversation.tutor_phase == "close":
            raise ConversationClosed("This conversation is closed.")
        if conversation.tutor_phase is not None and mode == MODE_ANSWER:
            raise InvalidConversationMode("Answer mode cannot continue a tutor conversation.")
        if source.status != SOURCE_STATUS_READY:
            # A stale-ready race resolves here on the next turn.
            raise SourceNotReady("Source is not ready for conversations.")

        # The corpus map is only read by the two callees that can use it: a teach
        # turn resolves its target through it, and a scoped turn expands its scope
        # through it. A whole-book answer turn — every legacy ask — would discard the
        # whole table of contents, so it never loads it.
        sections: Sequence[StructureSection] = ()
        by_anchor: dict[str, StructureSection] = {}
        if mode == MODE_TEACH or conversation.scope_anchors:
            structure = self._corpus.get_structure(conversation.source_id)
            sections = structure.sections if structure is not None else ()
            by_anchor = {section.anchor: section for section in sections}

        # The teach invariant is checked before retrieval so a turn that cannot be
        # taught costs nothing and persists nothing (I-CM-7).
        target = self._resolve_target(conversation, by_anchor) if mode == MODE_TEACH else None
        anchors = self._scoped_anchors(conversation, sections, by_anchor)

        # Bounded conversation context: the last ``history_turns`` message/response
        # pairs (response empty for a not-found turn), all of them when fewer exist.
        # ``recent_history`` skips the citation payloads ``list_for_conversation``
        # loads — the turn path never uses them — and its count is the next index.
        turn_index, history = self._turns.recent_history(conversation_id, self._history_turns)
        if mode == MODE_TEACH and turn_index == 0 and not TeachingPolicy.is_opening(message):
            raise InvalidConversationMode("The first teach turn must be the session-start message.")

        return _TurnPrep(
            conversation=conversation,
            target=target,
            history=history,
            turn_index=turn_index,
            anchors=anchors,
            tutor_state=self._next_tutor_state(conversation, mode=mode, message=message),
        )

    def _retrieve_evidence(
        self, *, user: User, prep: _TurnPrep, message: str, mode: str
    ) -> _TurnPlan:
        """Search the conversation's scope for this turn's evidence.

        Split out of the guards so the streaming path can run it *after* the first
        frame is on the wire while the buffered path still runs it straight through:
        the two paths must see the same evidence, only at different moments.
        """
        evidence = self._retrieve(
            user=user,
            source_id=prep.conversation.source_id,
            query=self._retrieval_query(mode=mode, message=message, conversation=prep.conversation),
            top_k=self._evidence_top_k,
            anchors=prep.anchors,
            include_notes=prep.conversation.include_notes,
        )
        return _TurnPlan(
            conversation=prep.conversation,
            target=prep.target,
            history=prep.history,
            evidence=evidence,
            turn_index=prep.turn_index,
            tutor_state=prep.tutor_state,
        )

    @staticmethod
    def _retrieval_query(*, mode: str, message: str, conversation: Conversation) -> str:
        if mode != MODE_TEACH or message != TUTOR_OPENING_MESSAGE:
            return message
        if conversation.target_title:
            return conversation.target_title
        return conversation.target_anchor or message

    def _resolve_target(
        self, conversation: Conversation, by_anchor: dict[str, StructureSection]
    ) -> StructureSection:
        """Re-resolve the teach target against the current corpus (I-CM-7)."""
        if not conversation.scope_anchors or conversation.target_anchor is None:
            raise ConversationTargetUnavailable(
                "This conversation covers the whole book; scope one to a section to teach it."
            )
        target = resolve_section(
            conversation.target_anchor,
            by_anchor=by_anchor,
            corpus=self._corpus,
            source_id=conversation.source_id,
        )
        if target is None:
            # Re-ingestion (AD-018) replaced the corpus and dropped the section.
            raise ConversationTargetUnavailable(
                "The section this conversation teaches no longer exists; start a new one."
            )
        return target

    def _scoped_anchors(
        self,
        conversation: Conversation,
        sections: Sequence[StructureSection],
        by_anchor: dict[str, StructureSection],
    ) -> tuple[str, ...] | None:
        """Expand the stored scope to the anchors retrieval may see this turn.

        ``None`` — the whole source — is returned for, and only for, a conversation
        with an empty scope. A scoped conversation contributes each anchor's section
        *and its descendants* (``section_path`` prefix match), then the whole set goes
        through ``expand_anchors`` so evidence from a section normalization merged
        away is still reachable (AD-085). An anchor that resolves to nothing is kept
        as itself: it matches no chunk, which is the honest outcome, where dropping it
        could empty the set and silently widen the search (I-CM-3).

        The anchors the canonical map misses are expanded **in one call** rather than
        one per anchor: the sections that expansion reaches are exactly the sections
        those anchors address, so their subtrees are the same set a per-anchor walk
        would collect. Each miss is also kept as itself, which costs nothing — an
        anchor an alias resolved is one the closing expansion would have added back
        anyway — and keeps a miss that resolved to nothing in the set.
        """
        if not conversation.scope_anchors:
            return None
        base: list[str] = []
        seen: set[str] = set()

        def add(anchor: str) -> None:
            if anchor not in seen:
                seen.add(anchor)
                base.append(anchor)

        def add_subtree(section: StructureSection) -> None:
            depth = len(section.section_path)
            for s in sections:
                if s.section_path[:depth] == section.section_path:
                    add(s.anchor)

        misses = [a for a in conversation.scope_anchors if a not in by_anchor]
        aliased = (
            [
                c
                for c in self._corpus.expand_anchors(conversation.source_id, misses)
                if c in by_anchor
            ]
            if misses
            else []
        )
        for anchor in conversation.scope_anchors:
            section = by_anchor.get(anchor)
            if section is None:
                add(anchor)
            else:
                add_subtree(section)
        for canonical in aliased:
            add_subtree(by_anchor[canonical])
        return self._corpus.expand_anchors(conversation.source_id, base)

    def _target_path(self, mode: str, plan: _TurnPlan) -> tuple[str, ...] | None:
        """The teach target's section path, or ``None`` when this turn answers.

        Read from the mode and never from the conversation's target snapshot: a
        conversation scoped to a chapter carries a target in *either* mode (AD-194),
        so target-presence would route scoped asks through the teaching prompt.
        """
        if mode != MODE_TEACH:
            return None
        assert plan.target is not None  # the preflight resolved it or raised
        return plan.target.section_path

    def _generate(self, *, mode: str, message: str, plan: _TurnPlan) -> GeneratedAnswer:
        return self._generation.generate(
            message=message,
            mode=mode,
            evidence=plan.evidence,
            history=plan.history,
            target_section_path=self._target_path(mode, plan),
            tutor_phase=plan.tutor_state.phase if mode == MODE_TEACH else None,
            hint_level=plan.tutor_state.hint_level if mode == MODE_TEACH else None,
        )

    def _generate_stream(
        self, *, mode: str, message: str, plan: _TurnPlan
    ) -> Iterator[AnswerStreamEvent]:
        return self._generation.generate_stream(
            message=message,
            mode=mode,
            evidence=plan.evidence,
            history=plan.history,
            target_section_path=self._target_path(mode, plan),
            tutor_phase=plan.tutor_state.phase if mode == MODE_TEACH else None,
            hint_level=plan.tutor_state.hint_level if mode == MODE_TEACH else None,
        )

    def _turn_from_generated(
        self,
        *,
        plan: _TurnPlan,
        message: str,
        mode: str,
        generated: GeneratedAnswer,
    ) -> ConversationTurn:
        """Ground the port result, with a teach carve-out for citation-free replies.

        Answer mode still collapses empty citations to not-found (AD-027). Teach
        mode keeps a non-sentinel reply with no surviving citations as answered
        so a Socratic question can persist (AD-295). ``found=False`` and blank
        text stay not-found in both modes.
        """
        grounded = ground(generated, plan.evidence)
        if grounded is not None:
            return self._answered_turn(
                plan,
                message,
                mode,
                grounded,
                generated.model,
                ground_spans(generated, grounded[1]),
            )
        if mode == MODE_TEACH and generated.found and generated.text.strip():
            return self._answered_turn(
                plan, message, mode, (generated.text, []), generated.model, ()
            )
        return self._not_found_turn(plan, message, mode, len(plan.evidence), generated.model)

    def _answered_turn(
        self,
        plan: _TurnPlan,
        message: str,
        mode: str,
        grounded: tuple[str, list[Evidence]],
        model: str,
        spans: tuple[CitedSpan, ...],
    ) -> ConversationTurn:
        text, citations = grounded
        return ConversationTurn(
            id=self._ids(),
            conversation_id=plan.conversation.id,
            turn_index=plan.turn_index,
            message=message,
            mode=mode,
            answer_status=ANSWERED,
            answer_text=text,
            model=model,
            evidence_count=len(plan.evidence),
            citations=_with_spans(citations, spans),
            created_at=self._clock.now(),
        )

    def _not_found_turn(
        self,
        plan: _TurnPlan,
        message: str,
        mode: str,
        evidence_count: int,
        model: str,
    ) -> ConversationTurn:
        # Persisted like an answered turn but with empty text and no citations. The
        # verdict names what was actually searched: the reader's scope, or the book.
        status = NOT_FOUND_IN_SCOPE if plan.conversation.scope_anchors else NOT_FOUND_IN_SOURCE
        return ConversationTurn(
            id=self._ids(),
            conversation_id=plan.conversation.id,
            turn_index=plan.turn_index,
            message=message,
            mode=mode,
            answer_status=status,
            answer_text="",
            model=model,
            evidence_count=evidence_count,
            citations=(),
            created_at=self._clock.now(),
        )

    def _failed_turn(self, plan: _TurnPlan, message: str, mode: str) -> ConversationTurn:
        """The turn a broken generation leaves behind: the question, and no answer.

        A not-found turn is a verdict about the book; this one is the absence of a
        verdict, and it exists for one reason — the reader's question must survive
        the failure (AD-262). Reload is the test: a thread that only ever held the
        question in the browser loses it to a refresh, which is how a first ask
        vanished entirely. Empty text and no citations say there is nothing to read
        rather than something to distrust, and the model is the configured one
        because a call that failed returned no identity to record.
        """
        return ConversationTurn(
            id=self._ids(),
            conversation_id=plan.conversation.id,
            turn_index=plan.turn_index,
            message=message,
            mode=mode,
            answer_status=FAILED,
            answer_text="",
            model=self._generation.model,
            evidence_count=len(plan.evidence),
            citations=(),
            created_at=self._clock.now(),
        )

    def _persist_failed(self, plan: _TurnPlan, message: str, mode: str) -> None:
        """Write the failed turn, then let the caller surface the failure as before.

        Persisting first and raising second keeps both halves of the contract: the
        HTTP status (or the stream's error frame) still reports that generation
        failed, and the conversation still holds what the reader asked (ASK-01).
        Prior turns are untouched — this is an append at the next index like any
        other turn, so a conversation that has been working for an hour keeps its
        history and gains one failed row (ASK-05).
        """
        self._persist(plan, self._failed_turn(plan, message, mode), mode)

    @staticmethod
    def _unsearched_plan(prep: _TurnPrep) -> _TurnPlan:
        """The plan of a turn that broke before retrieval answered: no evidence."""
        return _TurnPlan(
            conversation=prep.conversation,
            target=prep.target,
            history=prep.history,
            evidence=[],
            turn_index=prep.turn_index,
            tutor_state=prep.tutor_state,
        )

    def _persist(self, plan: _TurnPlan, turn: ConversationTurn, mode: str) -> ConversationTurn:
        """Write the turn, bump the conversation's activity, and log the outcome.

        The DB unique is the turn-index race arbiter; a conflict propagates as a 409
        for the losing writer — nothing is bumped or logged for it.
        """
        persisted = self._turns.add(turn)
        now = self._clock.now()
        self._conversations.touch(plan.conversation.id, now)
        stored = self._stored_tutor(plan, persisted)
        if stored.phase is not None or plan.conversation.tutor_phase is not None:
            self._conversations.update_tutor_state(
                replace(
                    plan.conversation,
                    tutor_phase=stored.phase,
                    hint_level=stored.hint_level,
                    tutor_ordinary_turns=stored.ordinary_turns,
                    tutor_scaffold_misses=stored.scaffold_misses,
                    tutor_check_text=stored.check_text,
                    updated_at=now,
                )
            )
        logger.info(
            "conversation turn completed outcome=%s conversation_id=%s source_id=%s mode=%s "
            "evidence_count=%s model=%s",
            persisted.answer_status,
            plan.conversation.id,
            plan.conversation.source_id,
            mode,
            persisted.evidence_count,
            persisted.model,
        )
        return persisted

    def _stream_turn(self, plan: _TurnPlan, turn: ConversationTurn, mode: str) -> StreamTurn:
        """Persist the turn and echo the tutor ladder the buffered read would return."""
        persisted = self._persist(plan, turn, mode)
        stored = self._stored_tutor(plan, persisted)
        return StreamTurn(
            turn=persisted,
            tutor_phase=stored.phase,
            hint_level=stored.hint_level,
            tutor_check_text=stored.check_text,
        )

    @staticmethod
    def _stored_tutor(plan: _TurnPlan, persisted: ConversationTurn) -> TutorState:
        if persisted.answer_status == FAILED:
            return plan.tutor_state
        return TeachingPolicy.after_tutor_turn(plan.tutor_state)

    def _next_tutor_state(
        self, conversation: Conversation, *, mode: str, message: str
    ) -> TutorState:
        current = TutorState(
            phase=conversation.tutor_phase,
            hint_level=conversation.hint_level,
            ordinary_turns=conversation.tutor_ordinary_turns,
            scaffold_misses=conversation.tutor_scaffold_misses,
            check_text=conversation.tutor_check_text,
        )
        if mode != MODE_TEACH:
            return current
        if current.phase is None and not TeachingPolicy.is_opening(message):
            return current
        return TeachingPolicy.advance(
            current, message=message, check_after=self._tutor_check_after_turns
        )

    def _restatement_turn(self, prep: _TurnPrep, message: str, mode: str) -> ConversationTurn:
        return ConversationTurn(
            id=self._ids(),
            conversation_id=prep.conversation.id,
            turn_index=prep.turn_index,
            message=message,
            mode=mode,
            answer_status=ANSWERED,
            answer_text="",
            model=self._generation.model,
            evidence_count=0,
            citations=(),
            created_at=self._clock.now(),
        )
