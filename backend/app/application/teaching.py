"""Teaching-session use-case services (design §Components).

Framework-free orchestration of the teaching aggregate: starting a session
anchored to a corpus section, reading a session's full conversation, and listing
a source's sessions. Ownership is enforced exactly like the Q&A path —
``authorized_source`` collapses a missing source and a non-owner to
``SourceNotFound`` (404) for the source-rooted services, and the session-rooted
read collapses the same way to ``TeachingSessionNotFound`` so a session's
existence is never disclosed. No FastAPI / SQLAlchemy / provider-SDK type crosses
this boundary (ADR-0007/0009).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from uuid import UUID

from app.application.errors import (
    AnswerGenerationFailed,
    InvalidTeachingTarget,
    NotAuthorized,
    SourceNotReady,
    TeachingSessionNotFound,
    TeachingTargetGone,
)
from app.application.grounding import ground
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import SOURCE_STATUS_READY, authorized_source
from app.application.retrieval import RetrieveEvidence
from app.application.streaming import (
    StreamTurn,
    TurnStreamEvent,
    hold_back_deltas,
)
from app.domain.entities import (
    Evidence,
    HistoryTurn,
    Source,
    StructureSection,
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)
from app.domain.ports import (
    Clock,
    CorpusRepository,
    SourceRepository,
    TeachingGenerationPort,
    TeachingSessionRepository,
    TeachingTurnRepository,
)

logger = logging.getLogger(__name__)

# ``TeachingTurn.answer_status`` vocabulary (mirrors the Q&A ``status`` values):
# ``answered`` carries a grounded citation set; ``not_found_in_source`` is the
# explicit "the target cannot support this" outcome, still persisted (TEACH-14).
_ANSWERED = "answered"
_NOT_FOUND_IN_SOURCE = "not_found_in_source"


def authorized_session(
    *,
    user: User,
    session_id: UUID,
    sessions: TeachingSessionRepository,
    sources: SourceRepository,
    authorize: AuthorizeOwnership,
) -> tuple[TeachingSession, Source]:
    """Resolve a session the caller owns, or raise ``TeachingSessionNotFound``.

    Mirrors ``authorized_source`` for the session-rooted services: a missing
    session, a missing parent source, and a non-owner all collapse to the same
    error so a session's existence is never disclosed (TEACH-06). This is the
    single home of that rule — services never re-implement the collapse.
    """
    session = sessions.get_by_id(session_id)
    if session is None:
        raise TeachingSessionNotFound("Teaching session not found.")
    source = sources.get_by_id(session.source_id)
    if source is None:
        raise TeachingSessionNotFound("Teaching session not found.")
    try:
        authorize(user=user, owner_id=source.user_id)
    except NotAuthorized as exc:
        raise TeachingSessionNotFound("Teaching session not found.") from exc
    return session, source


class StartTeachingSession:
    """Create a session anchored to a section of an owned, ready source (TEACH-01).

    Ownership is enforced first via ``authorized_source`` (missing + non-owner →
    ``SourceNotFound``, 404). A source whose ``status != "ready"`` raises
    ``SourceNotReady`` before the corpus is read (TEACH-03). The ``target_anchor``
    is resolved against the corpus structure; no matching section raises
    ``InvalidTeachingTarget`` (TEACH-04). The resolved section's anchor,
    ``section_path`` and title are snapshotted onto the persisted session so it
    renders without re-reading the corpus (the anchor is re-resolved per turn).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        corpus: CorpusRepository,
        sessions: TeachingSessionRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._sessions = sessions
        self._authorize = authorize
        self._clock = clock
        self._ids = ids

    def __call__(
        self, *, user: User, source_id: UUID, target_anchor: str
    ) -> TeachingSession:
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        if source.status != SOURCE_STATUS_READY:
            # Guard before touching the corpus so a not-ready source never starts
            # a session (TEACH-03).
            raise SourceNotReady("Source is not ready for teaching.")

        structure = self._corpus.get_structure(source_id)
        sections = structure.sections if structure is not None else ()
        section = next((s for s in sections if s.anchor == target_anchor), None)
        if section is None:
            # The anchor matches no section of the current corpus (TEACH-04).
            raise InvalidTeachingTarget("Target does not exist in this source.")

        now = self._clock.now()
        session = TeachingSession(
            id=self._ids(),
            source_id=source_id,
            target_anchor=section.anchor,
            target_section_path=section.section_path,
            target_title=section.title,
            created_at=now,
            updated_at=now,
        )
        return self._sessions.add(session)


