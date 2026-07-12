"""Worker logging seam (unit) — the Celery app keeps app-owned logging.

Guards the seam that keeps secret redaction + trace correlation alive inside the
worker process: Celery must not hijack the root logger, and importing the app
must install the app's handler carrying both filters. A regression that re-enabled
the hijack would silently drop worker-log redaction; this test catches it.
"""

from __future__ import annotations

import logging

from app.core.logging import SensitiveDataFilter
from app.core.tracing import TraceContextFilter
from app.worker.celery_app import celery_app


def test_celery_does_not_hijack_the_root_logger() -> None:
    assert celery_app.conf.worker_hijack_root_logger is False


def test_importing_worker_installs_app_logging_with_both_filters() -> None:
    # Importing app.worker.celery_app calls configure_logging(); the app-owned
    # handler must be present and carry redaction + trace correlation.
    root = logging.getLogger()
    learny_handlers = [h for h in root.handlers if getattr(h, "_learny", False)]
    assert len(learny_handlers) == 1
    handler = learny_handlers[0]
    assert any(isinstance(f, SensitiveDataFilter) for f in handler.filters)
    assert any(isinstance(f, TraceContextFilter) for f in handler.filters)
