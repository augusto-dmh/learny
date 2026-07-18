"""T5 gate — Celery ingestion task + step/enqueuer adapters (integration, live DB).

Drives the ``run_ingestion`` task *function* directly against the migrated test
engine with a controllable bound ``self`` — no Redis, no eager mode — and asserts
the durable job/event/source state the task commits (ING-02/07/08). Because the
task commits through its own engine (not the rolled-back ``db_conn``), each test
seeds committed rows and the fixture deletes the seeded user afterwards (FK
cascade → sources → jobs → events). Also asserts the Celery enqueuer puts only
ids on the queue (ING-09) without a broker.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy import delete as sa_delete

import app.worker.tasks as tasks_module
from app.core.tracing import TraceContextFilter, current_trace
from app.domain.entities import (
    CorpusStructure,
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
    Source,
    User,
)
from app.infrastructure.db.metadata import (
    corpus_blocks,
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    users,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.worker.enqueuer import CeleryIngestionEnqueuer
from app.infrastructure.worker.steps import NoOpIngestionStep, RetryableIngestionError
from app.worker.tasks import run_ingestion
from tests.conftest import requires_db
from tests.fakes import FakeStorage
from tests.fixtures_epub import (
    EXPECTED_VALID_TITLE,
    no_toc_book,
    not_an_epub,
    valid_book,
)

pytestmark = requires_db

# The raw (unbound) task function, so tests drive it with a fake ``self`` and
# never need a broker or eager execution.
_run = run_ingestion.run.__func__


class FakeSelf:
    """A controllable bound-task ``self``: request.retries, max_retries, retry()."""

    class RetrySignal(Exception):
        """Sentinel raised by :meth:`retry`, standing in for Celery's ``Retry``."""

    def __init__(self, *, retries: int = 0, max_retries: int = 3) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = max_retries
        self.retry_calls: list[dict] = []

    def retry(self, *, exc, countdown):  # noqa: ANN001, ANN202 — mirrors Celery's retry
        self.retry_calls.append({"exc": exc, "countdown": countdown})
        raise self.RetrySignal


class RaisingStep:
    """``IngestionStep`` double that always raises the configured error."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def run(self, *, source: Source, job: IngestionJob) -> None:  # noqa: ARG002
        raise self._exc


@pytest.fixture
def seed(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the task's engine at the test DB and seed committed rows.

    Returns a callable that commits a user + source (+ optional queued job with a
    ``queued`` event) and records the user for cascade cleanup at teardown.
    """
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created_users: list[UUID] = []

    def _seed(
        job_status: str = IngestionStatus.QUEUED, *, with_job: bool = True
    ) -> SimpleNamespace:
        now = datetime.now(UTC)
        user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=now)
        source = Source(
            id=uuid4(),
            user_id=user.id,
            title="A Book",
            filename="a-book.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="d" * 64,
            object_key=f"sources/{uuid4()}.epub",
            status="processing",
            created_at=now,
            updated_at=now,
        )
        job = IngestionJob(
            id=uuid4(),
            source_id=source.id,
            status=job_status,
            attempts=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        created_users.append(user.id)
        with db_engine.begin() as conn:
            SqlAlchemyUserRepository(conn).add(user)
            SqlAlchemySourceRepository(conn).add(source)
            if with_job:
                SqlAlchemyIngestionJobRepository(conn).add(job)
                SqlAlchemyIngestionEventRepository(conn).append(
                    IngestionEvent(
                        id=uuid4(),
                        job_id=job.id,
                        type=IngestionEventType.QUEUED,
                        message=None,
                        created_at=now,
                    )
                )
        return SimpleNamespace(user=user, source=source, job=job)

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created_users:
            conn.execute(sa_delete(users).where(users.c.id == user_id))


def _read_job(engine: Engine, job_id: UUID) -> IngestionJob | None:
    with engine.connect() as conn:
        return SqlAlchemyIngestionJobRepository(conn).get_by_id(job_id)


def _read_source_status(engine: Engine, source_id: UUID) -> str:
    with engine.connect() as conn:
        return SqlAlchemySourceRepository(conn).get_by_id(source_id).status


def _read_events(engine: Engine, job_id: UUID) -> list[IngestionEvent]:
    with engine.connect() as conn:
        return SqlAlchemyIngestionEventRepository(conn).list_for_job(job_id)


def _read_event_types(engine: Engine, job_id: UUID) -> list[str]:
    return [e.type for e in _read_events(engine, job_id)]


def _read_structure(engine: Engine, source_id: UUID) -> CorpusStructure | None:
    with engine.connect() as conn:
        return SqlAlchemyCorpusRepository(conn).get_structure(source_id)


def _count_for_source(engine: Engine, table, source_id: UUID) -> int:  # noqa: ANN001
    """Count rows of a corpus table reachable from ``source_id`` via FK joins."""
    stmt = select(func.count()).select_from(table)
    if table in (corpus_blocks, corpus_chunks):
        stmt = stmt.join(corpus_sections, table.c.section_id == corpus_sections.c.id)
        stmt = stmt.join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
    elif table is corpus_sections:
        stmt = stmt.join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
    stmt = stmt.where(corpus_documents.c.source_id == source_id)
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def _count_embedded(engine: Engine, source_id: UUID) -> int:
    """Count the source's chunks whose ``embedding`` is non-NULL (via FK joins)."""
    stmt = (
        select(func.count())
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == source_id)
        .where(corpus_chunks.c.embedding.isnot(None))
    )
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def _count_embedded_with_model(engine: Engine, source_id: UUID, model: str) -> int:
    """Count the source's chunks stamped with ``embedding_model = model`` (EMB-14)."""
    stmt = (
        select(func.count())
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == source_id)
        .where(corpus_chunks.c.embedding_model == model)
    )
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def _serve_bytes(monkeypatch, object_key: str, data: bytes) -> None:  # noqa: ANN001
    """Point the task's storage factory at a fake serving ``data`` for ``object_key``.

    Keeps the REAL parser/converter/repository/engine; only object storage is faked
    so a committed source's bytes come from the fixture, not a live object store.
    """
    storage = FakeStorage()
    storage.objects[object_key] = data
    monkeypatch.setattr("app.worker.tasks._build_storage", lambda: storage)


