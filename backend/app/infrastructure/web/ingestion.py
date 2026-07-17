"""Ingestion router — start and observe a source's ingestion job (Phase 4).

Thin FastAPI adapter over the framework-free ingestion services. The start
handler owns the commit-then-enqueue-then-compensate orchestration (AD-016): it
commits the queued job in UoW1, enqueues after commit so the worker always sees
a durable row, and on an enqueue failure opens UoW2 to drive the job to terminal
``failed`` (leaving no phantom active job, ING-11) before returning ``502``.

Contract (also consumed by the Next.js proxy):
- ``POST /api/sources/{id}/ingestion`` → 202, start ingestion; auth + CSRF/Origin.
- ``GET  /api/sources/{id}/ingestion`` → 200 latest job + ordered events (auth).

Application errors are translated to HTTP status codes by the global handlers in
``error_handlers``; the returned ``IngestionSummary`` is secret-free.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from app.application.errors import ActiveIngestionExists, EnqueueFailed
from app.application.ingestion import ReadIngestion
from app.domain.entities import IngestionEvent, IngestionJob, User
from app.domain.ports import IngestionEnqueuer
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    build_compensate,
    build_start_ingestion,
    get_authenticated_user,
    get_ingestion_enqueuer,
    get_ingestion_uow,
    get_read_ingestion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["ingestion"])

# A fixed, non-secret durable error for the enqueue-failure compensation (ING-11);
# the underlying broker exception is never surfaced to the client or the log line.
_ENQUEUE_FAILURE_ERROR = "Failed to enqueue ingestion task."


class IngestionEventView(BaseModel):
    """Public view of one progress-log entry (safe to return)."""

    type: str
    message: str | None
    created_at: datetime

    @classmethod
    def from_entity(cls, event: IngestionEvent) -> IngestionEventView:
        return cls(type=event.type, message=event.message, created_at=event.created_at)


class IngestionSummary(BaseModel):
    """Public, secret-free view of a job + its events (spec P1-Observe AC4).

    Exposes only job/event lifecycle state — never the source's ``object_key`` or
    ``checksum`` (those are internal storage/integrity details).
    """

    id: UUID
    status: str
    attempts: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    events: list[IngestionEventView]

    @classmethod
    def from_entities(
        cls, job: IngestionJob, events: list[IngestionEvent]
    ) -> IngestionSummary:
        return cls(
            id=job.id,
            status=job.status,
            attempts=job.attempts,
            error=job.last_error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            events=[IngestionEventView.from_entity(e) for e in events],
        )


UowFactory = Annotated[
    Callable[[], AbstractContextManager[Connection]], Depends(get_ingestion_uow)
]
Enqueuer = Annotated[IngestionEnqueuer, Depends(get_ingestion_enqueuer)]


@router.post(
    "/{source_id}/ingestion",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_origin), Depends(enforce_csrf)],
)
def start_ingestion(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    uow_factory: UowFactory,
    enqueuer: Enqueuer,
) -> IngestionSummary:
    """Create a queued job and enqueue it (202); 409/404/502 per the ingestion ACs.

    ``StartIngestion`` guards the active-job invariant with an application
    pre-check (→ 409); the ``IntegrityError`` catch here is defense-in-depth for
    the true-race loser whose INSERT hits the partial unique index (ING-03).
    """
    # UoW1: create the queued job, mark the source processing, append ``queued``.
    # ``StartIngestion`` returns the job with its ``queued`` event so the response
    # is composed without the handler touching a persistence adapter.
    with uow_factory() as conn:
        try:
            job, events, content_type = build_start_ingestion(conn)(
                user=user, source_id=source_id
            )
        except IntegrityError as exc:
            raise ActiveIngestionExists("Ingestion is already in progress.") from exc

    # Enqueue only after the job is durably committed (AD-016), so no worker can
    # dequeue a row that does not yet exist. The content type selects the queue so
    # a PDF parse lands on the isolated worker, not the default one (ING-17).
    try:
        enqueuer.enqueue_ingestion(
            source_id=source_id, job_id=job.id, content_type=content_type
        )
    except Exception as exc:  # noqa: BLE001 — any enqueue failure compensates → 502
        # UoW2: no worker will ever run this job, so drive it terminal ``failed``
        # (source ``failed`` + ``failed`` event). Terminal ⇒ it leaves the active
        # set, so a restart POST is not blocked (ING-11).
        with uow_factory() as conn:
            build_compensate(conn).fail(job.id, _ENQUEUE_FAILURE_ERROR)
        logger.warning(
            "ingestion enqueue failed",
            extra={"source_id": str(source_id), "job_id": str(job.id)},
        )
        raise EnqueueFailed("Could not start ingestion.") from exc

    logger.info(
        "ingestion started",
        extra={"source_id": str(source_id), "job_id": str(job.id)},
    )
    return IngestionSummary.from_entities(job, events)


@router.get("/{source_id}/ingestion")
def read_ingestion(
    source_id: UUID,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[ReadIngestion, Depends(get_read_ingestion)],
) -> IngestionSummary:
    """Return the latest job + its chronological events (200); 404 if none/owned by another."""
    job, events = service(user=user, source_id=source_id)
    return IngestionSummary.from_entities(job, events)
