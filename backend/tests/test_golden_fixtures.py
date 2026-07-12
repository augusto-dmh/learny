"""A1 gate — golden fixture data is well-formed and internally consistent (EVAL-09).

A typo in a hand-authored golden anchor or an off-by-one chunk count is a bug in
the *expectations*, not the pipeline. Catching it here — before any parser or DB
runs — keeps the ingestion/retrieval/citation golden failures meaning "the
pipeline drifted", not "the golden data is wrong". Pure: no parser, no DB.
"""

from __future__ import annotations

import pytest

from tests.golden_expected import (
    CITATION_CASES,
    GOLDEN_FIXTURES,
    GOLDEN_SECTION_ANCHORS,
    RETRIEVAL_CASES,
)


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=lambda f: f.name)
def test_fixture_builds_nonempty_bytes(fixture) -> None:  # noqa: ANN001 — GoldenFixture
    data = fixture.epub()
    assert isinstance(data, bytes)
    assert len(data) > 0


@pytest.mark.parametrize("fixture", GOLDEN_FIXTURES, ids=lambda f: f.name)
def test_expected_corpus_is_internally_consistent(fixture) -> None:  # noqa: ANN001
    expected = fixture.expected
    anchors = [section.anchor for section in expected.sections]
    # Anchors are the stable citation identity — they must be unique per corpus.
    assert len(anchors) == len(set(anchors)), f"duplicate anchors in {fixture.name}"
    # chunk_count is the sum of every section's authored chunk texts (EVAL-04/03).
    total_chunks = sum(len(section.chunk_texts) for section in expected.sections)
    assert expected.chunk_count == total_chunks
    assert expected.block_count > 0
    assert expected.sections, "a fixture must expect at least one section"


@pytest.mark.parametrize("case", RETRIEVAL_CASES, ids=lambda c: c.expected_anchor)
def test_retrieval_case_targets_a_real_golden_anchor(case) -> None:  # noqa: ANN001
    # A recall case must point at an anchor the golden book actually has (EVAL-09).
    assert case.expected_anchor in GOLDEN_SECTION_ANCHORS


@pytest.mark.parametrize("case", CITATION_CASES, ids=lambda c: c.expected_anchor)
def test_citation_case_targets_a_real_golden_anchor(case) -> None:  # noqa: ANN001
    assert case.expected_anchor in GOLDEN_SECTION_ANCHORS
