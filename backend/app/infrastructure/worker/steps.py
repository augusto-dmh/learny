"""Ingestion step adapter + its transient-failure signal (design §Components).

``NoOpIngestionStep`` is this cycle's default ``IngestionStep`` adapter: it drives
the lifecycle without doing any parsing. Phase 5 swaps this for the real EPUB
parser without touching the task, the lifecycle services, or the schema.

``RetryableIngestionError`` is the ``IngestionStep`` contract's transient-failure
signal (see :class:`app.domain.ports.IngestionStep`): a step raises it for a
retryable fault; any other exception is terminal. It lives here — beside the
port's adapter — so the task and its tests share one definition without the
application error module depending on the worker layer.
"""

from __future__ import annotations

from app.domain.entities import IngestionJob, Source


class RetryableIngestionError(Exception):
    """A transient ``IngestionStep`` failure worth retrying (ING-07)."""


class NoOpIngestionStep:
    """Default ``IngestionStep``: performs no work this cycle (Phase-5 seam)."""

    def run(self, *, source: Source, job: IngestionJob) -> None:
        # TODO(Phase 5): parse EPUB
        return None
