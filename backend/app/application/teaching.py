"""Compatibility layer for the pre-unification teaching endpoints (ADR-0029).

A teaching session *is* a conversation: one scoped to a single section, taught turn
by turn. The aggregate and its mechanics now live in
``app/application/conversations.py``, so nothing here orchestrates retrieval,
generation, grounding, or persistence — these adapters only translate the old
vocabulary (session, target anchor) into the unified services, and translate their
errors back into the wording the old panel has always received. They exist so this
release is invisible to the current UI and are deleted with the legacy endpoints
when it re-points at ``/api/conversations`` (ADR-0029's retirement plan).

Framework-free (ADR-0007/0009): no FastAPI / SQLAlchemy / provider-SDK type
crosses this boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from app.application.conversations import (
    PostConversationTurn,
    ReadConversation,
    StartConversation,
)
from app.application.errors import (
    ConversationNotFound,
    ConversationTargetUnavailable,
    InvalidConversationScope,
    SourceNotReady,
)
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.application.streaming import TurnStreamEvent
from app.domain.entities import (
    MODE_TEACH,
    Conversation,
    ConversationSummary,
    ConversationTurn,
    User,
)
from app.domain.ports import ConversationRepository, SourceRepository


@contextmanager
def _teaching_wording() -> Iterator[None]:
    """Re-raise the unified services' errors with the legacy details.

    The status codes are identical either way (the global handlers map the error
    types, not the messages); what would change without this is the ``detail`` text
    a client reads, which is part of the frozen wire. Each error keeps its type, so
    the mapping is invisible above the message.

    Why the wording lives here while its sibling — the scoped-status collapse — lives
    in ``app/infrastructure/web/legacy_status.py``: a message rides the error's own
    type to the global handler, so it is authored where the error is raised; a value
    the router chooses per response is projected at the transport edge. The rule is
    stated once, in that module's docstring. Both halves are deleted together.
    """
    try:
        yield
    except ConversationNotFound as exc:
        raise ConversationNotFound("Teaching session not found.") from exc
    except SourceNotReady as exc:
        raise SourceNotReady("Source is not ready for teaching.") from exc
    except InvalidConversationScope as exc:
        raise InvalidConversationScope("Target does not exist in this source.") from exc
    except ConversationTargetUnavailable as exc:
        raise ConversationTargetUnavailable(
            "The teaching target no longer exists; start a new session."
        ) from exc


class StartTeachingSession:
    """Start a session as a conversation scoped to exactly its target (TEACH-01..04).

    The target anchor becomes the whole scope, so retrieval sees the target subtree
    and nothing else; the title defaults to the target's title (the unified default
    for a scoped conversation) and notes stay off, which is teaching's standing
    choice (AD-147). Ownership, readiness, and anchor resolution are the unified
    service's guards — a missing/unowned source is still a 404, a not-ready source a
    409, and an anchor that resolves to no live section a 422.
    """

    def __init__(self, *, start: StartConversation) -> None:
        self._start = start

    def __call__(self, *, user: User, source_id: UUID, target_anchor: str) -> Conversation:
        with _teaching_wording():
            return self._start(
                user=user,
                source_id=source_id,
                scope_anchors=(target_anchor,),
                include_notes=False,
            )


class ReadTeachingSession:
    """Return an owned session with its full ordered conversation (TEACH-05/06/20).

    A conversation with no teach target is not a teaching session, so it reads as
    absent here exactly like an unowned one — the old panel's world contains only
    targeted sessions, and its views require the target snapshot.

    This is one half of a single rule with two homes: the per-source list applies it
    in SQL (``ConversationRepository.list_for_source_with_target``, where it stays so
    the legacy ``created_at`` ordering and its query remain one deletable unit), and
    the turn adapter below applies it to writes. All three retire together with the
    panel.
    """

    def __init__(self, *, read: ReadConversation) -> None:
        self._read = read

    def __call__(
        self, *, user: User, session_id: UUID
    ) -> tuple[Conversation, list[ConversationTurn]]:
        with _teaching_wording():
            session, turns = self._read(user=user, conversation_id=session_id)
        if session.teach_target is None:
            raise ConversationNotFound("Teaching session not found.")
        return session, turns


class ListTeachingSessions:
    """Return an owned source's teaching sessions, newest first (TEACH-21).

    Source-rooted rather than user-rooted (a missing or unowned source is a 404, not
    an empty list), and filtered to conversations that carry a teach target, so the
    conversations a question created never surface in the old panel (CONV-23).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        conversations: ConversationRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._conversations = conversations
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID) -> list[ConversationSummary]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        return self._conversations.list_for_source_with_target(source_id)


class PostTeachingTurn:
    """Run one teach-mode turn in the session's conversation (TEACH-07..17, 19, 24).

    Every guard, the scope expansion, the bounded history, the grounding guard, and
    persist-after-grounding belong to the unified turn service; this only fixes the
    mode to ``teach``, forwards the request's notes choice as a per-request override
    (never changing what the conversation stores, AD-147), and keeps this surface's
    rule that a target-less conversation is not a session at all — see
    :meth:`_targetless_is_absent`.
    """

    def __init__(
        self, *, post: PostConversationTurn, conversations: ConversationRepository
    ) -> None:
        self._post = post
        self._conversations = conversations

    def __call__(
        self,
        *,
        user: User,
        session_id: UUID,
        message: str,
        include_notes: bool = False,
    ) -> ConversationTurn:
        with _teaching_wording(), self._targetless_is_absent(session_id):
            return self._post(
                user=user,
                conversation_id=session_id,
                message=message,
                mode=MODE_TEACH,
                include_notes_override=include_notes,
            )

    def stream(
        self,
        *,
        user: User,
        session_id: UUID,
        message: str,
        include_notes: bool = False,
    ) -> Iterator[TurnStreamEvent]:
        """Stream one teach-mode turn; the guards still run before this returns."""
        with _teaching_wording(), self._targetless_is_absent(session_id):
            return self._post.stream(
                user=user,
                conversation_id=session_id,
                message=message,
                mode=MODE_TEACH,
                include_notes_override=include_notes,
            )

    @contextmanager
    def _targetless_is_absent(self, session_id: UUID) -> Iterator[None]:
        """Report a turn against a target-less conversation as an absent session.

        The unified surface answers 409 for both shapes of "cannot teach this"
        (I-CM-7). Here they are different answers: a session whose target a re-ingest
        dropped existed and is gone (409), while a conversation that never had a
        target — every question asked since ADR-0029 — was never a teaching session,
        and this surface's other two reads already say so with a 404. Without this
        the old panel would report a 409 about "the teaching target" for an id its
        own read reports as missing.

        The extra read happens only on the failure path, and it discloses nothing:
        an unowned conversation is a 404 from the unified service either way.
        """
        try:
            yield
        except ConversationTargetUnavailable as exc:
            conversation = self._conversations.get_by_id(session_id)
            if conversation is not None and conversation.teach_target is None:
                raise ConversationNotFound("Teaching session not found.") from exc
            raise
