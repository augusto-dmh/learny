"""T4 gate — ingestion application services (unit, fake ports).

1:1 to the worker-foundation spec ACs, driven entirely through in-memory fakes:
- ``StartIngestion`` — create queued job + source→processing + queued event
  (ING-01); active job → ``ActiveIngestionExists`` (ING-03); non-owner/missing →
  ``SourceNotFound`` (ING-04); terminal-prior-job → restart (ING-05).
- ``RunIngestion`` — begin_run missing/terminal no-op (ING-08 AC3); running +
  attempts+1 + started event (ING-02); complete → succeeded + source ready
  (ING-02); record_retry → last_error + retrying event (ING-07); fail → failed +
  source failed + failed event (ING-08); run_step drives the Phase-5 seam.
- ``ReadIngestion`` — latest job + ordered events (ING-06); no job →
  ``IngestionNotFound`` (ING-12); non-owner/missing → ``SourceNotFound`` (ING-04).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.errors import (
    ActiveIngestionExists,
    IngestionNotFound,
    SourceNotFound,
)
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import (
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_PROCESSING,
    SOURCE_STATUS_READY,
    ReadIngestion,
    RunIngestion,
    StartIngestion,
)
from app.domain.entities import IngestionEventType, IngestionStatus, Source, User
from tests.fakes import (
    FakeClock,
    FakeIngestionEventRepository,
    FakeIngestionJobRepository,
    FakeIngestionStep,
    FakeSourceRepository,
)

_NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=UTC)


def _ids():  # noqa: ANN202 — Callable[[], UUID]
    return uuid4()


def _user(email: str = "reader@example.com") -> User:
    return User(id=uuid4(), email=email, created_at=_NOW)


def _stored_source(sources: FakeSourceRepository, owner: User) -> Source:
    source = Source(
        id=uuid4(),
        user_id=owner.id,
        title="Meditations",
        filename="meditations.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{owner.id}/{uuid4()}.epub",
        status="uploaded",
        created_at=_NOW,
        updated_at=_NOW,
    )
    return sources.add(source)


def _start_service(
    sources: FakeSourceRepository,
    jobs: FakeIngestionJobRepository,
    events: FakeIngestionEventRepository,
    clock: FakeClock,
) -> StartIngestion:
    return StartIngestion(
        sources=sources,
        jobs=jobs,
        events=events,
        authorize=AuthorizeOwnership(),
        clock=clock,
        ids=_ids,
    )


def _run_service(
    sources: FakeSourceRepository,
    jobs: FakeIngestionJobRepository,
    events: FakeIngestionEventRepository,
    clock: FakeClock,
    step: FakeIngestionStep | None = None,
) -> RunIngestion:
    return RunIngestion(
        sources=sources,
        jobs=jobs,
        events=events,
        step=step or FakeIngestionStep(),
        clock=clock,
        ids=_ids,
    )


# ---- StartIngestion -------------------------------------------------------


def test_start_creates_queued_job_sets_processing_and_appends_queued_event() -> None:
    # ING-01: queued job + source→processing + queued event.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    start = _start_service(sources, jobs, events, FakeClock(_NOW))

    job, returned_events = start(user=owner, source_id=source.id)

    assert job.status == IngestionStatus.QUEUED
    assert job.attempts == 0
    assert job.source_id == source.id
    assert jobs.get_by_id(job.id) is not None
    # source.status projection flipped to processing.
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_PROCESSING
    # exactly one queued event, tied to the new job.
    logged = events.list_for_job(job.id)
    assert [e.type for e in logged] == [IngestionEventType.QUEUED]
    assert logged[0].message is None
    # The service returns that same queued event so the web layer needs no repo.
    assert [e.id for e in returned_events] == [e.id for e in logged]


def test_start_with_active_job_raises_active_ingestion_exists() -> None:
    # ING-03: a source with an active (queued) job rejects a second start.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    start = _start_service(sources, jobs, events, FakeClock(_NOW))
    start(user=owner, source_id=source.id)

    with pytest.raises(ActiveIngestionExists):
        start(user=owner, source_id=source.id)

    # No second active job was created (only the first add succeeded).
    assert jobs.add_calls == 1


def test_start_non_owner_source_raises_source_not_found() -> None:
    # ING-04: non-owner start → 404 (no existence disclosure), nothing enqueued.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user("owner@example.com")
    source = _stored_source(sources, owner)
    intruder = _user("intruder@example.com")
    start = _start_service(sources, jobs, events, FakeClock(_NOW))

    with pytest.raises(SourceNotFound):
        start(user=intruder, source_id=source.id)
    assert jobs.add_calls == 0


def test_start_missing_source_raises_source_not_found() -> None:
    # ING-04: unknown source → 404.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    start = _start_service(sources, jobs, events, FakeClock(_NOW))

    with pytest.raises(SourceNotFound):
        start(user=_user(), source_id=uuid4())
    assert jobs.add_calls == 0


def test_start_after_terminal_job_creates_new_queued_job() -> None:
    # ING-05: a terminal latest job does not block a restart.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)

    first, _ = start(user=owner, source_id=source.id)
    run.begin_run(first.id)
    run.fail(first.id, "permanent")  # first job now terminal (failed)

    restarted, _ = start(user=owner, source_id=source.id)

    assert restarted.id != first.id
    assert restarted.status == IngestionStatus.QUEUED
    assert jobs.get_latest_for_source(source.id).id == restarted.id


# ---- RunIngestion: begin_run ----------------------------------------------


def test_begin_run_missing_job_returns_none() -> None:
    # ING-08 AC3: task fires for a missing row → defensive no-op.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    run = _run_service(sources, jobs, events, FakeClock(_NOW))

    assert run.begin_run(uuid4()) is None


def test_begin_run_terminal_job_returns_none() -> None:
    # Idempotent redelivery of an already-terminal job → no-op.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)
    job, _ = start(user=owner, source_id=source.id)
    run.begin_run(job.id)
    run.complete(job.id)  # job is now terminal (succeeded)

    events_before = len(events.list_for_job(job.id))
    assert run.begin_run(job.id) is None
    # No extra event appended by the no-op.
    assert len(events.list_for_job(job.id)) == events_before


def test_begin_run_transitions_running_increments_attempts_and_logs_started() -> None:
    # ING-02: queued → running (+source processing) + started event.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)
    job, _ = start(user=owner, source_id=source.id)

    started = run.begin_run(job.id)

    assert started.status == IngestionStatus.RUNNING
    assert started.attempts == 1
    assert jobs.get_by_id(job.id).status == IngestionStatus.RUNNING
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_PROCESSING
    assert [e.type for e in events.list_for_job(job.id)] == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
    ]


# ---- RunIngestion: complete / record_retry / fail -------------------------


def test_complete_sets_succeeded_source_ready_and_succeeded_event() -> None:
    # ING-02: terminal success path.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)
    job, _ = start(user=owner, source_id=source.id)
    run.begin_run(job.id)

    done = run.complete(job.id)

    assert done.status == IngestionStatus.SUCCEEDED
    assert done.last_error is None
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_READY
    assert events.list_for_job(job.id)[-1].type == IngestionEventType.SUCCEEDED


def test_record_retry_sets_last_error_stays_running_and_logs_retrying() -> None:
    # ING-07: retryable failure keeps the job active with a durable last_error.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)
    job, _ = start(user=owner, source_id=source.id)
    started = run.begin_run(job.id)

    retried = run.record_retry(job.id, "transient boom")

    assert retried.status == IngestionStatus.RUNNING
    assert retried.last_error == "transient boom"
    # record_retry does not increment attempts (begin_run/started owns that).
    assert retried.attempts == started.attempts
    last_event = events.list_for_job(job.id)[-1]
    assert last_event.type == IngestionEventType.RETRYING
    assert last_event.message == "transient boom"


def test_fail_sets_failed_source_failed_and_logs_failed() -> None:
    # ING-08: exhausted/non-retryable → terminal failed with durable last_error.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)
    job, _ = start(user=owner, source_id=source.id)
    run.begin_run(job.id)

    failed = run.fail(job.id, "permanent boom")

    assert failed.status == IngestionStatus.FAILED
    assert failed.last_error == "permanent boom"
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_FAILED
    last_event = events.list_for_job(job.id)[-1]
    assert last_event.type == IngestionEventType.FAILED
    assert last_event.message == "permanent boom"


# ---- RunIngestion: run_step (Phase-5 seam) --------------------------------


def test_run_step_invokes_step_with_source_and_job() -> None:
    # The seam is called with the job's source and job (no-op by default).
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    step = FakeIngestionStep()
    run = _run_service(sources, jobs, events, clock, step=step)
    job, _ = start(user=owner, source_id=source.id)

    run.run_step(job)

    assert len(step.calls) == 1
    called_source, called_job = step.calls[0]
    assert called_source.id == source.id
    assert called_job.id == job.id


def test_run_step_propagates_step_error() -> None:
    # A raising step propagates to the task for retry/terminal classification.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    boom = RuntimeError("step failed")
    run = _run_service(sources, jobs, events, clock, step=FakeIngestionStep(error=boom))
    job, _ = start(user=owner, source_id=source.id)

    with pytest.raises(RuntimeError, match="step failed"):
        run.run_step(job)


# ---- ReadIngestion --------------------------------------------------------


def test_read_returns_latest_job_with_ordered_events() -> None:
    # ING-06: latest job + chronological events across the full lifecycle.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock)
    job, _ = start(user=owner, source_id=source.id)
    run.begin_run(job.id)
    run.complete(job.id)
    read = ReadIngestion(
        sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership()
    )

    latest, logged = read(user=owner, source_id=source.id)

    assert latest.id == job.id
    assert latest.status == IngestionStatus.SUCCEEDED
    assert [e.type for e in logged] == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.SUCCEEDED,
    ]


def test_read_no_job_raises_ingestion_not_found() -> None:
    # ING-12: reading before any start → 404.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    read = ReadIngestion(
        sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership()
    )

    with pytest.raises(IngestionNotFound):
        read(user=owner, source_id=source.id)


def test_read_non_owner_raises_source_not_found() -> None:
    # ING-04: non-owner read → 404 (no existence disclosure).
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user("owner@example.com")
    source = _stored_source(sources, owner)
    intruder = _user("intruder@example.com")
    read = ReadIngestion(
        sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership()
    )

    with pytest.raises(SourceNotFound):
        read(user=intruder, source_id=source.id)


def test_read_missing_source_raises_source_not_found() -> None:
    # ING-04: unknown source read → 404.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    read = ReadIngestion(
        sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership()
    )

    with pytest.raises(SourceNotFound):
        read(user=_user(), source_id=uuid4())
