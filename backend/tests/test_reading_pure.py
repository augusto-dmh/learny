"""A3 gate — pure reader core (unit, no DB).

Covers chapter partitioning, anchor resolution, and whole-book percent math over the
flat ``ChapterIndexRow`` read model (design §Components), deriving every case from the
spec ACs and edge cases:

- ``partition`` (AD-121): depth-0 boundaries, a flat book (one-section chapters), a
  book whose first row is deeper than 0, a single-chapter book, and the empty index.
- ``locate`` (mirrors ``get_section``): canonical match, alias match, an alias-vs-
  canonical collision (canonical wins), duplicate anchors (lowest position), and a miss.
- ``percent_at`` (RD-16): position math, 2-decimal quantization, and a zero-total book.
- ``words_before_row``, ``page_at`` and ``pages_from_words``: the page unit derived from
  the word counts already stored per section, with no DB and no HTTP.
- ``words_credited``: the forward-only reading volume one position save earns, at every
  edge (advance, retreat, no baseline, a baseline that no longer resolves).
"""

from __future__ import annotations

from decimal import Decimal

from app.application.reading import (
    Chapter,
    locate,
    page_at,
    pages_from_words,
    partition,
    percent_at,
    words_before_row,
    words_credited,
)
from app.domain.entities import ChapterIndexRow


def _row(position: int, depth: int, anchor: str, *, aliases=(), words: int = 0) -> ChapterIndexRow:
    return ChapterIndexRow(
        position=position,
        depth=depth,
        title=f"S{position}",
        section_path=(f"S{position}",),
        anchor=anchor,
        anchor_aliases=tuple(aliases),
        word_count=words,
    )


def _index(depths: list[int]) -> tuple[ChapterIndexRow, ...]:
    return tuple(_row(i, depth, f"a{i}") for i, depth in enumerate(depths))


# --- partition (AD-121) --------------------------------------------------------


def test_partition_opens_a_chapter_at_each_depth_zero_row() -> None:
    # A depth-0 section plus its contiguous deeper sections form one chapter.
    chapters = partition(_index([0, 1, 1, 0, 1]))
    assert chapters == (Chapter(start=0, end=3), Chapter(start=3, end=5))


def test_partition_flat_book_yields_one_section_chapters() -> None:
    # Every row depth 0 -> each section is its own chapter.
    chapters = partition(_index([0, 0, 0]))
    assert chapters == (
        Chapter(start=0, end=1),
        Chapter(start=1, end=2),
        Chapter(start=2, end=3),
    )


def test_partition_book_starting_below_depth_zero_opens_chapter_at_row_zero() -> None:
    # The first row is deeper than 0 but still opens a chapter, so no row is orphaned.
    chapters = partition(_index([2, 1, 0, 1]))
    assert chapters == (Chapter(start=0, end=2), Chapter(start=2, end=4))


def test_partition_single_chapter_book_has_one_span() -> None:
    chapters = partition(_index([0, 1, 2]))
    assert chapters == (Chapter(start=0, end=3),)


def test_partition_empty_index_yields_no_chapters() -> None:
    assert partition(()) == ()


# --- locate (mirrors get_section) ----------------------------------------------


def test_locate_returns_canonical_match_index() -> None:
    index = (_row(0, 0, "a0"), _row(1, 1, "a1"))
    assert locate(index, "a1") == 1


def test_locate_resolves_an_alias() -> None:
    index = (_row(0, 0, "a0"), _row(1, 1, "canon", aliases=("old-anchor",)))
    assert locate(index, "old-anchor") == 1


def test_locate_prefers_canonical_over_a_lower_position_alias() -> None:
    # Row 0 carries "a" as an alias; row 1's canonical anchor is "a". The canonical
    # match wins even though the alias sits at a lower position (get_section semantics).
    index = (_row(0, 0, "b", aliases=("a",)), _row(1, 1, "a"))
    assert locate(index, "a") == 1


def test_locate_duplicate_canonical_anchors_resolves_to_lowest_position() -> None:
    index = (_row(0, 0, "dup"), _row(1, 1, "dup"))
    assert locate(index, "dup") == 0


def test_locate_unknown_anchor_returns_none() -> None:
    index = (_row(0, 0, "a0"), _row(1, 1, "a1"))
    assert locate(index, "missing") is None


# --- percent_at (RD-16) --------------------------------------------------------


def test_percent_at_is_words_before_the_row_over_total() -> None:
    index = (_row(0, 0, "a", words=1), _row(1, 0, "b", words=1), _row(2, 0, "c", words=1))
    assert percent_at(index, 0) == Decimal("0.00")
    assert percent_at(index, 1) == Decimal("33.33")
    assert percent_at(index, 2) == Decimal("66.67")
    assert percent_at(index, 3) == Decimal("100.00")


def test_percent_at_quantizes_to_two_decimals() -> None:
    index = (_row(0, 0, "a", words=1), _row(1, 0, "b", words=7))
    # 1 / 8 * 100 = 12.5 exactly -> 12.50 at two decimals.
    result = percent_at(index, 1)
    assert result == Decimal("12.50")
    assert result.as_tuple().exponent == -2


def test_percent_at_zero_total_is_zero_not_division_error() -> None:
    index = (_row(0, 0, "a", words=0), _row(1, 0, "b", words=0))
    assert percent_at(index, 1) == Decimal("0.00")


# --- words_before_row ----------------------------------------------------------


