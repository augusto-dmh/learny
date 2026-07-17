"""Unit suite for the format-agnostic normalization pass (ING-01..08).

Every ING-01..08 acceptance criterion and every spec edge case that applies to
``normalize_book`` gets a discriminating test here; ``ParsedBook`` DTOs are
constructed directly (no parser). The idempotency property (ING-01) is asserted
against every fixture built below.
"""

from __future__ import annotations

import pytest

from app.application.normalization import (
    NormalizationCounts,
    normalize_book,
)
from app.domain.entities import ParsedBlock, ParsedBook, ParsedSection

_LONG_TEXT = " ".join(["word"] * 40)  # 40 words: keeps a heading-less section alive.


def _block(position: int, block_type: str, html_fragment: str) -> ParsedBlock:
    return ParsedBlock(
        position=position, block_type=block_type, html_fragment=html_fragment
    )


def _heading(position: int, level: int, text: str) -> ParsedBlock:
    return _block(position, "heading", f"<h{level}>{text}</h{level}>")


def _para(position: int, text: str) -> ParsedBlock:
    return _block(position, "paragraph", f"<p>{text}</p>")


def _long_para(position: int) -> ParsedBlock:
    return _para(position, _LONG_TEXT)


def _image(position: int) -> ParsedBlock:
    return _block(position, "img", "<img src='plate.png'/>")


def _section(
    position: int,
    title: str,
    depth: int,
    section_path: tuple[str, ...],
    anchor: str,
    blocks: tuple[ParsedBlock, ...],
    anchor_aliases: tuple[str, ...] = (),
) -> ParsedSection:
    return ParsedSection(
        position=position,
        title=title,
        depth=depth,
        section_path=section_path,
        anchor=anchor,
        blocks=blocks,
        anchor_aliases=anchor_aliases,
    )


def _book(*sections: ParsedSection) -> ParsedBook:
    return ParsedBook(
        title="A Book", authors=("Author",), language="en", sections=sections
    )


# --- Fixtures reused across specific assertions and the idempotency property ---


def clean_book() -> ParsedBook:
    """An already-clean, correctly-nested book (ING-08 regression sensor)."""
    return _book(
        _section(
            0, "Introduction", 0, ("Introduction",), "intro.html",
            (_heading(0, 1, "Introduction"), _long_para(1)),
        ),
        _section(
            1, "Origins", 1, ("Introduction", "Origins"), "origins.html",
            (_heading(2, 2, "Origins"), _long_para(3)),
        ),
        _section(
            2, "Aftermath", 0, ("Aftermath",), "aftermath.html",
            (_heading(4, 1, "Aftermath"), _long_para(5)),
        ),
    )


def generic_title_book() -> ParsedBook:
    return _book(
        _section(
            0, "part0034", 0, ("part0034",), "part0034.html",
            (_heading(0, 1, "The Real Chapter"), _long_para(1)),
        ),
        _section(
            1, "wrap0000", 0, ("wrap0000",), "wrap0000.html",
            (_para(2, "A Styled Heading"), _long_para(3)),
        ),
        _section(
            2, "text0002", 0, ("text0002",), "text0002.html",
            (_long_para(4),),
        ),
    )


def flat_toc_book() -> ParsedBook:
    return _book(
        _section(0, "Alpha", 0, ("Alpha",), "c1.html", (_heading(0, 1, "Alpha"),)),
        _section(1, "Beta", 0, ("Beta",), "c2.html", (_heading(1, 2, "Beta"),)),
        _section(2, "Gamma", 0, ("Gamma",), "c3.html", (_heading(2, 2, "Gamma"),)),
    )


def gutenberg_book() -> ParsedBook:
    return _book(
        _section(
            0, "The Front", 0, ("The Front",), "front.html",
            (
                _para(0, "Some license boilerplate before the book."),
                _para(1, "*** START OF THE PROJECT GUTENBERG EBOOK MY BOOK ***"),
            ),
        ),
        _section(
            1, "The Story", 0, ("The Story",), "body.html",
            (_heading(2, 1, "Chapter One"), _long_para(3)),
        ),
        _section(
            2, "The Back", 0, ("The Back",), "back.html",
            (
                _para(4, "*** END OF THE PROJECT GUTENBERG EBOOK MY BOOK ***"),
                _para(5, "Trailing license text after the book."),
            ),
        ),
    )


