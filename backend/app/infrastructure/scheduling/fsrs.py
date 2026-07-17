"""FSRS-6 scheduling adapter (implements ``SchedulingPort``, QUIZ-11).

The py-fsrs library lives only here (ADR-0007/0009): callers work with the Learny-owned
:class:`~app.domain.entities.SchedulingSnapshot` and integer ratings, never with
``fsrs.Card``/``fsrs.Rating``. The scheduler uses FSRS-6 defaults (``desired_retention``,
default learning steps, ``maximum_interval=36500``); fuzzing is settings-controlled so
tests can disable the due-date randomization and assert monotonic behaviour rather than
exact intervals. All datetimes are timezone-aware UTC.

Created during Phase C because the deck worker (``generate_quiz_deck``) needs a concrete
``SchedulingPort`` to create initial scheduling rows; Phase D (the review path) reuses the
same adapter for ``review``.
"""

from __future__ import annotations

from datetime import datetime

from fsrs import Card, Rating, Scheduler, State

from app.domain.entities import ReviewLogEntry, SchedulingSnapshot

# The FSRS-6 maximum interval (days) — a card is never scheduled further out (design).
_MAXIMUM_INTERVAL = 36500


def _to_snapshot(card: Card) -> SchedulingSnapshot:
    """Project an ``fsrs.Card`` onto the Learny-owned snapshot (state as its int)."""
    return SchedulingSnapshot(
        state=int(card.state),
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=card.due,
        last_review=card.last_review,
    )


def _to_card(snapshot: SchedulingSnapshot) -> Card:
    """Reconstruct an ``fsrs.Card`` from a persisted snapshot."""
    return Card(
        state=State(snapshot.state),
        step=snapshot.step,
        stability=snapshot.stability,
        difficulty=snapshot.difficulty,
        due=snapshot.due,
        last_review=snapshot.last_review,
    )


class FsrsSchedulingAdapter:
    """``SchedulingPort`` backed by py-fsrs (FSRS-6).

    Wraps one :class:`fsrs.Scheduler`; ``initial`` returns a fresh card's state (``due``
    now, Learning), and ``review`` applies a 1–4 rating at ``reviewed_at`` and returns the
    advanced snapshot plus the review-log entry the service persists.
    """

    def __init__(
        self,
        *,
        desired_retention: float = 0.9,
        fuzzing: bool = True,
        maximum_interval: int = _MAXIMUM_INTERVAL,
    ) -> None:
        self._scheduler = Scheduler(
            desired_retention=desired_retention,
            enable_fuzzing=fuzzing,
            maximum_interval=maximum_interval,
        )

    def initial(self) -> SchedulingSnapshot:
        """Return the initial scheduling state for a new item (``due`` now, Learning)."""
        return _to_snapshot(Card())

    def review(
        self, snapshot: SchedulingSnapshot, rating: int, reviewed_at: datetime
    ) -> tuple[SchedulingSnapshot, ReviewLogEntry]:
        """Apply a grade to ``snapshot`` at ``reviewed_at`` (rating 1–4)."""
        card, _log = self._scheduler.review_card(
            _to_card(snapshot), Rating(rating), review_datetime=reviewed_at
        )
        return _to_snapshot(card), ReviewLogEntry(rating=rating, reviewed_at=reviewed_at)
