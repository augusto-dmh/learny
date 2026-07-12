"""Celery application (worker foundation).

Boots against the Redis broker to prove the worker wiring (FR-SCAF-001/002) and
registers the ingestion task module. Long-running ingestion/corpus/embedding work
runs here, never inside HTTP request handlers (ADR-005).
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging

_settings = get_settings()

celery_app = Celery(
    "learny",
    broker=_settings.broker_url(),
    backend=_settings.result_backend(),
    include=["app.worker.tasks"],
)

# Conservative long-task defaults (celery-workers skill: reliability). ``acks_late``
# + ``prefetch=1`` need idempotent tasks; ``visibility_timeout`` stays above
# ``task_time_limit`` so Redis does not redeliver a job mid-run.
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
    task_track_started=True,
    broker_transport_options={"visibility_timeout": 3600},
    # Keep the app-owned root logging (redaction + trace-field correlation, AD-041);
    # Celery otherwise replaces the root handlers on worker boot and drops our
    # filters. ``configure_logging`` then installs our handler in this process.
    worker_hijack_root_logger=False,
)

configure_logging()
