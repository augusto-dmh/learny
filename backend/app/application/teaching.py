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

from collections.abc import Callable
from uuid import UUID

from app.application.errors import (
    InvalidTeachingTarget,
    NotAuthorized,
    SourceNotReady,
    TeachingSessionNotFound,
)
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import SOURCE_STATUS_READY, authorized_source
from app.domain.entities import (
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)
from app.domain.ports import (
    Clock,
    CorpusRepository,
    SourceRepository,
    TeachingSessionRepository,
    TeachingTurnRepository,
)


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
        session = self._sessions.get_by_id(session_id)
        if session is None:
            raise TeachingSessionNotFound("Teaching session not found.")
        source = self._sources.get_by_id(session.source_id)
        if source is None:
            raise TeachingSessionNotFound("Teaching session not found.")
        try:
            self._authorize(user=user, owner_id=source.user_id)
        except NotAuthorized as exc:
            raise TeachingSessionNotFound("Teaching session not found.") from exc
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
