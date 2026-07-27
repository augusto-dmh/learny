"""T4 gate — notes use cases (unit, fakes; NF-04..06 + edges).

Drives Update/Delete/Get/List and CaptureHighlight over in-memory fakes, pinning:
owner scoping (non-owner collapses to ``NoteNotFound``), the body cap, wikilink
derivation (resolved / unresolved / self-link), lowercase tag normalization, the
book-scoped list (an unowned book is the same 404 as an unknown one; each row's page
comes from the book's word counts and an unresolvable anchor keeps its row with no
page), and highlight capture — the only way a note is created (owned-source +
served-section consistency, atomic note+anchor, optional quote, empty body allowed,
stale/unknown-anchor errors).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.errors import (
    CorpusNotFound,
    NoteBodyTooLong,
    NoteNotFound,
    SourceNotFound,
    StaleCaptureTarget,
)
from app.application.identity import AuthorizeOwnership
from app.application.notes import (
    CaptureHighlight,
    DeleteNote,
    GetBacklinks,
    GetNote,
    ListNotes,
    ReconcileNoteAnchors,
    UpdateNote,
)
from app.domain.entities import (
    AnchorBlockSnapshot,
    AnchorSection,
    ChapterIndexRow,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    Source,
    User,
)
from tests.fakes import (
    FakeAnchorCorpus,
    FakeClock,
    FakeNoteRepository,
    FakeSourceRepository,
    IdentityMarkupConverter,
)


def _user(user_id=None) -> User:  # noqa: ANN001
    return User(id=user_id or uuid4(), email="reader@example.com", created_at=datetime.now(UTC))


def _source(user_id, *, title: str = "A Book") -> Source:  # noqa: ANN001
    now = datetime.now(UTC)
    return Source(
        id=uuid4(),
        user_id=user_id,
        title=title,
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )


def _seed_note(
    notes: FakeNoteRepository,
    user: User,
    *,
    title: str,
    body_markdown: str = "",
    tags: Sequence[str] = (),
) -> Note:
    """Persist a note directly, standing in for one the repository already holds.

    Its derived indexes are written by the real save path so a seeded body's wikilinks
    and tags exist exactly as a save would leave them.
    """
    now = datetime.now(UTC)
    note = Note(
        id=uuid4(),
        user_id=user.id,
        title=title,
        body_markdown="",
        created_at=now,
        updated_at=now,
    )
    notes.add(note)
    UpdateNote(notes=notes, clock=FakeClock(), max_body_chars=100000)(
        user=user,
        note_id=note.id,
        title=title,
        body_markdown=body_markdown,
        tags=list(tags),
    )
    stored = notes.get_by_id(note.id)
    assert stored is not None
    return stored


# --- UpdateNote (NF-05) ---------------------------------------------------------


def test_update_note_rewrites_body_tags_and_links() -> None:
    notes = FakeNoteRepository()
    user = _user()
    target = _seed_note(notes, user, title="Target")
    note = _seed_note(notes, user, title="Note", tags=["old"])

    update = UpdateNote(notes=notes, clock=FakeClock(), max_body_chars=100000)
    view, body_changed = update(
        user=user,
        note_id=note.id,
        title="Note",
        body_markdown="now links [[Target]]",
        tags=["new"],
    )

    assert view.tags == ("new",)
    assert body_changed is True  # body went from "" to non-empty
    links = notes.links_for_note(note.id)
    assert [link.target_note_id for link in links] == [target.id]


def test_update_note_reports_body_unchanged_for_title_or_tag_only_edit() -> None:
    """A PATCH that leaves body_markdown byte-identical reports body_changed=False,
    so the web layer skips the async re-embed (NL-01: embed only when body changed)."""
    notes = FakeNoteRepository()
    user = _user()
    note = _seed_note(notes, user, title="Note", body_markdown="stable body", tags=["a"])

    update = UpdateNote(notes=notes, clock=FakeClock(), max_body_chars=100000)
    _, body_changed = update(
        user=user,
        note_id=note.id,
        title="Renamed",
        body_markdown="stable body",
        tags=["a", "b"],
    )

    assert body_changed is False


def test_update_note_by_non_owner_is_not_found() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    note = _seed_note(notes, owner, title="Owned")

    update = UpdateNote(notes=notes, clock=FakeClock(), max_body_chars=100000)
    with pytest.raises(NoteNotFound):
        update(user=other, note_id=note.id, title="Hacked", body_markdown="", tags=[])
    # The owner's note is untouched.
    assert notes.get_by_id(note.id).title == "Owned"


# --- DeleteNote / GetNote / ListNotes (NF-05) -----------------------------------


def test_delete_note_owner_scoped() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    note = _seed_note(notes, owner, title="Owned")

    delete = DeleteNote(notes=notes)
    with pytest.raises(NoteNotFound):
        delete(user=other, note_id=note.id)
    delete(user=owner, note_id=note.id)
    assert notes.get_by_id(note.id) is None


def test_get_note_returns_tags_and_is_owner_scoped() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    note = _seed_note(notes, owner, title="Owned", tags=["python"])

    get = GetNote(notes=notes)
    assert get(user=owner, note_id=note.id).tags == ("python",)
    with pytest.raises(NoteNotFound):
        get(user=other, note_id=note.id)


def _list_notes(
    notes: FakeNoteRepository,
    *,
    sources: FakeSourceRepository | None = None,
    corpus: FakeAnchorCorpus | None = None,
    words_per_page: int = 100,
) -> ListNotes:
    return ListNotes(
        notes=notes,
        sources=sources if sources is not None else FakeSourceRepository(),
        corpus=corpus if corpus is not None else FakeAnchorCorpus(),
        authorize=AuthorizeOwnership(),
        words_per_page=words_per_page,
    )


def _anchor_note(
    notes: FakeNoteRepository,
    user: User,
    source_id,  # noqa: ANN001
    *,
    title: str,
    anchor: str = "ch1",
    quote_exact: str = "the passage it came from",
    status: str = NoteAnchorStatus.ACTIVE,
) -> Note:
    """Seed one of ``user``'s notes carrying a single anchor on ``source_id``."""
    note = _seed_note(notes, user, title=title)
    now = datetime.now(UTC)
    notes.add_anchor(
        NoteAnchor(
            id=uuid4(),
            note_id=note.id,
            source_id=source_id,
            source_title="A Book",
            anchor=anchor,
            section_path=("Part One", "Prefácio"),
            block_hash=None,
            block_ordinal=None,
            start_offset=None,
            end_offset=None,
            quote_exact=quote_exact,
            quote_prefix="",
            quote_suffix="",
            status=status,
            created_at=now,
            updated_at=now,
        )
    )
    return note


