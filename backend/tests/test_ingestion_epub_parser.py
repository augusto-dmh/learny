"""T6 gate — EbooklibEpubParser structure recovery (unit).

Derived from CORP-01/02/03/06 and the parser Done-when, asserting against the
golden structures the synthetic fixtures (T5) declare. Metadata, spine order,
TOC-derived section paths/anchors/depths (A-1..A-4), the global block sequence
with preserved HTML, in-document fragment section switching, the A-2 fallback,
A-3 non-linear exclusion, dropped dangling TOC entries, empty-body sections, and
terminal InvalidEpubError classification are each pinned here.
"""

from __future__ import annotations

import pytest

from app.application.errors import InvalidEpubError
from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection
from app.infrastructure.ingestion.epub import EbooklibEpubParser
from tests import fixtures_epub as fx

_parser = EbooklibEpubParser()


def _parse(book_bytes: bytes) -> ParsedBook:
    return _parser.parse(book_bytes, filename="book.epub")


def _as_expected(section: ParsedSection) -> fx.ExpectedSection:
    return fx.ExpectedSection(
        position=section.position,
        title=section.title,
        depth=section.depth,
        section_path=section.section_path,
        anchor=section.anchor,
        blocks=tuple(
            fx.ExpectedBlock(b.position, b.block_type, b.html_fragment)
            for b in section.blocks
        ),
    )


# --- metadata (CORP-01) -----------------------------------------------------


def test_parses_opf_metadata() -> None:
    book = _parse(fx.valid_book())

    assert book.title == fx.EXPECTED_VALID_TITLE
    assert book.authors == fx.EXPECTED_VALID_AUTHORS
    assert book.language == fx.EXPECTED_VALID_LANGUAGE


def test_missing_metadata_becomes_none_and_empty_tuple() -> None:
    book = _parse(fx.no_toc_book())

    assert book.title is None
    assert book.authors == ()
    assert book.language is None


# --- whole-structure golden equality (CORP-01/02/03) ------------------------


def test_valid_book_matches_expected_structure_exactly() -> None:
    book = _parse(fx.valid_book())

    assert [_as_expected(s) for s in book.sections] == list(fx.EXPECTED_VALID_SECTIONS)


# --- spine order (CORP-02) --------------------------------------------------


def test_sections_follow_spine_reading_order() -> None:
    book = _parse(fx.valid_book())

    assert [s.title for s in book.sections] == [
        "Cover",
        "Part I",
        "Chapter 1",
        "Section 2",
        "Chapter 2",
    ]
    assert [s.position for s in book.sections] == [0, 1, 2, 3, 4]


# --- section paths & depths (A-1/A-2) ---------------------------------------


def test_section_paths_and_depths_follow_toc_nesting() -> None:
    book = _parse(fx.valid_book())
    by_title = {s.title: s for s in book.sections}

    assert by_title["Part I"].section_path == ("Part I",)
    assert by_title["Part I"].depth == 0
    assert by_title["Chapter 1"].section_path == ("Part I", "Chapter 1")
    assert by_title["Chapter 1"].depth == 1
    assert by_title["Section 2"].section_path == ("Part I", "Section 2")
    assert by_title["Section 2"].depth == 1


# --- anchors, bare and fragment (A-4) ---------------------------------------


def test_section_anchors_carry_href_and_optional_fragment() -> None:
    book = _parse(fx.valid_book())
    by_title = {s.title: s for s in book.sections}

    assert by_title["Chapter 1"].anchor == "chap1.xhtml"
    assert by_title["Section 2"].anchor == "chap1.xhtml#sec-2"


# --- block sequence + preserved HTML (CORP-03) ------------------------------


def test_blocks_carry_global_position_type_and_preserved_html() -> None:
    book = _parse(fx.valid_book())
    blocks = [b for s in book.sections for b in s.blocks]

    assert [b.position for b in blocks] == list(range(12))
    assert [b.block_type for b in blocks] == [
        "heading",
        "img",
        "heading",
        "paragraph",
        "heading",
        "paragraph",
        "list",
        "heading",
        "paragraph",
        "other",
        "heading",
        "paragraph",
    ]
    # The list block keeps its full inner markup, not a flattened text form.
    list_block = next(b for b in blocks if b.block_type == "list")
    assert list_block.html_fragment == "<ul><li>alpha</li><li>beta</li></ul>"


# --- TOC-fragment section switching (A-1/A-4) -------------------------------


def test_in_document_fragment_switches_section_before_that_element() -> None:
    book = _parse(fx.valid_book())
    by_title = {s.title: s for s in book.sections}

    # Everything up to (but not including) the #sec-2 heading is Chapter 1.
    assert [b.html_fragment for b in by_title["Chapter 1"].blocks] == [
        "<h2>Chapter 1</h2>",
        "<p>First paragraph of chapter one.</p>",
        "<ul><li>alpha</li><li>beta</li></ul>",
    ]
    # The #sec-2 heading itself and everything after it is Section 2.
    assert by_title["Section 2"].blocks[0].html_fragment == '<h3 id="sec-2">Section 2</h3>'
    assert by_title["Section 2"].blocks[0].block_type == "heading"