def _add_queued_job(engine: Engine, source_id: UUID) -> IngestionJob:
    """Commit a fresh queued job for a source whose prior job is already terminal."""
    now = datetime.now(UTC)
    job = IngestionJob(
        id=uuid4(),
        source_id=source_id,
        status=IngestionStatus.QUEUED,
        attempts=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    with engine.begin() as conn:
        SqlAlchemyIngestionJobRepository(conn).add(job)
    return job


_VALID_SECTION_TITLES = ["Cover", "Part I", "Chapter 1", "Section 2", "Chapter 2"]

# Fixed, non-secret durable failure text the task persists (ING-08 redaction).
_REDACTED = "Ingestion processing failed."


def test_run_ingestion_success_drives_job_to_succeeded(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)

    # Lifecycle-only assertion: inject the no-op step so no parsing/storage runs
    # (the real corpus-build path is covered by the fixture-EPUB tests below).
    with patch("app.worker.tasks._build_step", lambda conn: NoOpIngestionStep()):
        _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.SUCCEEDED
    assert job.attempts == 1
    assert job.last_error is None
    assert _read_source_status(db_engine, ctx.source.id) == "ready"
    # The embed step runs after the (no-op) corpus step: with no corpus it embeds
    # zero chunks and still appends an ``embeddings_built`` (count 0) event.
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        "embeddings_built",
        IngestionEventType.SUCCEEDED,
    ]


def test_run_ingestion_plain_error_is_terminal_failure(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    # A secret-bearing raw error must never reach the owner-readable durable field
    # (ING-08 "redacted, non-secret"): it is stored as a fixed summary, logged raw.
    secret = "s3://learny-sources/u1/private-key.epub could not be read"

    with patch(
        "app.worker.tasks._build_step",
        lambda conn: RaisingStep(RuntimeError(secret)),
    ):
        _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.FAILED
    # Redacted: fixed summary persisted, raw secret absent from last_error.
    assert job.last_error == _REDACTED
    assert "s3://" not in (job.last_error or "")
    # The failed event message is user-readable via GET too — redact it as well.
    failed_event = _read_events(db_engine, ctx.job.id)[-1]
    assert failed_event.type == IngestionEventType.FAILED
    assert failed_event.message == _REDACTED
    assert _read_source_status(db_engine, ctx.source.id) == "failed"
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.FAILED,
    ]


