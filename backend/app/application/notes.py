"""Notes use-case services (RFC-003 Cycle E; ADR-0026 §2, design §Components).

Framework-free orchestration of the notes aggregate: create/update/delete/get/list
of whole-Markdown notes and highlight capture from the reader. Nothing here imports
FastAPI, SQLAlchemy, or Celery (ADR-007/009); the web layer (Phase C) owns the
per-request transaction so a note and its anchor are created atomically.

Two derived indexes are rebuilt from a note's body on every save (NF-05): the
``[[wikilink]]`` backlink index (title-matched case-insensitively against the user's
own notes) and the explicit tag set (lowercase-normalized, unique per user). Owner
scoping is identical to sources/quiz — a non-owner read collapses to ``NoteNotFound``
so a note's existence is never disclosed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from uuid import UUID

from app.application.anchoring import AnchorBlock, resolve
from app.application.errors import (
    CorpusNotFound,
    NoteBodyTooLong,
    NoteNotFound,
    StaleCaptureTarget,
)
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.domain.entities import (
    DerivedNoteLink,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    NoteSummary,
    NoteView,
    User,
)
from app.domain.ports import (
    Clock,
    CorpusRepository,
    MarkupConverterPort,
    NoteRepository,
    SourceRepository,
)

# The wikilink token: the inner text between ``[[`` and the next ``]]`` (D-4).
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def _parse_wikilinks(body: str) -> list[str]:
    """Return the note body's ``[[...]]`` targets, trimmed and deduped case-insensitively.

    First-seen casing is preserved for the stored ``target_text`` so a broken link still
    renders as the author wrote it; blank targets are dropped.
    """
    seen: set[str] = set()
    targets: list[str] = []
    for raw in _WIKILINK.findall(body):
        text = raw.strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        targets.append(text)
    return targets


def _normalize_tags(tags: Sequence[str]) -> list[str]:
    """Lowercase, trim, drop blanks, and dedupe tag names, order preserved (edge case)."""
    seen: set[str] = set()
    names: list[str] = []
    for tag in tags:
        name = tag.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _validate_body(body_markdown: str, max_chars: int) -> None:
    """Raise :class:`NoteBodyTooLong` when the body exceeds the cap (NF-04)."""
    if len(body_markdown) > max_chars:
        raise NoteBodyTooLong("Note body is too long.")


def _owned_note(notes: NoteRepository, user: User, note_id: UUID) -> Note:
    """Return the caller's note or raise ``NoteNotFound`` (404, no disclosure).

    A missing note and a non-owner collapse to the same error, mirroring
    ``authorized_source``.
    """
    note = notes.get_by_id(note_id)
    if note is None or note.user_id != user.id:
        raise NoteNotFound("Note not found.")
    return note


def _rewrite_indexes(
    notes: NoteRepository,
    *,
    note_id: UUID,
    user_id: UUID,
    body_markdown: str,
    tags: Sequence[str],
) -> None:
    """Rebuild a note's derived wikilink and tag indexes from its body on save (NF-05)."""
    targets = _parse_wikilinks(body_markdown)
    resolved = notes.resolve_titles(user_id, targets) if targets else {}
    links: list[DerivedNoteLink] = []
    for target in targets:
        target_note_id = resolved.get(target.lower())
        # A wikilink to the note's own title (self-link) is ignored (edge case).
        if target_note_id == note_id:
            continue
        links.append(DerivedNoteLink(target_text=target, target_note_id=target_note_id))
    notes.set_links(note_id, links)
    notes.set_tags(note_id, user_id, _normalize_tags(tags))


def _view(notes: NoteRepository, note: Note) -> NoteView:
    """Assemble the note-detail read model (note + tags + anchors)."""
    return NoteView(
        note=note,
        tags=tuple(notes.tags_for_note(note.id)),
        anchors=tuple(notes.anchors_for_note(note.id)),
    )


class CreateNote:
    """Create a whole-Markdown note for its owner and derive its indexes (NF-05).

    Empty body allowed. The body cap (NF-04) is enforced before any write; the
    wikilink and tag indexes are rebuilt from the body in the same transaction.
    """

    def __init__(
        self,
        *,
        notes: NoteRepository,
        clock: Clock,
        ids: Callable[[], UUID],
        max_body_chars: int,
    ) -> None:
        self._notes = notes
        self._clock = clock
        self._ids = ids
        self._max_body_chars = max_body_chars

    def __call__(
        self,
        *,
        user: User,
        title: str,
        body_markdown: str,
        tags: Sequence[str] = (),
    ) -> NoteView:
        _validate_body(body_markdown, self._max_body_chars)
        now = self._clock.now()
        note = Note(
            id=self._ids(),
            user_id=user.id,
            title=title,
            body_markdown=body_markdown,
            created_at=now,
            updated_at=now,
        )
        self._notes.add(note)
        _rewrite_indexes(
            self._notes,
            note_id=note.id,
            user_id=user.id,
            body_markdown=body_markdown,
            tags=tags,
        )
        return _view(self._notes, note)