def trivial_merge_book() -> ParsedBook:
    return _book(
        _section(
            0, "Chapter", 0, ("Chapter",), "chapter.html",
            (_heading(0, 1, "Chapter"), _long_para(1)),
        ),
        _section(1, "Plate", 0, ("Plate",), "plate.html", (_image(2),)),
    )


def all_trivial_book() -> ParsedBook:
    return _book(
        _section(0, "A", 0, ("A",), "a.html", (_para(0, "hi there"),)),
        _section(1, "B", 0, ("B",), "b.html", (_para(1, "hello world"),)),
        _section(2, "C", 0, ("C",), "c.html", (_para(2, "third snippet"),)),
    )


_FIXTURES = [
    clean_book(),
    generic_title_book(),
    flat_toc_book(),
    gutenberg_book(),
    trivial_merge_book(),
    all_trivial_book(),
]


# --- ING-01: pure + idempotent ---------------------------------------------


@pytest.mark.parametrize("book", _FIXTURES)
def test_normalization_is_idempotent(book: ParsedBook) -> None:
    once = normalize_book(book).book
    twice = normalize_book(once).book
    assert twice == once


def test_normalization_does_not_mutate_input() -> None:
    book = generic_title_book()
    before = book.sections
    normalize_book(book)
    assert book.sections is before
    assert book.sections[0].title == "part0034"


# --- ING-08: clean book passes through unchanged -----------------------------


def test_clean_book_unchanged() -> None:
    book = clean_book()
    result = normalize_book(book)
    assert result.book == book
    assert result.counts == NormalizationCounts(0, 0, 0, 0)


# --- ING-02: title cascade ---------------------------------------------------


def test_generic_title_replaced_by_first_heading() -> None:
    result = normalize_book(generic_title_book())
    assert result.book.sections[0].title == "The Real Chapter"


def test_generic_title_replaced_by_short_leading_text_when_no_heading() -> None:
    result = normalize_book(generic_title_book())
    assert result.book.sections[1].title == "A Styled Heading"


def test_generic_title_replaced_by_placeholder_when_no_candidate() -> None:
    result = normalize_book(generic_title_book())
    assert result.book.sections[2].title == "Untitled section (3)"


def test_title_replacement_updates_section_path_leaf() -> None:
    result = normalize_book(generic_title_book())
    assert result.book.sections[0].section_path == ("The Real Chapter",)


def test_generic_title_count_reported() -> None:
    result = normalize_book(generic_title_book())
    assert result.counts.titles_replaced == 3


@pytest.mark.parametrize(
    "title", ["part0034", "wrap0000", "split_12", "index3", "text0001", "chapter5",
              "ch2", "0034", "", "   "],
)
def test_generic_titles_are_replaced(title: str) -> None:
    book = _book(
        _section(0, title, 0, (title,), "file.html",
                 (_heading(0, 1, "Canonical Heading"),))
    )
    result = normalize_book(book)
    assert result.book.sections[0].title == "Canonical Heading"


@pytest.mark.parametrize("title", ["Introduction", "Chapter One", "The Wrap Up", "Part Two"])
def test_meaningful_titles_are_kept(title: str) -> None:
    book = _book(
        _section(0, title, 0, (title,), "c1.html",
                 (_heading(0, 1, "Canonical Heading"), _long_para(1)))
    )
    result = normalize_book(book)
    assert result.book.sections[0].title == title


def test_title_matching_href_stem_is_generic() -> None:
    book = _book(
        _section(0, "introduction", 0, ("introduction",), "introduction.html",
                 (_heading(0, 1, "A Warm Welcome"),))
    )
    result = normalize_book(book)
    assert result.book.sections[0].title == "A Warm Welcome"


def test_no_section_title_is_a_raw_filename_stem() -> None:
    result = normalize_book(generic_title_book())
    for section in result.book.sections:
        stem = section.anchor.split("#", 1)[0].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        assert section.title != stem


# --- ING-03: flat-TOC hierarchy inference ------------------------------------


