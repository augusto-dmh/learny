"""Notes schema — inverse-cascade and constraint proofs (integration, live test DB).

Exercises the 0010 notes schema at the table level (repositories arrive in a later
phase): the CORE INVARIANT that a note and its anchor survive a source delete
(``note_anchors.source_id`` is a bare UUID, no FK — NF-01), per-user tag uniqueness,
the ``note_links.target_note_id`` SET NULL on target-note delete, and the
within-aggregate cascades from ``notes``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, insert, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError

from app.domain.entities import Source, User
from app.infrastructure.db.metadata import (
    note_anchors,
    note_links,
    note_tags,
    notes,
    sources,
    tags,
)
from app.infrastructure.db.repositories import (
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
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
