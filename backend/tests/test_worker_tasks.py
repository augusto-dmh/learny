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

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy import delete as sa_delete

from app.domain.entities import (
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
    Source,
    User,
)
from app.infrastructure.db.metadata import users
from app.infrastructure.db.repositories import (
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.worker.enqueuer import CeleryIngestionEnqueuer
from app.infrastructure.worker.steps import RetryableIngestionError
from app.worker.tasks import run_ingestion
from tests.conftest import requires_db

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


# Fixed, non-secret durable failure text the task persists (ING-08 redaction).
_REDACTED = "Ingestion processing failed."


def test_run_ingestion_success_drives_job_to_succeeded(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)

    _run(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.SUCCEEDED
    assert job.attempts == 1
    assert job.last_error is None
    assert _read_source_status(db_engine, ctx.source.id) == "ready"
    assert _read_event_types(db_engine, ctx.job.id) == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.SUCCEEDED,
    ]


def test_run_ingestion_plain_error_is_terminal_failure(seed, db_engine: Engine) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    # A secret-bearing raw error must never reach the owner-readable durable field
    # (ING-08 "redacted, non-secret"): it is stored as a fixed summary, logged raw.
    secret = "s3://learny-sources/u1/private-key.epub could not be read"

    with patch(
        "app.worker.tasks.NoOpIngestionStep",
        lambda: RaisingStep(RuntimeError(secret)),
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


def test_run_ingestion_retryable_records_retry_and_retries(
    seed, db_engine: Engine
) -> None:
    ctx = seed(IngestionStatus.QUEUED)
    fake_self = FakeSelf(retries=0, max_retries=3)

    with patch(
        "app.worker.tasks.NoOpIngestionStep",
        lambda: RaisingStep(
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

    with patch(
        "app.worker.tasks.NoOpIngestionStep",
        lambda: RaisingStep(RetryableIngestionError("still unreachable")),
    ):
        _run(fake_self, str(ctx.source.id), str(ctx.job.id))

    assert fake_self.retry_calls == []  # no further retry once exhausted
    job = _read_job(db_engine, ctx.job.id)
    assert job.status == IngestionStatus.FAILED
    assert job.last_error == _REDACTED
    assert _read_source_status(db_engine, ctx.source.id) == "failed"
    assert IngestionEventType.FAILED in _read_event_types(db_engine, ctx.job.id)


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


def test_celery_enqueuer_applies_async_with_ids_only() -> None:
    source_id = uuid4()
    job_id = uuid4()

    with patch("app.worker.tasks.run_ingestion.apply_async") as apply_async:
        CeleryIngestionEnqueuer().enqueue_ingestion(source_id=source_id, job_id=job_id)

    apply_async.assert_called_once_with(args=[str(source_id), str(job_id)])