def test_flat_toc_depths_rederived_from_heading_levels() -> None:
    result = normalize_book(flat_toc_book())
    assert [s.depth for s in result.book.sections] == [0, 1, 1]


def test_flat_toc_inference_rebuilds_section_paths() -> None:
    result = normalize_book(flat_toc_book())
    assert result.book.sections[1].section_path == ("Alpha", "Beta")
    assert result.book.sections[2].section_path == ("Alpha", "Gamma")


def test_flat_toc_inference_skipped_when_a_depth_is_nonzero() -> None:
    book = _book(
        _section(0, "Alpha", 0, ("Alpha",), "c1.html", (_heading(0, 1, "Alpha"),)),
        _section(1, "Beta", 1, ("Alpha", "Beta"), "c2.html", (_heading(1, 2, "Beta"),)),
    )
    result = normalize_book(book)
    assert [s.depth for s in result.book.sections] == [0, 1]


def test_flat_toc_inference_skipped_with_single_heading_level() -> None:
    book = _book(
        _section(0, "Alpha", 0, ("Alpha",), "c1.html", (_heading(0, 1, "Alpha"),)),
        _section(1, "Beta", 0, ("Beta",), "c2.html", (_heading(1, 1, "Beta"),)),
    )
    result = normalize_book(book)
    assert [s.depth for s in result.book.sections] == [0, 0]


def test_flat_toc_heading_less_section_keeps_predecessor_depth() -> None:
    book = _book(
        _section(0, "Alpha", 0, ("Alpha",), "c1.html", (_heading(0, 1, "Alpha"),)),
        _section(1, "Mid", 0, ("Mid",), "c2.html", (_long_para(1),)),
        _section(2, "Gamma", 0, ("Gamma",), "c3.html", (_heading(2, 2, "Gamma"),)),
    )
    result = normalize_book(book)
    assert [s.depth for s in result.book.sections] == [0, 0, 1]


# --- ING-04: depth clamp -----------------------------------------------------


def test_depth_jump_is_clamped_to_parent_plus_one() -> None:
    book = _book(
        _section(0, "Top", 0, ("Top",), "a.html", (_heading(0, 1, "Top"), _long_para(1))),
        _section(1, "Deep", 2, ("Top", "Deep"), "b.html",
                 (_heading(2, 3, "Deep"), _long_para(3))),
    )
    result = normalize_book(book)
    assert [s.depth for s in result.book.sections] == [0, 1]


def test_depth_adjustment_count_reported() -> None:
    book = _book(
        _section(0, "Top", 0, ("Top",), "a.html", (_heading(0, 1, "Top"), _long_para(1))),
        _section(1, "Deep", 2, ("Top", "Deep"), "b.html",
                 (_heading(2, 3, "Deep"), _long_para(3))),
    )
    result = normalize_book(book)
    assert result.counts.depths_adjusted == 1


# --- ING-05: trivial-section merge + anchor promotion ------------------------


def test_trailing_trivial_section_merges_backward_with_alias() -> None:
    result = normalize_book(trivial_merge_book())
    assert len(result.book.sections) == 1
    survivor = result.book.sections[0]
    assert survivor.anchor == "chapter.html"
    assert survivor.anchor_aliases == ("plate.html",)


def test_merged_section_content_moves_into_survivor() -> None:
    result = normalize_book(trivial_merge_book())
    survivor = result.book.sections[0]
    assert any(block.block_type == "img" for block in survivor.blocks)


def test_leading_trivial_section_merges_forward_with_alias() -> None:
    book = _book(
        _section(0, "Cover", 0, ("Cover",), "cover.html", (_para(0, "brief cover"),)),
        _section(1, "Main", 0, ("Main",), "main.html",
                 (_heading(1, 1, "Main"), _long_para(2))),
    )
    result = normalize_book(book)
    assert len(result.book.sections) == 1
    survivor = result.book.sections[0]
    assert survivor.anchor == "main.html"
    assert survivor.anchor_aliases == ("cover.html",)
    assert survivor.blocks[0].html_fragment == "<p>brief cover</p>"


