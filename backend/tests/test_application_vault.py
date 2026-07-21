"""T16 gate — ``ExportVault`` service grouping (unit, fakes; NL-16/20).

Pins the framework-free gather step: notes carry their own anchors (grouped by note),
all anchors group by the source they cite (for the book files), a note with no anchors
yields an empty tuple, and only the caller's own data is returned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.application.vault import ExportVault
from app.domain.entities import Note, NoteAnchor, NoteAnchorStatus, User
from tests.fakes import FakeNoteRepository

_NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)


def _user() -> User:
    return User(id=uuid4(), email="reader@example.com", created_at=_NOW)


def _note(user_id, *, title: str = "Note") -> Note:
    return Note(
        id=uuid4(),
        user_id=user_id,
        title=title,
        body_markdown="body",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _anchor(note_id, source_id, *, quote: str = "q") -> NoteAnchor:
    return NoteAnchor(
        id=uuid4(),
        note_id=note_id,
        source_id=source_id,
        source_title="Book",
        anchor="ch1",
        section_path=("A",),
        block_hash=None,
        block_ordinal=None,
        start_offset=None,
        end_offset=None,
        quote_exact=quote,
        quote_prefix="",
        quote_suffix="",
        status=NoteAnchorStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_groups_anchors_by_note_and_by_source() -> None:
    repo = FakeNoteRepository()
    user = _user()
    first = _note(user.id, title="A")
    second = _note(user.id, title="B")
    bare = _note(user.id, title="C")
    for note in (first, second, bare):
        repo.add(note)
    shared_source = uuid4()
    other_source = uuid4()
    a1 = repo.add_anchor(_anchor(first.id, shared_source))
    a2 = repo.add_anchor(_anchor(second.id, shared_source))
    a3 = repo.add_anchor(_anchor(second.id, other_source))

    views, by_source = ExportVault(notes=repo)(user=user)

    anchors_by_note = {v.note.id: {a.id for a in v.anchors} for v in views}
    assert anchors_by_note[first.id] == {a1.id}
    assert anchors_by_note[second.id] == {a2.id, a3.id}
    assert anchors_by_note[bare.id] == set()  # a note with no anchors
    assert {a.id for a in by_source[shared_source]} == {a1.id, a2.id}
    assert {a.id for a in by_source[other_source]} == {a3.id}


def test_returns_only_the_callers_notes_and_anchors() -> None:
    repo = FakeNoteRepository()
    caller, intruder = _user(), _user()
    mine = repo.add(_note(caller.id, title="Mine"))
    theirs = repo.add(_note(intruder.id, title="Theirs"))
    repo.add_anchor(_anchor(mine.id, uuid4()))
    repo.add_anchor(_anchor(theirs.id, uuid4()))

    views, by_source = ExportVault(notes=repo)(user=caller)

    assert [v.note.id for v in views] == [mine.id]
    assert all(
        anchor.note_id == mine.id for anchors in by_source.values() for anchor in anchors
    )


def test_user_with_no_notes_yields_empty_collections() -> None:
    views, by_source = ExportVault(notes=FakeNoteRepository())(user=_user())
    assert views == []
    assert by_source == {}