def _index_row(anchor: str, *, word_count: int, aliases: tuple[str, ...] = ()) -> ChapterIndexRow:
    return ChapterIndexRow(
        position=0,
        depth=0,
        title=anchor,
        section_path=(anchor,),
        anchor=anchor,
        anchor_aliases=aliases,
        word_count=word_count,
    )


def test_list_notes_filters_by_tag_lowercased() -> None:
    notes = FakeNoteRepository()
    user = _user()
    _seed_note(notes, user, title="Tagged", tags=["python"])
    _seed_note(notes, user, title="Untagged")

    summaries = _list_notes(notes)(user=user, tag="PYTHON")

    assert [s.note.title for s in summaries] == ["Tagged"]


def test_list_notes_across_books_carries_no_passage_or_page() -> None:
    notes = FakeNoteRepository()
    user = _user()
    source_id = uuid4()
    _anchor_note(notes, user, source_id, title="Anchored")

    summary = _list_notes(notes)(user=user)[0]

    assert summary.anchor is None
    assert summary.page is None


def test_list_notes_scoped_to_an_unowned_book_is_not_found() -> None:
    notes = FakeNoteRepository()
    sources = FakeSourceRepository()
    owner = _user()
    intruder = _user()
    source = sources.add(_source(owner.id))
    _anchor_note(notes, owner, source.id, title="Owned")

    with pytest.raises(SourceNotFound):
        _list_notes(notes, sources=sources)(user=intruder, source_id=source.id)


