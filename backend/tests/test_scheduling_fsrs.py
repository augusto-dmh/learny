"""D1 gate — FSRS-6 scheduling adapter (unit, fuzzing off).

Pins the ``SchedulingPort`` behaviour the review path relies on (QUIZ-11) at the
adapter level, never the py-fsrs internals: ``initial`` yields a due-now Learning
card; the four ratings advance monotonically (Again short-resets, Easy's interval
exceeds Good's); repeated Good in the Review state grows the interval; every
datetime is timezone-aware UTC; and a ``SchedulingSnapshot`` round-trips through
the private card mapping losslessly. Fuzzing is disabled so due dates are
deterministic and the assertions are exact orderings, not fixed intervals
(design §Scheduling adapter).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.entities import ReviewLogEntry, SchedulingSnapshot
from app.infrastructure.scheduling.fsrs import (
    FsrsSchedulingAdapter,
    _to_card,
    _to_snapshot,
)

# The FSRS-6 ``State`` enum ints the snapshot stores (design §Domain).
_LEARNING = 1
_REVIEW = 2

# Ratings are the port's integers Again(1)/Hard(2)/Good(3)/Easy(4) — callers never
# touch ``fsrs.Rating`` (QUIZ-11).
_AGAIN, _HARD, _GOOD, _EASY = 1, 2, 3, 4

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _adapter() -> FsrsSchedulingAdapter:
    """Build the adapter with fuzzing off so due dates are deterministic (design)."""
    return FsrsSchedulingAdapter(fuzzing=False)


def _interval(rating: int) -> timedelta:
    """Return ``due - reviewed_at`` after applying ``rating`` to a fresh initial card."""
    adapter = _adapter()
    snapshot, _log = adapter.review(adapter.initial(), rating, _T0)
    return snapshot.due - _T0


# --- initial() (QUIZ-11: due now, Learning) -------------------------------------


def test_initial_is_due_now_learning() -> None:
    adapter = _adapter()
    before = datetime.now(UTC)
    snapshot = adapter.initial()
    after = datetime.now(UTC)

    assert snapshot.state == _LEARNING
    assert snapshot.step == 0
    assert snapshot.last_review is None
    # ``due`` is "now" — bracketed by the wall-clock readings around the call.
    assert before <= snapshot.due <= after


def test_initial_due_is_timezone_aware_utc() -> None:
    snapshot = _adapter().initial()
    assert snapshot.due.tzinfo is not None
    assert snapshot.due.utcoffset() == timedelta(0)


# --- monotonic ratings (QUIZ-11: Again short-reset, Easy > Good) ----------------


def test_ratings_are_monotonic_from_initial() -> None:
    # The four ratings applied to the same fresh card produce strictly increasing
    # next-review intervals — the core FSRS ordering the 4-button grade bar relies on.
    again = _interval(_AGAIN)
    hard = _interval(_HARD)
    good = _interval(_GOOD)
    easy = _interval(_EASY)

    assert again < hard < good < easy


def test_easy_interval_exceeds_good_interval() -> None:
    # QUIZ-11 names this explicitly: Easy schedules further out than Good.
    assert _interval(_EASY) > _interval(_GOOD)


def test_again_resets_short_and_keeps_learning() -> None:
    # Again is the short-reset: it stays in Learning and is due again well before
    # a Good on the same card would be.
    adapter = _adapter()
    snapshot, _log = adapter.review(adapter.initial(), _AGAIN, _T0)

    assert snapshot.state == _LEARNING
    assert snapshot.due - _T0 < _interval(_GOOD)


def test_repeated_good_grows_interval() -> None:
    # Two Goods graduate the card into Review; each further Good in Review grows the
    # interval versus the previous one (spaced-repetition expansion).
    adapter = _adapter()
    step1, _log = adapter.review(adapter.initial(), _GOOD, _T0)
    graduated, _log = adapter.review(step1, _GOOD, step1.due)
    assert graduated.state == _REVIEW
    interval_into_review = graduated.due - step1.due

    grown, _log = adapter.review(graduated, _GOOD, graduated.due)
    next_interval = grown.due - graduated.due

    assert next_interval > interval_into_review


# --- review-log entry (QUIZ-12) -------------------------------------------------


def test_review_returns_log_entry_with_rating_and_time() -> None:
    adapter = _adapter()
    snapshot, log = adapter.review(adapter.initial(), _GOOD, _T0)

    assert isinstance(log, ReviewLogEntry)
    assert log.rating == _GOOD
    assert log.reviewed_at == _T0
    # The adapter does not attach a duration — the service does (QUIZ-12).
    assert log.review_duration_ms is None


# --- UTC everywhere (QUIZ-11) ---------------------------------------------------


def test_review_datetimes_are_timezone_aware_utc() -> None:
    adapter = _adapter()
    snapshot, _log = adapter.review(adapter.initial(), _GOOD, _T0)

    assert snapshot.due.utcoffset() == timedelta(0)
    assert snapshot.last_review is not None
    assert snapshot.last_review.utcoffset() == timedelta(0)


# --- snapshot ↔ Card round-trip -------------------------------------------------


def test_snapshot_card_roundtrip_is_lossless() -> None:
    # A persisted snapshot reconstructs into an ``fsrs.Card`` and back with every
    # field identical — so scheduling state survives the DB round-trip unchanged.
    snapshot = SchedulingSnapshot(
        state=_REVIEW,
        step=None,
        stability=12.5,
        difficulty=6.0,
        due=datetime(2026, 2, 3, 12, 0, tzinfo=UTC),
        last_review=datetime(2026, 1, 20, 8, 30, tzinfo=UTC),
    )

    assert _to_snapshot(_to_card(snapshot)) == snapshot


def test_review_from_persisted_snapshot_is_deterministic() -> None:
    # Reviewing the same persisted snapshot twice yields identical advanced state —
    # proof the snapshot carries all scheduling state the adapter needs (round-trip).
    adapter = _adapter()
    persisted, _log = adapter.review(adapter.initial(), _GOOD, _T0)
    later = persisted.due

    first, _ = adapter.review(persisted, _GOOD, later)
    second, _ = adapter.review(persisted, _GOOD, later)

    assert first == second
