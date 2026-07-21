"""Study read services (unit, in-memory fakes).

Drives ``GetStudySummary`` and ``ContinueReading`` over fakes, asserting the spec ACs
and edges without a DB:

- ``GetStudySummary``: returns the requested window's rows (day-ordered) plus
  ``studied_last_14`` computed at read time; the 14-day adherence count is independent of
  the requested window (survives a window < 14); the client timezone sets "today"; a
  brand-new user gets an empty window and 0 (HOME-11/12, I-4).
- ``ContinueReading``: resolves the most-recent position into the hero with its chapter
  title (canonical then alias), falls back to the first chapter for a stale anchor, yields
  an empty chapter title without a corpus, and returns ``None`` with no positions
  (HOME-01/02).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.application.study import ContinueReading, GetStudySummary
from app.domain.entities import (
    ContinuePoint,
    CorpusSectionRecord,
    ParsedSection,
    RecentReadingPosition,
    StudyDay,
    User,
)
from tests.fakes import FakeClock, FakeCorpusRepository, FakeStudyDayRepository


def _user() -> User:
    return User(id=uuid4(), email="study@example.com", created_at=datetime.now(UTC))


# --- GetStudySummary -----------------------------------------------------------

# A fixed "today" so the window math is deterministic. Noon UTC so a positive-offset
# zone does not cross into the next day unless a test intends it to.
_TODAY = date(2026, 7, 21)
_NOON = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


def _seed_days(study: FakeStudyDayRepository, user_id, days: list[date]) -> None:  # noqa: ANN001
    for d in days:
        study.record(user_id, d, reviews=1)


def test_summary_returns_window_rows_day_ordered() -> None:
    user = _user()
    study = FakeStudyDayRepository()
    _seed_days(study, user.id, [date(2026, 7, 20), date(2026, 7, 15), date(2026, 7, 10)])
    service = GetStudySummary(study_days=study, clock=FakeClock(_NOON))

    summary = service(user=user, window=84, tz=None)

    assert [d.day for d in summary.days] == [
        date(2026, 7, 10),
        date(2026, 7, 15),
        date(2026, 7, 20),
    ]
    assert all(isinstance(d, StudyDay) for d in summary.days)


def test_summary_studied_last_14_counts_distinct_days_in_the_14_day_window() -> None:
    # Spec independent test: 12 study days within the last 14 → "Studied 12 of 14".
    # today = the 21st, so the 14-day window is [the 8th, the 21st] inclusive (14 days);
    # seed 12 of those days (drop the 9th and the 18th).
    user = _user()
    study = FakeStudyDayRepository()
    twelve = [date(2026, 7, d) for d in range(8, 22) if d not in (9, 18)]
    assert len(twelve) == 12  # 14 days in [8, 21], minus 2
    _seed_days(study, user.id, twelve)
    service = GetStudySummary(study_days=study, clock=FakeClock(_NOON))

    summary = service(user=user, window=84, tz=None)

    assert summary.studied_last_14 == 12


def test_summary_studied_last_14_excludes_days_older_than_14() -> None:
    user = _user()
    study = FakeStudyDayRepository()
    # The 7th is 14 days before the 21st (today-14) → outside the 14-day window.
    _seed_days(study, user.id, [date(2026, 7, 7), date(2026, 7, 8), date(2026, 7, 21)])
    service = GetStudySummary(study_days=study, clock=FakeClock(_NOON))

    summary = service(user=user, window=84, tz=None)

    assert summary.studied_last_14 == 2  # the 8th and the 21st, not the 7th


def test_summary_adherence_is_independent_of_a_small_window() -> None:
    # HOME-12: even with window=7, studied_last_14 reports over the full 14 days — the
    # adherence count is not truncated to the requested heatmap window.
    user = _user()
    study = FakeStudyDayRepository()
    # Two days that fall in the 14-day window but OUTSIDE the 7-day window.
    _seed_days(study, user.id, [date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 21)])
    service = GetStudySummary(study_days=study, clock=FakeClock(_NOON))

    summary = service(user=user, window=7, tz=None)

    # The 7-day window ([the 15th, the 21st]) contains only the 21st...
    assert [d.day for d in summary.days] == [date(2026, 7, 21)]
    # ...but adherence still counts all three days in the 14-day window.
    assert summary.studied_last_14 == 3


def test_summary_uses_client_timezone_for_today() -> None:
    # HOME-09/11: at 23:30 UTC, Tokyo is already the 22nd, so "today" (and the window
    # end) shifts a day forward — a row on the 22nd local is inside the window.
    user = _user()
    study = FakeStudyDayRepository()
    _seed_days(study, user.id, [date(2026, 7, 22)])
    near_midnight = datetime(2026, 7, 21, 23, 30, 0, tzinfo=UTC)
    service = GetStudySummary(study_days=study, clock=FakeClock(near_midnight))

    summary = service(user=user, window=84, tz="Asia/Tokyo")

    assert [d.day for d in summary.days] == [date(2026, 7, 22)]
    assert summary.studied_last_14 == 1


def test_summary_empty_for_a_user_with_no_activity() -> None:
    # Brand-new-user edge: empty window, adherence 0.
    user = _user()
    service = GetStudySummary(study_days=FakeStudyDayRepository(), clock=FakeClock(_NOON))

    summary = service(user=user, window=84, tz=None)

    assert summary.days == ()
    assert summary.studied_last_14 == 0


# --- ContinueReading -----------------------------------------------------------


class _FakeRecentPositions:
    """A ``ReadingPositionRepository`` double for the hero: preset most-recent result."""

    def __init__(self, recent: RecentReadingPosition | None) -> None:
        self._recent = recent

    def most_recent_for_user(self, user_id):  # noqa: ANN001, ANN201
        return self._recent


def _record(position, depth, anchor, markdown, aliases=()) -> CorpusSectionRecord:  # noqa: ANN001
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=f"Chapter {position}",
            depth=depth,
            section_path=(f"Chapter {position}",),
            anchor=anchor,
            blocks=(),
            anchor_aliases=tuple(aliases),
        ),
        markdown=markdown,
        chunks=(),
    )


def _seed_book(corpus: FakeCorpusRepository, source_id) -> None:  # noqa: ANN001
    # Two chapters (depths 0,1,0,1); "c2" also resolvable via the alias "old-c2".
    corpus.replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _record(0, 0, "c1", "a b c"),
            _record(1, 1, "c1s1", "d e"),
            _record(2, 0, "c2", "f", aliases=("old-c2",)),
            _record(3, 1, "c2s1", "g h i j"),
        ],
    )


def _recent(source_id, *, anchor: str) -> RecentReadingPosition:  # noqa: ANN001
    return RecentReadingPosition(
        source_id=source_id,
        source_title="A Book",
        anchor=anchor,
        percent=Decimal("30.00"),
        updated_at=datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC),
    )


def test_continue_resolves_the_chapter_title_of_the_stored_anchor() -> None:
    user = _user()
    source_id = uuid4()
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source_id)
    positions = _FakeRecentPositions(_recent(source_id, anchor="c1s1"))
    service = ContinueReading(positions=positions, corpus=corpus)

    point = service(user=user)

    assert point == ContinuePoint(
        source_id=source_id,
        source_title="A Book",
        # c1s1 (position 1, depth 1) belongs to the first chapter, titled "Chapter 0".
        chapter_title="Chapter 0",
        percent=Decimal("30.00"),
        updated_at=datetime(2026, 7, 20, 10, 0, 0, tzinfo=UTC),
    )


def test_continue_resolves_an_alias_anchor_to_its_chapter() -> None:
    user = _user()
    source_id = uuid4()
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source_id)
    positions = _FakeRecentPositions(_recent(source_id, anchor="old-c2"))
    service = ContinueReading(positions=positions, corpus=corpus)

    point = service(user=user)

    # The alias "old-c2" resolves to the second chapter, titled "Chapter 2".
    assert point is not None
    assert point.chapter_title == "Chapter 2"


def test_continue_stale_anchor_falls_back_to_the_first_chapter_title() -> None:
    # The stored anchor no longer resolves (a superseded corpus) → the first chapter,
    # never an error or dangling render.
    user = _user()
    source_id = uuid4()
    corpus = FakeCorpusRepository()
    _seed_book(corpus, source_id)
    positions = _FakeRecentPositions(_recent(source_id, anchor="gone"))
    service = ContinueReading(positions=positions, corpus=corpus)

    point = service(user=user)

    assert point is not None
    assert point.chapter_title == "Chapter 0"


def test_continue_without_a_corpus_yields_an_empty_chapter_title() -> None:
    user = _user()
    source_id = uuid4()
    positions = _FakeRecentPositions(_recent(source_id, anchor="c1"))
    # FakeCorpusRepository with no book → get_chapter_index returns None.
    service = ContinueReading(positions=positions, corpus=FakeCorpusRepository())

    point = service(user=user)

    assert point is not None
    assert point.chapter_title == ""
    assert point.source_title == "A Book"


def test_continue_returns_none_when_the_user_has_no_positions() -> None:
    user = _user()
    service = ContinueReading(
        positions=_FakeRecentPositions(None), corpus=FakeCorpusRepository()
    )

    assert service(user=user) is None
