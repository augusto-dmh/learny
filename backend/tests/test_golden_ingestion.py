"""A2 gate — ingestion golden checks (EVAL-01..04).

Runs each golden fixture EPUB through the real parser + Markdown converter +
chunker via ``BuildCorpus`` and pins the persisted corpus against hand-authored
expectations. This is the layer the parser tests do not reach: the *derived
chunk text*. Pure — no DB, no network (EVAL-10).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Connection, text

from app.infrastructure.db.repositories import SqlAlchemyEmbeddingIndexRepository
from tests.conftest import requires_db
from tests.eval_runner import build_corpus_in_db, run_ingestion, seed_source
from tests.golden_corpus_pt import EXPECTED_PT_GOLDEN_SECTIONS, portuguese_golden_book
from tests.golden_expected import GOLDEN_FIXTURES


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=lambda f: f.name)
def test_metadata_matches_golden(fixture) -> None:  # noqa: ANN001 — GoldenFixture
    # EVAL-01: corpus document metadata equals the golden values (null-safe for the
    # A-2/CORP-01 minimal-metadata fixture).
    built = run_ingestion(fixture.epub())
    assert built.title == fixture.expected.title
    assert built.authors == fixture.expected.authors
    assert built.language == fixture.expected.language


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=lambda f: f.name)
def test_section_structure_matches_golden(fixture) -> None:  # noqa: ANN001
    # EVAL-02: ordered sections' (section_path, anchor, depth) equal the golden
    # structure — position order preserved.
    built = run_ingestion(fixture.epub())
    actual = [
        (record.section.section_path, record.section.anchor, record.section.depth)
        for record in built.sections
    ]
    expected = [
        (section.section_path, section.anchor, section.depth)
        for section in fixture.expected.sections
    ]
    assert actual == expected


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=lambda f: f.name)
def test_derived_chunks_match_golden(fixture) -> None:  # noqa: ANN001
    # EVAL-03: each section's derived chunks (text, section_path, anchor, page_span
    # None) equal the golden chunk expectations, keyed by anchor (stable identity).
    built = run_ingestion(fixture.epub())
    by_anchor = {record.section.anchor: record for record in built.sections}
    for section in fixture.expected.sections:
        record = by_anchor[section.anchor]
        assert tuple(chunk.text for chunk in record.chunks) == section.chunk_texts
        for chunk in record.chunks:
            assert chunk.section_path == section.section_path
            assert chunk.anchor == section.anchor
            assert chunk.page_span is None


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=lambda f: f.name)
def test_block_and_chunk_totals_match_golden(fixture) -> None:  # noqa: ANN001
    # EVAL-04: persisted block/chunk totals equal the golden counts.
    built = run_ingestion(fixture.epub())
    assert built.block_count == fixture.expected.block_count
    assert built.chunk_count == fixture.expected.chunk_count


@requires_db
def test_portuguese_book_ingests_with_portuguese_search_config(db_conn: Connection) -> None:
    # The persisted chunks of the Portuguese book stem in Portuguese: OPF ``pt``
    # resolves to the ``portuguese`` regconfig on every chunk, and the stored
    # chunks carry the golden sections and anchors in reading order.
    _, source = seed_source(db_conn, email=f"golden-pt-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, portuguese_golden_book())
    chunk_ids = [
        chunk.id
        for chunk in SqlAlchemyEmbeddingIndexRepository(db_conn).chunks_for_source(source.id)
    ]

    rows = db_conn.execute(
        text(
            "SELECT c.anchor, c.section_path, c.text, c.search_config FROM corpus_chunks c "
            "JOIN corpus_sections s ON s.id = c.section_id "
            "WHERE c.id = ANY(:ids) ORDER BY s.position, c.chunk_index"
        ),
        {"ids": chunk_ids},
    ).all()

    assert {row.search_config for row in rows} == {"portuguese"}
    assert [(row.anchor, tuple(row.section_path), row.text) for row in rows] == [
        (section["anchor"], section["section_path"], section["chunk_texts"][0])
        for section in EXPECTED_PT_GOLDEN_SECTIONS
    ]