def test_run_ingestion_retryable_records_retry_and_retries(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    fake_self = FakeSelf(retries=0, max_retries=3)

    with patch(
        "app.worker.tasks._build_step",
        lambda conn: RaisingStep(
            RetryableIngestionError("timeout calling https://internal/api?token=abc")
        ),
    ):
        with pytest.raises(FakeSelf.RetrySignal):
            _run(fake_self, str(ctx.source.id), str(ctx.job.id))

    # self.retry was invoked once with a positive backoff (ING-07 "with backoff").
    assert len(fake_self.retry_calls) == 1
    assert fake_self.retry_calls[0]["countdown"] > 0
    # record_retry persisted: attempts climbed, job stays active, error redacted.
    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.RUNNING
    assert job.attempts == 1
    assert job.last_error == _REDACTED
    assert "token=" not in (job.last_error or "")
    # The retrying event message is redacted too.
    assert _read_events(db_engine, ctx.job.id)[-1].message == _REDACTED
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.RETRYING,
    ]


def test_run_ingestion_retryable_exhausted_fails(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    fake_self = FakeSelf(retries=3, max_retries=3)  # retries == max ⇒ exhausted

    with _capture_worker_logs() as handler:
        with patch(
            "app.worker.tasks._build_step",
            lambda conn: RaisingStep(RetryableIngestionError("still unreachable")),
        ):
            _run(fake_self, str(ctx.source.id), str(ctx.job.id))

    assert fake_self.retry_calls == []  # no further retry once exhausted
    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.FAILED
    assert job.last_error == _REDACTED
    assert _read_source_status(db_engine, ctx.source.id) == "failed"
    assert IngestionEventType.FAILED in _read_event_types(db_engine, ctx.job.id)
    # This third terminal branch also carries trace fields + a duration (PROD-14).
    rec = _record_for(handler, "ingestion.run: failed (retries exhausted)")
    assert rec.job_id == str(ctx.job.id)
    assert rec.source_id == str(ctx.source.id)
    assert isinstance(rec.duration_ms, float)
    assert rec.duration_ms >= 0.0


def test_run_ingestion_missing_job_is_noop(seed, db_engine: Engine) -> None:
    ctx = seed(with_job=False)
    missing_job_id = uuid4()

    _run(FakeSelf(), str(ctx.source.id), str(missing_job_id))

    assert _read_job(db_engine, missing_job_id) is None
    assert _read_event_types(db_engine, missing_job_id) == []
    # The source is untouched — no lifecycle transition ran for a phantom job.
    assert _read_source_status(db_engine, ctx.source.id) == "processing"


def test_run_ingestion_terminal_job_is_noop(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.SUCCEEDED)  # already terminal (redelivery)

    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.SUCCEEDED  # unchanged
    assert job.attempts == 0  # begin_run did not start a new attempt
    # No started/succeeded appended — only the seeded queued event remains.
    assert _read_event_types(db_engine, ctx.job.id) == [IngestionEventType.QUEUED]


def test_celery_enqueuer_routes_epub_to_default_queue_with_ids_only() -> None:
    source_id = uuid4()
    job_id = uuid4()

    with patch("app.worker.tasks.run_ingestion.apply_async") as apply_async:
        CeleryIngestionEnqueuer().enqueue_ingestion(
            source_id=source_id,
            job_id=job_id,
            content_type="application/epub+zip",
        )

    # EPUB stays on the default queue: no ``queue`` kwarg, ids-only payload (ING-17).
    apply_async.assert_called_once_with(args=[str(source_id), str(job_id)])


def test_celery_enqueuer_routes_pdf_to_ingest_pdf_queue() -> None:
    source_id = uuid4()
    job_id = uuid4()

    with patch("app.worker.tasks.run_ingestion.apply_async") as apply_async:
        CeleryIngestionEnqueuer().enqueue_ingestion(
            source_id=source_id,
            job_id=job_id,
            content_type="application/pdf",
        )

    # PDF is routed to the dedicated isolated queue; payload is still ids-only.
    apply_async.assert_called_once_with(
        args=[str(source_id), str(job_id)], queue="ingest-pdf"
    )


# --- Corpus build through the real step (T9 integration) ------------------------
#
# These drive the full task with the REAL parser/converter/repository/engine and
# only fake object storage (serving fixture bytes), so the fixture EPUB becomes a
# durable corpus end-to-end (CORP-01..10) and malformed/replace paths are exercised
# against Postgres exactly as production runs them.


def test_run_ingestion_builds_corpus_from_valid_epub(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, valid_book())

    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.SUCCEEDED
    assert _read_source_status(db_engine, ctx.source.id) == "ready"

    # The canonical corpus is persisted with the fixture's structure (CORP-01/02).
    structure = _read_structure(db_engine, ctx.source.id)
    assert structure is not None
    assert structure.title == EXPECTED_VALID_TITLE
    assert structure.authors == ("Ada Lovelace", "Alan Turing")
    assert structure.language == "en"
    assert [s.title for s in structure.sections] == _VALID_SECTION_TITLES

    # Block and chunk rows exist with the fixture's counts (CORP-03/05).
    assert _count_for_source(db_engine, corpus_sections, ctx.source.id) == 5
    assert _count_for_source(db_engine, corpus_blocks, ctx.source.id) == 12
    assert _count_for_source(db_engine, corpus_chunks, ctx.source.id) == 5

    # The corpus_built event records the exact counts (CORP-10); the embed step
    # then appends embeddings_built, both between started and succeeded in the log.
    built = [e for e in _read_events(db_engine, ctx.job.id) if e.type == "corpus_built"]
    assert len(built) == 1
    assert built[0].message == "sections=5 blocks=12 chunks=5"
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        "corpus_normalized",
        "corpus_built",
        "embeddings_built",
        IngestionEventType.SUCCEEDED,
    ]


