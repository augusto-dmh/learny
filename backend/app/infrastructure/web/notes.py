"""Notes + highlights router — capture, organize, and read notes (Cycle E).

Thin FastAPI adapter over the framework-free notes services (assembled in
``dependencies``). A signed-in owner creates whole-Markdown notes, lists/filters
them by tag, reads/edits/deletes one, reads a note's backlinks, and captures a
highlight from the reader (create a note + one book anchor atomically). Every note
path is one request-scoped transaction, so no commit-then-enqueue orchestration is
needed here (unlike the deck/ingestion start paths).

Application errors are translated to HTTP by the global handlers
(``NoteNotFound`` → 404, ``NoteBodyTooLong`` → 422, ``StaleCaptureTarget`` → 409,
``SourceNotFound`` → 404, ``CorpusNotFound`` → 404).

Contract (also consumed by the Next.js proxy):
- ``POST   /api/notes`` → 201 note; auth + CSRF/Origin + limit.
- ``GET    /api/notes`` → 200 note summaries (optional ``?tag=`` filter); auth.
- ``GET    /api/notes/{id}`` → 200 note detail; auth.
- ``PATCH  /api/notes/{id}`` → 200 updated note detail; auth + CSRF/Origin + limit.
- ``DELETE /api/notes/{id}`` → 204; auth + CSRF/Origin + limit.
- ``GET    /api/notes/{id}/backlinks`` → 200 inbound links; auth.
- ``POST   /api/sources/{source_id}/highlights`` → 201 note; auth + CSRF/Origin +
  limit.

NF-09 lists an optional capture payload alongside ``POST /api/notes``. The reader's
capture path is served by the dedicated ``POST /api/sources/{source_id}/highlights``
route (the ``CaptureHighlight`` use case), which carries the source in the path and
the selection payload in the body; ``POST /api/notes`` stays a plain note create
(``CreateNote``, whose signature has no capture fields), so capture is not duplicated
across two shapes. This matches the design's architecture diagram (CRUD vs capture).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from app.application.notes import (
    CaptureHighlight,
    DeleteNote,
    GetBacklinks,
    GetNote,
    ListNotes,
)
from app.application.reading import ListSourceHighlights
from app.domain.entities import (
    Backlink,
    NoteAnchor,
    NoteSummary,
    NoteView,
    SourceHighlight,
    User,
)
from app.domain.ports import NoteIndexEnqueuer
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    build_create_note,
    build_update_note,
    get_authenticated_user,
    get_capture_highlight,
    get_delete_note,
    get_get_backlinks,
    get_get_note,
    get_list_notes,
    get_list_source_highlights,
    get_note_index_enqueuer,
    get_note_uow,
)
from app.infrastructure.web.rate_limit import rate_limit_notes

router = APIRouter(tags=["notes"])

# Create/update commit in this UoW factory before the after-commit embed enqueue
# (AD-016), mirroring the ingestion/deck start paths; tests override both.
NoteUowFactory = Annotated[
    Callable[[], AbstractContextManager[Connection]], Depends(get_note_uow)
]
NoteEnqueuer = Annotated[NoteIndexEnqueuer, Depends(get_note_index_enqueuer)]


# --- Request bodies ------------------------------------------------------------


class NoteWriteRequest(BaseModel):
    """Create/update body (NF-05): title plus an optional Markdown body and tags.

    An empty body is allowed (a note may be just a title or, after capture, a bare
    quote card). Tags are normalized (lowercased/deduped) by the use case; the body
    cap is enforced there too (``NoteBodyTooLong`` → 422).
    """

    title: str
    body_markdown: str = ""
    tags: list[str] = Field(default_factory=list)


class CaptureRequest(BaseModel):
    """Highlight-capture body (NF-06): the selection payload plus the new note's fields.

    ``anchor`` addresses the reader section; ``quote_exact`` (+ 32-char
    ``quote_prefix``/``quote_suffix`` context) is the selection resolved server-side
    against the section's blocks. An empty ``body_markdown`` yields a bare highlight.
    """

    anchor: str
    quote_exact: str
    quote_prefix: str = ""
    quote_suffix: str = ""
    title: str
    body_markdown: str = ""
    tags: list[str] = Field(default_factory=list)


# --- Response views ------------------------------------------------------------


class NoteAnchorView(BaseModel):
    """A note's book citation (NF-10): the orphan-badge status + jump-back payload.

    Carries ``source_id``/``anchor``/``quote_exact`` so the reader can jump back to
    the passage (and re-place the highlight via the in-block offsets), plus the
    ``source_title`` snapshot and ``status`` so an orphaned anchor still renders from
    its quote after the source is gone.
    """

    id: UUID
    source_id: UUID
    source_title: str
    anchor: str
    section_path: list[str]
    block_ordinal: int | None
    start_offset: int | None
    end_offset: int | None
    quote_exact: str
    quote_prefix: str
    quote_suffix: str
    status: str

    @classmethod
    def from_anchor(cls, anchor: NoteAnchor) -> NoteAnchorView:
        return cls(
            id=anchor.id,
            source_id=anchor.source_id,
            source_title=anchor.source_title,
            anchor=anchor.anchor,
            section_path=list(anchor.section_path),
            block_ordinal=anchor.block_ordinal,
            start_offset=anchor.start_offset,
            end_offset=anchor.end_offset,
            quote_exact=anchor.quote_exact,
            quote_prefix=anchor.quote_prefix,
            quote_suffix=anchor.quote_suffix,
            status=anchor.status,
        )


class NoteDetailView(BaseModel):
    """The note-detail read model (NF-05/10): the note, its tags, and its anchors."""

    id: UUID
    title: str
    body_markdown: str
    tags: list[str]
    anchors: list[NoteAnchorView]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: NoteView) -> NoteDetailView:
        return cls(
            id=view.note.id,
            title=view.note.title,
            body_markdown=view.note.body_markdown,
            tags=list(view.tags),
            anchors=[NoteAnchorView.from_anchor(a) for a in view.anchors],
            created_at=view.note.created_at,
            updated_at=view.note.updated_at,
        )


class NoteSummaryView(BaseModel):
    """One row in the notes list (NF-13): the note with its tags and anchor statuses.

    ``anchor_statuses`` lets the list render active/stale/orphaned badges without
    loading the anchor payloads.
    """

    id: UUID
    title: str
    tags: list[str]
    anchor_statuses: list[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_summary(cls, summary: NoteSummary) -> NoteSummaryView:
        return cls(
            id=summary.note.id,
            title=summary.note.title,
            tags=list(summary.tags),
            anchor_statuses=list(summary.anchor_statuses),
            created_at=summary.note.created_at,
            updated_at=summary.note.updated_at,
        )


class BacklinkView(BaseModel):
    """One inbound wikilink for the backlinks panel (NF-10/13): the linking note."""

    note_id: UUID
    title: str

    @classmethod
    def from_backlink(cls, backlink: Backlink) -> BacklinkView:
        return cls(note_id=backlink.note_id, title=backlink.title)


class SourceHighlightView(BaseModel):
    """One of the caller's highlights on a source, for inline reader painting (RD-28).

    The owning ``note_id`` plus the anchor's quote-with-context and ``status`` — the
    reader paints ``active`` quotes and ignores stale/orphaned ones (RD-29). The
    origin note's ``note_title`` and a ``has_body`` flag let the margin rail label each
    entry and tell a bare highlight from an annotated one without a second request
    (CAP-19); the painter ignores both.
    """

    note_id: UUID
    anchor: str
    quote_exact: str
    quote_prefix: str
    quote_suffix: str
    status: str
    note_title: str
    has_body: bool

    @classmethod
    def from_highlight(cls, highlight: SourceHighlight) -> SourceHighlightView:
        return cls(
            note_id=highlight.note_id,
            anchor=highlight.anchor,
            quote_exact=highlight.quote_exact,
            quote_prefix=highlight.quote_prefix,
            quote_suffix=highlight.quote_suffix,
            status=highlight.status,
            note_title=highlight.note_title,
            has_body=highlight.has_body,
        )


# --- Endpoints -----------------------------------------------------------------


@router.post(
    "/api/notes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_notes),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def create_note(
    user: Annotated[User, Depends(get_authenticated_user)],
    uow_factory: NoteUowFactory,
    enqueuer: NoteEnqueuer,
    body: NoteWriteRequest,
) -> NoteDetailView:
    """Create a whole-Markdown note for the caller and derive its indexes (201).

    ``CreateNote`` validates the body cap (``NoteBodyTooLong`` → 422) then persists
    the note and rebuilds its wikilink/tag indexes in one committed UoW; the note is
    then embedded asynchronously (only when it has a body to embed, NL-01), enqueued
    after commit so the worker reads a durable row (AD-016).
    """
    with uow_factory() as conn:
        view = build_create_note(conn)(
            user=user, title=body.title, body_markdown=body.body_markdown, tags=body.tags
        )
    if body.body_markdown:
        enqueuer.enqueue_embed(view.note.id)
    return NoteDetailView.from_view(view)


@router.get("/api/notes")
def list_notes(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListNotes, Depends(get_list_notes)],
    tag: Annotated[str | None, Query()] = None,
) -> list[NoteSummaryView]:
    """Return the caller's notes (newest-edited first), optionally filtered by tag (200).

    ``tag`` is matched case-insensitively; every returned summary still lists all of
    its own tags.
    """
    summaries = service(user=user, tag=tag)
    return [NoteSummaryView.from_summary(s) for s in summaries]


@router.get("/api/notes/{note_id}")
def get_note(
    note_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[GetNote, Depends(get_get_note)],
) -> NoteDetailView:
    """Return an owned note's detail (200; 404).

    ``GetNote`` collapses a missing note and a non-owner to ``NoteNotFound`` → 404 so
    a note's existence is never disclosed.
    """
    return NoteDetailView.from_view(service(user=user, note_id=note_id))


@router.patch(
    "/api/notes/{note_id}",
    dependencies=[
        Depends(rate_limit_notes),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def update_note(
    note_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    uow_factory: NoteUowFactory,
    enqueuer: NoteEnqueuer,
    body: NoteWriteRequest,
) -> NoteDetailView:
    """Update an owned note and rewrite its derived indexes (200; 404/422).

    Missing/non-owner → ``NoteNotFound`` → 404; over-cap body → ``NoteBodyTooLong`` →
    422. The wikilink/tag indexes are rebuilt from the new body in one committed UoW;
    the note is re-embedded asynchronously only when its body actually changed (a
    title/tags-only edit enqueues nothing, NL-01), after commit (AD-016).
    """
    with uow_factory() as conn:
        view, body_changed = build_update_note(conn)(
            user=user,
            note_id=note_id,
            title=body.title,
            body_markdown=body.body_markdown,
            tags=body.tags,
        )
    if body_changed:
        enqueuer.enqueue_embed(note_id)
    return NoteDetailView.from_view(view)


@router.delete(
    "/api/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(rate_limit_notes),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def delete_note(
    note_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[DeleteNote, Depends(get_delete_note)],
) -> Response:
    """Delete an owned note (204; 404).

    Its anchors/tags/links cascade and inbound links from other notes are SET NULL;
    missing/non-owner → ``NoteNotFound`` → 404.
    """
    service(user=user, note_id=note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/notes/{note_id}/backlinks")
def get_note_backlinks(
    note_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[GetBacklinks, Depends(get_get_backlinks)],
) -> list[BacklinkView]:
    """Return the notes whose wikilinks resolve to an owned note (200; 404).

    Owner-scoped like ``GetNote`` (missing/non-owner → ``NoteNotFound`` → 404).
    """
    backlinks = service(user=user, note_id=note_id)
    return [BacklinkView.from_backlink(b) for b in backlinks]


@router.post(
    "/api/sources/{source_id}/highlights",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(rate_limit_notes),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def capture_highlight(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[CaptureHighlight, Depends(get_capture_highlight)],
    body: CaptureRequest,
) -> NoteDetailView:
    """Capture a highlight from the reader: create a note + one anchor atomically (201).

    ``CaptureHighlight`` authorizes the source (missing/non-owner → ``SourceNotFound``
    → 404), resolves the addressed section (unknown anchor → ``CorpusNotFound`` → 404),
    and binds the selection against its blocks — if the served evidence no longer
    matches (a mid-flight re-ingest) nothing is persisted and ``StaleCaptureTarget`` →
    409. Over-cap body → ``NoteBodyTooLong`` → 422.
    """
    view = service(
        user=user,
        source_id=source_id,
        anchor=body.anchor,
        quote_exact=body.quote_exact,
        quote_prefix=body.quote_prefix,
        quote_suffix=body.quote_suffix,
        title=body.title,
        body_markdown=body.body_markdown,
        tags=body.tags,
    )
    return NoteDetailView.from_view(view)


@router.get("/api/sources/{source_id}/highlights")
def get_source_highlights(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListSourceHighlights, Depends(get_list_source_highlights)],
) -> list[SourceHighlightView]:
    """Return the caller's highlights on an owned source (200); 404 missing/non-owner.

    Owner-scoped like the other source reads (``SourceNotFound`` → 404); every status is
    returned so the reader paints the ``active`` quotes and lists the rest.
    """
    return [
        SourceHighlightView.from_highlight(h)
        for h in service(user=user, source_id=source_id)
    ]