class ReadTeachingSession:
    """Return an owned session with its full ordered conversation (TEACH-05).

    A missing session, and a session whose parent source is not the caller's,
    both collapse to ``TeachingSessionNotFound`` (404) so existence is never
    disclosed (TEACH-06). Turns come back ``turn_index``-ascending with their
    citation snapshots (the repository's contract), so re-ingestion never breaks
    history (TEACH-20).
    """

    def __init__(
        self,
        *,
        sessions: TeachingSessionRepository,
        turns: TeachingTurnRepository,
        sources: SourceRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._sources = sources
        self._authorize = authorize

    def __call__(
        self, *, user: User, session_id: UUID
    ) -> tuple[TeachingSession, list[TeachingTurn]]:
        session, _ = authorized_session(
            user=user,
            session_id=session_id,
            sessions=self._sessions,
            sources=self._sources,
            authorize=self._authorize,
        )
        return session, self._turns.list_for_session(session_id)


class ListTeachingSessions:
    """Return an owned source's sessions, newest first (TEACH-21).

    Ownership is enforced via ``authorized_source`` (missing + non-owner →
    ``SourceNotFound``, 404 — TEACH-02 semantics). The per-source summaries carry
    each session's turn count for the resume list.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        sessions: TeachingSessionRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._sessions = sessions
        self._authorize = authorize

    def __call__(
        self, *, user: User, source_id: UUID
    ) -> list[TeachingSessionSummary]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        return self._sessions.list_for_source(source_id)


class PostTeachingTurn:
    """Run one cited teaching turn scoped to the session's target subtree.

    Mirrors the Q&A answer path with three teaching additions: the target subtree
    scopes retrieval, bounded prior history reaches the generation port, and the
    turn (either outcome) is persisted with its citation snapshots. Ownership is
    resolved via the session's parent source and collapses missing + non-owner to
    ``TeachingSessionNotFound`` (404, TEACH-06 semantics); a source that is no
    longer ``ready`` raises ``SourceNotReady`` (409, TEACH-15) and a target anchor
    that no longer resolves raises ``TeachingTargetGone`` (409, TEACH-16).

    Retrieval is restricted to the target section and its descendants (prefix
    match on ``section_path``), so no citation can reference a chunk outside the
    subtree (TEACH-09). Empty scoped evidence short-circuits to
    ``not_found_in_source`` without invoking the port (TEACH-11); otherwise the
    port's answer passes through the shared grounding guard (AD-027), any port
    raise becomes ``AnswerGenerationFailed`` with nothing persisted (TEACH-13),
    and the not-found outcome is still persisted with empty text and no citations
    (TEACH-14). ``turn_index`` is the count of prior turns; the repository's
    ``(session_id, turn_index)`` unique makes the DB the race arbiter — the loser's
    ``TeachingTurnConflict`` propagates (TEACH-17). Exactly one content-free log
    line records each completed turn (TEACH-19). Framework-free (ADR-0007/0009).
    """

    def __init__(
        self,
        *,
        sessions: TeachingSessionRepository,
        turns: TeachingTurnRepository,
        sources: SourceRepository,
        corpus: CorpusRepository,
        retrieve: RetrieveEvidence,
        generation: TeachingGenerationPort,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
        evidence_top_k: int,
        history_turns: int,
    ) -> None:
        self._sessions = sessions
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

    def _preflight(
        self, *, user: User, session_id: UUID, message: str
    ) -> tuple[StructureSection, list[HistoryTurn], list[Evidence], int]:
        """Run the shared turn guards and scoped retrieval (buffered + streaming).

        Resolves the owned session (missing/non-owner → 404), enforces readiness
        (409, TEACH-15) and the target's continued existence (409, TEACH-16),
        gathers the bounded prior history (TEACH-12), and runs target-subtree-scoped
        retrieval (TEACH-09). Returns the resolved target, that history, the scoped
        evidence, and the next ``turn_index``. Both the buffered ``__call__`` and the
        streaming ``stream`` run this identically before any generation, so the same
        HTTP error outcomes surface (for the stream path, before any SSE bytes).
        """
        session, source = authorized_session(
            user=user,
            session_id=session_id,
            sessions=self._sessions,
            sources=self._sources,
            authorize=self._authorize,
        )
        if source.status != SOURCE_STATUS_READY:
            # A stale-ready race resolves here on the next turn (TEACH-15).
            raise SourceNotReady("Source is not ready for teaching.")

        # Re-resolve the target against the current corpus: re-ingestion (AD-018)
        # may have dropped the anchored section (TEACH-16). The subtree is the
        # target and every descendant (section_path prefix match), always ≥ 1
        # anchor (the target itself), so retrieval scoping is never empty.
        structure = self._corpus.get_structure(session.source_id)
        sections = structure.sections if structure is not None else ()
        target = next(
            (s for s in sections if s.anchor == session.target_anchor), None
        )
        if target is None:
            raise TeachingTargetGone(
                "The teaching target no longer exists; start a new session."
            )
        depth = len(target.section_path)
        subtree_anchors = [
            s.anchor for s in sections if s.section_path[:depth] == target.section_path
        ]
        # Expand the subtree to the anchors normalization merged away (AD-085) so
        # evidence from a section a re-ingest folded into the subtree is still in
        # scope (ING-23); the retrieval port signature is unchanged.
        scoped_anchors = self._corpus.expand_anchors(
            session.source_id, subtree_anchors
        )

        # Bounded conversation context: the last ``history_turns`` message/response
        # pairs (response empty for a not-found turn), all of them when fewer exist
        # (TEACH-12). ``recent_history`` skips the citation payloads that
        # ``list_for_session`` loads — the turn path never uses them.
        total_turns, history = self._turns.recent_history(
            session_id, self._history_turns
        )

        evidence = self._retrieve(
            user=user,
            source_id=session.source_id,
            query=message,
            top_k=self._evidence_top_k,
            anchors=scoped_anchors,
        )
        return target, history, evidence, total_turns

    def __call__(
        self, *, user: User, session_id: UUID, message: str
    ) -> TeachingTurn:
        target, history, evidence, turn_index = self._preflight(
            user=user, session_id=session_id, message=message
        )

        if not evidence:
            # No scoped evidence → not-found; the port is never invoked, and the
            # model identity comes from the port attribute (TEACH-11 / TEACH-24).
            turn = self._not_found_turn(
                session_id, turn_index, message, 0, self._generation.model
            )
        else:
            try:
                generated = self._generation.generate(
                    message=message,
                    target_section_path=target.section_path,
                    history=history,
                    evidence=evidence,
                )
            except Exception as exc:  # any port failure maps to 502 (TEACH-13)
                raise AnswerGenerationFailed("Answer generation failed.") from exc

            grounded = ground(generated, evidence)
            if grounded is None:
                # found=false / blank text / nothing survives grounding (TEACH-10).
                turn = self._not_found_turn(
                    session_id,
                    turn_index,
                    message,
                    len(evidence),
                    generated.model,
                )
            else:
                text, citations = grounded
                turn = TeachingTurn(
                    id=self._ids(),
                    session_id=session_id,
                    turn_index=turn_index,
                    message=message,
                    answer_status=_ANSWERED,
                    answer_text=text,
                    model=generated.model,
                    evidence_count=len(evidence),
                    citations=tuple(citations),
                    created_at=self._clock.now(),
                )

        # The DB unique is the turn-index race arbiter; a conflict propagates as a
        # 409 for the losing writer (TEACH-17) — nothing is logged for it.
        persisted = self._turns.add(turn)
        logger.info(
            "teaching turn completed outcome=%s session_id=%s evidence_count=%s model=%s",
            persisted.answer_status,
            session_id,
            persisted.evidence_count,
            persisted.model,
        )
        return persisted

    def stream(
        self, *, user: User, session_id: UUID, message: str
    ) -> Iterator[TurnStreamEvent]:
        """Run one cited turn incrementally, persisting only on stream completion.

        The shared guards + scoped retrieval run **eagerly** (before this returns),
        so the turn's HTTP error outcomes (404/409) surface before any SSE bytes.
        Non-empty evidence drives the generation port's stream through the sentinel
        hold-back and the shared grounding guard; the turn (either outcome) is
        persisted and yielded as the terminal
        :class:`~app.application.streaming.StreamTurn` **only after grounding
        completes**, so a consumer disconnect mid-stream (``GeneratorExit`` closing
        the port stream) persists nothing (TEACH-13/17 streaming analog). A port
        failure surfaces as ``AnswerGenerationFailed`` from within the stream.
        """
        target, history, evidence, turn_index = self._preflight(
            user=user, session_id=session_id, message=message
        )
        return self._turn_stream(
            session_id=session_id,
            target=target,
            message=message,
            history=history,
            evidence=evidence,
            turn_index=turn_index,
        )

    def _turn_stream(
        self,
        *,
        session_id: UUID,
        target: StructureSection,
        message: str,
        history: list[HistoryTurn],
        evidence: list[Evidence],
        turn_index: int,
    ) -> Iterator[TurnStreamEvent]:
        if not evidence:
            # No scoped evidence → not-found, persisted with empty text/citations;
            # the port is never invoked (TEACH-11 / TEACH-14).
            turn = self._not_found_turn(
                session_id, turn_index, message, 0, self._generation.model
            )
            yield StreamTurn(self._turns.add(turn))
            return

        stream = self._generation.generate_stream(
            message=message,
            target_section_path=target.section_path,
            history=history,
            evidence=evidence,
        )
        # Hold-back yields presentable deltas and returns the authoritative answer;
        # nothing is persisted until it completes (so cancellation persists nothing).
        answer = yield from hold_back_deltas(stream)

        grounded = ground(answer, evidence)
        if grounded is None:
            turn = self._not_found_turn(
                session_id, turn_index, message, len(evidence), answer.model
            )
        else:
            text, citations = grounded
            turn = TeachingTurn(
                id=self._ids(),
                session_id=session_id,
                turn_index=turn_index,
                message=message,
                answer_status=_ANSWERED,
                answer_text=text,
                model=answer.model,
                evidence_count=len(evidence),
                citations=tuple(citations),
                created_at=self._clock.now(),
            )
        # The DB unique remains the turn-index race arbiter (TEACH-17).
        yield StreamTurn(self._turns.add(turn))

    def _not_found_turn(
        self,
        session_id: UUID,
        turn_index: int,
        message: str,
        evidence_count: int,
        model: str,
    ) -> TeachingTurn:
        # Persisted like an answered turn but with empty text and no citations
        # (TEACH-14).
        return TeachingTurn(
            id=self._ids(),
            session_id=session_id,
            turn_index=turn_index,
            message=message,
            answer_status=_NOT_FOUND_IN_SOURCE,
            answer_text="",
            model=model,
            evidence_count=evidence_count,
            citations=(),
            created_at=self._clock.now(),
        )