def test_list_notes_scoped_to_an_unknown_book_is_the_same_not_found() -> None:
    # The unowned and the unknown source raise the identical error, so the response
    # cannot tell a caller that someone else's book exists.
    notes = FakeNoteRepository()
    user = _user()

    with pytest.raises(SourceNotFound):
        _list_notes(notes)(user=user, source_id=uuid4())


def test_list_notes_scoped_to_a_book_derives_the_page_from_its_word_counts() -> None:
    notes = FakeNoteRepository()
    sources = FakeSourceRepository()
    user = _user()
    source = sources.add(_source(user.id))
    _anchor_note(notes, user, source.id, title="Late in the book", anchor="ch3")
    corpus = FakeAnchorCorpus()
    # 250 + 250 words precede ch3; at 100 words to a page that is page 6, counted from
    # the book's first word rather than restarted per chapter.
    corpus.set_chapter_index(
        source.id,
        [
            _index_row("ch1", word_count=250),
            _index_row("ch2", word_count=250),
            _index_row("ch3", word_count=250),
        ],
    )

    summary = _list_notes(notes, sources=sources, corpus=corpus, words_per_page=100)(
        user=user, source_id=source.id
    )[0]

    assert summary.page == 6


def test_list_notes_pages_an_anchor_the_book_now_carries_only_as_an_alias() -> None:
    """An anchor a re-ingest demoted to an alias still pages to its section."""
    notes = FakeNoteRepository()
    sources = FakeSourceRepository()
    user = _user()
    source = sources.add(_source(user.id))
    _anchor_note(notes, user, source.id, title="Written before the re-ingest", anchor="old-ch2")
    corpus = FakeAnchorCorpus()
    corpus.set_chapter_index(
        source.id,
        [
            _index_row("ch1", word_count=250),
            _index_row("ch2", word_count=250, aliases=("old-ch2",)),
        ],
    )

    summary = _list_notes(notes, sources=sources, corpus=corpus, words_per_page=100)(
        user=user, source_id=source.id
    )[0]

    assert summary.page == 3


def test_list_notes_pages_a_canonical_anchor_over_a_section_holding_it_as_an_alias() -> None:
    """A canonical match wins over an alias, so the page names the section the rest of
    the app would resolve — the precedence anchor lookup has always had."""
    notes = FakeNoteRepository()
    sources = FakeSourceRepository()
    user = _user()
    source = sources.add(_source(user.id))
    _anchor_note(notes, user, source.id, title="On the real chapter two", anchor="ch2")
    corpus = FakeAnchorCorpus()
    # An earlier section carries "ch2" merely as an alias; the section whose own anchor
    # is "ch2" is the one that must supply the page.
    corpus.set_chapter_index(
        source.id,
        [
            _index_row("ch1", word_count=250, aliases=("ch2",)),
            _index_row("ch2", word_count=250),
        ],
    )

    summary = _list_notes(notes, sources=sources, corpus=corpus, words_per_page=100)(
        user=user, source_id=source.id
    )[0]

    assert summary.page == 3


def test_list_notes_keeps_an_unresolvable_anchors_row_with_its_quote_and_no_page() -> None:
    notes = FakeNoteRepository()
    sources = FakeSourceRepository()
    user = _user()
    source = sources.add(_source(user.id))
    _anchor_note(
        notes,
        user,
        source.id,
        title="Orphaned",
        anchor="ch-gone",
        quote_exact="a passage that outlived its section",
        status=NoteAnchorStatus.ORPHANED,
    )
    corpus = FakeAnchorCorpus()
    corpus.set_chapter_index(source.id, [_index_row("ch1", word_count=250)])

    summaries = _list_notes(notes, sources=sources, corpus=corpus)(user=user, source_id=source.id)

    assert [s.note.title for s in summaries] == ["Orphaned"]
    assert summaries[0].anchor is not None
    assert summaries[0].anchor.quote_exact == "a passage that outlived its section"
    assert summaries[0].page is None


# --- GetBacklinks (NF-10) -------------------------------------------------------