class UpdateNote:
    """Update an owned note and rewrite its derived indexes in the same transaction (NF-05)."""

    def __init__(
        self,
        *,
        notes: NoteRepository,
        clock: Clock,
        max_body_chars: int,
    ) -> None:
        self._notes = notes
        self._clock = clock
        self._max_body_chars = max_body_chars

    def __call__(
        self,
        *,
        user: User,
        note_id: UUID,
        title: str,
        body_markdown: str,
        tags: Sequence[str] = (),
    ) -> NoteView:
        _owned_note(self._notes, user, note_id)
        _validate_body(body_markdown, self._max_body_chars)
        now = self._clock.now()
        self._notes.update(
            note_id, title=title, body_markdown=body_markdown, updated_at=now
        )
        _rewrite_indexes(
            self._notes,
            note_id=note_id,
            user_id=user.id,
            body_markdown=body_markdown,
            tags=tags,
        )
        updated = self._notes.get_by_id(note_id)
        assert updated is not None  # just updated in this transaction
        return _view(self._notes, updated)


class DeleteNote:
    """Delete an owned note (its anchors/tags/links cascade; inbound links SET NULL)."""

    def __init__(self, *, notes: NoteRepository) -> None:
        self._notes = notes

    def __call__(self, *, user: User, note_id: UUID) -> None:
        _owned_note(self._notes, user, note_id)
        self._notes.delete(note_id)


class GetNote:
    """Return an owned note's detail (note + tags + anchors), or a 404 (NF-05/10)."""

    def __init__(self, *, notes: NoteRepository) -> None:
        self._notes = notes

    def __call__(self, *, user: User, note_id: UUID) -> NoteView:
        note = _owned_note(self._notes, user, note_id)
        return _view(self._notes, note)


class ListNotes:
    """Return the caller's notes (newest-edited first), optionally filtered by tag (NF-13)."""

    def __init__(self, *, notes: NoteRepository) -> None:
        self._notes = notes

    def __call__(
        self, *, user: User, tag: str | None = None
    ) -> list[NoteSummary]:
        return self._notes.list_summaries(
            user.id, tag=tag.strip().lower() if tag else None
        )


class CaptureHighlight:
    """Capture a highlight from the reader: create a note + one anchor atomically (NF-06).

    Validates the section belongs to an owned source's corpus (a non-owned/unknown
    source is a 404; an unknown anchor a 404), then resolves the selection against the
    section's blocks (NF-03). If the served evidence no longer matches — the section was
    replaced mid-flight — nothing is persisted and ``StaleCaptureTarget`` (409) is
    raised. Otherwise a note (empty body allowed) plus its book anchor are created and
    the note's derived indexes are rebuilt, all in the caller's transaction.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        notes: NoteRepository,
        corpus: CorpusRepository,
        markup: MarkupConverterPort,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
        max_body_chars: int,
    ) -> None:
        self._sources = sources
        self._notes = notes
        self._corpus = corpus
        self._markup = markup
        self._authorize = authorize
        self._clock = clock
        self._ids = ids
        self._max_body_chars = max_body_chars

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID,
        anchor: str,
        quote_exact: str,
        quote_prefix: str = "",
        quote_suffix: str = "",
        title: str,
        body_markdown: str = "",
        tags: Sequence[str] = (),
    ) -> NoteView:
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        section = self._corpus.blocks_for_section(source_id, anchor)
        if section is None:
            raise CorpusNotFound("No section for this anchor.")

        blocks = [
            AnchorBlock(
                ordinal=block.ordinal,
                content_hash=block.content_hash,
                text=self._markup.to_markdown(block.html_fragment),
            )
            for block in section.blocks
        ]
        binding = resolve(blocks, quote_exact, quote_prefix, quote_suffix)
        if binding is None:
            raise StaleCaptureTarget(
                "The selected passage no longer matches the source."
            )
        _validate_body(body_markdown, self._max_body_chars)

        now = self._clock.now()
        note = Note(
            id=self._ids(),
            user_id=user.id,
            title=title,
            body_markdown=body_markdown,
            created_at=now,
            updated_at=now,
        )
        self._notes.add(note)
        _rewrite_indexes(
            self._notes,
            note_id=note.id,
            user_id=user.id,
            body_markdown=body_markdown,
            tags=tags,
        )
        self._notes.add_anchor(
            NoteAnchor(
                id=self._ids(),
                note_id=note.id,
                source_id=source_id,
                source_title=source.title,
                anchor=section.anchor,
                section_path=section.section_path,
                block_hash=binding.block_hash,
                block_ordinal=binding.block_ordinal,
                start_offset=binding.start_offset,
                end_offset=binding.end_offset,
                quote_exact=quote_exact,
                quote_prefix=quote_prefix,
                quote_suffix=quote_suffix,
                status=NoteAnchorStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        return _view(self._notes, note)
