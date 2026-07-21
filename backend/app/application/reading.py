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
from uuid import UUID

from app.application.dates import local_day
from app.application.errors import CorpusNotFound
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.domain.entities import (
    ChapterContent,
    ChapterIndexRow,
    ReadingPosition,
    SourceHighlight,
    User,
)
from app.domain.ports import (
    Clock,
    CorpusRepository,
    NoteRepository,
    ReadingPositionRepository,
    SourceRepository,
    StudyDayRepository,
)

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


def _chapter_of(chapters: Sequence[Chapter], row_idx: int) -> int:
    """Return the index of the chapter whose half-open span contains ``row_idx``.

    ``partition`` tiles the whole index, so a valid ``row_idx`` always lands in exactly
    one chapter; the final chapter is the defensive fallback.
    """
    for i, chapter in enumerate(chapters):
        if chapter.start <= row_idx < chapter.end:
            return i
    return len(chapters) - 1


def chapter_title(index: Sequence[ChapterIndexRow] | None, anchor: str) -> str:
    """Return the title of the chapter containing ``anchor`` (mirrors ``ReadChapter``).

    Resolves the anchor's row (canonical then alias), falls back to the first row when the
    anchor no longer resolves (a superseded corpus), then returns the depth-0 title of the
    chapter that row belongs to. An absent/empty index yields ``""`` — a caller shows the
    book without a chapter label rather than erroring.
    """
    if not index:
        return ""
    row_idx = locate(index, anchor)
    if row_idx is None:
        row_idx = 0
    chapters = partition(index)
    chapter = chapters[_chapter_of(chapters, row_idx)]
    return index[chapter.start].title


class ReadChapter:
    """Assemble the chapter containing an anchor (or the resume point) for the owner.

    Mirrors ``ReadSection``'s ownership-first shape: a missing source and a non-owner
    collapse to ``SourceNotFound`` (no existence disclosure). An owned source with no
    corpus, or an ``anchor`` that resolves to no section, raises ``CorpusNotFound`` —
    the web layer maps both to 404, so a valid anchor is indistinguishable from an
    unknown one to a non-owner.

    ``anchor is None`` is the resume path (spec P1-Position AC4): the reader opens at
    the stored position's chapter, or the first chapter when there is no stored
    position or the stored anchor no longer resolves (a superseded corpus) — the stored
    row is left untouched in that case. The stored position is always returned (or
    ``None``) so the reader can show book percent immediately.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        corpus: CorpusRepository,
        positions: ReadingPositionRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._positions = positions
        self._authorize = authorize

    def __call__(
        self, *, user: User, source_id: UUID, anchor: str | None
    ) -> tuple[ChapterContent, ReadingPosition | None]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        index = self._corpus.get_chapter_index(source_id)
        if not index:
            raise CorpusNotFound("No corpus for this source.")

        stored = self._positions.get(user.id, source_id)
        if anchor is not None:
            target_idx = locate(index, anchor)
            if target_idx is None:
                raise CorpusNotFound("No section for this anchor.")
        else:
            # Resume: the stored anchor's row, else the first chapter. A stale stored
            # anchor (superseded corpus) falls back to row 0 without touching the row.
            target_idx = locate(index, stored.anchor) if stored is not None else None
            if target_idx is None:
                target_idx = 0

        content = self._assemble(source_id, index, target_idx)
        return content, stored

    def _assemble(
        self, source_id: UUID, index: Sequence[ChapterIndexRow], target_idx: int
    ) -> ChapterContent:
        chapters = partition(index)
        chapter_index = _chapter_of(chapters, target_idx)
        chapter = chapters[chapter_index]

        first_row = index[chapter.start]
        last_row = index[chapter.end - 1]
        sections = self._corpus.get_sections_span(
            source_id, first_row.position, last_row.position
        )

        prev_anchor = (
            index[chapters[chapter_index - 1].start].anchor
            if chapter_index > 0
            else None
        )
        next_anchor = (
            index[chapters[chapter_index + 1].start].anchor
            if chapter_index < len(chapters) - 1
            else None
        )
        return ChapterContent(
            chapter_title=first_row.title,
            chapter_anchor=first_row.anchor,
            chapter_index=chapter_index,
            chapter_count=len(chapters),
            prev_anchor=prev_anchor,
            next_anchor=next_anchor,
            words_before_chapter=sum(
                index[i].word_count for i in range(chapter.start)
            ),
            chapter_word_count=sum(
                index[i].word_count for i in range(chapter.start, chapter.end)
            ),
            total_word_count=sum(row.word_count for row in index),
            sections=sections,
        )


class SaveReadingPosition:
    """Store where the owner stopped reading a source, with a server-computed percent.

    Ownership-first like ``ReadChapter``. The ``anchor`` is resolved against the chapter
    index (``locate`` — canonical then alias); a miss raises ``CorpusNotFound`` → 404 and
    nothing is stored (RD-09). The **canonical** anchor of the matched row is persisted,
    so an alias write normalizes to the canonical anchor (survives renormalization), and
    the whole-book percent at that row is computed server-side (never client-forged).
    Last-write-wins on the ``(user, source)`` key (RD-12).

    Saving a position also credits the reader's study day: an atomic
    ``StudyDayRepository.record`` (``reading_updates += 1``) on the user-local day derived
    from ``client_tz`` (HOME-08), issued on the same connection as the position upsert so
    the two commit together (I-1). It runs only on the success path — a bad anchor 404s
    before anything is stored and earns no study credit. A missing/invalid ``client_tz``
    degrades to UTC (HOME-09), never an error.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        corpus: CorpusRepository,
        positions: ReadingPositionRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
        study_days: StudyDayRepository,
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._positions = positions
        self._authorize = authorize
        self._clock = clock
        self._study_days = study_days

    def __call__(
        self, *, user: User, source_id: UUID, anchor: str, client_tz: str | None = None
    ) -> ReadingPosition:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        index = self._corpus.get_chapter_index(source_id)
        target_idx = locate(index, anchor) if index else None
        if target_idx is None:
            raise CorpusNotFound("No section for this anchor.")

        now = self._clock.now()
        percent = percent_at(index, target_idx)
        position = self._positions.upsert(
            user.id,
            source_id,
            anchor=index[target_idx].anchor,
            percent=percent,
            updated_at=now,
        )
        self._study_days.record(user.id, local_day(now, client_tz), reading_updates=1)
        return position


class ListSourceHighlights:
    """Return the owner's highlights on a source for inline reader painting (RD-28).

    Ownership-first (missing/non-owner → ``SourceNotFound`` → 404); then the caller's
    ``(user, source)``-scoped highlights, every status included so the client paints the
    active ones and ignores stale/orphaned (RD-29).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        notes: NoteRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._notes = notes
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID) -> tuple[SourceHighlight, ...]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        return self._notes.highlights_for_source(user.id, source_id)
