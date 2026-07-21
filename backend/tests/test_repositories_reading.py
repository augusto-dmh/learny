"""A4 gate — reader-core repository adapters (integration, live test DB).

Exercises the read models and writes the chapter-flow reader depends on:

- ``CorpusRepository.get_chapter_index`` — the flat, position-ordered index with
  aliases and persisted word counts; ``None`` when the source has no corpus.
- ``CorpusRepository.get_sections_span`` — the position-bounded chapter body, ordered.
- ``ReadingPositionRepository`` — upsert/get round-trip and last-write-wins overwrite.
- ``NoteRepository.highlights_for_source`` — the caller's highlights on a source,
  scoped to ``(user, source)`` (never another user's or another source's anchors).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.domain.entities import (
    CorpusSectionRecord,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    ParsedSection,
    RecentReadingPosition,
    Source,
    User,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemyReadingPositionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from tests.conftest import requires_db

pytestmark = requires_db


# --- Seeding -------------------------------------------------------------------


def _add_user(db_conn: Connection, email: str) -> UUID:
    user = User(id=uuid4(), email=email, created_at=datetime.now(UTC))
    return SqlAlchemyUserRepository(db_conn).add(user).id


def _persist_source(db_conn: Connection, user_id: UUID) -> UUID:
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source).id


def _section(
    *,
    position: int,
    depth: int,
    anchor: str,
    markdown: str,
    aliases: tuple[str, ...] = (),
) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=f"Section {position}",
            depth=depth,
            section_path=(f"Section {position}",),
            anchor=anchor,
            blocks=(),
            anchor_aliases=aliases,
        ),
        markdown=markdown,
        chunks=(),
    )


def _replace(db_conn: Connection, source_id: UUID, records: list[CorpusSectionRecord]) -> None:
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=records,
    )


def _note(
    db_conn: Connection, user_id: UUID, *, title: str = "Note", body: str = ""
) -> UUID:
    now = datetime.now(UTC)
    note = Note(
        id=uuid4(),
        user_id=user_id,
        title=title,
        body_markdown=body,
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemyNoteRepository(db_conn).add(note).id


def _anchor(
    db_conn: Connection,
    note_id: UUID,
    source_id: UUID,
    *,
    anchor: str = "ch1",
    quote_exact: str = "a quote",
    status: str = NoteAnchorStatus.ACTIVE,
) -> None:
    now = datetime.now(UTC)
    SqlAlchemyNoteRepository(db_conn).add_anchor(
        NoteAnchor(
            id=uuid4(),
            note_id=note_id,
            source_id=source_id,
            source_title="A Book",
            anchor=anchor,
            section_path=("Section 0",),
            block_hash=None,
            block_ordinal=None,
            start_offset=None,
            end_offset=None,
            quote_exact=quote_exact,
            quote_prefix="before ",
            quote_suffix=" after",
            status=status,
            created_at=now,
            updated_at=now,
        )
    )


# --- get_chapter_index ---------------------------------------------------------


def test_get_chapter_index_returns_ordered_rows_with_aliases_and_counts(
    db_conn: Connection,
) -> None:
    user_id = _add_user(db_conn, "reader-index@example.com")
    source_id = _persist_source(db_conn, user_id)
    _replace(
        db_conn,
        source_id,
        [
            _section(position=0, depth=0, anchor="a0", markdown="one two three"),
            _section(position=1, depth=1, anchor="a1", markdown="four five", aliases=("old1",)),
            _section(position=2, depth=0, anchor="a2", markdown="six"),
        ],
    )

    index = SqlAlchemyCorpusRepository(db_conn).get_chapter_index(source_id)

    assert index is not None
    assert [row.position for row in index] == [0, 1, 2]
    assert [row.depth for row in index] == [0, 1, 0]
    assert [row.anchor for row in index] == ["a0", "a1", "a2"]
    assert index[1].anchor_aliases == ("old1",)
    # word_count is the persisted per-section token count of the markdown.
    assert [row.word_count for row in index] == [3, 2, 1]
    assert index[0].section_path == ("Section 0",)


def test_get_chapter_index_returns_none_without_corpus(db_conn: Connection) -> None:
    user_id = _add_user(db_conn, "reader-nocorpus@example.com")
    source_id = _persist_source(db_conn, user_id)
    assert SqlAlchemyCorpusRepository(db_conn).get_chapter_index(source_id) is None


# --- get_sections_span ---------------------------------------------------------


def test_get_sections_span_returns_ordered_sections_in_range(
    db_conn: Connection,
) -> None:
    user_id = _add_user(db_conn, "reader-span@example.com")
    source_id = _persist_source(db_conn, user_id)
    _replace(
        db_conn,
        source_id,
        [
            _section(position=0, depth=0, anchor="a0", markdown="zero"),
            _section(position=1, depth=1, anchor="a1", markdown="one one"),
            _section(position=2, depth=1, anchor="a2", markdown="two two two"),
            _section(position=3, depth=0, anchor="a3", markdown="three"),
        ],
    )

    span = SqlAlchemyCorpusRepository(db_conn).get_sections_span(source_id, 1, 2)

    assert [s.anchor for s in span] == ["a1", "a2"]
    assert span[0].markdown == "one one"
    assert span[0].word_count == 2
    assert span[1].word_count == 3
    assert span[0].section_path == ("Section 1",)


# --- ReadingPositionRepository -------------------------------------------------


def test_reading_position_upsert_then_get_roundtrips(db_conn: Connection) -> None:
    user_id = _add_user(db_conn, "reader-rp-rt@example.com")
    source_id = _persist_source(db_conn, user_id)
    repo = SqlAlchemyReadingPositionRepository(db_conn)
    when = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)

    stored = repo.upsert(
        user_id, source_id, anchor="a1", percent=Decimal("42.50"), updated_at=when
    )
    assert stored.anchor == "a1"
    assert stored.percent == Decimal("42.50")
    assert stored.updated_at == when

    fetched = repo.get(user_id, source_id)
    assert fetched is not None
    assert fetched.anchor == "a1"
    assert fetched.percent == Decimal("42.50")
    assert fetched.updated_at == when


def test_reading_position_get_absent_returns_none(db_conn: Connection) -> None:
    user_id = _add_user(db_conn, "reader-rp-absent@example.com")
    source_id = _persist_source(db_conn, user_id)
    assert SqlAlchemyReadingPositionRepository(db_conn).get(user_id, source_id) is None


def test_reading_position_upsert_overwrites_last_write_wins(db_conn: Connection) -> None:
    user_id = _add_user(db_conn, "reader-rp-lww@example.com")
    source_id = _persist_source(db_conn, user_id)
    repo = SqlAlchemyReadingPositionRepository(db_conn)
    first = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
    second = datetime(2026, 7, 19, 13, 0, 0, tzinfo=UTC)

    repo.upsert(user_id, source_id, anchor="a1", percent=Decimal("10.00"), updated_at=first)
    repo.upsert(user_id, source_id, anchor="a9", percent=Decimal("90.00"), updated_at=second)

    fetched = repo.get(user_id, source_id)
    assert fetched is not None
    # The later write wins on the (user, source) primary key — one row, new values.
    assert fetched.anchor == "a9"
    assert fetched.percent == Decimal("90.00")
    assert fetched.updated_at == second


# --- highlights_for_source -----------------------------------------------------


def test_highlights_for_source_scoped_to_user_and_source(db_conn: Connection) -> None:
    owner = _add_user(db_conn, "reader-hl-owner@example.com")
    other = _add_user(db_conn, "reader-hl-other@example.com")
    source_a = _persist_source(db_conn, owner)
    source_b = _persist_source(db_conn, owner)

    owner_note = _note(db_conn, owner, title="Owner note")
    _anchor(db_conn, owner_note, source_a, anchor="ch1", quote_exact="wanted quote")
    # Same owner, different source — must be excluded when querying source_a.
    _anchor(db_conn, owner_note, source_b, anchor="ch9", quote_exact="other-source quote")
    # Different user, same source_a — must never leak into the owner's highlights.
    other_note = _note(db_conn, other, title="Other note")
    _anchor(db_conn, other_note, source_a, anchor="ch1", quote_exact="intruder quote")

    highlights = SqlAlchemyNoteRepository(db_conn).highlights_for_source(owner, source_a)

    assert len(highlights) == 1
    hit = highlights[0]
    assert hit.note_id == owner_note
    assert hit.anchor == "ch1"
    assert hit.quote_exact == "wanted quote"
    assert hit.quote_prefix == "before "
    assert hit.quote_suffix == " after"
    assert hit.status == NoteAnchorStatus.ACTIVE


def test_highlights_for_source_returns_all_statuses(db_conn: Connection) -> None:
    # The endpoint returns every status (anchor, quote, status); the client paints
    # active-only (RD-28/29), so a stale anchor is still listed here.
    owner = _add_user(db_conn, "reader-hl-status@example.com")
    source_id = _persist_source(db_conn, owner)
    note_id = _note(db_conn, owner)
    _anchor(db_conn, note_id, source_id, anchor="ch1", quote_exact="active one")
    _anchor(
        db_conn,
        note_id,
        source_id,
        anchor="ch2",
        quote_exact="stale one",
        status=NoteAnchorStatus.STALE,
    )

    highlights = SqlAlchemyNoteRepository(db_conn).highlights_for_source(owner, source_id)

    assert {h.status for h in highlights} == {
        NoteAnchorStatus.ACTIVE,
        NoteAnchorStatus.STALE,
    }


# --- rail labelling: note title + has-body (CAP-19) ----------------------------


def test_highlights_carry_their_origin_note_title(db_conn: Connection) -> None:
    """The rail labels each entry with the note it belongs to, from this one query."""
    owner = _add_user(db_conn, "reader-hl-title@example.com")
    source_id = _persist_source(db_conn, owner)
    note_id = _note(db_conn, owner, title="On attention")
    _anchor(db_conn, note_id, source_id, anchor="ch1", quote_exact="a quote")

    highlights = SqlAlchemyNoteRepository(db_conn).highlights_for_source(owner, source_id)

    assert len(highlights) == 1
    assert highlights[0].note_title == "On attention"


def test_highlights_report_whether_their_note_has_a_body(db_conn: Connection) -> None:
    """A bare highlight and an annotated one are different rail entries, so the flag
    distinguishes real prose from an empty body."""
    owner = _add_user(db_conn, "reader-hl-body@example.com")
    source_id = _persist_source(db_conn, owner)
    annotated = _note(db_conn, owner, title="Annotated", body="Why this matters.")
    bare = _note(db_conn, owner, title="Bare", body="")
    _anchor(db_conn, annotated, source_id, anchor="ch1", quote_exact="annotated quote")
    _anchor(db_conn, bare, source_id, anchor="ch2", quote_exact="bare quote")

    highlights = SqlAlchemyNoteRepository(db_conn).highlights_for_source(owner, source_id)

    by_title = {h.note_title: h.has_body for h in highlights}
    assert by_title == {"Annotated": True, "Bare": False}


def test_whitespace_only_note_body_does_not_count_as_a_body(
    db_conn: Connection,
) -> None:
    """A body of blank lines is not an annotation — it would label an empty entry."""
    owner = _add_user(db_conn, "reader-hl-blank@example.com")
    source_id = _persist_source(db_conn, owner)
    note_id = _note(db_conn, owner, title="Blank", body="   \n\t  ")
    _anchor(db_conn, note_id, source_id, anchor="ch1", quote_exact="a quote")

    highlights = SqlAlchemyNoteRepository(db_conn).highlights_for_source(owner, source_id)

    assert highlights[0].has_body is False


# --- most_recent_for_user (HOME-01/04) -----------------------------------------


def _persist_titled_source(db_conn: Connection, user_id: UUID, title: str) -> UUID:
    now = datetime.now(UTC)
    source = Source(
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
    return SqlAlchemySourceRepository(db_conn).add(source).id


def test_most_recent_for_user_returns_latest_across_sources_with_title(
    db_conn: Connection,
) -> None:
    user_id = _add_user(db_conn, "reader-mru@example.com")
    older = _persist_titled_source(db_conn, user_id, "Older Book")
    newer = _persist_titled_source(db_conn, user_id, "Newer Book")
    repo = SqlAlchemyReadingPositionRepository(db_conn)
    t_old = datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC)
    t_new = datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC)
    repo.upsert(user_id, older, anchor="a1", percent=Decimal("10.00"), updated_at=t_old)
    repo.upsert(user_id, newer, anchor="a2", percent=Decimal("55.00"), updated_at=t_new)

    recent = repo.most_recent_for_user(user_id)

    assert recent == RecentReadingPosition(
        source_id=newer,
        source_title="Newer Book",
        anchor="a2",
        percent=Decimal("55.00"),
        updated_at=t_new,
    )


def test_most_recent_for_user_returns_none_without_positions(
    db_conn: Connection,
) -> None:
    user_id = _add_user(db_conn, "reader-mru-none@example.com")
    _persist_titled_source(db_conn, user_id, "A Book")  # source but no position
    assert SqlAlchemyReadingPositionRepository(db_conn).most_recent_for_user(user_id) is None


def test_most_recent_for_user_never_returns_another_users_position(
    db_conn: Connection,
) -> None:
    # HOME-04: another user's (even more recent) position is unreachable — the query is
    # scoped to the caller's own user_id in SQL.
    caller = _add_user(db_conn, "reader-mru-caller@example.com")
    other = _add_user(db_conn, "reader-mru-other@example.com")
    caller_source = _persist_titled_source(db_conn, caller, "Caller Book")
    other_source = _persist_titled_source(db_conn, other, "Other Book")
    repo = SqlAlchemyReadingPositionRepository(db_conn)
    repo.upsert(
        caller,
        caller_source,
        anchor="a1",
        percent=Decimal("10.00"),
        updated_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
    )
    # The other user's position is strictly more recent, yet must never surface.
    repo.upsert(
        other,
        other_source,
        anchor="a2",
        percent=Decimal("90.00"),
        updated_at=datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC),
    )

    recent = repo.most_recent_for_user(caller)

    assert recent is not None
    assert recent.source_id == caller_source
    assert recent.source_title == "Caller Book"


def test_most_recent_for_user_breaks_ties_deterministically(
    db_conn: Connection,
) -> None:
    # Two positions saved at the identical instant must resolve to one stable winner
    # (source_id DESC), never a nondeterministic pick.
    user_id = _add_user(db_conn, "reader-mru-tie@example.com")
    source_a = _persist_titled_source(db_conn, user_id, "Book A")
    source_b = _persist_titled_source(db_conn, user_id, "Book B")
    repo = SqlAlchemyReadingPositionRepository(db_conn)
    same = datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC)
    repo.upsert(user_id, source_a, anchor="a1", percent=Decimal("1.00"), updated_at=same)
    repo.upsert(user_id, source_b, anchor="a2", percent=Decimal("2.00"), updated_at=same)

    expected = max(source_a, source_b)  # the deterministic source_id DESC winner
    recent = repo.most_recent_for_user(user_id)

    assert recent is not None
    assert recent.source_id == expected


def test_most_recent_for_user_falls_back_when_top_source_deleted(
    db_conn: Connection,
) -> None:
    # A deleted source cascades its position away, so the query returns the next most
    # recent — never a dangling reference to the gone source.
    user_id = _add_user(db_conn, "reader-mru-cascade@example.com")
    older = _persist_titled_source(db_conn, user_id, "Older Book")
    newer = _persist_titled_source(db_conn, user_id, "Newer Book")
    repo = SqlAlchemyReadingPositionRepository(db_conn)
    repo.upsert(
        user_id,
        older,
        anchor="a1",
        percent=Decimal("10.00"),
        updated_at=datetime(2026, 7, 19, 10, 0, 0, tzinfo=UTC),
    )
    repo.upsert(
        user_id,
        newer,
        anchor="a2",
        percent=Decimal("55.00"),
        updated_at=datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC),
    )

    db_conn.execute(text("DELETE FROM sources WHERE id = :sid"), {"sid": newer})

    recent = repo.most_recent_for_user(user_id)

    assert recent is not None
    assert recent.source_id == older
