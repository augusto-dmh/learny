"""Ingestion worker tasks (ADR-005/ADR-014, design §Components).

Thin Celery adapters over the ``RunIngestion`` application service. The task owns
only the *retry decision* (a Celery concern — retry count lives on the request);
the pure service owns every durable DB transition. Each transition runs in its
own committed unit of work (``get_engine().begin()``), so the ``running`` state is
durable before the step runs and terminal state survives a crash.

No parsing happens here this cycle — the injected :class:`NoOpIngestionStep` is a
no-op (``# TODO(Phase 5): parse EPUB``). No FastAPI import crosses into this
module; Celery/SQLAlchemy never enter ``domain``/``application`` (ADR-007/009).
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.application.ingestion import RunIngestion
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.worker.steps import NoOpIngestionStep, RetryableIngestionError
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_clock = SystemClock()

# Manual backoff for retryable step failures (ING-07). Exponential in the attempt
# count, capped so a long-lived transient fault does not push retries out for hours.
_RETRY_BASE_COUNTDOWN = 10
_RETRY_MAX_COUNTDOWN = 600

# Durable failure text is a fixed, non-secret summary (ING-08 "redacted, non-secret").
# A step exception — in Phase 5 potentially carrying object keys, storage URLs, or
# filesystem paths — is written only to the server log (``exc_info``), never to the
# owner-readable ``last_error`` / event ``message``.
_STEP_FAILURE_ERROR = "Ingestion processing failed."


def _retry_countdown(retries: int) -> int:
    """Return the backoff (seconds) before the next retry given prior ``retries``."""
    return min(_RETRY_BASE_COUNTDOWN * (2**retries), _RETRY_MAX_COUNTDOWN)


def _build_run_ingestion(conn: Connection) -> RunIngestion:
    """Wire the ``RunIngestion`` driver on ``conn`` (the task's composition root)."""
    return RunIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        step=NoOpIngestionStep(),
        clock=_clock,
        ids=uuid4,
    )


@celery_app.task(bind=True, name="ingestion.run", max_retries=3)
def run_ingestion(self, source_id: str, job_id: str) -> None:  # noqa: ANN001 — bound task ``self``
    """Drive a source's ingestion job through its durable lifecycle (ING-02/07/08).

    Idempotent under ``acks_late`` redelivery: a missing or already-terminal job
    no-ops via ``begin_run``. On a retryable step failure with attempts remaining
    the task records a ``retrying`` event and re-raises ``self.retry``; otherwise
    (non-retryable error, or retries exhausted) it writes terminal ``failed`` and
    returns — the terminal state is already durable, so it is not re-raised.
    """
    jid = UUID(job_id)
    log = {"job_id": job_id, "source_id": source_id}

    # 1. Claim the job: queued/running → running (attempts+1). None ⇒ missing row
    #    (ING-08 AC3) or already terminal (redelivery) ⇒ idempotent no-op.
    with get_engine().begin() as conn:
        job = _build_run_ingestion(conn).begin_run(jid)
    if job is None:
        logger.info("ingestion.run: no-op (missing or terminal job)", extra=log)
        return
    logger.info("ingestion.run: started", extra=log)

    # 2. Run the Phase-5 seam OUTSIDE the lifecycle transaction, so the durable
    #    ``running`` state is already committed when the step runs / fails.
    try:
        with get_engine().connect() as conn:
            _build_run_ingestion(conn).run_step(job)
    except RetryableIngestionError as exc:
        # Persist only the fixed, non-secret summary (ING-08); the raw exception
        # goes to the server log via ``exc_info``, never the durable field.
        if self.request.retries < self.max_retries:
            with get_engine().begin() as conn:
                _build_run_ingestion(conn).record_retry(jid, _STEP_FAILURE_ERROR)
            logger.info("ingestion.run: retrying", extra=log, exc_info=exc)
            raise self.retry(
                exc=exc, countdown=_retry_countdown(self.request.retries)
            ) from exc
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).fail(jid, _STEP_FAILURE_ERROR)
        logger.info(
            "ingestion.run: failed (retries exhausted)", extra=log, exc_info=exc
        )
        return
    except Exception as exc:  # noqa: BLE001 — any non-retryable error is terminal
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).fail(jid, _STEP_FAILURE_ERROR)
        logger.info("ingestion.run: failed", extra=log, exc_info=exc)
        return

    # 3. Terminal success: succeeded + source ready + ``succeeded`` event.
    with get_engine().begin() as conn:
        _build_run_ingestion(conn).complete(jid)
    logger.info("ingestion.run: succeeded", extra=log)
