"""T1 gate — ingestion job/event entities + ports (unit).

Pure-domain checks derived from the worker-foundation spec ACs:
- ``IngestionJob``/``IngestionEvent`` carry every design field and are immutable.
- Transition helpers return *new* frozen instances with the spec-defined state:
  ``started`` → ``running`` + ``attempts+1`` (ING-02); ``succeeded`` → ``succeeded``
  (ING-02); ``retrying`` → ``last_error`` set, status stays ``running`` (ING-07);
  ``failed`` → ``failed`` + ``last_error`` (ING-08).
- Status/event constants match the spec vocabulary; ``ACTIVE_STATUSES`` is exactly
  ``{queued, running}`` (concurrency guard, ING-03).
- The four new ports + ``SourceRepository.set_status`` are structural Protocols.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.entities import (
    ACTIVE_STATUSES,
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
)
from app.domain.ports import (
    IngestionEnqueuer,
    IngestionEventRepository,
    IngestionJobRepository,
    IngestionStep,
    SourceRepository,
)

_T0 = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)
_T1 = _T0 + timedelta(seconds=5)


def _queued_job() -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        status=IngestionStatus.QUEUED,
        attempts=0,
        last_error=None,
        created_at=_T0,
        updated_at=_T0,
    )


def test_ingestion_job_carries_expected_fields() -> None:
    job = _queued_job()

    assert job.status == "queued"
    assert job.attempts == 0
    assert job.last_error is None
    assert job.created_at == job.updated_at == _T0


def test_ingestion_job_is_frozen() -> None:
    job = _queued_job()
    with pytest.raises(FrozenInstanceError):
        job.status = "running"  # type: ignore[misc]


def test_started_transitions_to_running_and_increments_attempts() -> None:
    job = _queued_job()

    running = job.started(_T1)

    assert running.status == "running"
    assert running.attempts == 1
    assert running.updated_at == _T1
    # Original instance is untouched (immutable transition).
    assert job.status == "queued"
    assert job.attempts == 0


def test_started_increments_attempts_each_call() -> None:
    # Each retry attempt goes through begin_run → started, so attempts climb.
    job = _queued_job().started(_T1).started(_T1)

    assert job.attempts == 2


def test_succeeded_transitions_to_succeeded() -> None:
    job = _queued_job().started(_T0)

    done = job.succeeded(_T1)

    assert done.status == "succeeded"
    assert done.updated_at == _T1
    assert done.last_error is None


def test_retrying_sets_last_error_and_stays_running() -> None:
    job = _queued_job().started(_T0)

    retried = job.retrying(_T1, "boom")

    assert retried.status == "running"
    assert retried.last_error == "boom"
    assert retried.attempts == job.attempts
    assert retried.updated_at == _T1


def test_failed_transitions_to_failed_with_last_error() -> None:
    job = _queued_job().started(_T0)

    failed = job.failed(_T1, "permanent")

    assert failed.status == "failed"
    assert failed.last_error == "permanent"
    assert failed.updated_at == _T1


def test_active_statuses_are_exactly_queued_and_running() -> None:
    assert ACTIVE_STATUSES == {"queued", "running"}


def test_status_constants_match_spec_vocabulary() -> None:
    assert IngestionStatus.QUEUED == "queued"
    assert IngestionStatus.RUNNING == "running"
    assert IngestionStatus.SUCCEEDED == "succeeded"
    assert IngestionStatus.FAILED == "failed"


def test_event_type_constants_match_spec_vocabulary() -> None:
    assert IngestionEventType.QUEUED == "queued"
    assert IngestionEventType.STARTED == "started"
    assert IngestionEventType.RETRYING == "retrying"
    assert IngestionEventType.SUCCEEDED == "succeeded"
    assert IngestionEventType.FAILED == "failed"


def test_ingestion_event_carries_expected_fields_and_is_frozen() -> None:
    event = IngestionEvent(
        id=uuid4(),
        job_id=uuid4(),
        type=IngestionEventType.QUEUED,
        message=None,
        created_at=_T0,
    )

    assert event.type == "queued"
    assert event.message is None
    assert event.created_at == _T0
    with pytest.raises(FrozenInstanceError):
        event.type = "started"  # type: ignore[misc]


def test_ingestion_job_repository_is_runtime_checkable_protocol() -> None:
    class ConformingRepo:
        def add(self, job):  # noqa: ANN001, ANN201
            return job

        def get_by_id(self, job_id):  # noqa: ANN001, ANN201
            return None

        def get_latest_for_source(self, source_id):  # noqa: ANN001, ANN201
            return None

        def update(self, job):  # noqa: ANN001, ANN201
            return job

    class MissingMethodRepo:
        def add(self, job):  # noqa: ANN001, ANN201
            return job

    assert isinstance(ConformingRepo(), IngestionJobRepository)
    assert not isinstance(MissingMethodRepo(), IngestionJobRepository)


def test_ingestion_event_repository_is_runtime_checkable_protocol() -> None:
    class ConformingRepo:
        def append(self, event):  # noqa: ANN001, ANN201
            return event

        def list_for_job(self, job_id):  # noqa: ANN001, ANN201
            return []

    assert isinstance(ConformingRepo(), IngestionEventRepository)
    assert not isinstance(object(), IngestionEventRepository)


def test_ingestion_step_and_enqueuer_are_runtime_checkable_protocols() -> None:
    class ConformingStep:
        def run(self, *, source, job):  # noqa: ANN001, ANN201
            return None

    class ConformingEnqueuer:
        def enqueue_ingestion(self, *, source_id, job_id):  # noqa: ANN001, ANN201
            return None

    assert isinstance(ConformingStep(), IngestionStep)
    assert isinstance(ConformingEnqueuer(), IngestionEnqueuer)
    assert not isinstance(object(), IngestionStep)
    assert not isinstance(object(), IngestionEnqueuer)


def test_source_repository_requires_set_status() -> None:
    # set_status is the source.status projection maintained alongside job transitions.
    class WithoutSetStatus:
        def add(self, source):  # noqa: ANN001, ANN201
            return source

        def list_by_user(self, user_id):  # noqa: ANN001, ANN201
            return []

        def get_by_id(self, source_id):  # noqa: ANN001, ANN201
            return None

    class WithSetStatus(WithoutSetStatus):
        def set_status(self, source_id, status, updated_at):  # noqa: ANN001, ANN201
            return None

    assert not isinstance(WithoutSetStatus(), SourceRepository)
    assert isinstance(WithSetStatus(), SourceRepository)
