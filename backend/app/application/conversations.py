"""Unified grounded-conversation use-case services (ADR-0029).

One conversation is one grounded exchange about a book, defined by two axes: its
*scope* (the section anchors retrieval may see — empty means the whole book) and
each turn's *mode* (``answer`` replies as cited Q&A, ``teach`` as structured
teaching against the conversation's target section). These services generalize the
teaching-session mechanics that proved out in ``app/application/teaching.py``:
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
from collections.abc import Callable, Sequence
from uuid import UUID

from app.application.errors import (
    ConversationNotFound,
    InvalidConversationScope,
    InvalidConversationTitle,
    NotAuthorized,
    SourceNotReady,
)
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import SOURCE_STATUS_READY, authorized_source
from app.domain.entities import (
    Conversation,
    ConversationSummary,
    ConversationTurn,
    Source,
    StructureSection,
    User,
)
from app.domain.ports import (
    Clock,
    ConversationRepository,
    ConversationTurnRepository,
    CorpusRepository,
    SourceRepository,
)

logger = logging.getLogger(__name__)

# The longest title a conversation may carry (CONV-08). Titles are trimmed first,
# so trailing whitespace never costs a reader their title. The web layer declares
# the same bound on its request models; this is the enforcement.
TITLE_MAX_CHARS = 200


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
    enforce. The scope is stored exactly as given (order preserved, duplicates
    kept); expansion is a per-turn concern.

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
        scope = tuple(scope_anchors)
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
        head: StructureSection | None = None
        for anchor in scope:
            section = resolve_section(
                anchor, by_anchor=by_anchor, corpus=self._corpus, source_id=source_id
            )
            if section is None:
                raise InvalidConversationScope("Scope does not exist in this source.")
            if head is None:
                head = section
        return head

    @staticmethod
    def _default_title(head: StructureSection | None, source: Source) -> str:
        """Name a conversation after what it is about: its section, else the book."""
        if head is not None and head.title:
            return head.title
        return source.title


class ListConversations:
    """Return the caller's conversations, newest activity first (CONV-06).

    Spans every source the caller owns unless ``source_id`` narrows it. Ownership
    is the repository's join through ``sources`` (AD-014), so another user's
    conversations are unreachable rather than filtered afterwards — narrowing by a
    source the caller does not own yields an empty list, disclosing nothing.
    """

    def __init__(
        self,
        *,
        conversations: ConversationRepository,
    ) -> None:
        self._conversations = conversations

    def __call__(self, *, user: User, source_id: UUID | None = None) -> list[ConversationSummary]:
        return self._conversations.list_for_user(user.id, source_id)


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