def test_words_before_row_sums_the_preceding_rows() -> None:
    index = (_row(0, 0, "a", words=3), _row(1, 0, "b", words=2), _row(2, 0, "c", words=4))
    assert [words_before_row(index, i) for i in range(4)] == [0, 3, 5, 9]


def test_words_before_row_past_the_end_is_the_whole_book() -> None:
    index = (_row(0, 0, "a", words=3), _row(1, 0, "b", words=2))
    assert words_before_row(index, 99) == 5


# --- page_at (PAGE-03/PAGE-04, AD-189) ------------------------------------------


def test_page_at_starts_at_page_one_at_the_first_word() -> None:
    assert page_at(0, 275) == 1


def test_page_at_advances_one_page_per_quantum() -> None:
    # The first 275 words are page 1; the 276th word opens page 2 (PAGE-04).
    assert page_at(274, 275) == 1
    assert page_at(275, 275) == 2
    assert page_at(549, 275) == 2
    assert page_at(550, 275) == 3


def test_page_at_continues_the_books_numbering_into_a_later_chapter() -> None:
    # A chapter opening 5500 words into the book starts on page 21, not page 1 — the
    # count is book-global, so a page number locates a passage across the whole book.
    assert page_at(5500, 275) == 21


def test_page_at_follows_the_quantum_it_is_given() -> None:
    # The quantum is a parameter, never a constant baked into the derivation: the same
    # point in the same book pages differently under a different words-per-page.
    assert page_at(600, 275) == 3
    assert page_at(600, 300) == 3
    assert page_at(600, 200) == 4


def test_page_at_does_not_depend_on_the_length_of_the_book() -> None:
    # A page is words-before divided by the quantum, never a rounding of the percent:
    # the same offset in a short and a long book is the same page, though the two are
    # at wildly different percentages of their books.
    short_book = (_row(0, 0, "a", words=550), _row(1, 0, "b", words=550))
    long_book = (_row(0, 0, "a", words=550), _row(1, 0, "b", words=99450))

    assert page_at(words_before_row(short_book, 1), 275) == 3
    assert page_at(words_before_row(long_book, 1), 275) == 3
    assert percent_at(short_book, 1) != percent_at(long_book, 1)


def test_page_numbers_derive_from_the_stored_word_counts_alone() -> None:
    # I-PU-1: a book ingested long ago gains pages from nothing but the per-section
    # word counts already in its corpus — no new field, no re-processing, no DB access.
    index = (
        _row(0, 0, "c1", words=300),
        _row(1, 0, "c2", words=300),
        _row(2, 0, "c3", words=300),
    )
    assert [page_at(words_before_row(index, i), 275) for i in range(3)] == [1, 2, 3]


def test_page_at_degrades_to_page_one_for_a_non_positive_quantum() -> None:
    # A misconfigured setting must not raise on a read path.
    assert page_at(1000, 0) == 1


# --- pages_from_words (PAGE-09) -------------------------------------------------


def test_pages_from_words_counts_whole_pages_and_floors_the_remainder() -> None:
    assert pages_from_words(0, 275) == 0
    assert pages_from_words(274, 275) == 0
    assert pages_from_words(275, 275) == 1
    assert pages_from_words(549, 275) == 1
    assert pages_from_words(550, 275) == 2


def test_pages_from_words_never_reports_a_negative_figure() -> None:
    assert pages_from_words(-500, 275) == 0


def test_pages_from_words_degrades_to_zero_for_a_non_positive_quantum() -> None:
    assert pages_from_words(1000, 0) == 0


# --- words_credited (PAGE-07, I-PU-4/I-PU-5) ------------------------------------

# Word offsets 0, 3, 5, 6 (counts 3, 2, 1, 4); "c2" also answers to "old-c2".
_BOOK = (
    _row(0, 0, "c1", words=3),
    _row(1, 1, "c1s1", words=2),
    _row(2, 0, "c2", aliases=("old-c2",), words=1),
    _row(3, 1, "c2s1", words=4),
)


def test_words_credited_is_the_ground_covered_since_the_prior_position() -> None:
    # Moving from row 1 (3 words in) to row 3 (6 words in) covers 3 words.
    assert words_credited(_BOOK, prior_anchor="c1s1", target_idx=3) == 3


def test_words_credited_is_zero_when_the_reader_moves_backwards() -> None:
    # I-PU-4: re-reading credits nothing — never a negative that would eat the day's
    # earlier progress.
    assert words_credited(_BOOK, prior_anchor="c2s1", target_idx=1) == 0


def test_words_credited_is_zero_for_a_save_at_the_same_place() -> None:
    assert words_credited(_BOOK, prior_anchor="c1s1", target_idx=1) == 0


def test_words_credited_is_zero_without_a_prior_position() -> None:
    # I-PU-5: opening a book at the halfway mark must not claim half the book as read
    # today — with no baseline there is no evidence any ground was covered.
    assert words_credited(_BOOK, prior_anchor=None, target_idx=3) == 0


def test_words_credited_is_zero_when_the_prior_anchor_no_longer_resolves() -> None:
    # The corpus was replaced under the stored position: the old offset means nothing
    # against the current index, so it earns nothing.
    assert words_credited(_BOOK, prior_anchor="gone", target_idx=3) == 0


def test_words_credited_resolves_a_prior_anchor_by_alias() -> None:
    # A baseline stored under a superseded alias still locates its row (2 → offset 5),
    # so a renormalized corpus does not silently reset the reader's baseline.
    assert words_credited(_BOOK, prior_anchor="old-c2", target_idx=3) == 1
