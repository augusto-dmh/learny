"""A2 gate — ingestion golden checks (EVAL-01..04).

Runs each golden fixture EPUB through the real parser + Markdown converter +
chunker via ``BuildCorpus`` and pins the persisted corpus against hand-authored
expectations. This is the layer the parser tests do not reach: the *derived
chunk text*. Pure — no DB, no network (EVAL-10).
"""

from __future__ import annotations

import pytest

from tests.eval_runner import run_ingestion
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
