"""T15 gate — deterministic Obsidian vault builder (unit, pure; NL-17..21).

Pins the pure ``build_vault`` projection: two builds over identical data are
byte-identical (NL-19); only what the caller passes is serialized; filenames strip
path/Obsidian-hostile characters and de-collide deterministically (NL-21); a book file
renders positioned highlight callouts with stable ``^lh-<id>`` blocks and orphans in a
trailing section (NL-17); a deleted book still renders from its snapshot title; note
files carry only ``learny-*`` frontmatter with the body verbatim and anchors as deep
links into their book block, or a plain quote when no book carries them (NL-18); an
empty vault is a valid zip with the ``Learny/`` skeleton.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.entities import Note, NoteAnchor, NoteAnchorStatus, NoteView
from app.infrastructure.export.obsidian import build_vault

_EPOCH = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)


# --- builders ------------------------------------------------------------------


def _note(
    *,
    note_id: UUID | None = None,
    title: str = "My Note",
    body: str = "Some **markdown** body.",
    created_at: datetime = _EPOCH,
) -> Note:
    return Note(
        id=note_id or uuid4(),
        user_id=uuid4(),
        title=title,
        body_markdown=body,
        created_at=created_at,
        updated_at=created_at,
    )


def _anchor(
    *,
    note_id: UUID,
    anchor_id: UUID | None = None,
    source_id: UUID | None = None,
    source_title: str = "The Book",
    section_path: tuple[str, ...] = ("Chapter 1", "Intro"),
    block_ordinal: int | None = 2,
    start_offset: int | None = 5,
    quote_exact: str = "the quoted passage",
    status: str = NoteAnchorStatus.ACTIVE,
    created_at: datetime = _EPOCH,
) -> NoteAnchor:
    return NoteAnchor(
        id=anchor_id or uuid4(),
        note_id=note_id,
        source_id=source_id or uuid4(),
        source_title=source_title,
        anchor="ch1",
        section_path=section_path,
        block_hash="h" * 64,
        block_ordinal=block_ordinal,
        start_offset=start_offset,
        end_offset=None,
        quote_exact=quote_exact,
        quote_prefix="",
        quote_suffix="",
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )


def _view(note: Note, anchors: tuple[NoteAnchor, ...] = (), tags: tuple[str, ...] = ()) -> NoteView:
    return NoteView(note=note, tags=tags, anchors=anchors)


def _entries(data: bytes) -> dict[str, str]:
    """Return the zip's file entries as ``path -> decoded text`` (directories dropped)."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {
            info.filename: archive.read(info.filename).decode("utf-8")
            for info in archive.infolist()
            if not info.is_dir()
        }


# --- NL-19 determinism ---------------------------------------------------------


def test_two_builds_are_byte_identical() -> None:
    note = _note()
    anchor = _anchor(note_id=note.id)
    source_id = anchor.source_id
    notes = [_view(note, (anchor,), ("alpha", "beta"))]
    highlights = {source_id: [anchor]}

    first = build_vault(notes, highlights)
    second = build_vault(notes, highlights)

    assert first == second


def test_empty_vault_is_a_valid_zip_with_skeleton() -> None:
    data = build_vault([], {})

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
    assert "Learny/Books/" in names
    assert "Learny/Notes/" in names
    assert _entries(data) == {}


def test_entries_use_stored_compression_for_determinism() -> None:
    note = _note()
    with zipfile.ZipFile(io.BytesIO(build_vault([_view(note)], {}))) as archive:
        assert all(
            info.compress_type == zipfile.ZIP_STORED for info in archive.infolist()
        )


# --- NL-20 scoping (builder serializes only what it is given) -------------------


def test_only_the_supplied_notes_and_highlights_are_serialized() -> None:
    note = _note(title="Kept")
    data = build_vault([_view(note)], {})

    paths = _entries(data)
    assert "Learny/Notes/Kept.md" in paths
    assert all("Books" not in path for path in paths)


# --- NL-21 sanitization + de-collision -----------------------------------------


def test_hostile_filename_characters_are_stripped() -> None:
    note = _note(title='a/b:c*d?e"f<g>h|i#j')
    paths = _entries(build_vault([_view(note)], {}))

    assert "Learny/Notes/abcdefghij.md" in paths


def test_blank_title_falls_back_to_untitled() -> None:
    note = _note(title="///")
    assert "Learny/Notes/Untitled.md" in _entries(build_vault([_view(note)], {}))


def test_identical_note_titles_de_collide_deterministically() -> None:
    first = _note(title="Same", created_at=_EPOCH)
    second = _note(title="Same", created_at=_EPOCH + timedelta(hours=1))
    third = _note(title="Same", created_at=_EPOCH + timedelta(hours=2))
    notes = [_view(third), _view(first), _view(second)]

    paths = set(_entries(build_vault(notes, {})))

    assert paths == {
        "Learny/Notes/Same.md",
        "Learny/Notes/Same (2).md",
        "Learny/Notes/Same (3).md",
    }
    # The suffix assignment is stable across builds regardless of input order.
    assert _entries(build_vault(notes, {})) == _entries(
        build_vault(list(reversed(notes)), {})
    )


# --- NL-17 book files: callouts, block ids, ordering, orphans -------------------


