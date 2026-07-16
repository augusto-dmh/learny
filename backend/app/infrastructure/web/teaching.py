"""Teaching router — owner-scoped teaching sessions over a ready source (Phase 8).

Thin FastAPI adapter over the framework-free teaching services (assembled in
``dependencies``). A signed-in owner starts a session anchored to a section of one
of their ready sources, reads a session's full cited conversation, lists a
source's sessions, and posts cited turns. The handlers own input validation (422)
and let application errors propagate to the global handlers
(``TeachingSessionNotFound`` → 404, ``SourceNotReady`` → 409,
``InvalidTeachingTarget`` → 422, ``TeachingTargetGone`` → 409,
``TeachingTurnConflict`` → 409, ``AnswerGenerationFailed`` → 502), mirroring the
questions endpoint.

Contract (also consumed by the Next.js proxy):
- ``POST /api/teaching-sessions`` ``{source_id, target_anchor}`` → 201 session;
  auth + CSRF/Origin + rate limit (TEACH-01..04, 18, 23).
- ``GET  /api/teaching-sessions/{id}`` → 200 session + ordered cited turns; auth
  (TEACH-05, 06, 20).
- ``POST /api/teaching-sessions/{id}/turns`` ``{message}`` → 201 cited turn; auth
  + CSRF/Origin + rate limit. ``message`` is trimmed and validated 1..
  ``LEARNY_TEACHING_MESSAGE_MAX_CHARS`` chars → 422 otherwise (TEACH-07, 08, 18).
- ``GET  /api/sources/{source_id}/teaching-sessions`` → 200 per-source session
  summaries, newest first; auth (TEACH-21).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field, field_validator

from app.application.teaching import (
    ListTeachingSessions,
    PostTeachingTurn,
    ReadTeachingSession,
    StartTeachingSession,
)
from app.core.config import get_settings
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
    get_post_teaching_turn,
    get_read_teaching_session,
    get_start_teaching_session,
)
from app.infrastructure.web.rate_limit import rate_limit_teaching
from app.infrastructure.web.retrieval import EvidenceView
from app.infrastructure.web.ui_message_stream import (
    UI_MESSAGE_STREAM_HEADER_NAME,
    UI_MESSAGE_STREAM_PROTOCOL,
    to_ui_message_stream,
)

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


class TurnRequest(BaseModel):
    """Turn request body (TEACH-07/08).

    ``message`` must be non-blank after stripping and, once trimmed, at most
    ``LEARNY_TEACHING_MESSAGE_MAX_CHARS`` chars (inclusive). Both raise a Pydantic
    validation error → 422 before the service runs; the validator returns the
    **trimmed** value, so the service receives a normalized message.
    """

    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def _message_bounds(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message must not be empty or whitespace-only")
        max_chars = get_settings().teaching_message_max_chars
        if len(trimmed) > max_chars:
            raise ValueError(f"message must be at most {max_chars} characters")
        return trimmed


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


@router.post(
    "/api/teaching-sessions/{session_id}/turns",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_teaching),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def post_teaching_turn(
    session_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[PostTeachingTurn, Depends(get_post_teaching_turn)],
    body: TurnRequest,
) -> TurnView:
    """Run and persist one cited teaching turn (201); 422/404/409/429/502 per ACs.

    ``PostTeachingTurn`` resolves the session + owner (missing/non-owner →
    ``TeachingSessionNotFound`` → 404), enforces readiness (``SourceNotReady`` →
    409) and the target's continued existence (``TeachingTargetGone`` → 409),
    retrieves target-scoped evidence, and either composes a grounded answer or the
    explicit not-found outcome; a generation failure surfaces as
    ``AnswerGenerationFailed`` → 502 with nothing persisted, and a turn-index race
    loses with ``TeachingTurnConflict`` → 409.
    """
    turn = service(user=user, session_id=session_id, message=body.message)
    return TurnView.from_turn(turn)


@router.post(
    "/api/teaching-sessions/{session_id}/turns/stream",
    response_class=EventSourceResponse,
    dependencies=[
        Depends(rate_limit_teaching),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def post_teaching_turn_stream(
    session_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[PostTeachingTurn, Depends(get_post_teaching_turn)],
    body: TurnRequest,
    response: Response,
):
    """Stream one cited teaching turn as UI Message Stream v1 SSE frames (GEN-14).

    The SSE sibling of :func:`post_teaching_turn`: identical request schema and
    auth/CSRF/Origin/rate-limit dependencies. ``PostTeachingTurn.stream`` runs all
    guards **eagerly** here, so ownership (404), readiness / target-gone (409),
    validation (422) and rate-limit (429) surface as the same plain HTTP errors as
    the JSON endpoint before any SSE byte is sent. The turn is persisted only on
    stream completion, so a mid-stream failure (rendered as a protocol ``error``
    part) or a client disconnect persists nothing (TEACH-13/17).
    """
    events = service.stream(user=user, session_id=session_id, message=body.message)
    response.headers[UI_MESSAGE_STREAM_HEADER_NAME] = UI_MESSAGE_STREAM_PROTOCOL
    return to_ui_message_stream(events)


@router.get("/api/sources/{source_id}/teaching-sessions")
def list_teaching_sessions(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListTeachingSessions, Depends(get_list_teaching_sessions)],
) -> list[SessionSummaryView]:
    """Return an owned source's sessions, newest first (200; 404 missing/non-owner)."""
    return [SessionSummaryView.from_summary(s) for s in service(user=user, source_id=source_id)]