def test_get_backlinks_returns_the_linking_notes() -> None:
    notes = FakeNoteRepository()
    user = _user()
    target = _seed_note(notes, user, title="Target")
    linker = _seed_note(notes, user, title="Linker", body_markdown="see [[Target]]")

    backlinks = GetBacklinks(notes=notes)(user=user, note_id=target.id)

    assert [b.note_id for b in backlinks] == [linker.id]
    assert [b.title for b in backlinks] == ["Linker"]


def test_get_backlinks_is_owner_scoped() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    target = _seed_note(notes, owner, title="Owned")

    with pytest.raises(NoteNotFound):
        GetBacklinks(notes=notes)(user=other, note_id=target.id)


# --- CaptureHighlight (NF-06) ---------------------------------------------------


def _section(  # noqa: ANN001
    anchor: str = "ch1", *, text: str = "The quick brown fox", aliases=()
) -> AnchorSection:
    return AnchorSection(
        anchor=anchor,
        section_path=("Chapter 1",),
        anchor_aliases=tuple(aliases),
        blocks=(AnchorBlockSnapshot(ordinal=0, content_hash="h0", html_fragment=text),),
    )


def _capture(sources, notes, corpus) -> CaptureHighlight:  # noqa: ANN001
    return CaptureHighlight(
        sources=sources,
        notes=notes,
        corpus=corpus,
        markup=IdentityMarkupConverter(),
        authorize=AuthorizeOwnership(),
        clock=FakeClock(),
        ids=uuid4,
        max_body_chars=100000,
    )


def test_capture_highlight_creates_a_note_and_anchor() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="quick brown",
        quote_prefix="the ",
        quote_suffix=" fox",
        title="quick brown",
        body_markdown="",
    )

    assert len(view.anchors) == 1
    anchor = view.anchors[0]
    assert anchor.anchor == "ch1"
    assert anchor.section_path == ("Chapter 1",)
    assert anchor.block_hash == "h0"
    assert anchor.block_ordinal == 0
    assert anchor.quote_exact == "quick brown"
    assert anchor.source_title == "A Book"
    assert anchor.status == NoteAnchorStatus.ACTIVE
    assert view.note.body_markdown == ""  # empty body allowed


def test_capture_highlight_without_a_quote_creates_a_section_level_anchor() -> None:
    # A capture carrying no selection still writes the note and its anchor together;
    # the anchor addresses the section and binds to no block.
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        title="A thought about this chapter",
        body_markdown="",
    )

    assert notes.get_by_id(view.note.id) is not None
    assert len(view.anchors) == 1
    anchor = view.anchors[0]
    assert anchor.anchor == "ch1"
    assert anchor.section_path == ("Chapter 1",)
    assert anchor.quote_exact == ""
    assert anchor.block_hash is None
    assert anchor.block_ordinal is None
    assert anchor.start_offset is None
    assert anchor.end_offset is None
    assert anchor.status == NoteAnchorStatus.ACTIVE
    assert anchor.source_title == "A Book"


def test_capture_highlight_with_a_blank_quote_is_a_section_level_anchor_too() -> None:
    # A selection of pure whitespace is no selection. Treating it as one would send it
    # to the block binder, which cannot match it — the capture would fail as stale, and
    # the whitespace would be snapshotted as if it were the passage.
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="   \n  ",
        title="A thought about this chapter",
        body_markdown="",
    )

    anchor = view.anchors[0]
    assert anchor.quote_exact == ""
    assert anchor.block_hash is None
    assert anchor.status == NoteAnchorStatus.ACTIVE


def test_capture_highlight_without_a_quote_persists_nothing_when_the_body_is_over_cap() -> None:
    # The quote-less path keeps the note and its anchor atomic: a rejected body leaves
    # neither behind.
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})
    capture = CaptureHighlight(
        sources=sources,
        notes=notes,
        corpus=corpus,
        markup=IdentityMarkupConverter(),
        authorize=AuthorizeOwnership(),
        clock=FakeClock(),
        ids=uuid4,
        max_body_chars=10,
    )

    with pytest.raises(NoteBodyTooLong):
        capture(user=user, source_id=source.id, anchor="ch1", title="h", body_markdown="x" * 11)

    assert notes.list_summaries(user.id) == []
    assert notes.anchors_for_source(source.id) == []


