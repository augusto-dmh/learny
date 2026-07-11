"""Ingestion step adapters + their transient-failure signal (design §Components).

``EpubCorpusIngestionStep`` is Phase 5's real ``IngestionStep``: it binds
``BuildCorpus`` to the task's retry contract, mapping transient object-storage
faults to ``RetryableIngestionError`` (CORP-07) while letting terminal failures
(``ObjectNotFound``, ``InvalidEpubError``, and any other raise) propagate so the
task fails the job (CORP-06). ``NoOpIngestionStep`` stays exported: it drives the
lifecycle without parsing and remains the double the lifecycle tests inject.

``RetryableIngestionError`` is the ``IngestionStep`` contract's transient-failure
signal (see :class:`app.domain.ports.IngestionStep`): a step raises it for a
retryable fault; any other exception is terminal. It lives here — beside the
port's adapter — so the task and its tests share one definition without the
application error module depending on the worker layer.
"""

from __future__ import annotations

from botocore.exceptions import BotoCoreError, ClientError

from app.application.corpus import BuildCorpus
from app.domain.entities import IngestionJob, Source


class RetryableIngestionError(Exception):
    """A transient ``IngestionStep`` failure worth retrying (ING-07)."""


class NoOpIngestionStep:
    """An ``IngestionStep`` that performs no work (lifecycle-only test double)."""

    def run(self, *, source: Source, job: IngestionJob) -> None:
        return None


class EpubCorpusIngestionStep:
    """Run the EPUB corpus build under the task's retry contract (CORP-06/07/08).

    Delegates to :class:`~app.application.corpus.BuildCorpus`, which runs inside the
    task's single transaction. Transient object-storage faults surface from the S3
    adapter as ``ClientError``/``BotoCoreError`` and map to
    ``RetryableIngestionError`` so the existing backoff retry applies (CORP-07).
    Everything else — ``ObjectNotFound`` (missing object), ``InvalidEpubError``
    (unparseable EPUB), any other raise — propagates untouched and is terminal
    (CORP-06); the surrounding transaction then rolls back with no partial corpus
    (CORP-08).
    """

    def __init__(self, build: BuildCorpus) -> None:
        self._build = build

    def run(self, *, source: Source, job: IngestionJob) -> None:
        try:
            self._build(source=source, job=job)
        except (ClientError, BotoCoreError) as exc:
            raise RetryableIngestionError from exc
