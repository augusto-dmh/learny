"""Celery application (minimal — no tasks this cycle).

Boots against the Redis broker to prove the worker wiring (FR-SCAF-001/002).
Long-running ingestion/corpus/embedding work is added in a later cycle and will
run here, never inside HTTP request handlers.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "learny",
    broker=_settings.broker_url(),
    backend=_settings.result_backend(),
)

# Conservative defaults; tasks are registered in a later cycle.
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
