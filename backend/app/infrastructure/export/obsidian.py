"""Deterministic Obsidian-vault export (ADR-0026 d6; NL-16..21).

A pure ``(domain reads) -> zip bytes`` projection: given the caller's notes (each
with its tags and anchors) and every one of the caller's highlights grouped by the
source they cite, :func:`build_vault` returns a ``Learny/`` folder Obsidian opens
natively — one Markdown file per book that has highlights and one per note.

The projection is one-way and regenerable: nothing here reads back a prior export, so
re-exporting is the user's wholesale-replace action (ADR-0026 d6), and two builds over
identical data are byte-identical (NL-19). Determinism is by construction — a fixed
1980 zip timestamp, fixed permissions, ``STORED`` entries (no zlib-version variance),
and every filename/entry emitted in a sorted, collision-de-duplicated order.

A highlight IS a note anchor (AD-113): the same anchor renders once in its book file as
a positioned ``> [!quote]`` callout carrying a stable ``^lh-<id>`` block anchor, and
again in its note file as a deep link into that block. ``source_title`` is snapshotted
on the anchor, so a deleted book still renders from the snapshot.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping, Sequence
from uuid import UUID

from app.domain.entities import NoteAnchor, NoteAnchorStatus, NoteView

_ROOT = "Learny"
_BOOKS = f"{_ROOT}/Books"
_NOTES = f"{_ROOT}/Notes"

# Fixed 1980-01-01 zip timestamp + fixed perms + a fixed Unix create-system so two
# builds over identical data are byte-identical (NL-19). ``STORED`` (no compression)
# sidesteps zlib-version variance entirely — a personal vault is small text.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_FILE_ATTR = 0o644 << 16
_DIR_ATTR = (0o40755 << 16) | 0x10
_UNIX = 3

# Characters hostile to OS paths and to Obsidian link syntax, stripped from every
# emitted filename (NL-21); control characters go too.
_FILE_HOSTILE = re.compile(r'[\[\]:\\/^|#?*<>"\x00-\x1f]')
# Characters that would start a link/tag or break callout titles — neutralised in the
# free text emitted into a callout title (a section path may contain any of them).
_TEXT_HOSTILE = re.compile(r"[\[\]|#^]")


def build_vault(
    notes: Sequence[NoteView],
    highlights_by_source: Mapping[UUID, Sequence[NoteAnchor]],
) -> bytes:
    """Return the caller's notes + highlights as an Obsidian-vault zip (NL-16..21).

    ``notes`` render to ``Learny/Notes/<title>.md``; ``highlights_by_source`` renders
    to ``Learny/Books/<title>.md`` (one file per source that has highlights). A note
    anchor links into its book file's ``^lh-<id>`` block when that book carries it,
    else falls back to a plain cited quote (NL-18). Empty inputs yield a valid zip with
    the ``Learny/`` skeleton (empty-vault edge case).
    """
    entries: dict[str, bytes] = {}
    anchor_to_book: dict[UUID, str] = {}

    ordered_sources = [
        (source_id, sorted(anchors, key=lambda a: (a.created_at, str(a.id))))
        for source_id, anchors in sorted(
            highlights_by_source.items(), key=lambda kv: str(kv[0])
        )
        if anchors
    ]
    book_names = _dedupe(
        [_sanitize(anchors[0].source_title) for _, anchors in ordered_sources]
    )
    for (_source_id, anchors), name in zip(ordered_sources, book_names, strict=True):
        for anchor in anchors:
            anchor_to_book[anchor.id] = name
        entries[f"{_BOOKS}/{name}.md"] = _render_book(name, anchors)

    ordered_notes = sorted(notes, key=lambda nv: (nv.note.created_at, str(nv.note.id)))
    note_names = _dedupe([_sanitize(nv.note.title) for nv in ordered_notes])
    for view, name in zip(ordered_notes, note_names, strict=True):
        entries[f"{_NOTES}/{name}.md"] = _render_note(view, anchor_to_book)

    return _zip(entries)


def _zip(entries: Mapping[str, bytes]) -> bytes:
    """Pack ``entries`` (path -> bytes) into a deterministic zip with the vault skeleton."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for directory in (f"{_BOOKS}/", f"{_NOTES}/"):
            archive.writestr(_info(directory, _DIR_ATTR), b"")
        for path in sorted(entries):
            archive.writestr(_info(path, _FILE_ATTR), entries[path])
    return buffer.getvalue()