def test_book_highlight_renders_as_callout_with_block_id() -> None:
    note = _note()
    anchor = _anchor(
        note_id=note.id, section_path=("Chapter 1", "Intro"), quote_exact="a passage"
    )
    data = build_vault([_view(note, (anchor,))], {anchor.source_id: [anchor]})

    book = _entries(data)["Learny/Books/The Book.md"]
    assert "> [!quote] Chapter 1 › Intro" in book
    assert "> a passage" in book
    assert f"^lh-{anchor.id}" in book


def test_highlights_order_by_position_in_the_book() -> None:
    note = _note()
    source_id = uuid4()
    later = _anchor(note_id=note.id, source_id=source_id, block_ordinal=9, quote_exact="LATER")
    earlier = _anchor(note_id=note.id, source_id=source_id, block_ordinal=1, quote_exact="EARLIER")
    data = build_vault(
        [_view(note, (later, earlier))], {source_id: [later, earlier]}
    )

    book = _entries(data)["Learny/Books/The Book.md"]
    assert book.index("EARLIER") < book.index("LATER")


def test_null_position_highlights_sort_last() -> None:
    note = _note()
    source_id = uuid4()
    positioned = _anchor(
        note_id=note.id, source_id=source_id, block_ordinal=1, quote_exact="POSITIONED"
    )
    quote_only = _anchor(
        note_id=note.id,
        source_id=source_id,
        block_ordinal=None,
        start_offset=None,
        quote_exact="QUOTEONLY",
    )
    data = build_vault(
        [_view(note, (positioned, quote_only))], {source_id: [quote_only, positioned]}
    )

    book = _entries(data)["Learny/Books/The Book.md"]
    assert book.index("POSITIONED") < book.index("QUOTEONLY")


def test_orphaned_highlights_render_in_trailing_section() -> None:
    note = _note()
    source_id = uuid4()
    active = _anchor(note_id=note.id, source_id=source_id, quote_exact="LIVE")
    orphan = _anchor(
        note_id=note.id,
        source_id=source_id,
        status=NoteAnchorStatus.ORPHANED,
        quote_exact="LOSTPASSAGE",
    )
    data = build_vault([_view(note, (active, orphan))], {source_id: [active, orphan]})

    book = _entries(data)["Learny/Books/The Book.md"]
    assert "## Orphaned highlights" in book
    # The orphan renders from its quote snapshot, below the heading; the live one above.
    assert book.index("LIVE") < book.index("## Orphaned highlights")
    assert book.index("## Orphaned highlights") < book.index("LOSTPASSAGE")


def test_deleted_book_still_renders_from_snapshot_title() -> None:
    # No source row is needed — the anchor carries the snapshot title, so the builder
    # never asks whether the book still exists (edge case: anchored note, book deleted).
    note = _note()
    anchor = _anchor(note_id=note.id, source_title="A Deleted Book")
    data = build_vault([_view(note, (anchor,))], {anchor.source_id: [anchor]})

    assert "Learny/Books/A Deleted Book.md" in _entries(data)


# --- NL-18 note files: frontmatter, verbatim body, anchor links -----------------


def test_note_frontmatter_uses_only_learny_keys() -> None:
    note = _note(title="Ideas", body="body")
    anchor = _anchor(note_id=note.id, source_title="Src")
    data = build_vault([_view(note, (anchor,), ("z-tag", "a-tag"))], {anchor.source_id: [anchor]})

    text = _entries(data)["Learny/Notes/Ideas.md"]
    front = text.split("---\n", 2)[1]
    keys = [
        line.split(":", 1)[0]
        for line in front.splitlines()
        if line and not line.startswith(" ")
    ]
    assert keys == [
        "learny-id",
        "learny-created",
        "learny-updated",
        "learny-tags",
        "learny-sources",
    ]
    assert f"learny-id: {note.id}" in front
    assert '"z-tag"' in front and '"a-tag"' in front
    assert '"Src"' in front


def test_unanchored_note_omits_sources_key() -> None:
    note = _note(title="Solo")
    front = _entries(build_vault([_view(note)], {}))["Learny/Notes/Solo.md"]
    assert "learny-sources" not in front
    assert "learny-tags: []" in front


def test_note_body_and_wikilinks_are_verbatim() -> None:
    body = "See [[Other Note]] and [[Third|alias]].\n\nSecond *para* stays.\n"
    note = _note(title="Linker", body=body)
    text = _entries(build_vault([_view(note)], {}))["Learny/Notes/Linker.md"]

    assert body in text


def test_note_anchor_links_into_the_book_block() -> None:
    note = _note(title="Cited")
    anchor = _anchor(note_id=note.id, source_title="The Book", quote_exact="cited text")
    data = build_vault([_view(note, (anchor,))], {anchor.source_id: [anchor]})

    text = _entries(data)["Learny/Notes/Cited.md"]
    assert f"[[The Book#^lh-{anchor.id}]]" in text
    assert "> cited text" in text


def test_note_anchor_without_a_book_file_falls_back_to_plain_quote() -> None:
    # The note's anchor cites a source absent from ``highlights_by_source`` — no book
    # file carries the block, so it renders as a plain cited quote, not a dead link.
    note = _note(title="Loose")
    anchor = _anchor(note_id=note.id, source_title="Absent Book", quote_exact="loose quote")
    data = build_vault([_view(note, (anchor,))], {})

    text = _entries(data)["Learny/Notes/Loose.md"]
    assert "[[" not in text
    assert "> [!quote] Absent Book" in text
    assert "> loose quote" in text