def test_run_ingestion_invalid_epub_fails_with_no_corpus(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, not_an_epub())

    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.FAILED
    assert job.last_error == _REDACTED
    assert _read_source_status(db_engine, ctx.source.id) == "failed"

    # Terminal parse failure leaves zero corpus rows (CORP-06); no corpus_built.
    assert _read_structure(db_engine, ctx.source.id) is None
    assert _count_for_source(db_engine, corpus_documents, ctx.source.id) == 0
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.FAILED,
    ]


def test_reingestion_success_leaves_exactly_one_corpus(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, valid_book())
    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    # A second successful run on a fresh queued job with the same bytes (CORP-09).
    job2 = _add_queued_job(db_engine, ctx.source.id)
    _run(FakeSelf(), str(ctx.source.id), str(job2.id))

    assert _read_job(db_engine, job2.id).status == IngestionStatus.SUCCEEDED
    # Exactly one corpus for the source; sections/blocks not duplicated (CORP-09).
    assert _count_for_source(db_engine, corpus_documents, ctx.source.id) == 1
    assert _count_for_source(db_engine, corpus_sections, ctx.source.id) == 5
    assert _count_for_source(db_engine, corpus_blocks, ctx.source.id) == 12


def test_reingestion_failure_keeps_prior_corpus(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, valid_book())
    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))
    assert _count_for_source(db_engine, corpus_sections, ctx.source.id) == 5

    # Second run: serve a DIFFERENT (2-section) book, but force the corpus_built
    # append to raise AFTER replace has run. The step transaction must roll back the
    # delete+insert, so the prior 5-section corpus survives intact (CORP-08).
    _serve_bytes(monkeypatch, ctx.source.object_key, no_toc_book())
    original_append = SqlAlchemyIngestionEventRepository.append

    def _failing_append(self, event: IngestionEvent) -> IngestionEvent:  # noqa: ANN001
        if event.type == "corpus_built":
            raise RuntimeError("boom after replace")
        return original_append(self, event)

    monkeypatch.setattr(SqlAlchemyIngestionEventRepository, "append", _failing_append)

    job2 = _add_queued_job(db_engine, ctx.source.id)
    _run(FakeSelf(), str(ctx.source.id), str(job2.id))

    assert _read_job(db_engine, job2.id).status == IngestionStatus.FAILED
    assert _read_source_status(db_engine, ctx.source.id) == "failed"

    # Prior corpus intact and readable: still the original valid book (CORP-08).
    structure = _read_structure(db_engine, ctx.source.id)
    assert structure is not None
    assert [s.title for s in structure.sections] == _VALID_SECTION_TITLES
    assert _count_for_source(db_engine, corpus_documents, ctx.source.id) == 1
    assert _count_for_source(db_engine, corpus_sections, ctx.source.id) == 5


