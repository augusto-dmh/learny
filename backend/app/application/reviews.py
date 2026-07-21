"""Review use-case services (Cycle E, design §Application services).

Framework-free orchestration of the review path (ADR-007/009): nothing here
imports FastAPI, SQLAlchemy, or a provider SDK. ``GetDueQueue`` serves the
user-scoped due queue (QUIZ-13); ``SubmitReview`` grades one item, advancing its
FSRS scheduling and appending an immutable review-log row in one transaction
(QUIZ-12); ``ResetSchedule`` returns one card to its fresh state (NL-12). Ownership
is the card's own ``user_id`` (AD-149) — reachable even for a source-less ``note``
card — so a missing or non-owned item is indistinguishable (``QuizItemNotFound`` →
404, no disclosure).
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from app.application.dates import local_day
from app.application.errors import (
    QuizItemNotFound,
    QuizItemNotReviewable,
)
from app.domain.entities import (
    DueReviewItem,
    QuizItem,
    QuizItemStatus,
    SchedulingSnapshot,
    User,
)
from app.domain.ports import (
    Clock,
    QuizItemRepository,
    SchedulingPort,
    StudyDayRepository,
)


def _owned_item(items: QuizItemRepository, user: User, item_id: UUID) -> QuizItem:
    """Return the caller's quiz item, else ``QuizItemNotFound`` (AD-149 non-disclosure).

    Ownership is the item's denormalized ``user_id`` — the only reach that works for a
    source-less ``note`` card, and identical to the source owner for deck/highlight cards.
    A missing item and another user's item collapse to the same 404.
    """
    item = items.get_by_id(item_id)
    if item is None or item.user_id != user.id:
        raise QuizItemNotFound("Quiz item not found.")
    return item

# Due-queue bounds (A-6 / QUIZ-13): default page size and the hard cap the service
# enforces regardless of the requested limit (the web layer 422s over the cap first).
DEFAULT_DUE_LIMIT = 20
MAX_DUE_LIMIT = 100


class GetDueQueue:
    """Return the caller's due review queue across their sources (QUIZ-13).

    Active items with ``due <= now`` (stale/orphaned excluded, QUIZ-17), ordered
    ``due ASC, id ASC`` (A-6), optionally filtered to one ``source_id``. The limit
    defaults to :data:`DEFAULT_DUE_LIMIT` and is capped at :data:`MAX_DUE_LIMIT`;
    the total due count is the full count before the limit. Ownership is enforced
    by the repository's join through ``sources`` — no cross-user leakage.
    """

    def __init__(self, *, items: QuizItemRepository, clock: Clock) -> None:
        self._items = items
        self._clock = clock

    def __call__(
        self,
        *,
        user: User,
        limit: int | None = None,
        source_id: UUID | None = None,
    ) -> tuple[int, list[DueReviewItem]]:
        effective = DEFAULT_DUE_LIMIT if limit is None else limit
        capped = min(effective, MAX_DUE_LIMIT)
        return self._items.due_for_user(
            user.id, now=self._clock.now(), limit=capped, source_id=source_id
        )


class SubmitReview:
    """Grade one owned, active quiz item and schedule its next review (QUIZ-12).

    Loads the item and authorizes on its own ``user_id`` (AD-149; missing or non-owner →
    ``QuizItemNotFound`` → 404, no disclosure — a source-less ``note`` card is reviewable
    the same as any other), and rejects a non-``active`` item (``QuizItemNotReviewable`` →
    409). Early review of a not-yet-due active item is allowed (A-4, cramming). On success
    it advances the scheduling snapshot via :class:`~app.domain.ports.SchedulingPort` and
    appends the review-log row (with any client-supplied duration) in the caller's single
    transaction (QUIZ-12), returning the updated snapshot. Reviewing a note card naturally
    retires its "your note changed" badge — the due queue derives it against the last
    review time (NL-12), so no explicit clear is needed here.

    Submitting a review also credits the reviewer's study day: an atomic
    ``StudyDayRepository.record`` (``reviews_count += 1``) on the user-local day derived
    from ``client_tz`` (HOME-07), issued on the same connection as the log append so the
    review and its day credit commit together (I-1). A missing/invalid ``client_tz``
    degrades to UTC via :func:`~app.application.dates.local_day` (HOME-09), never an error.
    """

    def __init__(
        self,
        *,
        items: QuizItemRepository,
        scheduling: SchedulingPort,
        clock: Clock,
        study_days: StudyDayRepository,
    ) -> None:
        self._items = items
        self._scheduling = scheduling
        self._clock = clock
        self._study_days = study_days

    def __call__(
        self,
        *,
        user: User,
        item_id: UUID,
        rating: int,
        review_duration_ms: int | None = None,
        client_tz: str | None = None,
    ) -> SchedulingSnapshot:
        item = _owned_item(self._items, user, item_id)
        if item.status != QuizItemStatus.ACTIVE:
            raise QuizItemNotReviewable("Quiz item is not reviewable.")

        now = self._clock.now()
        snapshot = self._items.get_scheduling(item.id)
        advanced, log = self._scheduling.review(snapshot, rating, now)
        self._items.update_scheduling(item.id, advanced)
        self._items.append_log(item.id, replace(log, review_duration_ms=review_duration_ms))
        self._study_days.record(user.id, local_day(now, client_tz), reviews=1)
        return advanced


class ResetSchedule:
    """Return one owned, active card to the fresh state a new card receives (NL-12).

    The only non-review path that changes scheduling. Loads the item and authorizes on
    its ``user_id`` (AD-149; missing/non-owner → 404), rejects a non-``active`` item
    (``QuizItemNotReviewable`` → 409), then replaces its scheduling snapshot with
    :meth:`SchedulingPort.initial` — the same fresh state minting produces, never a
    hand-rolled FSRS literal — and clears its ``note_changed_at`` so the review badge
    retires. The append-only ``review_log`` is deliberately left untouched: a reset drops
    the schedule the reader chose to abandon, but their grade history stays (ADR-0026 d5).
    """

    def __init__(
        self,
        *,
        items: QuizItemRepository,
        scheduling: SchedulingPort,
    ) -> None:
        self._items = items
        self._scheduling = scheduling

    def __call__(self, *, user: User, item_id: UUID) -> SchedulingSnapshot:
        item = _owned_item(self._items, user, item_id)
        if item.status != QuizItemStatus.ACTIVE:
            raise QuizItemNotReviewable("Quiz item is not reviewable.")

        fresh = self._scheduling.initial()
        self._items.update_scheduling(item.id, fresh)
        self._items.clear_note_changed(item.id)
        return fresh
