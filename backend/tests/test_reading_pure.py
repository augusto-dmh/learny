"""A3 gate — pure reader core (unit, no DB).

Covers chapter partitioning, anchor resolution, and whole-book percent math over the
flat ``ChapterIndexRow`` read model (design §Components), deriving every case from the
spec ACs and edge cases:

- ``partition`` (AD-121): depth-0 boundaries, a flat book (one-section chapters), a
  book whose first row is deeper than 0, a single-chapter book, and the empty index.
- ``locate`` (mirrors ``get_section``): canonical match, alias match, an alias-vs-
  canonical collision (canonical wins), duplicate anchors (lowest position), and a miss.
- ``percent_at`` (RD-16): position math, 2-decimal quantization, and a zero-total book.
"""

from __future__ import annotations

from decimal import Decimal

from app.application.reading import (
    WORDS_PER_MINUTE,
    Chapter,
    locate,
    partition,
    percent_at,
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


def test_words_per_minute_constant_is_220() -> None:
    # AD-126 / spec P1-Position AC5: minutes-left is computed at 220 wpm.
    assert WORDS_PER_MINUTE == 220
