"""T9 gate (unit) — EpubCorpusIngestionStep error classification (CORP-06/07).

The step binds ``BuildCorpus`` to the task's retry contract: transient storage
faults (the Learny-owned ``StorageUnavailable``) become ``RetryableIngestionError``
so the backoff retry applies (CORP-07); ``ObjectNotFound``, ``InvalidEpubError``,
and any other raise propagate untouched and are terminal (CORP-06). A clean build
simply delegates. Driven with a stub ``build`` so classification is asserted in
isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.errors import InvalidEpubError, StorageUnavailable
from app.domain.entities import IngestionJob, Source
from app.infrastructure.storage.s3 import ObjectNotFound
from app.infrastructure.worker.steps import (
    EmbedCorpusIngestionStep,
    EpubCorpusIngestionStep,
    RetryableIngestionError,
)

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)


def _source() -> Source:
    return Source(
        id=uuid4(),
        user_id=uuid4(),
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key="sources/a-book.epub",
        status="processing",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _job(source_id) -> IngestionJob:  # noqa: ANN001
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        status="running",
        attempts=1,
        last_error=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _RaisingBuild:
    """A ``BuildCorpus`` stand-in that always raises the configured error."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def __call__(self, *, source: Source, job: IngestionJob) -> None:
        raise self._error


class _RecordingBuild:
    """A ``BuildCorpus`` stand-in that records its call and returns cleanly."""

    def __init__(self) -> None:
        self.calls: list[tuple[Source, IngestionJob]] = []

    def __call__(self, *, source: Source, job: IngestionJob) -> None:
        self.calls.append((source, job))


def _run(build) -> None:  # noqa: ANN001
    source = _source()
    EpubCorpusIngestionStep(build).run(source=source, job=_job(source.id))


def test_run_delegates_to_build_on_success() -> None:
    build = _RecordingBuild()
    source = _source()
    job = _job(source.id)

    EpubCorpusIngestionStep(build).run(source=source, job=job)

    assert build.calls == [(source, job)]


def test_transient_storage_unavailable_becomes_retryable() -> None:
    with pytest.raises(RetryableIngestionError):
        _run(_RaisingBuild(StorageUnavailable("sources/a-book.epub")))


def test_invalid_epub_error_propagates_terminal() -> None:
    with pytest.raises(InvalidEpubError):
        _run(_RaisingBuild(InvalidEpubError("bad epub")))


def test_object_not_found_propagates_terminal() -> None:
    with pytest.raises(ObjectNotFound):
        _run(_RaisingBuild(ObjectNotFound("sources/a-book.epub")))


# --- EmbedCorpusIngestionStep classification (RET-10/12) ------------------------
#
# The embed step binds ``EmbedCorpus`` to the same retry contract: a transient
# provider/storage fault (the Learny-owned ``StorageUnavailable``) becomes
# ``RetryableIngestionError`` so the backoff retry applies; any other raise
# propagates untouched and is terminal (the embed transaction then rolls back).


def _run_embed(embed) -> None:  # noqa: ANN001
    source = _source()
    EmbedCorpusIngestionStep(embed).run(source=source, job=_job(source.id))


def test_embed_run_delegates_to_embed_on_success() -> None:
    embed = _RecordingBuild()
    source = _source()
    job = _job(source.id)

    EmbedCorpusIngestionStep(embed).run(source=source, job=job)

    assert embed.calls == [(source, job)]


def test_embed_transient_storage_unavailable_becomes_retryable() -> None:
    with pytest.raises(RetryableIngestionError):
        _run_embed(_RaisingBuild(StorageUnavailable("embedding provider unavailable")))


def test_embed_plain_error_propagates_terminal() -> None:
    # A non-transient fault is terminal — it propagates unchanged (no wrapping).
    with pytest.raises(RuntimeError):
        _run_embed(_RaisingBuild(RuntimeError("boom")))
