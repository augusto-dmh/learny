"""A5 gate — reader-core use cases (unit, in-memory fakes).

Drives ``ReadChapter``, ``SaveReadingPosition``, and ``ListSourceHighlights`` over the
fakes, asserting the spec ACs and edges without a DB:

- Ownership collapse: a missing source and a non-owner both raise ``SourceNotFound``
  (no existence disclosure), for every use case (RD-02).
- ``ReadChapter``: assembles the chapter containing an anchor (shape, prev/next, word
  sums), resolves an alias to its canonical chapter, 404s an unknown anchor and an
  empty corpus, resumes the stored chapter, and falls back to the first chapter when
  there is no stored position or the stored anchor is stale (row untouched) (RD-01/10).
- ``SaveReadingPosition``: stores the canonical anchor + server-computed percent, an
  alias write normalizes to canonical, and an unknown anchor / empty corpus 404s with
  nothing stored (RD-08/09).
- ``ListSourceHighlights``: returns the owner's ``(user, source)`` highlights (RD-28).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.errors import CorpusNotFound, SourceNotFound
from app.application.identity import AuthorizeOwnership
from app.application.reading import (
    ListSourceHighlights,
    ReadChapter,
    SaveReadingPosition,
)
from app.domain.entities import (
    CorpusSectionRecord,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    ParsedSection,
    Source,
    User,
)
from tests.fakes import (
    FakeClock,
    FakeCorpusRepository,
    FakeNoteRepository,
    FakeReadingPositionRepository,
    FakeSourceRepository,
)

_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)


def _user() -> User:
    return User(id=uuid4(), email="reader@example.com", created_at=_NOW)


def _source(user_id) -> Source:  # noqa: ANN001
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="ready",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _record(position, depth, anchor, markdown, aliases=()) -> CorpusSectionRecord:  # noqa: ANN001
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=f"Section {position}",
            depth=depth,
            section_path=(f"Section {position}",),
            anchor=anchor,
            blocks=(),
            anchor_aliases=tuple(aliases),
        ),
        markdown=markdown,
        chunks=(),
    )


# The book both progress paths run over: two chapters (depths 0,1,0,1), word counts
# 3,2,1,4 (total 10), with "c2" also resolvable by the alias "old-c2".
def _seed_book(corpus: FakeCorpusRepository, source_id) -> None:  # noqa: ANN001
    corpus.replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _record(0, 0, "c1", "a b c"),
            _record(1, 1, "c1s1", "d e"),
            _record(2, 0, "c2", "f", aliases=("old-c2",)),
            _record(3, 1, "c2s1", "g h i j"),
        ],
    )


def _read_chapter(sources, corpus, positions) -> ReadChapter:  # noqa: ANN001
    return ReadChapter(
        sources=sources, corpus=corpus, positions=positions, authorize=AuthorizeOwnership()
    )


def _save_position(sources, corpus, positions) -> SaveReadingPosition:  # noqa: ANN001
    return SaveReadingPosition(
        sources=sources,
        corpus=corpus,
        positions=positions,
        authorize=AuthorizeOwnership(),
        clock=FakeClock(_NOW),
    )


# --- ReadChapter: assembly -----------------------------------------------------


def test_read_chapter_assembles_the_chapter_containing_the_anchor() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)

    content, position = _read_chapter(sources, corpus, FakeReadingPositionRepository())(
        user=user, source_id=source.id, anchor="c1s1"
    )

    assert content.chapter_index == 0
    assert content.chapter_count == 2
    assert content.chapter_anchor == "c1"
    assert content.chapter_title == "Section 0"
    assert content.prev_anchor is None
    assert content.next_anchor == "c2"
    assert content.words_before_chapter == 0
    assert content.chapter_word_count == 5
    assert content.total_word_count == 10
    assert [s.anchor for s in content.sections] == ["c1", "c1s1"]
    assert position is None


def test_read_chapter_second_chapter_has_prev_and_word_offset() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)

    content, _ = _read_chapter(sources, corpus, FakeReadingPositionRepository())(
        user=user, source_id=source.id, anchor="c2"
    )

    assert content.chapter_index == 1
    assert content.prev_anchor == "c1"
    assert content.next_anchor is None
    assert content.words_before_chapter == 5
    assert content.chapter_word_count == 5
    assert [s.anchor for s in content.sections] == ["c2", "c2s1"]


def test_read_chapter_resolves_an_alias_to_its_canonical_chapter() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)

    content, _ = _read_chapter(sources, corpus, FakeReadingPositionRepository())(
        user=user, source_id=source.id, anchor="old-c2"
    )

    assert content.chapter_anchor == "c2"
    assert content.chapter_index == 1


def test_read_chapter_unknown_anchor_raises_corpus_not_found() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)

    with pytest.raises(CorpusNotFound):
        _read_chapter(sources, corpus, FakeReadingPositionRepository())(
            user=user, source_id=source.id, anchor="missing"
        )


def test_read_chapter_empty_corpus_raises_corpus_not_found() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)

    with pytest.raises(CorpusNotFound):
        _read_chapter(sources, FakeCorpusRepository(), FakeReadingPositionRepository())(
            user=user, source_id=source.id, anchor=None
        )


# --- ReadChapter: resume -------------------------------------------------------


def test_read_chapter_resume_loads_the_stored_position_chapter() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    positions = FakeReadingPositionRepository()
    positions.upsert(
        user.id, source.id, anchor="c2", percent=Decimal("50.00"), updated_at=_NOW
    )

    content, stored = _read_chapter(sources, corpus, positions)(
        user=user, source_id=source.id, anchor=None
    )

    assert content.chapter_index == 1
    assert stored is not None
    assert stored.anchor == "c2"
    assert stored.percent == Decimal("50.00")


def test_read_chapter_resume_without_stored_loads_first_chapter() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)

    content, stored = _read_chapter(sources, corpus, FakeReadingPositionRepository())(
        user=user, source_id=source.id, anchor=None
    )

    assert content.chapter_index == 0
    assert stored is None


def test_read_chapter_stale_stored_anchor_falls_back_without_writing() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    positions = FakeReadingPositionRepository()
    positions.upsert(
        user.id, source.id, anchor="gone", percent=Decimal("77.00"), updated_at=_NOW
    )
    positions.upsert_calls.clear()

    content, stored = _read_chapter(sources, corpus, positions)(
        user=user, source_id=source.id, anchor=None
    )

    # Falls back to the first chapter; the stale row is returned unchanged and never
    # rewritten (ReadChapter never writes a position).
    assert content.chapter_index == 0
    assert stored is not None
    assert stored.anchor == "gone"
    assert positions.upsert_calls == []


# --- ReadChapter: ownership ----------------------------------------------------


def test_read_chapter_missing_and_non_owner_both_raise_source_not_found() -> None:
    owner = _user()
    intruder = _user()
    source = _source(owner.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    read = _read_chapter(sources, corpus, FakeReadingPositionRepository())

    with pytest.raises(SourceNotFound):
        read(user=intruder, source_id=source.id, anchor="c1")
    with pytest.raises(SourceNotFound):
        read(user=owner, source_id=uuid4(), anchor="c1")


# --- SaveReadingPosition -------------------------------------------------------


def test_save_reading_position_stores_canonical_anchor_and_percent() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    positions = FakeReadingPositionRepository()

    stored = _save_position(sources, corpus, positions)(
        user=user, source_id=source.id, anchor="c1s1"
    )

    # percent = words before row 1 (3) / total (10) * 100 = 30.00.
    assert stored.anchor == "c1s1"
    assert stored.percent == Decimal("30.00")
    assert stored.updated_at == _NOW
    assert positions.get(user.id, source.id) == stored


def test_save_reading_position_alias_write_stores_canonical() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    positions = FakeReadingPositionRepository()

    stored = _save_position(sources, corpus, positions)(
        user=user, source_id=source.id, anchor="old-c2"
    )

    # The alias "old-c2" normalizes to the canonical "c2"; percent = 5/10*100 = 50.00.
    assert stored.anchor == "c2"
    assert stored.percent == Decimal("50.00")


def test_save_reading_position_unknown_anchor_404s_and_stores_nothing() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    positions = FakeReadingPositionRepository()

    with pytest.raises(CorpusNotFound):
        _save_position(sources, corpus, positions)(
            user=user, source_id=source.id, anchor="missing"
        )
    assert positions.upsert_calls == []


def test_save_reading_position_empty_corpus_404s_and_stores_nothing() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    positions = FakeReadingPositionRepository()

    with pytest.raises(CorpusNotFound):
        _save_position(sources, FakeCorpusRepository(), positions)(
            user=user, source_id=source.id, anchor="c1"
        )
    assert positions.upsert_calls == []


def test_save_reading_position_non_owner_raises_source_not_found() -> None:
    owner = _user()
    intruder = _user()
    source = _source(owner.id)
    sources = FakeSourceRepository()
    sources.add(source)
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source.id)
    positions = FakeReadingPositionRepository()

    with pytest.raises(SourceNotFound):
        _save_position(sources, corpus, positions)(
            user=intruder, source_id=source.id, anchor="c1"
        )
    assert positions.upsert_calls == []


# --- ListSourceHighlights ------------------------------------------------------


def _list_highlights(sources, notes) -> ListSourceHighlights:  # noqa: ANN001
    return ListSourceHighlights(
        sources=sources, notes=notes, authorize=AuthorizeOwnership()
    )


def test_list_source_highlights_returns_owner_highlights() -> None:
    user = _user()
    source = _source(user.id)
    sources = FakeSourceRepository()
    sources.add(source)
    notes = FakeNoteRepository()
    note = Note(
        id=uuid4(),
        user_id=user.id,
        title="Note",
        body_markdown="",
        created_at=_NOW,
        updated_at=_NOW,
    )
    notes.add(note)
    notes.add_anchor(
        NoteAnchor(
            id=uuid4(),
            note_id=note.id,
            source_id=source.id,
            source_title="A Book",
            anchor="c1",
            section_path=("Section 0",),
            block_hash=None,
            block_ordinal=None,
            start_offset=None,
            end_offset=None,
            quote_exact="a quote",
            quote_prefix="before ",
            quote_suffix=" after",
            status=NoteAnchorStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )

    highlights = _list_highlights(sources, notes)(user=user, source_id=source.id)

    assert len(highlights) == 1
    assert highlights[0].note_id == note.id
    assert highlights[0].anchor == "c1"
    assert highlights[0].quote_exact == "a quote"
    assert highlights[0].status == NoteAnchorStatus.ACTIVE


def test_list_source_highlights_non_owner_raises_source_not_found() -> None:
    owner = _user()
    intruder = _user()
    source = _source(owner.id)
    sources = FakeSourceRepository()
    sources.add(source)

    with pytest.raises(SourceNotFound):
        _list_highlights(sources, FakeNoteRepository())(
            user=intruder, source_id=source.id
        )