def test_capture_highlight_without_a_quote_still_rejects_an_unknown_section() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section("ch1")]})

    with pytest.raises(CorpusNotFound):
        _capture(sources, notes, corpus)(
            user=user, source_id=source.id, anchor="ch-missing", title="h"
        )
    assert notes.list_summaries(user.id) == []


def test_capture_highlight_without_a_quote_still_rejects_an_unowned_source() -> None:
    owner = _user()
    intruder = _user()
    source = _source(owner.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    with pytest.raises(SourceNotFound):
        _capture(sources, notes, corpus)(
            user=intruder, source_id=source.id, anchor="ch1", title="h"
        )
    assert notes.list_summaries(intruder.id) == []


def test_capture_highlight_unknown_source_is_not_found() -> None:
    user = _user()
    sources = FakeSourceRepository()
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus()

    with pytest.raises(SourceNotFound):
        _capture(sources, notes, corpus)(
            user=user,
            source_id=uuid4(),
            anchor="ch1",
            quote_exact="quick brown",
            title="quick brown",
        )


def test_capture_highlight_unknown_anchor_is_not_found() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section("ch1")]})

    with pytest.raises(CorpusNotFound):
        _capture(sources, notes, corpus)(
            user=user,
            source_id=source.id,
            anchor="ch-missing",
            quote_exact="quick brown",
            title="quick brown",
        )


def test_capture_highlight_stale_section_is_conflict() -> None:
    # The served section no longer contains the quote → nothing persists, 409.
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section("ch1", text="entirely different text")]})

    with pytest.raises(StaleCaptureTarget):
        _capture(sources, notes, corpus)(
            user=user,
            source_id=source.id,
            anchor="ch1",
            quote_exact="quick brown",
            title="quick brown",
        )
    assert notes.list_summaries(user.id) == []


def test_capture_highlight_note_body_derives_wikilinks() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    # A prior note the captured note's body links to.
    _seed_note(notes, user, title="Concept")
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="quick brown",
        title="quick brown",
        body_markdown="ties to [[Concept]]",
    )

    links = notes.links_for_note(view.note.id)
    assert [link.target_text for link in links] == ["Concept"]


def test_capture_highlight_records_resolved_and_unresolved_wikilinks() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    target = _seed_note(notes, user, title="Target")
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="quick brown",
        title="quick brown",
        body_markdown="See [[Target]] and [[Missing]].",
    )

    links = notes.links_for_note(view.note.id)
    assert {link.target_text: link.target_note_id for link in links} == {
        "Target": target.id,
        "Missing": None,
    }


def test_capture_highlight_resolves_wikilinks_case_insensitively() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    target = _seed_note(notes, user, title="My Concept")
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="quick brown",
        title="quick brown",
        body_markdown="[[my concept]]",
    )

    links = notes.links_for_note(view.note.id)
    assert [(link.target_text, link.target_note_id) for link in links] == [
        ("my concept", target.id)
    ]


def test_capture_highlight_ignores_a_self_link() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="quick brown",
        title="Self",
        body_markdown="I reference [[Self]].",
    )

    assert notes.links_for_note(view.note.id) == []


def test_capture_highlight_normalizes_tags_lowercase_and_deduped() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    corpus = FakeAnchorCorpus({source.id: [_section()]})

    view = _capture(sources, notes, corpus)(
        user=user,
        source_id=source.id,
        anchor="ch1",
        quote_exact="quick brown",
        title="Tagged",
        tags=["Python", "python", " NOTES ", ""],
    )

    assert view.tags == ("notes", "python")


# --- ReconcileNoteAnchors (NF-07) -----------------------------------------------


