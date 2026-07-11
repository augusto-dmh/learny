"""Celery enqueuer adapter (design §Components, AD-016).

``CeleryIngestionEnqueuer`` is the concrete ``IngestionEnqueuer``: it keeps
``apply_async`` out of application/handler code (ADR-007/009) and puts only ids
on the queue (AD-014). The start handler calls it *after* the queued job is
committed, so the worker always dequeues a durable row.
"""

from __future__ import annotations

from uuid import UUID


class CeleryIngestionEnqueuer:
    """``IngestionEnqueuer`` backed by the Celery ``run_ingestion`` task."""

    def enqueue_ingestion(self, *, source_id: UUID, job_id: UUID) -> None:
        # Imported locally so the module import graph stays acyclic: the task
        # module wires this cycle's adapters, and the web composition root imports
        # this enqueuer.
        from app.worker.tasks import run_ingestion

        run_ingestion.apply_async(args=[str(source_id), str(job_id)])
