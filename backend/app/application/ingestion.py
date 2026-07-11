"""Ingestion use-case services (worker-foundation design §Components).

Framework-free services orchestrating the ingestion job/event repositories and
the ``source.status`` projection. Same layering as Sources/Identity (ADR-007/009):
nothing here imports FastAPI, SQLAlchemy, or Celery — the web handler (Phase 4)
owns the commit-then-enqueue orchestration and the task (Phase 3) owns retries;
these services only drive the durable state transitions.

``StartIngestion`` runs on the HTTP request; the ``RunIngestion`` driver methods
run inside the Celery task, one per transaction (the task opens a UoW per call).
``ReadIngestion`` serves the observe endpoint.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.errors import (
    ActiveIngestionExists,
    IngestionNotFound,
    NotAuthorized,
    SourceNotFound,
)
from app.application.identity import AuthorizeOwnership
from app.domain.entities import (
    ACTIVE_STATUSES,
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
    Source,
    User,
)
from app.domain.ports import (
    Clock,
    IngestionEventRepository,
    IngestionJobRepository,
    IngestionStep,
    SourceRepository,
)

# ``source.status`` projection values (spec §Assumptions). Distinct from the job
# lifecycle in :class:`IngestionStatus`: a source moves uploaded → processing →
# ready / failed as its latest job advances.
SOURCE_STATUS_PROCESSING = "processing"
SOURCE_STATUS_READY = "ready"
SOURCE_STATUS_FAILED = "failed"


def authorized_source(
    *,
    user: User,
    source_id: UUID,
    sources: SourceRepository,
    authorize: AuthorizeOwnership,
) -> Source:
    """Return the caller's source or raise ``SourceNotFound`` (404, no disclosure).

    Mirrors ``GetSource``: a missing source and a non-owner collapse to the same
    error so a source's existence is never disclosed (ING-04).
    """
    source = sources.get_by_id(source_id)
    if source is None:
        raise SourceNotFound("Source not found.")
    try:
        authorize(user=user, owner_id=source.user_id)
    except NotAuthorized as exc:
        raise SourceNotFound("Source not found.") from exc
    return source


class StartIngestion:
    """Create a ``queued`` job for an owned source and mark the source processing.

    Does *not* enqueue — the web handler orchestrates commit-then-enqueue so the
    worker always sees a committed row (ING-01, AD-016). The active-job invariant
    is guarded here (application pre-check → ``ActiveIngestionExists``) and, race-
    proof, by the partial unique index at the persistence layer (ING-03).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        jobs: IngestionJobRepository,
        events: IngestionEventRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._events = events
        self._authorize = authorize
        self._clock = clock
        self._ids = ids

    def __call__(
        self, *, user: User, source_id: UUID
    ) -> tuple[IngestionJob, list[IngestionEvent]]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )

        # At most one active job per source (ING-03). Only the latest job can be
        # active — a terminal latest means the source is free to (re)start (ING-05).
        latest = self._jobs.get_latest_for_source(source_id)
        if latest is not None and latest.status in ACTIVE_STATUSES:
            raise ActiveIngestionExists("Ingestion is already in progress.")

        now = self._clock.now()
        job = self._jobs.add(
            IngestionJob(
                id=self._ids(),
                source_id=source_id,
                status=IngestionStatus.QUEUED,
                attempts=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        self._sources.set_status(source_id, SOURCE_STATUS_PROCESSING, now)
        # Return the ``queued`` event so the web handler builds its response without
        # reaching into a persistence adapter (keeps storage access in this layer).
        queued = self._append_event(job.id, IngestionEventType.QUEUED, None, now)
        return job, [queued]

    def _append_event(
        self, job_id: UUID, event_type: str, message: str | None, now
    ) -> IngestionEvent:  # noqa: ANN001 — ``now`` is the injected clock's datetime
        event = IngestionEvent(
            id=self._ids(),
            job_id=job_id,
            type=event_type,
            message=message,
            created_at=now,
        )
        self._events.append(event)
        return event


class RunIngestion:
    """The background driver: one method per durable transition (ING-02/07/08).

    The Celery task calls these across separate units of work; each is idempotent
    on a missing row (defensive no-op, ING-08 AC3). Retry *counting* lives in the
    task; these methods only persist state and append events.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        jobs: IngestionJobRepository,
        events: IngestionEventRepository,
        step: IngestionStep,
        clock: Clock,
        ids: Callable[[], UUID],
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._events = events
        self._step = step
        self._clock = clock
        self._ids = ids

    def begin_run(self, job_id: UUID) -> IngestionJob | None:
        """Transition ``queued``/``running`` → ``running`` (attempts+1); else no-op.

        Returns ``None`` when the job is missing (ING-08 AC3) or already terminal
        (idempotent redelivery under ``acks_late``); otherwise persists the
        ``running`` transition, syncs ``source.status`` and appends ``started``.
        """
        job = self._jobs.get_by_id(job_id)
        if job is None or job.status not in ACTIVE_STATUSES:
            return None
        now = self._clock.now()
        started = self._jobs.update(job.started(now))
        self._sources.set_status(job.source_id, SOURCE_STATUS_PROCESSING, now)
        self._append_event(job.id, IngestionEventType.STARTED, None, now)
        return started

    def run_step(self, job: IngestionJob) -> None:
        """Invoke the Phase-5 seam for ``job`` (propagates for retry classification).

        The default adapter is a no-op this cycle; a raise is classified by the
        task as retryable-or-terminal.
        """
        source = self._sources.get_by_id(job.source_id)
        self._step.run(source=source, job=job)

    def complete(self, job_id: UUID) -> IngestionJob | None:
        """Terminal success: ``succeeded`` + ``source.status=ready`` + ``succeeded``."""
        job = self._jobs.get_by_id(job_id)
        if job is None:
            return None
        now = self._clock.now()
        done = self._jobs.update(job.succeeded(now))
        self._sources.set_status(job.source_id, SOURCE_STATUS_READY, now)
        self._append_event(job.id, IngestionEventType.SUCCEEDED, None, now)
        return done

    def record_retry(self, job_id: UUID, error: str) -> IngestionJob | None:
        """Retryable failure: persist ``last_error`` (stays ``running``) + ``retrying``."""
        job = self._jobs.get_by_id(job_id)
        if job is None:
            return None
        now = self._clock.now()
        retried = self._jobs.update(job.retrying(now, error))
        self._append_event(job.id, IngestionEventType.RETRYING, error, now)
        return retried

    def fail(self, job_id: UUID, error: str) -> IngestionJob | None:
        """Terminal failure: ``failed`` + durable ``last_error`` + source ``failed``."""
        job = self._jobs.get_by_id(job_id)
        if job is None:
            return None
        now = self._clock.now()
        failed = self._jobs.update(job.failed(now, error))
        self._sources.set_status(job.source_id, SOURCE_STATUS_FAILED, now)
        self._append_event(job.id, IngestionEventType.FAILED, error, now)
        return failed

    def _append_event(
        self, job_id: UUID, event_type: str, message: str | None, now
    ) -> None:  # noqa: ANN001 — ``now`` is the injected clock's datetime
        self._events.append(
            IngestionEvent(
                id=self._ids(),
                job_id=job_id,
                type=event_type,
                message=message,
                created_at=now,
            )
        )


class ReadIngestion:
    """Return the latest job + its ordered events for an owned source (ING-06)."""

    def __init__(
        self,
        *,
        sources: SourceRepository,
        jobs: IngestionJobRepository,
        events: IngestionEventRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._events = events
        self._authorize = authorize

    def __call__(
        self, *, user: User, source_id: UUID
    ) -> tuple[IngestionJob, list[IngestionEvent]]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        job = self._jobs.get_latest_for_source(source_id)
        if job is None:
            raise IngestionNotFound("No ingestion job for this source.")
        return job, self._events.list_for_job(job.id)