def _info(name: str, external_attr: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
    info.external_attr = external_attr
    info.create_system = _UNIX
    info.compress_type = zipfile.ZIP_STORED
    return info


def _render_book(title: str, anchors: Sequence[NoteAnchor]) -> bytes:
    """Render one book file: positioned highlight callouts, orphans in a trailing section."""
    positioned = sorted(
        (a for a in anchors if a.status != NoteAnchorStatus.ORPHANED), key=_position_key
    )
    orphaned = sorted(
        (a for a in anchors if a.status == NoteAnchorStatus.ORPHANED),
        key=lambda a: (a.created_at, str(a.id)),
    )
    lines = [f"# {_text(title)}", ""]
    for anchor in positioned:
        lines.extend(_callout(anchor))
    if orphaned:
        lines.extend(("## Orphaned highlights", ""))
        for anchor in orphaned:
            lines.extend(_callout(anchor))
    return _finalize(lines)


def _callout(anchor: NoteAnchor) -> list[str]:
    """A ``> [!quote]`` callout titled by section path, with a stable ``^lh-<id>`` block."""
    title = _text(" › ".join(anchor.section_path)) or _text(anchor.source_title) or "Highlight"
    return [f"> [!quote] {title}", *_blockquote(anchor.quote_exact), f"^lh-{anchor.id}", ""]


def _render_note(view: NoteView, anchor_to_book: Mapping[UUID, str]) -> bytes:
    """Render one note file: ``learny-*`` frontmatter, verbatim body, then its highlights."""
    note = view.note
    lines = _frontmatter(view)
    lines.append("")
    if note.body_markdown:
        lines.append(note.body_markdown)
    if view.anchors:
        if note.body_markdown:
            lines.append("")
        lines.extend(("## Highlights", ""))
        for anchor in view.anchors:
            lines.extend(_note_anchor(anchor, anchor_to_book))
    return _finalize(lines)


def _note_anchor(anchor: NoteAnchor, anchor_to_book: Mapping[UUID, str]) -> list[str]:
    """A highlight inside a note: a deep link into its book block, else a cited quote."""
    book = anchor_to_book.get(anchor.id)
    if book is not None:
        header = f"> [!quote] [[{book}#^lh-{anchor.id}]]"
    else:
        header = f"> [!quote] {_text(anchor.source_title) or 'Highlight'}"
    return [header, *_blockquote(anchor.quote_exact), ""]


def _frontmatter(view: NoteView) -> list[str]:
    """Obsidian Properties frontmatter using only namespaced ``learny-*`` keys (NL-18)."""
    note = view.note
    lines = [
        "---",
        f"learny-id: {note.id}",
        f"learny-created: {note.created_at.isoformat()}",
        f"learny-updated: {note.updated_at.isoformat()}",
        "learny-tags:" + _yaml_list(view.tags),
    ]
    sources = sorted({anchor.source_title for anchor in view.anchors})
    if sources:
        lines.append("learny-sources:" + _yaml_list(sources))
    lines.append("---")
    return lines


def _yaml_list(values: Sequence[str]) -> str:
    """A YAML flow ``[]`` when empty, else a block list of double-quoted scalars."""
    if not values:
        return " []"
    return "\n" + "\n".join(f"  - {_yaml_scalar(value)}" for value in values)


def _yaml_scalar(value: str) -> str:
    """Double-quote so YAML-special characters in a tag/title never break the frontmatter."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _blockquote(text: str) -> list[str]:
    """Prefix each line of ``text`` with ``> `` for a Markdown/callout blockquote body."""
    return [f"> {line}" for line in (text.splitlines() or [""])]


def _finalize(lines: Sequence[str]) -> bytes:
    """Join ``lines`` into a UTF-8 file ending in exactly one newline (body never stripped)."""
    document = "\n".join(lines)
    if not document.endswith("\n"):
        document += "\n"
    return document.encode("utf-8")


def _sanitize(title: str) -> str:
    """Strip path/Obsidian-hostile characters from a filename base (NL-21)."""
    cleaned = _FILE_HOSTILE.sub("", title).strip(" .\t\r\n")
    return cleaned or "Untitled"


def _text(value: str) -> str:
    """Neutralise link/tag/callout-hostile characters in free text emitted as a title."""
    return _TEXT_HOSTILE.sub("", value).strip()


def _dedupe(names: Sequence[str]) -> list[str]:
    """Assign each name a collision-free variant, appending `` (2)``, `` (3)`` in order.

    Deterministic given the caller's ordering (notes by ``(created_at, id)``, books by
    ``source_id``), so collision suffixes are stable across builds (NL-21).
    """
    used: set[str] = set()
    result: list[str] = []
    for name in names:
        candidate = name
        counter = 2
        while candidate in used:
            candidate = f"{name} ({counter})"
            counter += 1
        used.add(candidate)
        result.append(candidate)
    return result


def _position_key(anchor: NoteAnchor) -> tuple[object, ...]:
    """Order a highlight by its position in the book; NULL block/offset sorts last."""
    return (
        anchor.section_path,
        anchor.block_ordinal is None,
        anchor.block_ordinal or 0,
        anchor.start_offset is None,
        anchor.start_offset or 0,
        anchor.created_at,
        str(anchor.id),
    )
