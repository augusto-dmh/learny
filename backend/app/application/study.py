"""Study rollup + adherence application logic (RFC-004 Cycle E, design §Components).

Framework-free (ADR-007/009): no FastAPI/SQLAlchemy/SDK imports. ``local_day`` is the
pure day-boundary helper shared by the activity writes (``SubmitReview``,
``SaveReadingPosition``) and the read side — it maps a UTC instant to the user-local
calendar date from a client-supplied IANA timezone, degrading silently to UTC so a
garbage header can never break a write or a read. ``GetStudySummary`` serves the
adherence window + ``studied_last_14`` (recomputed per request, never stored — I-4);
``ContinueReading`` resolves the most-recent position into the Home hero.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.entities import ContinuePoint, StudySummary, User
from app.domain.ports import (
    Clock,
    CorpusRepository,
    ReadingPositionRepository,
    StudyDayRepository,
)

# The adherence line always reports over a fixed 14-day window regardless of the
# heatmap window the client asked for (HOME-12).
_ADHERENCE_WINDOW_DAYS = 14


def local_day(now: datetime, tz_name: str | None) -> date:
    """Return the user-local calendar date of ``now`` in ``tz_name`` (HOME-09, I-3).

    ``now`` is the timezone-aware UTC instant from the clock. A valid IANA ``tz_name``
    (e.g. ``"America/Sao_Paulo"``) yields the date in that zone, applying its current
    UTC offset (including DST). A missing, empty, or invalid name (e.g. ``"Mars/Olympus"``)
    falls back to the UTC date — this never raises, so an absent or garbage client header
    degrades to UTC rather than failing the request.
    """
    if tz_name:
        try:
            return now.astimezone(ZoneInfo(tz_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return now.astimezone(UTC).date()


class GetStudySummary:
    """Serve the caller's adherence window + ``studied_last_14`` (HOME-11, I-4).

    Returns the study-day rows for the ``window``-day range ending at the caller's local
    today (day boundary per ``local_day``, HOME-09), plus the count of distinct days with
    any activity in the fixed 14-day window ending today. Both are derived at read time
    from the ``study_days`` rollup — no streak/adherence value is ever persisted. The
    ``window`` bounds (7..365) are enforced by the web layer before this runs.
    """

    def __init__(
        self, *, study_days: StudyDayRepository, clock: Clock
    ) -> None:
        self._study_days = study_days
        self._clock = clock

    def __call__(self, *, user: User, window: int, tz: str | None) -> StudySummary:
        today = local_day(self._clock.now(), tz)
        window_start = today - timedelta(days=window - 1)
        last14_start = today - timedelta(days=_ADHERENCE_WINDOW_DAYS - 1)
        # One fetch over the union of the requested window and the 14-day adherence
        # window (the latter can reach earlier when window < 14), then slice both out.
        fetch_start = min(window_start, last14_start)
        rows = self._study_days.window(user.id, start=fetch_start, end=today)

        window_rows = tuple(row for row in rows if row.day >= window_start)
        # A study_days row exists only for a day that had activity, so counting the rows
        # in the 14-day window is the count of distinct studied days (HOME-12).
        studied_last_14 = sum(1 for row in rows if row.day >= last14_start)
        return StudySummary(days=window_rows, studied_last_14=studied_last_14)


class ContinueReading:
    """Resolve the caller's continue-reading hero, or ``None`` (HOME-01/02).

    Reads the caller's most-recent reading position across their sources (user-scoped in
    SQL, HOME-04), then resolves the stored anchor to its chapter title against the
    source's chapter index using the existing reader-core helpers. Returns ``None`` when
    the user has no positions (the hero renders its empty state). A stale anchor (the
    corpus was replaced) resolves to the first chapter rather than failing, and a source
    without a chapter index yields an empty chapter title — never a dangling render.
    """

    def __init__(
        self,
        *,
        positions: ReadingPositionRepository,
        corpus: CorpusRepository,
    ) -> None:
        self._positions = positions
        self._corpus = corpus

    def __call__(self, *, user: User) -> ContinuePoint | None:
        recent = self._positions.most_recent_for_user(user.id)
        if recent is None:
            return None
        index = self._corpus.get_chapter_index(recent.source_id)
        return ContinuePoint(
            source_id=recent.source_id,
            source_title=recent.source_title,
            chapter_title=_chapter_title(index, recent.anchor),
            percent=recent.percent,
            updated_at=recent.updated_at,
        )


def _chapter_title(index, anchor: str) -> str:  # noqa: ANN001 — Sequence[ChapterIndexRow] | None
    """Return the title of the chapter containing ``anchor`` (mirrors ``ReadChapter``).

    Resolves the anchor's row (canonical then alias), falls back to the first row when the
    anchor no longer resolves (a superseded corpus), then returns the depth-0 title of the
    chapter that row belongs to. An absent/empty index yields ``""`` — the hero shows the
    book without a chapter label rather than erroring.
    """
    # Imported here rather than at module scope: ``reading`` imports ``local_day`` from
    # this module, so a top-level import would form a cycle.
    from app.application.reading import _chapter_of, locate, partition

    if not index:
        return ""
    row_idx = locate(index, anchor)
    if row_idx is None:
        row_idx = 0
    chapters = partition(index)
    chapter = chapters[_chapter_of(chapters, row_idx)]
    return index[chapter.start].title
