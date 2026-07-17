"""Versioned golden expectations for the Cycle-8 evaluation harness (EVAL-09).

Hand-authored expected values — the golden targets the real pipeline is checked
against. They are deliberately *not* derived by running any part of the pipeline
(that would make the check a tautology): every value here is written by hand and
keyed on stable identity (``anchor``/``section_path``/snippet text), never on
per-run chunk UUIDs (AD-038). A drift between these constants and actual pipeline
output fails the corresponding golden check with a readable diff.

Ingestion golden covers two fixtures: the topically-rich ``golden_book`` (full
metadata + structure + derived chunks) and the metadata-sparse ``no_toc_book``
(the A-2 heading/href-stem fallback and null OPF metadata, end to end). Retrieval
and citation cases run against ``golden_book`` only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tests.fixtures_epub import no_toc_book
from tests.golden_corpus import (
    CH1_ANCHOR,
    CH2_ANCHOR,
    CH3_ANCHOR,
    EXPECTED_GOLDEN_BLOCK_COUNT,
    EXPECTED_GOLDEN_CHUNK_COUNT,
    EXPECTED_GOLDEN_SECTIONS,
    GOLDEN_AUTHORS,
    GOLDEN_LANGUAGE,
    GOLDEN_SECTION_ANCHORS,
    GOLDEN_TITLE,
    golden_book,
)


@dataclass(frozen=True)
class ExpectedCorpusSection:
    """One section's golden identity + derived-chunk texts (EVAL-02/03)."""

    section_path: tuple[str, ...]
    anchor: str
    depth: int
    chunk_texts: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedCorpus:
    """A fixture's golden ingestion output (EVAL-01..04)."""

    title: str | None
    authors: tuple[str, ...]
    language: str | None
    sections: tuple[ExpectedCorpusSection, ...]
    block_count: int
    chunk_count: int


@dataclass(frozen=True)
class GoldenFixture:
    """A named ingestion fixture: EPUB builder + its golden expected corpus."""

    name: str
    epub: Callable[[], bytes]
    expected: ExpectedCorpus


@dataclass(frozen=True)
class RetrievalCase:
    """A recall case: a query whose terms appear only in ``expected_anchor`` (EVAL-05)."""

    query: str
    expected_anchor: str


@dataclass(frozen=True)
class CitationCase:
    """An answerable case: the target the answer must cite (EVAL-07)."""

    question: str
    expected_anchor: str


_GOLDEN_EXPECTED = ExpectedCorpus(
    title=GOLDEN_TITLE,
    authors=GOLDEN_AUTHORS,
    language=GOLDEN_LANGUAGE,
    sections=tuple(
        ExpectedCorpusSection(
            section_path=section["section_path"],
            anchor=section["anchor"],
            depth=section["depth"],
            chunk_texts=section["chunk_texts"],
        )
        for section in EXPECTED_GOLDEN_SECTIONS
    ),
    block_count=EXPECTED_GOLDEN_BLOCK_COUNT,
    chunk_count=EXPECTED_GOLDEN_CHUNK_COUNT,
)

# The A-2 fallback fixture: no TOC, minimal OPF metadata. The parser recovers two
# sections ("Introduction" from its <h1>, "body" from its href stem), but the "body"
# section owns only a 3-word, heading-less paragraph — trivial by ING-05 — so
# normalization merges it into "Introduction" and keeps "body.xhtml" resolvable as
# an alias. The end-to-end corpus is therefore one section carrying both paragraphs;
# the parser's href-stem fallback stays covered by the parser-level golden. Title/
# language are None and authors empty (CORP-01).
_NO_TOC_EXPECTED = ExpectedCorpus(
    title=None,
    authors=(),
    language=None,
    sections=(
        ExpectedCorpusSection(
            section_path=("Introduction",),
            anchor="intro.xhtml",
            depth=0,
            chunk_texts=("# Introduction\n\nOpening remarks.\n\nNo heading here.",),
        ),
    ),
    block_count=3,
    chunk_count=1,
)

GOLDEN_FIXTURES = (
    GoldenFixture(name="golden-book", epub=golden_book, expected=_GOLDEN_EXPECTED),
    GoldenFixture(name="no-toc-book", epub=no_toc_book, expected=_NO_TOC_EXPECTED),
)

# Retrieval recall: each query's content tokens appear only in its target chapter,
# so the target is a rank-1 both-arm RRF hit (EVAL-05).
RETRIEVAL_CASES = (
    RetrievalCase(
        query="moon gravity pulls seawater into rising tides", expected_anchor=CH1_ANCHOR
    ),
    RetrievalCase(query="molten magma erupts from the volcano crater", expected_anchor=CH2_ANCHOR),
    RetrievalCase(query="movable metal type on the printing press", expected_anchor=CH3_ANCHOR),
)

# Citation grounding: an answerable question whose target chapter must be cited
# (EVAL-07). Tokens stay within the target chapter's vocabulary.
CITATION_CASES = (
    CitationCase(
        question="How do the moon's gravity and seawater cause tides?", expected_anchor=CH1_ANCHOR
    ),
    CitationCase(
        question="What happens when magma escapes and a volcano erupts?", expected_anchor=CH2_ANCHOR
    ),
    CitationCase(
        question="How did movable type on the printing press reproduce books?",
        expected_anchor=CH3_ANCHOR,
    ),
)

# A question whose terms appear in no chapter; against an un-embedded corpus both
# retrieval arms are empty, so the answer is the grounded not-found outcome (EVAL-08).
UNSUPPORTED_QUESTION = "How does photosynthesis convert sunlight inside plant leaves?"

# Re-exported for the grounding-bound assertion (EVAL-07) and case self-consistency.
__all__ = [
    "CITATION_CASES",
    "CitationCase",
    "ExpectedCorpus",
    "ExpectedCorpusSection",
    "GOLDEN_FIXTURES",
    "GOLDEN_SECTION_ANCHORS",
    "GoldenFixture",
    "RETRIEVAL_CASES",
    "RetrievalCase",
    "UNSUPPORTED_QUESTION",
]