def _seed_anchor(
    notes: FakeNoteRepository,
    source_id,  # noqa: ANN001
    *,
    anchor: str = "ch1",
    block_hash: str | None = "h0",
    block_ordinal: int | None = 0,
    start_offset: int | None = 0,
    end_offset: int | None = 11,
    quote_exact: str = "quick brown",
    quote_prefix: str = "the ",
    quote_suffix: str = " fox",
    status: str = NoteAnchorStatus.ACTIVE,
) -> NoteAnchor:
    now = datetime.now(UTC)
    note = _seed_note(notes, _user(), title="anchored")
    row = NoteAnchor(
        id=uuid4(),
        note_id=note.id,
        source_id=source_id,
        source_title="A Book",
        anchor=anchor,
        section_path=("Chapter 1",),
        block_hash=block_hash,
        block_ordinal=block_ordinal,
        start_offset=start_offset,
        end_offset=end_offset,
        quote_exact=quote_exact,
        quote_prefix=quote_prefix,
        quote_suffix=quote_suffix,
        status=status,
        created_at=now,
        updated_at=now,
    )
    return notes.add_anchor(row)


def _reconcile(notes: FakeNoteRepository, corpus: FakeAnchorCorpus) -> ReconcileNoteAnchors:
    return ReconcileNoteAnchors(notes=notes, corpus=corpus, markup=IdentityMarkupConverter())


def _anchor_section(
    anchor: str,
    *,
    content_hash: str | None,
    text: str,
    section_path=("Chapter 1",),  # noqa: ANN001
    aliases=(),  # noqa: ANN001
) -> AnchorSection:
    return AnchorSection(
        anchor=anchor,
        section_path=tuple(section_path),
        anchor_aliases=tuple(aliases),
        blocks=(AnchorBlockSnapshot(ordinal=0, content_hash=content_hash, html_fragment=text),),
    )


def test_reconcile_tier1_block_hash_match_stays_active() -> None:
    # The section resolves and holds a block whose stored hash equals the anchor's:
    # active, offsets provably valid, even though the block text changed around it.
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_anchor(notes, source_id, block_hash="h0")
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch1", content_hash="h0", text="rewritten around")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    result = notes.anchors_for_source(source_id)[0]
    assert result.status == NoteAnchorStatus.ACTIVE
    assert result.anchor == "ch1"
    assert result.block_hash == "h0"


def test_reconcile_tier2_quote_rebinds_in_the_same_section() -> None:
    # Hash changed but the quote is still in the section → active, payload rebound.
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_anchor(notes, source_id, block_hash="old", quote_exact="quick brown")
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch1", content_hash="new", text="the quick brown fox")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    result = notes.anchors_for_source(source_id)[0]
    assert result.status == NoteAnchorStatus.ACTIVE
    assert result.anchor == "ch1"
    assert result.block_hash == "new"  # rebound to the new block


def test_reconcile_tier3_relocates_when_quote_moved() -> None:
    # The anchor's section is gone, but the quote is found in another section → active,
    # anchor rewritten to the found section's canonical anchor.
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_anchor(notes, source_id, anchor="ch1", block_hash="old", quote_exact="quick brown")
    corpus = FakeAnchorCorpus(
        {
            source_id: [
                _anchor_section(
                    "ch2",
                    content_hash="h2",
                    text="the quick brown fox",
                    section_path=("Chapter 2",),
                ),
            ]
        }
    )

    _reconcile(notes, corpus)(source_id=source_id)

    result = notes.anchors_for_source(source_id)[0]
    assert result.status == NoteAnchorStatus.ACTIVE
    assert result.anchor == "ch2"
    assert result.section_path == ("Chapter 2",)


def test_reconcile_tier4_orphans_when_section_and_quote_gone() -> None:
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_anchor(notes, source_id, anchor="ch1", block_hash="old", quote_exact="quick brown")
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch9", content_hash="h9", text="unrelated content")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    assert notes.anchors_for_source(source_id)[0].status == NoteAnchorStatus.ORPHANED


def test_reconcile_stale_when_section_lives_but_quote_gone() -> None:
    # The anchor's section still resolves, but neither the hash nor the quote match and
    # the quote is nowhere else → stale (anchor lives, quote gone).
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_anchor(notes, source_id, anchor="ch1", block_hash="old", quote_exact="quick brown")
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch1", content_hash="new", text="entirely different")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    assert notes.anchors_for_source(source_id)[0].status == NoteAnchorStatus.STALE