# --- Chunk embedding through the real embed step (T7 integration) ----------------
#
# These drive the full task with the REAL corpus + embed steps (only object storage
# faked), so the fixture EPUB is parsed, chunked, and embedded end-to-end: after a
# successful run every chunk carries a non-NULL embedding (RET-09), the embed step
# runs in its own transaction after the corpus commit (RET-10), re-ingestion
# re-embeds exactly the rebuilt chunk set (RET-11), and a mid-embed failure rolls
# back with no partial vectors (RET-12).


def test_run_ingestion_embeds_every_chunk_of_the_source(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, valid_book())

    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    assert _read_job(db_engine, ctx.job.id).status == IngestionStatus.SUCCEEDED
    # Every one of the source's 5 chunks now has a non-NULL embedding (RET-09).
    assert _count_for_source(db_engine, corpus_chunks, ctx.source.id) == 5
    assert _count_embedded(db_engine, ctx.source.id) == 5
    # Each embedded chunk is stamped with the active adapter's model identity so a
    # stamped chunk records which model produced it (EMB-14, per-chunk versioning).
    assert _count_embedded_with_model(db_engine, ctx.source.id, "local-deterministic@1536") == 5
    # The embeddings_built event records the exact embedded-chunk count.
    embedded = [e for e in _read_events(db_engine, ctx.job.id) if e.type == "embeddings_built"]
    assert len(embedded) == 1
    assert embedded[0].message == "chunks=5"


def test_reingestion_reembeds_exactly_the_rebuilt_chunk_set(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, valid_book())
    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))
    assert _count_embedded(db_engine, ctx.source.id) == 5

    # Re-ingest a DIFFERENT book: the atomic corpus replace drops the old 5 chunks
    # and their vectors, and the embed step embeds exactly the rebuilt set — with no
    # stale/orphan vectors from the prior corpus (RET-11). Normalization merges
    # no_toc's trivial "body" section into "Introduction", so the rebuilt corpus is a
    # single chunk.
    _serve_bytes(monkeypatch, ctx.source.object_key, no_toc_book())
    job2 = _add_queued_job(db_engine, ctx.source.id)
    _run(FakeSelf(), str(ctx.source.id), str(job2.id))

    assert _read_job(db_engine, job2.id).status == IngestionStatus.SUCCEEDED
    assert _count_for_source(db_engine, corpus_chunks, ctx.source.id) == 1
    assert _count_embedded(db_engine, ctx.source.id) == 1


def test_run_ingestion_retryable_embed_fault_records_retry(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    fake_self = FakeSelf(retries=0, max_retries=3)

    # No-op corpus step (so the corpus step succeeds), then a transient embed fault:
    # the task records a retry and re-raises, exactly like a retryable corpus fault.
    with (
        patch("app.worker.tasks._build_step", lambda conn: NoOpIngestionStep()),
        patch(
            "app.worker.tasks._build_embed_step",
            lambda conn: RaisingStep(RetryableIngestionError("embedding provider timeout")),
        ),
    ):
        with pytest.raises(FakeSelf.RetrySignal):
            _run(fake_self, str(ctx.source.id), str(ctx.job.id))

    assert len(fake_self.retry_calls) == 1
    assert fake_self.retry_calls[0]["countdown"] > 0
    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.RUNNING
    assert job.attempts == 1
    assert job.last_error == _REDACTED
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.RETRYING,
    ]


def test_embed_failure_is_terminal_and_leaves_no_partial_vectors(
    seed, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    _serve_bytes(monkeypatch, ctx.source.object_key, valid_book())

    # Let the corpus step commit and the embed step's set_embeddings write the
    # vectors, but fail the embeddings_built append AFTER the write. The embed
    # transaction must roll back the vector writes, so a non-retryable embed error
    # ends the job ``failed`` with no chunk left partially embedded (RET-12).
    original_append = SqlAlchemyIngestionEventRepository.append

    def _failing_append(self, event: IngestionEvent) -> IngestionEvent:  # noqa: ANN001
        if event.type == "embeddings_built":
            raise RuntimeError("boom after set_embeddings")
        return original_append(self, event)

    monkeypatch.setattr(SqlAlchemyIngestionEventRepository, "append", _failing_append)

    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.FAILED
    assert job.last_error == _REDACTED
    assert _read_source_status(db_engine, ctx.source.id) == "failed"
    # Corpus survives (its step committed), but the embed txn rolled back: the 5
    # chunks exist with NO embedding persisted for this run (no partial vectors).
    assert _count_for_source(db_engine, corpus_chunks, ctx.source.id) == 5
    assert _count_embedded(db_engine, ctx.source.id) == 0
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        "corpus_normalized",
        "corpus_built",
        IngestionEventType.FAILED,
    ]


