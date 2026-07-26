"""Compatibility layer for the pre-unification question endpoints (ADR-0029).

Asking a question is starting a whole-book conversation and taking its first
answer-mode turn, so from this release a question is no longer thrown away when the
page reloads: each ask persists a conversation titled after the question (AD-195),
and it shows up in the unified list like any other. The answer path itself —
retrieval, generation, the grounding guard, persistence — belongs to
``app/application/conversations.py``; this only translates between the old
vocabulary and the unified services, and projects the persisted turn back into the
``QuestionAnswer`` the legacy endpoint has always returned.

An ask that fails leaves nothing behind: the pre-cycle path persisted nothing on
failure, and a conversation whose only turn never completed is not a conversation a
reader would want in their list, so a failure discards it (see :meth:`AskQuestion.
_discard`). Deleted with the legacy endpoints when the UI moves to
``/api/conversations`` (ADR-0029's retirement plan). Framework-free
(ADR-0007/0009).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from app.application.conversations import PostConversationTurn, StartConversation
from app.application.errors import SourceNotReady
from app.application.streaming import (
    AskStreamEvent,
    StreamAnswer,
    StreamTurn,
    TurnStreamEvent,
)
from app.domain.entities import (
    MODE_ANSWER,
    Conversation,
    ConversationTurn,
    QuestionAnswer,
    User,
)
from app.domain.ports import ConversationRepository

logger = logging.getLogger(__name__)

# How much of the question becomes the conversation's title (AD-195). A hard
# character cut, deliberately not a word boundary: the reader recognizes their own
# question from its opening either way, and a rule with no special cases is a rule
# that cannot surprise them. The question arrives trimmed from the web layer.
TITLE_MAX_CHARS = 80


@contextmanager
def _questions_wording() -> Iterator[None]:
    """Re-raise the unified readiness error with the detail this wire has always sent.

    The status code is identical either way (the global handlers map the error type,
    not the message); what would change without this is the ``detail`` a client
    reads, which is part of the frozen wire. Readiness is the only error the ask
    path can reach whose wording differs: a whole-book conversation has no scope to
    reject and no target to lose.

    Wording lives with the error it re-raises rather than beside the scoped-status
    collapse in ``app/infrastructure/web/legacy_status.py``; that module's docstring
    states the rule for both halves of the shim.
    """
    try:
        yield
    except SourceNotReady as exc:
        raise SourceNotReady("Source is not ready for questions.") from exc


class AskQuestion:
    """Answer a question as the first turn of a new whole-book conversation.

    The scope is empty — a question is asked of the whole book — so retrieval sees
    the entire source and a miss is reported as ``not_found_in_source``, exactly as
    before. ``include_notes`` is the caller's choice (the web layer defaults it on,
    AD-147) and is stored on the conversation, so a follow-up turn on the unified
    surface inherits what the reader asked for.

    Ownership and readiness are the start service's guards, and they run before
    anything is created: a missing/unowned source is still a 404 and a not-ready one
    a 409, with no conversation written. Every later failure — a generation failure,
    a stream that dies mid-flight, a consumer that disconnects — discards the
    conversation, so the endpoint keeps its pre-cycle promise that a failed ask
    leaves no trace.
    """

    def __init__(
        self,
        *,
        start: StartConversation,
        post: PostConversationTurn,
        conversations: ConversationRepository,
    ) -> None:
        self._start = start
        self._post = post
        self._conversations = conversations

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID,
        question: str,
        include_notes: bool = False,
    ) -> QuestionAnswer:
        conversation = self._open(
            user=user, source_id=source_id, question=question, include_notes=include_notes
        )
        try:
            with _questions_wording():
                turn = self._post(
                    user=user,
                    conversation_id=conversation.id,
                    message=question,
                    mode=MODE_ANSWER,
                )
        except BaseException:
            self._discard(conversation)
            raise
        return _as_answer(turn)

    def stream(
        self,
        *,
        user: User,
        source_id: UUID,
        question: str,
        include_notes: bool = False,
    ) -> Iterator[AskStreamEvent]:
        """Answer incrementally: the same guards and grounding as ``__call__``, streamed.

        The conversation is opened and every turn guard runs **eagerly** (before this
        returns), so ownership (404) and readiness (409) still surface as plain HTTP
        errors before any SSE byte; only then is the frame source returned.
        """
        conversation = self._open(
            user=user, source_id=source_id, question=question, include_notes=include_notes
        )
        try:
            with _questions_wording():
                events = self._post.stream(
                    user=user,
                    conversation_id=conversation.id,
                    message=question,
                    mode=MODE_ANSWER,
                )
        except BaseException:
            self._discard(conversation)
            raise
        return self._answer_stream(conversation, events)

    def _answer_stream(
        self, conversation: Conversation, events: Iterator[TurnStreamEvent]
    ) -> Iterator[AskStreamEvent]:
        """Project the turn stream onto the legacy answer stream, discarding on failure.

        The turn is persisted by the unified service only once the generation stream
        completes, so anything that ends this generator before the terminal event —
        a provider failure, a consumer disconnect — means there is no answer, and the
        conversation opened for it goes with it.
        """
        answered = False
        try:
            for event in events:
                if isinstance(event, StreamTurn):
                    answered = True
                    yield StreamAnswer(_as_answer(event.turn))
                else:
                    yield event
        finally:
            if not answered:
                self._discard(conversation)

    def _open(
        self, *, user: User, source_id: UUID, question: str, include_notes: bool
    ) -> Conversation:
        with _questions_wording():
            return self._start(
                user=user,
                source_id=source_id,
                scope_anchors=(),
                include_notes=include_notes,
                title=question[:TITLE_MAX_CHARS],
            )

    def _discard(self, conversation: Conversation) -> None:
        """Remove a conversation whose one turn never landed (nothing else can have)."""
        try:
            self._conversations.delete(conversation.id)
        except Exception:  # noqa: BLE001 - best effort; the original failure is the one to raise
            # The failure that brought us here is the one worth raising, and inside a
            # request this write is being rolled back around us anyway. But the
            # streaming path's cleanup can run after the response began and after the
            # request-scoped connection went back — exactly when the rollback is not
            # guaranteed to cover it — so one content-free line makes the leftover
            # conversation explainable instead of mysterious.
            logger.warning("ask discard failed conversation_id=%s", conversation.id)


def _as_answer(turn: ConversationTurn) -> QuestionAnswer:
    """Project the persisted answer turn onto the legacy result shape."""
    return QuestionAnswer(
        status=turn.answer_status,
        text=turn.answer_text,
        citations=turn.citations,
        evidence_count=turn.evidence_count,
        model=turn.model,
    )
