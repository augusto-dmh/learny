"""Teaching router — owner-scoped teaching sessions over a ready source (Phase 8).

Thin FastAPI adapter over the framework-free teaching services (assembled in
``dependencies``). A signed-in owner starts a session anchored to a section of one
of their ready sources, reads a session's full cited conversation, and lists a
source's sessions. The handlers own input validation (422) and let application
errors propagate to the global handlers (``TeachingSessionNotFound`` → 404,
``SourceNotReady`` → 409, ``InvalidTeachingTarget`` → 422), mirroring the
questions endpoint.

Contract (also consumed by the Next.js proxy):
- ``POST /api/teaching-sessions`` ``{source_id, target_anchor}`` → 201 session;
  auth + CSRF/Origin + rate limit (TEACH-01..04, 18, 23).
- ``GET  /api/teaching-sessions/{id}`` → 200 session + ordered cited turns; auth
  (TEACH-05, 06, 20).
- ``GET  /api/sources/{source_id}/teaching-sessions`` → 200 per-source session
  summaries, newest first; auth (TEACH-21).

The turn endpoint (``POST /api/teaching-sessions/{id}/turns``) is added alongside
the ``TurnView`` reused here for the read path.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.application.teaching import (
    ListTeachingSessions,
    ReadTeachingSession,
    StartTeachingSession,
)
from app.domain.entities import (
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_list_teaching_sessions,
    get_read_teaching_session,
    get_start_teaching_session,
)
from app.infrastructure.web.rate_limit import rate_limit_teaching
from app.infrastructure.web.retrieval import EvidenceView

router = APIRouter(tags=["teaching"])


# --- Request bodies ------------------------------------------------------------


class StartSessionRequest(BaseModel):
    """Start-session request body (TEACH-01/04).

    ``target_anchor`` must be non-blank; whether it resolves to a section of the
    source's corpus is the service's decision (an unknown anchor →
    ``InvalidTeachingTarget`` → 422). A missing/blank field or bad ``source_id``
    UUID is a Pydantic validation error → 422 before the service runs.
    """

    source_id: UUID
    target_anchor: str = Field(min_length=1)


# --- Response views ------------------------------------------------------------


class TargetView(BaseModel):
    """The session's target section snapshot (TEACH-01)."""

    anchor: str
    section_path: list[str]
    title: str

    @classmethod
    def from_session(cls, session: TeachingSession) -> TargetView:
        return cls(
            anchor=session.target_anchor,
            section_path=list(session.target_section_path),
            title=session.target_title,
        )


class SessionView(BaseModel):
    """The created/started session (TEACH-01)."""

    id: UUID
    source_id: UUID
    target: TargetView
    created_at: datetime

    @classmethod
    def from_session(cls, session: TeachingSession) -> SessionView:
        return cls(
            id=session.id,
            source_id=session.source_id,
            target=TargetView.from_session(session),
            created_at=session.created_at,
        )


class TurnView(BaseModel):
    """One cited teaching turn (TEACH-07/24).

    ``answer_status`` is ``answered`` or ``not_found_in_source``; ``text`` is empty
    and ``citations`` empty for the not-found outcome (TEACH-14). ``citations``
    reuses the retrieval endpoint's ``EvidenceView`` citation-only projection.
    """

    turn_index: int
    message: str
    answer_status: str
    text: str
    citations: list[EvidenceView]
    evidence_count: int
    model: str
    created_at: datetime

    @classmethod
    def from_turn(cls, turn: TeachingTurn) -> TurnView:
        return cls(
            turn_index=turn.turn_index,
            message=turn.message,
            answer_status=turn.answer_status,
            text=turn.answer_text,
            citations=[EvidenceView.from_evidence(c) for c in turn.citations],
            evidence_count=turn.evidence_count,
            model=turn.model,
            created_at=turn.created_at,
        )


class SessionDetailView(BaseModel):
    """A session with its full ordered conversation (TEACH-05/20).

    ``turns`` are ordered by ``turn_index`` ascending, each with its citation
    snapshots — so history renders intact after re-ingestion.
    """

    id: UUID
    source_id: UUID
    target: TargetView
    created_at: datetime
    turns: list[TurnView]

    @classmethod
    def from_session(
        cls, session: TeachingSession, turns: list[TeachingTurn]
    ) -> SessionDetailView:
        return cls(
            id=session.id,
            source_id=session.source_id,
            target=TargetView.from_session(session),
            created_at=session.created_at,
            turns=[TurnView.from_turn(t) for t in turns],
        )


class SessionSummaryView(BaseModel):
    """A per-source session summary for the resume list (TEACH-21)."""

    id: UUID
    target: TargetView
    created_at: datetime
    turn_count: int

    @classmethod
    def from_summary(cls, summary: TeachingSessionSummary) -> SessionSummaryView:
        return cls(
            id=summary.session.id,
            target=TargetView.from_session(summary.session),
            created_at=summary.session.created_at,
            turn_count=summary.turn_count,
        )


# --- Endpoints -----------------------------------------------------------------


@router.post(
    "/api/teaching-sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_teaching),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def start_teaching_session(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[StartTeachingSession, Depends(get_start_teaching_session)],
    body: StartSessionRequest,
) -> SessionView:
    """Start a session anchored to a section of an owned ready source (201).

    ``StartTeachingSession`` authorizes ownership (missing/non-owner →
    ``SourceNotFound`` → 404), enforces readiness (``SourceNotReady`` → 409), and
    resolves the target anchor (unknown → ``InvalidTeachingTarget`` → 422).
    """
    session = service(
        user=user, source_id=body.source_id, target_anchor=body.target_anchor
    )
    return SessionView.from_session(session)


@router.get("/api/teaching-sessions/{session_id}")
def read_teaching_session(
    session_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ReadTeachingSession, Depends(get_read_teaching_session)],
) -> SessionDetailView:
    """Return an owned session with its ordered cited conversation (200; 404)."""
    session, turns = service(user=user, session_id=session_id)
    return SessionDetailView.from_session(session, turns)


@router.get("/api/sources/{source_id}/teaching-sessions")
def list_teaching_sessions(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListTeachingSessions, Depends(get_list_teaching_sessions)],
) -> list[SessionSummaryView]:
    """Return an owned source's sessions, newest first (200; 404 missing/non-owner)."""
    return [SessionSummaryView.from_summary(s) for s in service(user=user, source_id=source_id)]
