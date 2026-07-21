"""Silver case resolution against the pgvector test DB (DEEP-01/02/18).

Integration: seeds sources + corpus rows directly (full control over checksum,
``created_at``, anchors, and aliases) so every resolution branch is exercised —
checksum hit/miss, duplicate-checksum determinism, anchor hit, alias hit, and the
broken-anchor case that must stay distinct from a skip. Uses the transactional
``db_conn`` fixture, so it self-skips when ``LEARNY_TEST_DATABASE_URL`` is unset
and rolls back after each test.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Connection, insert

from app.infrastructure.db.metadata import (
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    sources,
    users,
)
from tests.eval.silver import (
    BrokenCase,
    ResolvedCase,
    SilverCase,
    SkippedCase,
    resolve_case,
)

_CHECKSUM = "a" * 64


def _case(checksum: str = _CHECKSUM, anchors: Sequence[str] = ("ch1.xhtml",)) -> SilverCase:
    return SilverCase(
        case_id="c1",
        question="Q?",
        source_checksum=checksum,
        expected_anchors=tuple(anchors),
        expected_snippet="snippet",
        language="english",
    )


def _seed_book(
    conn: Connection,
    *,
    checksum: str,
    created_at: datetime,
    sections: Sequence[dict],
) -> tuple[str, dict[str, list[str]]]:
    """Insert a user + source + corpus document with the given sections.

    ``sections`` items are ``{"anchor", "aliases"?, "chunks": [text, ...]}``.
    Returns the source id and a map of section anchor -> its chunk ids (as str).
    """
    user_id = uuid4()
    conn.execute(
        insert(users).values(
            id=user_id, email=f"silver-{user_id}@example.com", created_at=created_at
        )
    )
    source_id = uuid4()
    conn.execute(
        insert(sources).values(
            id=source_id,
            user_id=user_id,
            title="Book",
            filename="book.epub",
            content_type="application/epub+zip",
            byte_size=1,
            checksum=checksum,
            object_key=f"sources/{user_id}/{uuid4()}.epub",
            status="ready",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    doc_id = uuid4()
    conn.execute(insert(corpus_documents).values(id=doc_id, source_id=source_id))

    chunk_ids_by_anchor: dict[str, list[str]] = {}
    for position, section in enumerate(sections):
        section_id = uuid4()
        path = ["Book", f"S{position}"]
        conn.execute(
            insert(corpus_sections).values(
                id=section_id,
                document_id=doc_id,
                position=position,
                depth=0,
                title=f"Section {position}",
                section_path=path,
                anchor=section["anchor"],
                anchor_aliases=list(section.get("aliases", ())),
                markdown="body",
                word_count=1,
            )
        )
        ids: list[str] = []
        for chunk_index, text in enumerate(section["chunks"]):
            chunk_id = uuid4()
            conn.execute(
                insert(corpus_chunks).values(
                    id=chunk_id,
                    section_id=section_id,
                    chunk_index=chunk_index,
                    text=text,
                    section_path=path,
                    anchor=section["anchor"],
                )
            )
            ids.append(str(chunk_id))
        chunk_ids_by_anchor[section["anchor"]] = ids
    return str(source_id), chunk_ids_by_anchor


def test_checksum_and_anchor_hit_resolves(db_conn: Connection) -> None:
    source_id, chunks = _seed_book(
        db_conn,
        checksum=_CHECKSUM,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[{"anchor": "ch1.xhtml", "chunks": ["alpha", "beta"]}],
    )

    resolved = resolve_case(db_conn, _case(anchors=("ch1.xhtml",)))

    assert isinstance(resolved, ResolvedCase)
    assert resolved.source_id == source_id
    assert set(resolved.expected_chunk_ids) == set(chunks["ch1.xhtml"])


def test_absent_book_is_skipped(db_conn: Connection) -> None:
    # Seed a different checksum so the DB is non-empty but the case's book is absent.
    _seed_book(
        db_conn,
        checksum="b" * 64,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[{"anchor": "ch1.xhtml", "chunks": ["x"]}],
    )

    result = resolve_case(db_conn, _case(checksum="c" * 64))

    assert isinstance(result, SkippedCase)
    assert "c" * 64 in result.reason


def test_duplicate_checksum_resolves_to_latest_created_at(db_conn: Connection) -> None:
    older_id, older_chunks = _seed_book(
        db_conn,
        checksum=_CHECKSUM,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[{"anchor": "ch1.xhtml", "chunks": ["old"]}],
    )
    newer_id, newer_chunks = _seed_book(
        db_conn,
        checksum=_CHECKSUM,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        sections=[{"anchor": "ch1.xhtml", "chunks": ["new"]}],
    )

    resolved = resolve_case(db_conn, _case(anchors=("ch1.xhtml",)))

    assert isinstance(resolved, ResolvedCase)
    # The newer source wins deterministically; its chunk (not the older one) is used.
    assert resolved.source_id == newer_id
    assert resolved.source_id != older_id
    assert set(resolved.expected_chunk_ids) == set(newer_chunks["ch1.xhtml"])
    assert set(resolved.expected_chunk_ids).isdisjoint(older_chunks["ch1.xhtml"])


def test_anchor_resolves_through_alias(db_conn: Connection) -> None:
    source_id, chunks = _seed_book(
        db_conn,
        checksum=_CHECKSUM,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[
            {"anchor": "ch2-new.xhtml", "aliases": ["ch2-old.xhtml"], "chunks": ["gamma"]}
        ],
    )

    # The case cites the pre-reingest anchor, kept resolvable as an alias (AD-085).
    resolved = resolve_case(db_conn, _case(anchors=("ch2-old.xhtml",)))

    assert isinstance(resolved, ResolvedCase)
    assert resolved.source_id == source_id
    assert set(resolved.expected_chunk_ids) == set(chunks["ch2-new.xhtml"])


def test_unresolvable_anchor_is_broken_not_skipped(db_conn: Connection) -> None:
    source_id, _ = _seed_book(
        db_conn,
        checksum=_CHECKSUM,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[{"anchor": "ch1.xhtml", "chunks": ["alpha"]}],
    )

    result = resolve_case(db_conn, _case(anchors=("ch99.xhtml",)))

    assert isinstance(result, BrokenCase)
    assert result.anchor == "ch99.xhtml"
    # Broken carries the resolved source id — the book is present, the anchor is stale.
    assert result.source_id == source_id


def test_partial_anchor_miss_is_broken_on_the_missing_one(db_conn: Connection) -> None:
    _seed_book(
        db_conn,
        checksum=_CHECKSUM,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[{"anchor": "ch1.xhtml", "chunks": ["alpha"]}],
    )

    result = resolve_case(db_conn, _case(anchors=("ch1.xhtml", "ch2.xhtml")))

    assert isinstance(result, BrokenCase)
    assert result.anchor == "ch2.xhtml"
