"""Vault-export use-case service (RFC-003 Cycle F; ADR-0026 d6, design §Vault export).

Framework-free orchestration of the Obsidian-vault export: ``ExportVault`` gathers the
caller's notes (with tags and their anchors) and every anchor the caller owns, grouped
for the pure builder. Nothing here imports FastAPI or the ``zipfile`` builder (ADR-007/
009) — mirroring ``ExportQuizDeck``, the service returns the domain reads and the web
layer packs the bytes.

Both reads are ``user_id``-scoped, so the export is intrinsically the caller's own data
and never another user's, regardless of source ownership (NL-20).
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import NoteAnchor, NoteView, User
from app.domain.ports import NoteRepository


class ExportVault:
    """Gather the caller's notes and highlights for the vault export (NL-16/20).

    Returns ``(notes, highlights_by_source)``: each :class:`NoteView` carries its own
    anchors (the note files), and every anchor grouped by the source it cites (the book
    files). The pure builder sorts both, so ordering here is immaterial. A caller with
    no notes yields empty collections — the builder still produces a valid skeleton zip.
    """

    def __init__(self, *, notes: NoteRepository) -> None:
        self._notes = notes

    def __call__(
        self, *, user: User
    ) -> tuple[list[NoteView], dict[UUID, list[NoteAnchor]]]:
        summaries = self._notes.list_summaries(user.id)
        anchors = self._notes.anchors_for_user(user.id)
        by_note: dict[UUID, list[NoteAnchor]] = {}
        by_source: dict[UUID, list[NoteAnchor]] = {}
        for anchor in anchors:
            by_note.setdefault(anchor.note_id, []).append(anchor)
            by_source.setdefault(anchor.source_id, []).append(anchor)
        views = [
            NoteView(
                note=summary.note,
                tags=summary.tags,
                anchors=tuple(by_note.get(summary.note.id, ())),
            )
            for summary in summaries
        ]
        return views, by_source