def test_caption_heavy_figure_section_is_trivial_by_image_rule() -> None:
    # 40 words of caption would survive the word-count rule; the image/caption
    # branch of ING-05 is what makes this section trivial.
    caption = " ".join(["figure"] * 40)
    book = _book(
        _section(0, "Chapter", 0, ("Chapter",), "chapter.html",
                 (_heading(0, 1, "Chapter"), _long_para(1))),
        _section(1, "Plate", 0, ("Plate",), "plate.html",
                 (_block(2, "figure", f"<figure><figcaption>{caption}</figcaption></figure>"),)),
    )
    result = normalize_book(book)
    assert len(result.book.sections) == 1
    assert result.book.sections[0].anchor_aliases == ("plate.html",)


def test_all_trivial_book_keeps_one_survivor_with_all_content() -> None:
    result = normalize_book(all_trivial_book())
    assert len(result.book.sections) == 1
    survivor = result.book.sections[0]
    assert survivor.anchor == "a.html"
    assert survivor.anchor_aliases == ("b.html", "c.html")
    assert len(survivor.blocks) == 3


def test_merge_count_reported() -> None:
    result = normalize_book(all_trivial_book())
    assert result.counts.sections_merged == 2


def test_aliases_accumulate_dedup_and_canonical_wins() -> None:
    book = _book(
        _section(0, "Keep", 0, ("Keep",), "keep.html",
                 (_heading(0, 1, "Keep"), _long_para(1))),
        _section(2, "One", 0, ("One",), "a1.html", (_para(2, "tiny"),)),
        _section(3, "Two", 0, ("Two",), "a2.html", (_para(3, "tiny"),)),
        _section(4, "Dup", 0, ("Dup",), "a1.html", (_para(4, "tiny"),)),
        _section(5, "Self", 0, ("Self",), "keep.html", (_para(5, "tiny"),)),
    )
    result = normalize_book(book)
    survivor = result.book.sections[0]
    assert survivor.anchor_aliases == ("a1.html", "a2.html")


# --- ING-06: Gutenberg marker stripping --------------------------------------


def test_gutenberg_markers_strip_outside_content() -> None:
    result = normalize_book(gutenberg_book())
    texts = [
        block.html_fragment
        for section in result.book.sections
        for block in section.blocks
    ]
    assert not any("boilerplate" in text for text in texts)
    assert not any("Trailing license" in text for text in texts)
    assert not any("PROJECT GUTENBERG" in text for text in texts)
    assert any("Chapter One" in text for text in texts)


def test_gutenberg_strip_count_reported() -> None:
    result = normalize_book(gutenberg_book())
    assert result.counts.noise_blocks_stripped == 4


def test_no_gutenberg_markers_strips_nothing() -> None:
    book = _book(
        _section(0, "Chapter", 0, ("Chapter",), "c.html",
                 (_heading(0, 1, "Chapter"), _long_para(1)))
    )
    result = normalize_book(book)
    assert result.counts.noise_blocks_stripped == 0
    assert len(result.book.sections[0].blocks) == 2


def test_start_marker_without_end_strips_nothing() -> None:
    book = _book(
        _section(0, "Chapter", 0, ("Chapter",), "c.html",
                 (_para(0, "*** START OF THE PROJECT GUTENBERG EBOOK X ***"),
                  _heading(1, 1, "Chapter"), _long_para(2)))
    )
    result = normalize_book(book)
    texts = [
        block.html_fragment
        for section in result.book.sections
        for block in section.blocks
    ]
    assert result.counts.noise_blocks_stripped == 0
    assert any("START OF THE PROJECT GUTENBERG" in text for text in texts)


# --- ING-04 edge: multi-jump tree keeps the parent+1 invariant ----------------


def test_clamp_enforces_parent_plus_one_invariant_across_jumps() -> None:
    depths = [0, 3, 5, 1]
    sections = tuple(
        _section(i, f"L{i}", depth, ("L0",), f"s{i}.html",
                 (_heading(i, min(depth + 1, 6), f"L{i}"), _long_para(100 + i)))
        for i, depth in enumerate(depths)
    )
    result = normalize_book(ParsedBook("B", (), "en", sections))
    got = [s.depth for s in result.book.sections]
    assert got == [0, 1, 2, 1]
    assert all(got[i] <= got[i - 1] + 1 for i in range(1, len(got)))
    assert all(depth >= 0 for depth in got)
