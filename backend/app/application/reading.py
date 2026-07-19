"""Reader-core application logic (RFC-004 Cycle B, design §Components).

The pure core the chapter-flow reader is built on: chapter partitioning, anchor
resolution, and whole-book percent math over the flat ``ChapterIndexRow`` read
model. Framework-free (ADR-007/009) — no FastAPI/SQLAlchemy/SDK imports — so the
progress math is unit-testable without a database, and the SQL read models stay
flat (the structure-endpoint precedent; no recursive queries).

A "chapter" is a depth-0 section plus all contiguous following sections of greater
depth, up to the next depth-0 section (AD-121). A book whose first section is not
depth 0 still opens a chapter at its first row, so every section belongs to exactly
one chapter. Anchor resolution mirrors ``get_section`` (repositories.py): a
canonical match beats an alias match, and position order breaks ties.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.entities import ChapterIndexRow

# Adult silent-reading rate for the minutes-left estimate (AD-126). A named constant
# — precision is not the product point; the view and client mirror this value.
WORDS_PER_MINUTE = 220

# Percent is stored/displayed to two decimals (NUMERIC(5,2)); all percent math
# quantizes to this so there is no float drift (design §Tech Decisions).
_PERCENT_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class Chapter:
    """A half-open ``[start, end)`` span of chapter-index rows (design §Components)."""

    start: int
    end: int


def partition(index: Sequence[ChapterIndexRow]) -> tuple[Chapter, ...]:
    """Split the position-ordered index into chapters (AD-121).

    A new chapter opens at every depth-0 row; the first row always opens one even if
    it is deeper than 0 (a book that starts mid-hierarchy still has a first chapter),
    so the chapters exactly tile the index with no row left out. A flat book (every
    row depth 0) yields one single-section chapter per row.
    """
    if not index:
        return ()
    starts = [0]
    starts.extend(i for i in range(1, len(index)) if index[i].depth == 0)
    return tuple(
        Chapter(start=start, end=(starts[j + 1] if j + 1 < len(starts) else len(index)))
        for j, start in enumerate(starts)
    )


def locate(index: Sequence[ChapterIndexRow], anchor: str) -> int | None:
    """Return the index of the row addressed by ``anchor``, or ``None`` (mirrors get_section).

    A canonical (``row.anchor``) match beats an alias (``anchor in row.anchor_aliases``)
    match — so a section whose canonical anchor is ``anchor`` wins over another that
    merely carries it as an alias — and position order breaks ties. The index is
    position-ordered, so the first canonical match is the lowest-position one; an
    alias fallback is used only when no row matches canonically.
    """
    alias_hit: int | None = None
    for i, row in enumerate(index):
        if row.anchor == anchor:
            return i
        if alias_hit is None and anchor in row.anchor_aliases:
            alias_hit = i
    return alias_hit


def percent_at(index: Sequence[ChapterIndexRow], row_idx: int) -> Decimal:
    """Return the whole-book percent *before* ``row_idx`` (design §Data Models, RD-16).

    ``sum(word_count of rows[:row_idx]) / total * 100`` quantized to two decimals; a
    total of 0 (an empty or prose-free book) yields ``0.00`` rather than dividing by
    zero.
    """
    total = sum(row.word_count for row in index)
    if total == 0:
        return Decimal("0.00")
    words_before = sum(row.word_count for row in index[:row_idx])
    return (Decimal(words_before) * 100 / Decimal(total)).quantize(_PERCENT_QUANTUM)
