"""Notes schema — inverse-cascade and constraint proofs (integration, live test DB).

Exercises the 0010 notes schema at the table level (repositories arrive in a later
phase): the CORE INVARIANT that a note and its anchor survive a source delete
(``note_anchors.source_id`` is a bare UUID, no FK — NF-01), per-user tag uniqueness,
the ``note_links.target_note_id`` SET NULL on target-note delete, and the
within-aggregate cascades from ``notes``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, insert, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError

from app.application.identity import AuthorizeOwnership
from app.application.notes import CaptureHighlight, ReconcileNoteAnchors
from app.domain.entities import (
    CorpusSectionRecord,
    DerivedNoteLink,
    Note,
    NoteAnchor,
    NoteAnchorStatus,
    ParsedBlock,
    ParsedSection,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.metadata import (
    note_anchors,
    note_links,
    note_tags,
    notes,
    sources,
    tags,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.ingestion.markup import Bs4MarkupConverter
from tests.conftest import requires_db

pytestmark = requires_db


def _persist_user(db_conn: Connection, email: str) -> User:
    user = User(id=uuid4(), email=email, created_at=datetime.now(UTC))
    return SqlAlchemyUserRepository(db_conn).add(user)


def _persist_source(db_conn: Connection, user_id: UUID) -> Source:
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
        status="uploaded",
        created_at=now,
        updated_at=now,
    )
    return SqlAlchemySourceRepository(db_conn).add(source)


def _note(
    user_id: UUID,
    *,
    title: str = "My note",
    body: str = "",
    created: datetime | None = None,
) -> Note:
    now = created or datetime.now(UTC)
    return Note(
        id=uuid4(),
        user_id=user_id,
        title=title,
        body_markdown=body,
        created_at=now,
        updated_at=now,
    )


def _anchor(
    note_id: UUID,
    source_id: UUID,
    *,
    anchor: str = "chapter01.xhtml#sec-1",
    section_path: tuple[str, ...] = ("Chapter 1",),
    block_hash: str | None = "a" * 64,
    block_ordinal: int | None = 3,
    start_offset: int | None = 5,
    end_offset: int | None = 12,
    quote_exact: str = "a highlighted quote",
    status: str = NoteAnchorStatus.ACTIVE,
) -> NoteAnchor:
    now = datetime.now(UTC)
    return NoteAnchor(
        id=uuid4(),
        note_id=note_id,
        source_id=source_id,
        source_title="A Book",
        anchor=anchor,
        section_path=section_path,
        block_hash=block_hash,
        block_ordinal=block_ordinal,
        start_offset=start_offset,
        end_offset=end_offset,
        quote_exact=quote_exact,
        quote_prefix="the text before ",
        quote_suffix=" the text after",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _insert_note(db_conn: Connection, user_id: UUID, *, title: str = "My note") -> UUID:
    note_id = uuid4()
    db_conn.execute(
        insert(notes).values(id=note_id, user_id=user_id, title=title, body_markdown="")
    )
    return note_id


def _insert_anchor(db_conn: Connection, note_id: UUID, source_id: UUID) -> UUID:
    anchor_id = uuid4()
    db_conn.execute(
        insert(note_anchors).values(
            id=anchor_id,
            note_id=note_id,
            source_id=source_id,
            source_title="A Book",
            anchor="chapter01.xhtml#sec-1",
            section_path=["Chapter 1"],
            block_hash="a" * 64,
            block_ordinal=3,
            start_offset=5,
            end_offset=12,
            quote_exact="a highlighted quote",
            quote_prefix="the text before ",
            quote_suffix=" the text after",
        )
    )
    return anchor_id


def test_deleting_a_source_leaves_notes_and_anchors_intact(db_conn: Connection) -> None:
    # THE inverse-cascade proof (NF-01): source_id is a bare UUID, so removing the
    # source can never cascade into — and destroy — a user's note or anchor.
    user = _persist_user(db_conn, "inverse-cascade@example.com")
    source = _persist_source(db_conn, user.id)
    note_id = _insert_note(db_conn, user.id)
    anchor_id = _insert_anchor(db_conn, note_id, source.id)

    db_conn.execute(sa_delete(sources).where(sources.c.id == source.id))

    surviving_note = db_conn.execute(
        select(notes.c.id).where(notes.c.id == note_id)
    ).one_or_none()
    surviving_anchor = db_conn.execute(
        select(note_anchors.c.id, note_anchors.c.source_id).where(
            note_anchors.c.id == anchor_id
        )
    ).one_or_none()
    assert surviving_note is not None
    assert surviving_anchor is not None
    # The anchor still points at the now-deleted source by value (snapshot survives).
    assert surviving_anchor.source_id == source.id


def test_tag_name_is_unique_per_user(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "tag-unique@example.com")
    db_conn.execute(insert(tags).values(id=uuid4(), user_id=user.id, name="python"))
    with pytest.raises(IntegrityError):
        db_conn.execute(insert(tags).values(id=uuid4(), user_id=user.id, name="python"))


def test_same_tag_name_allowed_for_different_users(db_conn: Connection) -> None:
    user_a = _persist_user(db_conn, "tag-a@example.com")
    user_b = _persist_user(db_conn, "tag-b@example.com")
    db_conn.execute(insert(tags).values(id=uuid4(), user_id=user_a.id, name="python"))
    # No collision across users — the unique is scoped to (user_id, name).
    db_conn.execute(insert(tags).values(id=uuid4(), user_id=user_b.id, name="python"))


def test_deleting_a_target_note_sets_inbound_links_null(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "link-setnull@example.com")
    source_note = _insert_note(db_conn, user.id, title="Source note")
    target_note = _insert_note(db_conn, user.id, title="Target note")
    link_id = uuid4()
    db_conn.execute(
        insert(note_links).values(
            id=link_id,
            note_id=source_note,
            target_note_id=target_note,
            target_text="Target note",
        )
    )

    db_conn.execute(sa_delete(notes).where(notes.c.id == target_note))

    row = db_conn.execute(
        select(note_links.c.target_note_id, note_links.c.target_text).where(
            note_links.c.id == link_id
        )
    ).one()
    # The link row survives with its text; only the resolved target is cleared.
    assert row.target_note_id is None
    assert row.target_text == "Target note"


def test_deleting_a_note_cascades_its_anchors_tags_and_links(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-cascade@example.com")
    source = _persist_source(db_conn, user.id)
    note_id = _insert_note(db_conn, user.id)
    other_note = _insert_note(db_conn, user.id, title="Other")
    anchor_id = _insert_anchor(db_conn, note_id, source.id)
    tag_id = uuid4()
    db_conn.execute(insert(tags).values(id=tag_id, user_id=user.id, name="python"))
    db_conn.execute(insert(note_tags).values(note_id=note_id, tag_id=tag_id))
    link_id = uuid4()
    db_conn.execute(
        insert(note_links).values(
            id=link_id, note_id=note_id, target_note_id=other_note, target_text="Other"
        )
    )

    db_conn.execute(sa_delete(notes).where(notes.c.id == note_id))

    assert (
        db_conn.execute(
            select(note_anchors.c.id).where(note_anchors.c.id == anchor_id)
        ).one_or_none()
        is None
    )
    assert (
        db_conn.execute(
            select(note_tags.c.note_id).where(note_tags.c.note_id == note_id)
        ).one_or_none()
        is None
    )
    assert (
        db_conn.execute(
            select(note_links.c.id).where(note_links.c.id == link_id)
        ).one_or_none()
        is None
    )
    # The tag itself is user-owned, not note-owned — it survives the note delete.
    assert (
        db_conn.execute(select(tags.c.id).where(tags.c.id == tag_id)).one_or_none()
        is not None
    )


# --- Repository adapter behaviour (NF-04) ---------------------------------------


def test_add_and_get_round_trips_a_note(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-crud@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    note = _note(user.id, title="Reading log", body="body text")

    repo.add(note)

    fetched = repo.get_by_id(note.id)
    assert fetched is not None
    assert (fetched.title, fetched.body_markdown) == ("Reading log", "body text")
    assert fetched.user_id == user.id


def test_update_rewrites_title_and_body(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-update@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    note = _note(user.id)
    repo.add(note)

    later = datetime.now(UTC) + timedelta(minutes=5)
    repo.update(note.id, title="New title", body_markdown="new body", updated_at=later)

    fetched = repo.get_by_id(note.id)
    assert fetched is not None
    assert (fetched.title, fetched.body_markdown) == ("New title", "new body")


def test_set_links_rewrites_the_derived_index(db_conn: Connection) -> None:
    # The derived-index rewrite: a second set_links replaces the prior rows wholesale.
    user = _persist_user(db_conn, "note-links@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    note = _note(user.id, title="Source")
    target = _note(user.id, title="Target")
    repo.add(note)
    repo.add(target)

    repo.set_links(note.id, [DerivedNoteLink(target_text="Target", target_note_id=target.id)])
    repo.set_links(note.id, [DerivedNoteLink(target_text="Broken", target_note_id=None)])

    rows = db_conn.execute(
        select(note_links.c.target_text, note_links.c.target_note_id).where(
            note_links.c.note_id == note.id
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].target_text == "Broken"
    assert rows[0].target_note_id is None


def test_set_tags_get_or_creates_and_reuses_one_tag_per_user(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-tags@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    note_a = _note(user.id, title="A")
    note_b = _note(user.id, title="B")
    repo.add(note_a)
    repo.add(note_b)

    repo.set_tags(note_a.id, user.id, ["python"])
    repo.set_tags(note_b.id, user.id, ["python"])

    # Both notes reference the SAME single tag row (per-user uniqueness).
    tag_count = db_conn.execute(
        select(tags.c.id).where(tags.c.user_id == user.id, tags.c.name == "python")
    ).all()
    assert len(tag_count) == 1
    assert repo.tags_for_note(note_a.id) == ["python"]
    assert repo.tags_for_note(note_b.id) == ["python"]

    # Rewrite drops the old tag membership.
    repo.set_tags(note_a.id, user.id, ["golang"])
    assert repo.tags_for_note(note_a.id) == ["golang"]


def test_resolve_titles_matches_case_insensitively(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-resolve@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    target = _note(user.id, title="My Concept")
    repo.add(target)

    resolved = repo.resolve_titles(user.id, ["MY CONCEPT", "no such note"])

    assert resolved == {"my concept": target.id}


def test_resolve_titles_earliest_note_wins_a_collision(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-resolve-dup@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    base = datetime.now(UTC)
    first = _note(user.id, title="Dup", created=base)
    second = _note(user.id, title="Dup", created=base + timedelta(minutes=1))
    repo.add(first)
    repo.add(second)

    resolved = repo.resolve_titles(user.id, ["dup"])

    assert resolved == {"dup": first.id}


def test_backlinks_returns_distinct_linking_notes(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-backlinks@example.com")
    repo = SqlAlchemyNoteRepository(db_conn)
    target = _note(user.id, title="Target")
    linker = _note(user.id, title="Linker")
    repo.add(target)
    repo.add(linker)
    # Two links from the same note to the target collapse to one backlink.
    repo.set_links(
        linker.id,
        [
            DerivedNoteLink(target_text="Target", target_note_id=target.id),
            DerivedNoteLink(target_text="Target", target_note_id=target.id),
        ],
    )

    backlinks = repo.backlinks(target.id)

    assert [(b.note_id, b.title) for b in backlinks] == [(linker.id, "Linker")]


def test_add_anchor_and_anchors_for_note(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-anchor@example.com")
    source = _persist_source(db_conn, user.id)
    repo = SqlAlchemyNoteRepository(db_conn)
    note = _note(user.id)
    repo.add(note)
    anchor = _anchor(note.id, source.id)

    repo.add_anchor(anchor)

    fetched = repo.anchors_for_note(note.id)
    assert len(fetched) == 1
    assert fetched[0].quote_exact == "a highlighted quote"
    assert fetched[0].block_ordinal == 3
    assert fetched[0].status == NoteAnchorStatus.ACTIVE


def test_anchors_for_source_spans_notes(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-anchor-src@example.com")
    source = _persist_source(db_conn, user.id)
    repo = SqlAlchemyNoteRepository(db_conn)
    note_a = _note(user.id, title="A")
    note_b = _note(user.id, title="B")
    repo.add(note_a)
    repo.add(note_b)
    repo.add_anchor(_anchor(note_a.id, source.id))
    repo.add_anchor(_anchor(note_b.id, source.id))

    anchors = repo.anchors_for_source(source.id)

    assert {a.note_id for a in anchors} == {note_a.id, note_b.id}


def test_update_anchor_reconciliation_writes_only_payload_and_status(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-anchor-reco@example.com")
    source = _persist_source(db_conn, user.id)
    repo = SqlAlchemyNoteRepository(db_conn)
    note = _note(user.id)
    repo.add(note)
    anchor = _anchor(note.id, source.id)
    repo.add_anchor(anchor)

    repo.update_anchor_reconciliation(
        anchor.id,
        anchor="chapter02.xhtml#sec-9",
        section_path=("Chapter 2",),
        block_hash="b" * 64,
        block_ordinal=7,
        start_offset=1,
        end_offset=4,
        status=NoteAnchorStatus.ACTIVE,
    )

    row = db_conn.execute(
        select(note_anchors).where(note_anchors.c.id == anchor.id)
    ).one()
    assert row.anchor == "chapter02.xhtml#sec-9"
    assert row.block_ordinal == 7
    assert tuple(row.section_path) == ("Chapter 2",)
    # The note body is never touched by reconciliation.
    assert repo.get_by_id(note.id).body_markdown == ""


def test_orphan_anchors_for_source_flips_active_to_orphaned(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-orphan@example.com")
    source = _persist_source(db_conn, user.id)
    repo = SqlAlchemyNoteRepository(db_conn)
    note = _note(user.id)
    repo.add(note)
    repo.add_anchor(_anchor(note.id, source.id, status=NoteAnchorStatus.ACTIVE))

    repo.orphan_anchors_for_source(source.id)

    anchors = repo.anchors_for_source(source.id)
    assert [a.status for a in anchors] == [NoteAnchorStatus.ORPHANED]
    # The note survives the orphaning (inverse-cascade invariant).
    assert repo.get_by_id(note.id) is not None


def test_list_summaries_filters_by_tag_and_carries_tags_and_statuses(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "note-list@example.com")
    source = _persist_source(db_conn, user.id)
    repo = SqlAlchemyNoteRepository(db_conn)
    tagged = _note(user.id, title="Tagged")
    untagged = _note(user.id, title="Untagged")
    repo.add(tagged)
    repo.add(untagged)
    repo.set_tags(tagged.id, user.id, ["python", "notes"])
    repo.add_anchor(_anchor(tagged.id, source.id, status=NoteAnchorStatus.STALE))

    summaries = repo.list_summaries(user.id, tag="python")

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.note.id == tagged.id
    assert summary.tags == ("notes", "python")
    assert summary.anchor_statuses == (NoteAnchorStatus.STALE,)


def _corpus_record(
    *,
    position: int,
    anchor: str,
    title: str,
    block_texts: list[str],
    aliases: tuple[str, ...] = (),
) -> CorpusSectionRecord:
    blocks = tuple(
        ParsedBlock(position=index, block_type="paragraph", html_fragment=text)
        for index, text in enumerate(block_texts)
    )
    section = ParsedSection(
        position=position,
        title=title,
        depth=1,
        section_path=(title,),
        anchor=anchor,
        blocks=blocks,
        anchor_aliases=aliases,
    )
    chunk = SectionChunk(
        index=0,
        text="\n\n".join(block_texts),
        section_path=(title,),
        anchor=anchor,
        page_span=None,
    )
    return CorpusSectionRecord(
        section=section,
        markdown="\n\n".join(block_texts),
        chunks=(chunk,),
        block_hashes=tuple(f"hash-{anchor}-{i}" for i in range(len(block_texts))),
    )


def test_blocks_for_section_returns_the_addressed_section_blocks(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "blocks-section@example.com")
    source = _persist_source(db_conn, user.id)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _corpus_record(
                position=0, anchor="ch1", title="One", block_texts=["alpha", "beta"]
            ),
            _corpus_record(position=1, anchor="ch2", title="Two", block_texts=["gamma"]),
        ],
    )

    section = SqlAlchemyCorpusRepository(db_conn).blocks_for_section(source.id, "ch1")

    assert section is not None
    assert section.anchor == "ch1"
    assert [b.html_fragment for b in section.blocks] == ["alpha", "beta"]
    assert section.blocks[0].content_hash == "hash-ch1-0"
    assert SqlAlchemyCorpusRepository(db_conn).blocks_for_section(source.id, "nope") is None


def test_blocks_for_reconcile_returns_all_sections_in_reading_order(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "blocks-reconcile@example.com")
    source = _persist_source(db_conn, user.id)
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _corpus_record(
                position=0,
                anchor="ch1",
                title="One",
                block_texts=["alpha"],
                aliases=("old-ch1",),
            ),
            _corpus_record(
                position=1, anchor="ch2", title="Two", block_texts=["gamma", "delta"]
            ),
        ],
    )

    sections = SqlAlchemyCorpusRepository(db_conn).blocks_for_reconcile(source.id)

    assert [s.anchor for s in sections] == ["ch1", "ch2"]
    assert sections[0].anchor_aliases == ("old-ch1",)
    assert [b.html_fragment for b in sections[1].blocks] == ["gamma", "delta"]


# --- End-to-end capture → re-ingest reconcile (NF-06/07/08) ---------------------

_QUOTE_BLOCK = "<p>The quick brown fox jumps over the lazy dog.</p>"
_QUOTE = "quick brown fox"


def _replace_corpus(db_conn: Connection, source_id: UUID, sections: list) -> None:  # noqa: ANN001
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=sections,
    )


def _capture_quote(db_conn: Connection, user: User, source_id: UUID) -> UUID:
    """Capture a highlight against the ``ch1`` quote block and return its anchor id."""
    view = CaptureHighlight(
        sources=SqlAlchemySourceRepository(db_conn),
        notes=SqlAlchemyNoteRepository(db_conn),
        corpus=SqlAlchemyCorpusRepository(db_conn),
        markup=Bs4MarkupConverter(),
        authorize=AuthorizeOwnership(),
        clock=SystemClock(),
        ids=uuid4,
        max_body_chars=100000,
    )(
        user=user,
        source_id=source_id,
        anchor="ch1",
        quote_exact=_QUOTE,
        title="highlight",
        body_markdown="",
    )
    return view.anchors[0].id


def _reconcile_notes(db_conn: Connection, source_id: UUID) -> None:
    ReconcileNoteAnchors(
        notes=SqlAlchemyNoteRepository(db_conn),
        corpus=SqlAlchemyCorpusRepository(db_conn),
        markup=Bs4MarkupConverter(),
    )(source_id=source_id)


def _anchor_status(db_conn: Connection, anchor_id: UUID) -> str:
    return db_conn.execute(
        select(note_anchors.c.status).where(note_anchors.c.id == anchor_id)
    ).scalar_one()


def _note_exists(db_conn: Connection, note_id: UUID) -> bool:
    row = db_conn.execute(select(notes.c.id).where(notes.c.id == note_id)).one_or_none()
    return row is not None


def test_reconcile_keeps_anchor_active_after_identical_reingest(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "reco-active@example.com")
    source = _persist_source(db_conn, user.id)
    quote_section = _corpus_record(
        position=0, anchor="ch1", title="One", block_texts=[_QUOTE_BLOCK]
    )
    _replace_corpus(db_conn, source.id, [quote_section])
    anchor_id = _capture_quote(db_conn, user, source.id)
    assert _anchor_status(db_conn, anchor_id) == NoteAnchorStatus.ACTIVE

    # Re-ingest the same book (identical corpus), then reconcile.
    _replace_corpus(db_conn, source.id, [quote_section])
    _reconcile_notes(db_conn, source.id)

    assert _anchor_status(db_conn, anchor_id) == NoteAnchorStatus.ACTIVE


def test_reconcile_orphans_anchor_after_mutated_reingest(db_conn: Connection) -> None:
    user = _persist_user(db_conn, "reco-orphan@example.com")
    source = _persist_source(db_conn, user.id)
    _replace_corpus(
        db_conn,
        source.id,
        [_corpus_record(position=0, anchor="ch1", title="One", block_texts=[_QUOTE_BLOCK])],
    )
    anchor_id = _capture_quote(db_conn, user, source.id)

    # Re-ingest a mutated book: the quoted passage is gone and the section renamed.
    _replace_corpus(
        db_conn,
        source.id,
        [
            _corpus_record(
                position=0,
                anchor="ch9",
                title="Rewritten",
                block_texts=["<p>Totally different prose about nothing.</p>"],
            )
        ],
    )
    _reconcile_notes(db_conn, source.id)

    assert _anchor_status(db_conn, anchor_id) == NoteAnchorStatus.ORPHANED
    # The note itself survives the mutation (prose is indestructible).
    note_id = db_conn.execute(
        select(note_anchors.c.note_id).where(note_anchors.c.id == anchor_id)
    ).scalar_one()
    assert _note_exists(db_conn, note_id)


def test_reconcile_orphans_anchors_after_source_delete(db_conn: Connection) -> None:
    # NF-08: deleting a source cascades its corpus away but leaves note_anchors (bare
    # UUID). Reconciling against the now-empty corpus orphans them; the note survives.
    user = _persist_user(db_conn, "reco-delete@example.com")
    source = _persist_source(db_conn, user.id)
    _replace_corpus(
        db_conn,
        source.id,
        [_corpus_record(position=0, anchor="ch1", title="One", block_texts=[_QUOTE_BLOCK])],
    )
    anchor_id = _capture_quote(db_conn, user, source.id)
    note_id = db_conn.execute(
        select(note_anchors.c.note_id).where(note_anchors.c.id == anchor_id)
    ).scalar_one()

    db_conn.execute(sa_delete(sources).where(sources.c.id == source.id))
    _reconcile_notes(db_conn, source.id)

    assert _anchor_status(db_conn, anchor_id) == NoteAnchorStatus.ORPHANED
    assert _note_exists(db_conn, note_id)