# --- Observability: worker trace fields + duration (PROD-14) --------------------


class _TraceRecordingHandler(logging.Handler):
    """Capture records off the worker logger, self-stamping bound trace fields."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.addFilter(TraceContextFilter())
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def _capture_worker_logs():
    """Attach a recording handler to the worker task logger, forced enabled."""
    handler = _TraceRecordingHandler()
    logger = logging.getLogger("app.worker.tasks")
    previous_level, previous_disabled = logger.level, logger.disabled
    logger.setLevel(logging.INFO)
    logger.disabled = False
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled


def _record_for(handler: _TraceRecordingHandler, message: str) -> logging.LogRecord:
    hits = [r for r in handler.records if r.getMessage() == message]
    assert len(hits) == 1, f"expected one {message!r} record, got {len(hits)}"
    return hits[0]


def test_run_ingestion_success_logs_trace_fields_and_duration(
    seed, db_engine: Engine
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    with _capture_worker_logs() as handler:
        with patch("app.worker.tasks._build_step", lambda conn: NoOpIngestionStep()):
            _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    rec = _record_for(handler, "ingestion.run: succeeded")
    assert rec.job_id == str(ctx.job.id)
    assert rec.source_id == str(ctx.source.id)
    assert isinstance(rec.duration_ms, float)
    assert rec.duration_ms >= 0.0


def test_run_ingestion_failure_logs_trace_fields_and_duration(
    seed, db_engine: Engine
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    with _capture_worker_logs() as handler:
        with patch(
            "app.worker.tasks._build_step",
            lambda conn: RaisingStep(RuntimeError("boom")),
        ):
            _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    rec = _record_for(handler, "ingestion.run: failed")
    assert rec.job_id == str(ctx.job.id)
    assert rec.source_id == str(ctx.source.id)
    assert isinstance(rec.duration_ms, float)
    assert rec.duration_ms >= 0.0


def test_run_ingestion_populates_trace_context_during_the_task(
    seed, db_engine: Engine
) -> None:
    """The task binds job/source into the trace context that the filter stamps
    onto *every* downstream log record — not just the ones passing ``extra=``
    (PROD-14 correlation seam). A no-op ``bind_trace`` leaves this empty."""
    ctx = seed(IngestionStatus.QUEUED)
    seen: dict[str, str] = {}
    orig = tasks_module._build_run_ingestion

    def spy(conn):  # noqa: ANN001, ANN202
        # Snapshot the trace context while the task body executes — this is what
        # TraceContextFilter injects into downstream records with no explicit extra.
        seen.update(current_trace())
        return orig(conn)

    with (
        patch("app.worker.tasks._build_step", lambda conn: NoOpIngestionStep()),
        patch("app.worker.tasks._build_run_ingestion", spy),
    ):
        _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    assert seen == {"job_id": str(ctx.job.id), "source_id": str(ctx.source.id)}


def test_note_reconcile_runs_after_quiz_reconcile(seed, db_engine: Engine) -> None:
    """The note-anchor reconcile is a sibling step wired AFTER quiz reconcile (NF-07).

    Both builders are replaced with recorders so ordering is observed without a corpus:
    the quiz reconcile must run before the note reconcile in the ingestion body.
    """
    ctx = seed(IngestionStatus.QUEUED)
    order: list[str] = []

    class _Recorder:
        def __init__(self, name: str) -> None:
            self._name = name

        def __call__(self, *, source_id: UUID) -> None:  # noqa: ARG002
            order.append(self._name)

    with (
        patch("app.worker.tasks._build_step", lambda conn: NoOpIngestionStep()),
        patch("app.worker.tasks._build_reconcile", lambda conn: _Recorder("quiz")),
        patch("app.worker.tasks._build_reconcile_notes", lambda conn: _Recorder("notes")),
    ):
        _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    assert order == ["quiz", "notes"]
