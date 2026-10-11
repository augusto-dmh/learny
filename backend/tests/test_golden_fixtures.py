"""A1 gate — golden fixture data is well-formed and internally consistent (EVAL-09).

A typo in a hand-authored golden anchor or an off-by-one chunk count is a bug in
the *expectations*, not the pipeline. Catching it here — before any parser or DB
runs — keeps the ingestion/retrieval/citation golden failures meaning "the
pipeline drifted", not "the golden data is wrong". Pure: no parser, no DB.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from tests import golden_corpus_pt
from tests.golden_corpus_pt import (
    EXPECTED_PT_GOLDEN_SECTIONS,
    PT_GOLDEN_PROVENANCE,
    PT_GOLDEN_SECTION_ANCHORS,
    portuguese_golden_book,
)
from tests.golden_expected import (
    CITATION_CASES,
    GOLDEN_FIXTURES,
    GOLDEN_SECTION_ANCHORS,
    PORTUGUESE_CASES,
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


def test_portuguese_book_declares_language_and_provenance() -> None:
    # The book says it is Portuguese where an EPUB reader looks — the OPF
    # ``dc:language`` — and the module that builds it says where the text came
    # from and why it may be redistributed.
    with zipfile.ZipFile(io.BytesIO(portuguese_golden_book())) as archive:
        opf = archive.read("content.opf").decode("utf-8")
        chapter_text = "".join(
            archive.read(anchor).decode("utf-8") for anchor in sorted(PT_GOLDEN_SECTION_ANCHORS)
        )
    assert re.findall(r"<dc:language>([^<]*)</dc:language>", opf) == ["pt"]
    assert "Machado de Assis" in opf

    provenance = golden_corpus_pt.__doc__ or ""
    assert "Project Gutenberg eBook #55752" in provenance
    assert "public domain" in provenance
    assert PT_GOLDEN_PROVENANCE["source"] == "https://www.gutenberg.org/ebooks/55752"
    assert PT_GOLDEN_PROVENANCE["licence"].startswith("public domain")
    # Small by design: a paragraph per chapter, every one of them in the EPUB.
    for section in EXPECTED_PT_GOLDEN_SECTIONS:
        (chunk,) = section["chunk_texts"]
        prose = chunk.split("\n\n", 1)[1]
        assert len(prose) < 400
        assert prose in chapter_text


@pytest.mark.parametrize("case", PORTUGUESE_CASES, ids=lambda c: c.expected_anchor)
def test_portuguese_case_needs_the_stemmer_to_reach_its_section(case) -> None:  # noqa: ANN001
    # A Portuguese case targets a real anchor of the Portuguese book, and each of
    # its inflected words is absent, as a word, from that section — so a match can
    # only come from stemming, never from the literal token.
    assert case.expected_anchor in PT_GOLDEN_SECTION_ANCHORS
    (chunk,) = next(
        s["chunk_texts"] for s in EXPECTED_PT_GOLDEN_SECTIONS if s["anchor"] == case.expected_anchor
    )
    words = set(re.findall(r"\w+", chunk.lower()))
    assert case.inflected
    for word in case.inflected:
        assert word in case.question
        assert word not in words, f"{word!r} occurs verbatim in {case.expected_anchor}"