# --- A-2 fallback -----------------------------------------------------------


def test_untocd_spine_document_becomes_its_own_section() -> None:
    # cover.xhtml has no TOC entry; it forms a section titled from its <h1>.
    book = _parse(fx.valid_book())

    cover = book.sections[0]
    assert cover.title == "Cover"
    assert cover.section_path == ("Cover",)
    assert cover.depth == 0
    assert cover.anchor == "cover.xhtml"


def test_a2_fallback_uses_first_heading_then_href_stem() -> None:
    book = _parse(fx.no_toc_book())

    assert [_as_expected(s) for s in book.sections] == list(fx.EXPECTED_NO_TOC_SECTIONS)
    # First section titled from its heading; second (headingless) from href stem.
    assert book.sections[0].title == "Introduction"
    assert book.sections[1].title == "body"


# --- A-3 non-linear exclusion -----------------------------------------------


def test_non_linear_spine_item_is_excluded() -> None:
    book = _parse(fx.valid_book())

    titles = {s.title for s in book.sections}
    anchors = {s.anchor for s in book.sections}
    assert "Endnotes" not in titles
    assert "notes.xhtml" not in anchors


# --- dangling TOC entry dropped ---------------------------------------------


def test_toc_entry_absent_from_spine_is_dropped_without_error() -> None:
    book = _parse(fx.valid_book())

    anchors = {s.anchor for s in book.sections}
    assert "missing.xhtml" not in anchors
    assert len(book.sections) == 5


# --- empty body edge case ---------------------------------------------------


def test_empty_body_yields_a_zero_block_section() -> None:
    book = _parse(fx.empty_body_book())

    assert len(book.sections) == 1
    assert _as_expected(book.sections[0]) == fx.EXPECTED_EMPTY_SECTION
    assert book.sections[0].blocks == ()


# --- terminal failure classification (CORP-06) ------------------------------


def test_non_epub_bytes_raise_invalid_epub_error() -> None:
    with pytest.raises(InvalidEpubError):
        _parse(fx.not_an_epub())


def test_unresolvable_spine_raises_invalid_epub_error() -> None:
    with pytest.raises(InvalidEpubError):
        _parse(fx.broken_spine_book())


# --- library-free boundary (ADR-0009) ---------------------------------------


def test_returns_only_library_free_domain_types() -> None:
    book = _parse(fx.valid_book())

    assert isinstance(book, ParsedBook)
    for section in book.sections:
        assert isinstance(section, ParsedSection)
        for block in section.blocks:
            assert isinstance(block, ParsedBlock)
            assert isinstance(block.html_fragment, str)


# --- inflation cap (decompression-bomb guard) --------------------------------


def test_archive_over_uncompressed_cap_raises_invalid_epub_error() -> None:
    """An archive declaring more uncompressed bytes than the cap fails terminally.

    The upload limit bounds only compressed bytes; the parser must refuse to
    inflate an archive whose declared uncompressed total exceeds the configured
    cap, before any item is read into memory (CORP-06 terminal path).
    """
    capped = EbooklibEpubParser(max_uncompressed_bytes=1024)

    with pytest.raises(InvalidEpubError):
        capped.parse(fx.valid_book(), filename="book.epub")


def test_archive_under_uncompressed_cap_parses() -> None:
    """The same book parses when its declared size fits the configured cap."""
    roomy = EbooklibEpubParser(max_uncompressed_bytes=10 * 1024 * 1024)

    book = roomy.parse(fx.valid_book(), filename="book.epub")

    assert book.title == fx.EXPECTED_VALID_TITLE


# --- descendant fragment anchors (A-1/A-4) -----------------------------------


def test_descendant_fragment_id_switches_section_at_wrapper_block() -> None:
    """A TOC fragment id on a descendant splits the section at the wrapper block.

    Wrapped heading ids (e.g. ``<div><h3 id=...>``) are common in real EPUBs;
    the switch must happen before the wrapper is assigned, so the wrapper and
    everything after it belong to the fragment's section with the
    ``href#fragment`` anchor intact.
    """
    book = _parse(fx.nested_fragment_book())

    assert [_as_expected(s) for s in book.sections] == list(fx.EXPECTED_NESTED_SECTIONS)


# --- EPUB2 / NCX table of contents (A-1) -------------------------------------


def test_ncx_only_toc_yields_nested_section_paths() -> None:
    """An EPUB2 book with only an NCX navMap still yields nested TOC paths.

    ebooklib feeds ``book.toc`` from ``toc.ncx`` here — a different input shape
    than the EPUB3 nav fixtures; section paths, depths, and anchors must come
    out equivalent.
    """
    book = _parse(fx.ncx_book())

    assert book.title == "The NCX Book"
    assert [s.title for s in book.sections] == ["Part I", "Chapter 1"]
    assert [s.depth for s in book.sections] == [0, 1]
    assert [s.section_path for s in book.sections] == [
        ("Part I",),
        ("Part I", "Chapter 1"),
    ]
    assert [s.anchor for s in book.sections] == ["part1.xhtml", "chap1.xhtml"]
