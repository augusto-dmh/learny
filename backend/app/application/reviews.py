"""Review use-case services (Cycle E, design §Application services).

Framework-free orchestration of the review path (ADR-007/009): nothing here
imports FastAPI, SQLAlchemy, or a provider SDK. ``GetDueQueue`` serves the
user-scoped due queue (QUIZ-13); ``SubmitReview`` grades one item, advancing its
FSRS scheduling and appending an immutable review-log row in one transaction
(QUIZ-12). Ownership is reached through the item's parent source, so a missing or
non-owned item is indistinguishable (``QuizItemNotFound`` → 404, no disclosure).
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from app.application.errors import (
    NotAuthorized,
    QuizItemNotFound,
    QuizItemNotReviewable,
)
from app.application.identity import AuthorizeOwnership
from app.domain.entities import (
    DueReviewItem,
    QuizItemStatus,
    SchedulingSnapshot,
    User,
)
from app.domain.ports import (
    Clock,
    QuizItemRepository,
    SchedulingPort,
    SourceRepository,
)

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

    Loads the item (missing → ``QuizItemNotFound`` → 404), authorizes through its
    parent source (non-owner → the same 404, no disclosure), and rejects a
    non-``active`` item (``QuizItemNotReviewable`` → 409). Early review of a
    not-yet-due active item is allowed (A-4, cramming). On success it advances the
    scheduling snapshot via :class:`~app.domain.ports.SchedulingPort` and appends
    the review-log row (with any client-supplied duration) in the caller's single
    transaction (QUIZ-12), returning the updated snapshot.
    """

    def __init__(
        self,
        *,
        items: QuizItemRepository,
        sources: SourceRepository,
        scheduling: SchedulingPort,
        authorize: AuthorizeOwnership,
        clock: Clock,
    ) -> None:
        self._items = items
        self._sources = sources
        self._scheduling = scheduling
        self._authorize = authorize
        self._clock = clock

    def __call__(
        self,
        *,
        user: User,
        item_id: UUID,
        rating: int,
        review_duration_ms: int | None = None,
    ) -> SchedulingSnapshot:
        item = self._items.get_by_id(item_id)
        if item is None:
            raise QuizItemNotFound("Quiz item not found.")

        # Ownership is reachable only via the parent source (AD-014). A missing
        # source and a non-owner both collapse to the same 404 (no disclosure).
        source = self._sources.get_by_id(item.source_id)
        if source is None:
            raise QuizItemNotFound("Quiz item not found.")
        try:
            self._authorize(user=user, owner_id=source.user_id)
        except NotAuthorized as exc:
            raise QuizItemNotFound("Quiz item not found.") from exc

        if item.status != QuizItemStatus.ACTIVE:
            raise QuizItemNotReviewable("Quiz item is not reviewable.")

        snapshot = self._items.get_scheduling(item.id)
        advanced, log = self._scheduling.review(snapshot, rating, self._clock.now())
        self._items.update_scheduling(item.id, advanced)
        self._items.append_log(item.id, replace(log, review_duration_ms=review_duration_ms))
        return advanced
