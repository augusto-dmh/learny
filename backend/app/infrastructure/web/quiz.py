"""Quiz + review router — deck generation, overview, due queue, review (Cycle E).

Thin FastAPI adapter over the framework-free quiz/review services (assembled in
``dependencies``). A signed-in owner generates a quiz deck for a ready source,
polls the per-source overview for progress, pulls their cross-source due queue,
and submits 4-button self-grades. The deck POST owns the same commit-then-enqueue-
then-compensate orchestration as ingestion (AD-016): it commits the queued job in
UoW1, enqueues after commit so the worker always sees a durable row, and on an
enqueue failure opens UoW2 to drive the job terminal ``failed`` before returning
502 — so no phantom queued job blocks the QUIZ-04 single-in-flight guard.

Application errors are translated to HTTP by the global handlers
(``SourceNotFound`` → 404, ``SourceNotReady`` → 409, ``QuizDeckConflict`` → 409,
``QuizItemNotFound`` → 404, ``QuizItemNotReviewable`` → 409, ``EnqueueFailed`` →
502). Rating bounds (1..4) and the due ``limit`` cap (≤ 100) are Pydantic
validation → 422.

Contract (also consumed by the Next.js proxy):
- ``POST /api/sources/{id}/quiz/deck`` → 202 deck job; auth + CSRF/Origin + limit.
- ``GET  /api/sources/{id}/quiz`` → 200 items + counts + due count + latest job.
- ``GET  /api/reviews/due`` → 200 due queue + total; auth.
- ``POST /api/quiz-items/{id}/reviews`` → 200 updated scheduling; auth + CSRF/Origin
  + limit.
- ``POST /api/quiz-items/{id}/schedule-reset`` → 200 fresh scheduling + badge cleared;
  auth + CSRF/Origin + limit (NL-12).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from app.application.errors import EnqueueFailed
from app.application.quiz import ExportQuizDeck, ListQuizItems, QuizOverview
from app.application.reviews import GetDueQueue, ResetSchedule, SubmitReview
from app.domain.entities import (
    CardProvenance,
    DueReviewItem,
    QuizGenerationJob,
    QuizItem,
    QuizItemStatus,
    SchedulingSnapshot,
    User,
)
from app.domain.ports import QuizDeckEnqueuer
from app.infrastructure.export.anki import build_apkg
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    build_deck_compensate,
    build_plan_deck_generation,
    get_authenticated_user,
    get_due_queue,
    get_export_quiz_deck,
    get_list_quiz_items,
    get_quiz_deck_enqueuer,
    get_quiz_uow,
    get_reset_schedule,
    get_submit_review,
)
from app.infrastructure.web.rate_limit import rate_limit_quiz

logger = logging.getLogger(__name__)

router = APIRouter(tags=["quiz"])

# A fixed, non-secret durable error for the enqueue-failure compensation; the
# underlying broker exception is never surfaced to the client or the log line.
_ENQUEUE_FAILURE_ERROR = "Failed to enqueue quiz deck generation."


def _export_filename(source_title: str) -> str:
    """Return a safe ``<title>.apkg`` attachment filename derived from ``source_title``.

    Strips everything but ASCII word chars, spaces, and dashes (Content-Disposition
    is latin-1 encoded, so non-ASCII would break it), collapses whitespace, and
    falls back to ``deck`` when nothing printable remains.
    """
    base = re.sub(r"[^A-Za-z0-9 _-]+", "", source_title).strip()
    base = re.sub(r"\s+", "_", base) or "deck"
    return f"{base}.apkg"


# --- Request bodies ------------------------------------------------------------


class ReviewRequest(BaseModel):
    """Review-submit body (QUIZ-12).

    ``rating`` is FSRS's Again(1)/Hard(2)/Good(3)/Easy(4) — anything outside 1..4 is
    a Pydantic validation error → 422 before the service runs. ``review_duration_ms``
    is the optional client-supplied timing (non-negative).
    """

    rating: int = Field(ge=1, le=4)
    review_duration_ms: int | None = Field(default=None, ge=0)


# --- Response views ------------------------------------------------------------


class QuizJobView(BaseModel):
    """A deck-generation job's public state (QUIZ-03/09/14) — the deck-poll target."""

    id: UUID
    status: str
    attempts: int
    generated_count: int
    discarded_count: int
    failed_sections: int
    error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: QuizGenerationJob) -> QuizJobView:
        return cls(
            id=job.id,
            status=job.status,
            attempts=job.attempts,
            generated_count=job.generated_count,
            discarded_count=job.discarded_count,
            failed_sections=job.failed_sections,
            error=job.last_error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class QuizItemSummaryView(BaseModel):
    """One item in the per-source overview (QUIZ-14): id, type, question, status, due."""

    id: UUID
    item_type: str
    question: str
    status: str
    due: datetime | None

    @classmethod
    def from_item(cls, item: QuizItem, due: datetime | None) -> QuizItemSummaryView:
        return cls(
            id=item.id,
            item_type=item.item_type,
            question=item.question,
            status=item.status,
            due=due,
        )


class QuizOverviewView(BaseModel):
    """The per-source overview: items, per-status counts, due count, latest job (QUIZ-14)."""

    items: list[QuizItemSummaryView]
    counts_by_status: dict[str, int]
    due_count: int
    latest_job: QuizJobView | None

    @classmethod
    def from_overview(cls, overview: QuizOverview, *, now: datetime) -> QuizOverviewView:
        # The due count is the active items whose scheduled ``due`` has arrived — the
        # same active-and-due<=now predicate as the review queue (QUIZ-13/17).
        due_count = sum(
            1
            for item in overview.items
            if item.status == QuizItemStatus.ACTIVE
            and (d := overview.due_by_item.get(item.id)) is not None
            and d <= now
        )
        return cls(
            items=[
                QuizItemSummaryView.from_item(item, overview.due_by_item.get(item.id))
                for item in overview.items
            ],
            counts_by_status=overview.counts_by_status,
            due_count=due_count,
            latest_job=(
                QuizJobView.from_job(overview.latest_job)
                if overview.latest_job is not None
                else None
            ),
        )


class CitationView(BaseModel):
    """A due card's citation snapshot (QUIZ-15) — resolves via the reader anchor."""

    section_path: list[str]
    anchor: str
    source_excerpt: str


class CardProvenanceView(BaseModel):
    """The origin note of a card accepted from a highlight (CAP-16).

    Read by join, so a renamed note shows its current title at review.
    """

    note_id: UUID
    note_title: str

    @classmethod
    def from_provenance(cls, provenance: CardProvenance) -> CardProvenanceView:
        return cls(note_id=provenance.note_id, note_title=provenance.note_title)


class DueItemView(BaseModel):
    """One due review card (QUIZ-13/15).

    Carries the full card — question, answer, and citation — because reveal is a
    client-side act in the self-grade flow (no server round-trip to reveal).
    ``provenance`` is the origin note of a card the student made at a passage; it is
    explicitly ``null`` for a deck card and for a card whose origin note was deleted,
    both of which stay in the queue and stay reviewable from their own citation
    snapshot (CAP-15/16).
    """

    id: UUID
    # ``null`` for a source-less ``note`` card (AD-149); ``source_title`` is then the
    # constant "Your notes".
    source_id: UUID | None
    source_title: str
    item_type: str
    question: str
    answer: str
    citation: CitationView
    provenance: CardProvenanceView | None
    status: str
    due: datetime
    # The "your note changed" badge (NL-12): the origin note changed since this card was
    # last reviewed or created. Always ``false`` for deck/highlight cards.
    note_changed: bool

    @classmethod
    def from_due(cls, due: DueReviewItem) -> DueItemView:
        item = due.item
        return cls(
            id=item.id,
            source_id=item.source_id,
            source_title=due.source_title,
            item_type=item.item_type,
            question=item.question,
            answer=item.answer,
            citation=CitationView(
                section_path=list(item.section_path),
                anchor=item.anchor,
                source_excerpt=item.source_excerpt,
            ),
            provenance=(
                CardProvenanceView.from_provenance(due.provenance)
                if due.provenance is not None
                else None
            ),
            status=item.status,
            due=due.due,
            note_changed=due.note_changed,
        )


class DueQueueView(BaseModel):
    """The due queue response (QUIZ-13): the page of items and the full due total."""

    items: list[DueItemView]
    total_due: int


class SchedulingView(BaseModel):
    """The updated scheduling snapshot returned after a review (QUIZ-12)."""

    state: int
    step: int | None
    stability: float | None
    difficulty: float | None
    due: datetime
    last_review: datetime | None

    @classmethod
    def from_snapshot(cls, snapshot: SchedulingSnapshot) -> SchedulingView:
        return cls(
            state=snapshot.state,
            step=snapshot.step,
            stability=snapshot.stability,
            difficulty=snapshot.difficulty,
            due=snapshot.due,
            last_review=snapshot.last_review,
        )


UowFactory = Annotated[
    Callable[[], AbstractContextManager[Connection]], Depends(get_quiz_uow)
]
DeckEnqueuer = Annotated[QuizDeckEnqueuer, Depends(get_quiz_deck_enqueuer)]


# --- Endpoints -----------------------------------------------------------------


@router.post(
    "/api/sources/{source_id}/quiz/deck",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(rate_limit_quiz),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def generate_quiz_deck(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    uow_factory: UowFactory,
    enqueuer: DeckEnqueuer,
) -> QuizJobView:
    """Create a queued deck job and enqueue it (202); 404/409/502 per the deck ACs.

    ``PlanDeckGeneration`` authorizes ownership (missing/non-owner →
    ``SourceNotFound`` → 404), enforces readiness (``SourceNotReady`` → 409), and
    guards the single-in-flight invariant (``QuizDeckConflict`` → 409). The job is
    committed in UoW1 before the enqueue; an enqueue failure compensates the job to
    terminal ``failed`` in UoW2 and returns 502 (no phantom queued job).
    """
    # UoW1: create the queued job (ownership/readiness/single-in-flight enforced).
    with uow_factory() as conn:
        job = build_plan_deck_generation(conn)(user=user, source_id=source_id)

    # Enqueue only after the job is durably committed (AD-016).
    try:
        enqueuer.enqueue_quiz_deck(source_id=source_id, job_id=job.id)
    except Exception as exc:  # noqa: BLE001 — any enqueue failure compensates → 502
        with uow_factory() as conn:
            build_deck_compensate(conn).fail(job.id, _ENQUEUE_FAILURE_ERROR)
        logger.warning(
            "quiz deck enqueue failed",
            extra={"source_id": str(source_id), "job_id": str(job.id)},
        )
        raise EnqueueFailed("Could not start quiz deck generation.") from exc

    logger.info(
        "quiz deck generation started",
        extra={"source_id": str(source_id), "job_id": str(job.id)},
    )
    return QuizJobView.from_job(job)


@router.get("/api/sources/{source_id}/quiz")
def get_quiz_overview(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ListQuizItems, Depends(get_list_quiz_items)],
) -> QuizOverviewView:
    """Return the owned source's items + counts + due count + latest job (200; 404).

    The deck-progress polling target: ``ListQuizItems`` authorizes ownership
    (missing/non-owner → ``SourceNotFound`` → 404) and returns the overview.
    """
    overview = service(user=user, source_id=source_id)
    return QuizOverviewView.from_overview(overview, now=datetime.now(UTC))


@router.get("/api/reviews/due")
def get_due_reviews(
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[GetDueQueue, Depends(get_due_queue)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    source_id: Annotated[UUID | None, Query()] = None,
) -> DueQueueView:
    """Return the caller's due queue across their sources (200).

    Active items with ``due <= now`` (stale/orphaned excluded), ordered ``due ASC,
    id ASC``; optional ``source_id`` filter. ``limit`` defaults to 20 and is capped
    at 100 by Pydantic — over-100 → 422.
    """
    total, items = service(user=user, limit=limit, source_id=source_id)
    return DueQueueView(items=[DueItemView.from_due(d) for d in items], total_due=total)


@router.post(
    "/api/quiz-items/{item_id}/reviews",
    dependencies=[
        Depends(rate_limit_quiz),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def submit_review(
    item_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[SubmitReview, Depends(get_submit_review)],
    body: ReviewRequest,
) -> SchedulingView:
    """Grade one owned active item and return its updated scheduling (200).

    ``SubmitReview`` resolves the item + owner (missing/non-owner →
    ``QuizItemNotFound`` → 404), rejects a non-active item
    (``QuizItemNotReviewable`` → 409), advances the FSRS schedule, and appends the
    review-log row (with the optional duration) in one transaction. Rating outside
    1..4 → 422 (Pydantic, before the service runs).
    """
    snapshot = service(
        user=user,
        item_id=item_id,
        rating=body.rating,
        review_duration_ms=body.review_duration_ms,
    )
    return SchedulingView.from_snapshot(snapshot)


@router.post(
    "/api/quiz-items/{item_id}/schedule-reset",
    dependencies=[
        Depends(rate_limit_quiz),
        Depends(enforce_origin),
        Depends(enforce_csrf),
    ],
)
def reset_schedule(
    item_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ResetSchedule, Depends(get_reset_schedule)],
) -> SchedulingView:
    """Reset one owned active card to its fresh state and retire the badge (200; 404/409).

    ``ResetSchedule`` resolves the item on its own ``user_id`` (missing/non-owner →
    ``QuizItemNotFound`` → 404, no disclosure — a source-less note card resets the same as
    any other), rejects a non-active item (``QuizItemNotReviewable`` → 409), replaces the
    scheduling snapshot with the fresh initial state, and clears the note-changed flag. The
    append-only review log is left untouched. This is the only non-review path that changes
    scheduling (NL-12).
    """
    return SchedulingView.from_snapshot(service(user=user, item_id=item_id))


@router.get("/api/sources/{source_id}/quiz/export")
def export_quiz_deck(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ExportQuizDeck, Depends(get_export_quiz_deck)],
) -> Response:
    """Stream the owned source's quiz deck as a genanki ``.apkg`` (200; 404).

    ``ExportQuizDeck`` authorizes ownership (missing/non-owner → ``SourceNotFound``
    → 404). A source with no items → 404 (nothing to export, QUIZ-22). Otherwise the
    package bytes are returned as an ``application/octet-stream`` attachment named
    from the (sanitized) book title.
    """
    title, items = service(user=user, source_id=source_id)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No quiz items to export."
        )
    data = build_apkg(items, title)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{_export_filename(title)}"'
        },
    )
