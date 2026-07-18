"""T4 gate — notes use cases (unit, fakes; NF-04..06 + edges).

Drives Create/Update/Delete/Get/List and CaptureHighlight over in-memory fakes,
pinning: owner scoping (non-owner collapses to ``NoteNotFound``), the body cap,
wikilink derivation (resolved / unresolved / self-link), lowercase tag normalization,
and highlight capture (owned-source + served-section consistency, atomic note+anchor,
empty body allowed, stale/unknown-anchor errors).
"""

from __future__ import annotations

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
    CreateNote,
    DeleteNote,
    GetNote,
    ListNotes,
    UpdateNote,
)
from app.domain.entities import AnchorBlockSnapshot, AnchorSection, NoteAnchorStatus, Source, User
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


def _create(notes: FakeNoteRepository, *, max_body_chars: int = 100000) -> CreateNote:
    return CreateNote(notes=notes, clock=FakeClock(), ids=uuid4, max_body_chars=max_body_chars)


# --- CreateNote (NF-05) ---------------------------------------------------------


def test_create_note_persists_and_returns_the_detail_view() -> None:
    notes = FakeNoteRepository()
    user = _user()

    view = _create(notes)(user=user, title="Reading log", body_markdown="body", tags=[])

    assert view.note.title == "Reading log"
    assert view.note.body_markdown == "body"
    assert notes.get_by_id(view.note.id) is not None


def test_create_note_allows_an_empty_body() -> None:
    notes = FakeNoteRepository()
    user = _user()

    view = _create(notes)(user=user, title="Quote card", body_markdown="", tags=[])

    assert view.note.body_markdown == ""


def test_create_note_rejects_a_body_over_the_cap() -> None:
    notes = FakeNoteRepository()
    user = _user()

    with pytest.raises(NoteBodyTooLong):
        _create(notes, max_body_chars=10)(
            user=user, title="Too long", body_markdown="x" * 11, tags=[]
        )
    # Nothing was persisted.
    assert notes.list_summaries(user.id) == []


def test_create_note_derives_resolved_and_unresolved_wikilinks() -> None:
    notes = FakeNoteRepository()
    user = _user()
    create = _create(notes)
    target = create(user=user, title="Target", body_markdown="", tags=[])

    source = create(
        user=user,
        title="Source",
        body_markdown="See [[Target]] and [[Missing]].",
        tags=[],
    )

    links = notes.links_for_note(source.note.id)
    by_text = {link.target_text: link.target_note_id for link in links}
    assert by_text == {"Target": target.note.id, "Missing": None}


def test_create_note_resolves_wikilinks_case_insensitively() -> None:
    notes = FakeNoteRepository()
    user = _user()
    create = _create(notes)
    target = create(user=user, title="My Concept", body_markdown="", tags=[])

    source = create(user=user, title="Source", body_markdown="[[my concept]]", tags=[])

    links = notes.links_for_note(source.note.id)
    assert [(link.target_text, link.target_note_id) for link in links] == [
        ("my concept", target.note.id)
    ]


def test_create_note_ignores_a_self_link() -> None:
    notes = FakeNoteRepository()
    user = _user()

    view = _create(notes)(
        user=user, title="Self", body_markdown="I reference [[Self]].", tags=[]
    )

    assert notes.links_for_note(view.note.id) == []


def test_create_note_normalizes_tags_lowercase_and_deduped() -> None:
    notes = FakeNoteRepository()
    user = _user()

    view = _create(notes)(
        user=user,
        title="Tagged",
        body_markdown="",
        tags=["Python", "python", " NOTES ", ""],
    )

    assert view.tags == ("notes", "python")


# --- UpdateNote (NF-05) ---------------------------------------------------------


def test_update_note_rewrites_body_tags_and_links() -> None:
    notes = FakeNoteRepository()
    user = _user()
    create = _create(notes)
    target = create(user=user, title="Target", body_markdown="", tags=[])
    note = create(user=user, title="Note", body_markdown="", tags=["old"])

    update = UpdateNote(notes=notes, clock=FakeClock(), max_body_chars=100000)
    view = update(
        user=user,
        note_id=note.note.id,
        title="Note",
        body_markdown="now links [[Target]]",
        tags=["new"],
    )

    assert view.tags == ("new",)
    links = notes.links_for_note(note.note.id)
    assert [link.target_note_id for link in links] == [target.note.id]


def test_update_note_by_non_owner_is_not_found() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    note = _create(notes)(user=owner, title="Owned", body_markdown="", tags=[])

    update = UpdateNote(notes=notes, clock=FakeClock(), max_body_chars=100000)
    with pytest.raises(NoteNotFound):
        update(user=other, note_id=note.note.id, title="Hacked", body_markdown="", tags=[])
    # The owner's note is untouched.
    assert notes.get_by_id(note.note.id).title == "Owned"


# --- DeleteNote / GetNote / ListNotes (NF-05) -----------------------------------


def test_delete_note_owner_scoped() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    note = _create(notes)(user=owner, title="Owned", body_markdown="", tags=[])

    delete = DeleteNote(notes=notes)
    with pytest.raises(NoteNotFound):
        delete(user=other, note_id=note.note.id)
    delete(user=owner, note_id=note.note.id)
    assert notes.get_by_id(note.note.id) is None


def test_get_note_returns_tags_and_is_owner_scoped() -> None:
    notes = FakeNoteRepository()
    owner = _user()
    other = _user()
    note = _create(notes)(user=owner, title="Owned", body_markdown="", tags=["python"])

    get = GetNote(notes=notes)
    assert get(user=owner, note_id=note.note.id).tags == ("python",)
    with pytest.raises(NoteNotFound):
        get(user=other, note_id=note.note.id)


def test_list_notes_filters_by_tag_lowercased() -> None:
    notes = FakeNoteRepository()
    user = _user()
    create = _create(notes)
    create(user=user, title="Tagged", body_markdown="", tags=["python"])
    create(user=user, title="Untagged", body_markdown="", tags=[])

    summaries = ListNotes(notes=notes)(user=user, tag="PYTHON")

    assert [s.note.title for s in summaries] == ["Tagged"]


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
    _create(notes)(user=user, title="Concept", body_markdown="", tags=[])
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
