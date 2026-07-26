"""Conversations router — the unified grounded-conversation surface (ADR-0029).

Thin FastAPI adapter over the unified services in ``app.application.conversations``
(assembled in ``dependencies``). One resource covers what the Ask and Teach panels
split between them: a conversation is a scope (the section anchors retrieval may
see, empty meaning the whole book) plus per-turn modes, and it can be started,
listed across every source the caller owns, read, renamed, deleted, and continued
with a turn — buffered or streamed.

The handlers own input validation (422) and let application errors propagate to the
global handlers (``SourceNotFound``/``ConversationNotFound`` → 404,
``SourceNotReady``/``ConversationTargetUnavailable``/``ConversationTurnConflict`` →
409, ``InvalidConversationScope``/``InvalidConversationTitle`` → 422,
``AnswerGenerationFailed`` → 502), exactly as the legacy routers do.

Contract (also consumed by the Next.js proxy):
- ``POST   /api/conversations`` ``{source_id, scope_anchors?, include_notes, title?}``
  → 201 conversation. ``include_notes`` has **no default**: the notes choice is
  explicit per conversation (ADR-0029), so an omitted flag is a 422 (CONV-15).
- ``GET    /api/conversations[?source_id=]`` → 200 summaries, newest activity first
  (CONV-16).
- ``GET    /api/conversations/{id}`` → 200 conversation + ordered cited turns
  (CONV-17).
- ``PATCH  /api/conversations/{id}`` ``{title}`` → 200 renamed conversation (CONV-18).
- ``DELETE /api/conversations/{id}`` → 204 (CONV-19).
- ``POST   /api/conversations/{id}/turns`` ``{message, mode}`` → 201 cited turn
  (CONV-20).
- ``POST   /api/conversations/{id}/turns/stream`` → 200 UI Message Stream v1 SSE
  (CONV-21).

Every mutating route carries auth + Origin/CSRF enforcement and the single
``rate_limit_conversations`` policy that governs the whole unified surface
(CONV-22); the reads carry auth alone, as elsewhere.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from app.application.conversations import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    TITLE_MAX_CHARS,
    DeleteConversation,
    ListConversations,
    PostConversationTurn,
    ReadConversation,
    RenameConversation,
    StartConversation,
)
from app.core.config import get_settings
from app.domain.entities import (
    MODE_ANSWER,
    MODE_TEACH,
    Conversation,
    ConversationSummary,
    ConversationTurn,
    User,
)
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_delete_conversation,
    get_list_conversations,
    get_post_conversation_turn,
    get_read_conversation,
    get_rename_conversation,
    get_start_conversation,
)
from app.infrastructure.web.rate_limit import rate_limit_conversations
from app.infrastructure.web.retrieval import EvidenceView
from app.infrastructure.web.ui_message_stream import to_sse_response

router = APIRouter(tags=["conversations"])

#: The turn modes a client may ask for, named by the domain so the wire vocabulary
#: and the dispatch inside the service can never drift apart.
CONVERSATION_MODES = (MODE_ANSWER, MODE_TEACH)


# --- Request bodies ------------------------------------------------------------


def _bounded_title(value: str) -> str:
    """Trim a title and enforce the shared 1..``TITLE_MAX_CHARS`` bound (CONV-18).

    Trimming first means trailing whitespace never costs a reader their title, and
    the bound is the application's constant rather than a second number that could
    drift away from it.
    """
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("title must not be empty or whitespace-only")
    if len(trimmed) > TITLE_MAX_CHARS:
        raise ValueError(f"title must be at most {TITLE_MAX_CHARS} characters")
    return trimmed


def _bounded_scope(anchors: list[str]) -> list[str]:
    """Enforce the server's bounds on a requested scope (CONV-15).

    A scope is the one field on this surface whose size the client chooses, and it
    is not a per-request cost: every anchor is resolved against the corpus when the
    conversation starts *and re-expanded on every turn for as long as it lives*, and
    the list is stored. So it is bounded like ``message`` and ``title`` are — by
    server-controlled settings rather than literals — in both directions: how many
    anchors a conversation may name, and how long each may be.
    """
    settings = get_settings()
    max_anchors = settings.conversation_scope_max_anchors
    if len(anchors) > max_anchors:
        raise ValueError(f"scope_anchors must contain at most {max_anchors} anchors")
    max_chars = settings.conversation_scope_anchor_max_chars
    if any(len(anchor) > max_chars for anchor in anchors):
        raise ValueError(f"each scope anchor must be at most {max_chars} characters")
    return anchors


class StartConversationRequest(BaseModel):
    """Start-conversation request body (CONV-15).

    ``include_notes`` is deliberately declared **without a default**: ADR-0029 makes
    the notes choice explicit per conversation, so a client that omits it is asking
    the server to guess and gets a 422 instead. ``scope_anchors`` defaults to the
    empty list, which is the one spelling of "the whole book"; its size and the
    length of each anchor are bounded here (see :func:`_bounded_scope`), while
    whether each anchor resolves to a live section is the service's decision (an
    unresolvable anchor → ``InvalidConversationScope`` → 422). ``title`` is optional
    — absent or blank means "name it for me" and the service applies its default.
    """

    source_id: UUID
    scope_anchors: list[str] = Field(default_factory=list)
    include_notes: bool
    title: str | None = None

    @field_validator("scope_anchors")
    @classmethod
    def _scope_bounds(cls, value: list[str]) -> list[str]:
        return _bounded_scope(value)

    @field_validator("title")
    @classmethod
    def _title_bounds(cls, value: str | None) -> str | None:
        # A blank title is "not given" on this path, so it falls through to the
        # service's default rather than being rejected.
        if value is None or not value.strip():
            return None
        return _bounded_title(value)


class RenameConversationRequest(BaseModel):
    """Rename request body (CONV-18).

    Unlike the start path, a blank title here is a rejected request: the caller
    asked for a specific title. The validator returns the **trimmed** value, so the
    service stores what the reader will see.
    """

    title: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _title_bounds(cls, value: str) -> str:
        return _bounded_title(value)


class TurnRequest(BaseModel):
    """Turn request body (CONV-20).

    ``message`` must be non-blank after stripping and, once trimmed, at most
    ``LEARNY_CONVERSATION_MESSAGE_MAX_CHARS`` chars (inclusive); the validator
    returns the **trimmed** value, so the service receives a normalized message.
    ``mode`` must name one of the two turn modes — an unknown mode is a 422 before
    the service runs, so the service's own guard is never the thing a client meets.
    """

    message: str = Field(min_length=1)
    mode: str

    @field_validator("message")
    @classmethod
    def _message_bounds(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message must not be empty or whitespace-only")
        max_chars = get_settings().conversation_message_max_chars
        if len(trimmed) > max_chars:
            raise ValueError(f"message must be at most {max_chars} characters")
        return trimmed

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, value: str) -> str:
        if value not in CONVERSATION_MODES:
            raise ValueError(f"mode must be one of: {', '.join(CONVERSATION_MODES)}")
        return value


# --- Response views ------------------------------------------------------------


class ConversationView(BaseModel):
    """One conversation as the client sees it (CONV-15/18).

    ``scope_anchors`` is echoed exactly as stored (order preserved) and
    ``include_notes`` is the choice the conversation was created with — together
    they are the promise the turn path keeps.
    """

    id: UUID
    source_id: UUID
    title: str
    scope_anchors: list[str]
    include_notes: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> ConversationView:
        return cls(
            id=conversation.id,
            source_id=conversation.source_id,
            title=conversation.title,
            scope_anchors=list(conversation.scope_anchors),
            include_notes=conversation.include_notes,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationTurnView(BaseModel):
    """One grounded turn (CONV-17/20).

    ``mode`` names how the turn was answered (``answer`` or ``teach``);
    ``answer_status`` is ``answered``, ``not_found_in_scope`` (a scoped conversation
    came up short) or ``not_found_in_source`` (a whole-book one did), with ``text``
    and ``citations`` empty for both not-found outcomes. ``citations`` reuses the
    retrieval endpoint's ``EvidenceView`` citation-only projection.
    """

    turn_index: int
    message: str
    mode: str
    answer_status: str
    text: str
    citations: list[EvidenceView]
    evidence_count: int
    model: str
    created_at: datetime

    @classmethod
    def from_turn(cls, turn: ConversationTurn) -> ConversationTurnView:
        return cls(
            turn_index=turn.turn_index,
            message=turn.message,
            mode=turn.mode,
            answer_status=turn.answer_status,
            text=turn.answer_text,
            citations=[EvidenceView.from_evidence(c) for c in turn.citations],
            evidence_count=turn.evidence_count,
            model=turn.model,
            created_at=turn.created_at,
        )


class ConversationDetailView(ConversationView):
    """A conversation with its full ordered conversation history (CONV-17).

    ``turns`` are ordered by ``turn_index`` ascending, each with its citation
    snapshots — so history renders intact after re-ingestion (I-CM-1).
    """

    turns: list[ConversationTurnView]

    @classmethod
    def from_conversation_turns(
        cls, conversation: Conversation, turns: list[ConversationTurn]
    ) -> ConversationDetailView:
        return cls(
            **ConversationView.from_conversation(conversation).model_dump(),
            turns=[ConversationTurnView.from_turn(t) for t in turns],
        )


class ConversationSummaryView(BaseModel):
    """A list row for the global conversation list (CONV-16).

    ``source_title`` rides along because the list spans every source the caller
    owns: a row that named only the conversation would not say which book it is
    about.
    """

    id: UUID
    source_id: UUID
    source_title: str
    title: str
    scope_anchors: list[str]
    include_notes: bool
    turn_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_summary(cls, summary: ConversationSummary) -> ConversationSummaryView:
        conversation = summary.conversation
        return cls(
            id=conversation.id,
            source_id=conversation.source_id,
            source_title=summary.source_title,
            title=conversation.title,
            scope_anchors=list(conversation.scope_anchors),
            include_notes=conversation.include_notes,
            turn_count=summary.turn_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


# --- Endpoints -----------------------------------------------------------------


@router.post(
    "/api/conversations",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_conversations),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def start_conversation(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[StartConversation, Depends(get_start_conversation)],
    body: StartConversationRequest,
) -> ConversationView:
    """Start a conversation over an owned ready source (201).

    ``StartConversation`` authorizes ownership (missing/non-owner → ``SourceNotFound``
    → 404, so an unowned source is indistinguishable from one that never existed),
    enforces readiness (``SourceNotReady`` → 409), and resolves every scope anchor —
    one that addresses nothing fails the whole start with ``InvalidConversationScope``
    → 422, having created nothing.
    """
    conversation = service(
        user=user,
        source_id=body.source_id,
        scope_anchors=body.scope_anchors,
        include_notes=body.include_notes,
        title=body.title,
    )
    return ConversationView.from_conversation(conversation)


@router.get("/api/conversations")
def list_conversations(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListConversations, Depends(get_list_conversations)],
    source_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationSummaryView]:
    """Return a page of the caller's conversations, newest activity first (200).

    Spans every source the caller owns unless ``source_id`` narrows it. Ownership is
    the repository's join through ``sources``, so narrowing by a source the caller
    does not own returns an empty list rather than disclosing anything.

    The answer is always one page of the ``updated_at DESC, id DESC`` order:
    ``limit`` defaults to 20 and is capped at 100 by Pydantic — outside those bounds
    → 422 — and ``offset`` walks the same order, an offset past the end being an
    empty page. That order is total, so a caller paging through it sees every
    conversation exactly once.
    """
    summaries = service(user=user, source_id=source_id, limit=limit, offset=offset)
    return [ConversationSummaryView.from_summary(s) for s in summaries]


@router.get("/api/conversations/{conversation_id}")
def read_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ReadConversation, Depends(get_read_conversation)],
) -> ConversationDetailView:
    """Return an owned conversation with its ordered cited turns (200; 404).

    A missing conversation and another user's conversation produce the identical
    404 body — existence is never disclosed (I-CM-6).
    """
    conversation, turns = service(user=user, conversation_id=conversation_id)
    return ConversationDetailView.from_conversation_turns(conversation, turns)


@router.patch(
    "/api/conversations/{conversation_id}",
    dependencies=[
        Depends(rate_limit_conversations),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def rename_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[RenameConversation, Depends(get_rename_conversation)],
    body: RenameConversationRequest,
) -> ConversationView:
    """Retitle an owned conversation and bump its activity (200; 404/422)."""
    return ConversationView.from_conversation(
        service(user=user, conversation_id=conversation_id, title=body.title)
    )


@router.delete(
    "/api/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(rate_limit_conversations),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def delete_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[DeleteConversation, Depends(get_delete_conversation)],
) -> Response:
    """Delete an owned conversation with its turns and citations (204; 404).

    A second delete reports absence like any other missing conversation.
    """
    service(user=user, conversation_id=conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/conversations/{conversation_id}/turns",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_conversations),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def post_conversation_turn(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[PostConversationTurn, Depends(get_post_conversation_turn)],
    body: TurnRequest,
) -> ConversationTurnView:
    """Run and persist one grounded turn (201); 404/409/422/429/502 per the ACs.

    ``PostConversationTurn`` resolves the conversation + owner (missing/non-owner →
    ``ConversationNotFound`` → 404), enforces readiness (``SourceNotReady`` → 409)
    and — for a teach turn — that the conversation still has a resolvable target
    (``ConversationTargetUnavailable`` → 409), retrieves evidence within the
    conversation's scope, and either composes a grounded answer or the explicit
    not-found outcome. A generation failure surfaces as ``AnswerGenerationFailed`` →
    502 with nothing persisted, and a turn-index race loses with
    ``ConversationTurnConflict`` → 409.
    """
    turn = service(
        user=user,
        conversation_id=conversation_id,
        message=body.message,
        mode=body.mode,
    )
    return ConversationTurnView.from_turn(turn)


@router.post(
    "/api/conversations/{conversation_id}/turns/stream",
    dependencies=[
        Depends(rate_limit_conversations),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def post_conversation_turn_stream(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[PostConversationTurn, Depends(get_post_conversation_turn)],
    body: TurnRequest,
):
    """Stream one grounded turn as UI Message Stream v1 SSE frames (CONV-21).

    The SSE sibling of :func:`post_conversation_turn`: identical request schema and
    auth/CSRF/Origin/rate-limit dependencies. ``PostConversationTurn.stream`` runs
    all guards **eagerly** here, so ownership (404), readiness / target-gone (409),
    validation (422) and rate-limit (429) surface as the same plain HTTP errors as
    the JSON endpoint before any SSE byte is sent. The turn is persisted only on
    stream completion, so a mid-stream failure (rendered as a protocol ``error``
    part) or a client disconnect persists nothing. The handler stays synchronous and
    returns the response instance so the frame generator runs in the threadpool —
    see the contract on ``to_sse_response``.
    """
    events = service.stream(
        user=user,
        conversation_id=conversation_id,
        message=body.message,
        mode=body.mode,
    )
    return to_sse_response(events)
