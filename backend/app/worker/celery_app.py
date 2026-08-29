"""Celery application (worker foundation).

Boots against the Redis broker to prove the worker wiring (FR-SCAF-001/002) and
registers the ingestion task module. Long-running ingestion/corpus/embedding work
runs here, never inside HTTP request handlers (ADR-005).
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.instrumentation import InstrumentRecorder, set_recorder
from app.core.logging import configure_logging
from app.worker.instrumentation import install_task_duration_signals

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
#
# ``task_reject_on_worker_lost`` covers the death ``acks_late`` alone does not: when
# the worker process is killed outright (OOM, SIGKILL, a container stopped mid-task)
# no ``except`` in the task body ever runs, and without rejection the message is
# dropped — leaving the ingestion job row saying ``running`` with nothing behind it,
# forever. Rejecting requeues it instead. That is only safe because the number of
# attempts is capped durably on the job row: a requeued message keeps its original
# delivery headers, so this task's own retry count does not advance across these
# redeliveries and a job that reliably kills its worker would loop indefinitely.
#
# Deliberately absent: ``broker_heartbeat``. It is an AMQP setting and does nothing
# on the Redis transport; worker liveness comes from the ``celery inspect ping``
# container healthchecks instead.
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
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
# This module is the worker's composition root, the counterpart of ``create_app``,
# so the instrument's bounds are built from settings here too. Every ``get_engine()``
# call installs the slow-query listener, and the tasks make ~20 of them, so this
# process feeds the recorder exactly as the API does — without this, its capacity
# and statement cap would sit at the module defaults while the runbook documents
# both as per-process settings (the threshold, read at engine build time, is the
# one that *was* honoured here, which is what hid the asymmetry). Assembly time is
# where settings may safely be read; import time is not, and the settings this
# module already reads for the broker are the same single read (lesson L-007).
set_recorder(
    InstrumentRecorder(
        capacity=_settings.instrument_capacity,
        statement_max_chars=_settings.slow_query_statement_chars,
    )
)
# Every task reports its duration through Celery's own signals, so no task needs
# instrumentation code of its own (AD-176).
install_task_duration_signals()