def test_reconcile_relocates_alias_aware_and_rewrites_anchor() -> None:
    # The anchor was captured against an anchor normalization later merged into a
    # survivor as an alias; the survivor resolves it and the anchor is rewritten (D-6).
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_anchor(notes, source_id, anchor="old-ch1", block_hash="h0", quote_exact="quick brown")
    corpus = FakeAnchorCorpus(
        {
            source_id: [
                _anchor_section(
                    "ch1",
                    content_hash="h0",
                    text="the quick brown fox",
                    aliases=("old-ch1",),
                ),
            ]
        }
    )

    _reconcile(notes, corpus)(source_id=source_id)

    result = notes.anchors_for_source(source_id)[0]
    assert result.status == NoteAnchorStatus.ACTIVE
    assert result.anchor == "ch1"  # rewritten from the alias to the canonical


def _seed_section_level_anchor(notes: FakeNoteRepository, source_id, *, anchor="ch1"):  # noqa: ANN001, ANN202
    """Seed the anchor a quote-less capture writes: section addressed, nothing bound."""
    return _seed_anchor(
        notes,
        source_id,
        anchor=anchor,
        block_hash=None,
        block_ordinal=None,
        start_offset=None,
        end_offset=None,
        quote_exact="",
        quote_prefix="",
        quote_suffix="",
    )


def test_reconcile_keeps_a_section_level_anchor_active_while_its_section_lives() -> None:
    # There is no quote to rebind, so a rewritten section must not make the anchor
    # stale — the passage it names is the section, and the section is still there.
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_section_level_anchor(notes, source_id)
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch1", content_hash="new", text="entirely rewritten")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    result = notes.anchors_for_source(source_id)[0]
    assert result.status == NoteAnchorStatus.ACTIVE
    assert result.anchor == "ch1"


def test_reconcile_rewrites_a_section_level_anchor_to_the_surviving_canonical_one() -> None:
    # The re-ingest merged the captured anchor into a survivor that now carries it as
    # an alias. With no quote to rebind, the short-circuit must still adopt the
    # survivor's canonical anchor and section path — otherwise the stored anchor keeps
    # naming a section the book no longer has, and the next reconcile orphans it.
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_section_level_anchor(notes, source_id, anchor="old-ch1")
    corpus = FakeAnchorCorpus(
        {
            source_id: [
                _anchor_section(
                    "ch1",
                    content_hash="h0",
                    text="entirely rewritten",
                    section_path=("Chapter One",),
                    aliases=("old-ch1",),
                ),
            ]
        }
    )

    _reconcile(notes, corpus)(source_id=source_id)

    result = notes.anchors_for_source(source_id)[0]
    assert result.status == NoteAnchorStatus.ACTIVE
    assert result.anchor == "ch1"
    assert result.section_path == ("Chapter One",)


def test_reconcile_orphans_a_section_level_anchor_when_its_section_is_gone() -> None:
    notes = FakeNoteRepository()
    source_id = uuid4()
    _seed_section_level_anchor(notes, source_id)
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch9", content_hash="h9", text="unrelated content")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    assert notes.anchors_for_source(source_id)[0].status == NoteAnchorStatus.ORPHANED


def test_reconcile_writes_only_when_the_outcome_changed() -> None:
    # An anchor whose block hash still matches its section keeps active, same anchor,
    # same offsets → nothing is written (write-only-on-change discipline).
    notes = FakeNoteRepository()
    source_id = uuid4()
    anchor = _seed_anchor(notes, source_id, anchor="ch1", block_hash="h0", block_ordinal=0)
    corpus = FakeAnchorCorpus(
        {source_id: [_anchor_section("ch1", content_hash="h0", text="the quick brown fox")]}
    )

    _reconcile(notes, corpus)(source_id=source_id)

    assert anchor.id not in notes.reconciliation_writes


def test_reconcile_no_anchors_is_a_noop() -> None:
    notes = FakeNoteRepository()
    source_id = uuid4()
    corpus = FakeAnchorCorpus({source_id: []})

    _reconcile(notes, corpus)(source_id=source_id)

    assert notes.reconciliation_writes == []
