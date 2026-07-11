"""Ingestion worker tasks (ADR-005/ADR-014, design §Components).

Thin Celery adapters over the ``RunIngestion`` application service. The task owns
only the *retry decision* (a Celery concern — retry count lives on the request);
the pure service owns every durable DB transition. Each transition runs in its
own committed unit of work (``get_engine().begin()``), so the ``running`` state is
durable before the step runs and terminal state survives a crash.

The step now parses the EPUB and builds the canonical corpus: the step block runs
inside its own ``get_engine().begin()`` transaction, so a mid-build failure rolls
back with no partial corpus (CORP-08) and a successful build commits atomically.
No FastAPI import crosses into this module; Celery/SQLAlchemy never enter
``domain``/``application`` (ADR-007/009).
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.application.corpus import BuildCorpus
from app.application.ingestion import RunIngestion
from app.core.config import get_settings
from app.domain.ports import IngestionStep, StoragePort
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.ingestion.epub import EbooklibEpubParser
from app.infrastructure.ingestion.markup import Bs4MarkupConverter
from app.infrastructure.storage.s3 import S3StorageAdapter
from app.infrastructure.worker.steps import (
    EpubCorpusIngestionStep,
    RetryableIngestionError,
)
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


def _build_storage() -> StoragePort:
    """Build the S3-compatible storage adapter from settings (web-layer mirror)."""
    settings = get_settings()
    return S3StorageAdapter(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )


def _build_step(conn: Connection) -> IngestionStep:
    """Wire the real EPUB corpus step on ``conn`` (the injectable Phase-5 seam).

    Factored out so lifecycle tests can inject a lifecycle-only double without a
    live object store or a real EPUB, exactly as prior cycles patched the step.
    """
    return EpubCorpusIngestionStep(
        BuildCorpus(
            storage=_build_storage(),
            parser=EbooklibEpubParser(),
            markup=Bs4MarkupConverter(),
            corpus=SqlAlchemyCorpusRepository(conn),
            events=SqlAlchemyIngestionEventRepository(conn),
            clock=_clock,
            ids=uuid4,
            chunk_max_chars=get_settings().chunk_max_chars,
        )
    )


def _build_run_ingestion(conn: Connection) -> RunIngestion:
    """Wire the ``RunIngestion`` driver on ``conn`` (the task's composition root)."""
    return RunIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        step=_build_step(conn),
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

    # 2. Run the corpus-build step in its OWN committed transaction, separate from
    #    the lifecycle transitions: the durable ``running`` state is already
    #    committed, and the whole build (parse → replace → counts event) commits
    #    atomically or rolls back with no partial corpus on any raise (CORP-08).
    try:
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).run_step(job)
    except RetryableIngestionError as exc:
        # Persist only the fixed, non-secret summary (ING-08); the raw exception
        # goes to the server log via ``exc_info``, never the durable field.
        if self.request.retries < self.max_retries:
            with get_engine().begin() as conn:
                _build_run_ingestion(conn).record_retry(jid, _STEP_FAILURE_ERROR)
            logger.info("ingestion.run: retrying", extra=log, exc_info=exc)
            raise self.retry(exc=exc, countdown=_retry_countdown(self.request.retries)) from exc
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).fail(jid, _STEP_FAILURE_ERROR)
        logger.info("ingestion.run: failed (retries exhausted)", extra=log, exc_info=exc)
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
