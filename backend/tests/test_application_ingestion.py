"""T4 gate — ingestion application services (unit, fake ports).

1:1 to the worker-foundation spec ACs, driven entirely through in-memory fakes:
- ``StartIngestion`` — create queued job + source→processing + queued event
  (ING-01); active job → ``ActiveIngestionExists`` (ING-03); non-owner/missing →
  ``SourceNotFound`` (ING-04); terminal-prior-job → restart (ING-05).
- ``RunIngestion`` — begin_run missing/terminal no-op (ING-08 AC3); running +
  attempts+1 + started event (ING-02); a job whose attempts are spent stops at the
  claim, failed terminally rather than run again; complete → succeeded + source ready
  (ING-02); record_retry → last_error + retrying event (ING-07); fail → failed +
  source failed + failed event (ING-08); run_step drives the Phase-5 seam.
- ``ReadIngestion`` — latest job + ordered events (ING-06); no job →
  ``IngestionNotFound`` (ING-12); non-owner/missing → ``SourceNotFound`` (ING-04).
"""

from __future__ import annotations

import logging
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
    max_attempts: int = 5,
) -> RunIngestion:
    return RunIngestion(
        sources=sources,
        jobs=jobs,
        events=events,
        step=step or FakeIngestionStep(),
        clock=clock,
        ids=_ids,
        max_attempts=max_attempts,
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

    job, returned_events, content_type = start(user=owner, source_id=source.id)

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
    # It also returns the source's content type so the handler routes the enqueue.
    assert content_type == source.content_type


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

    first, _, _ = start(user=owner, source_id=source.id)
    run.begin_run(first.id)
    run.fail(first.id, "permanent")  # first job now terminal (failed)

    restarted, _, _ = start(user=owner, source_id=source.id)

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
    job, _, _ = start(user=owner, source_id=source.id)
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
    job, _, _ = start(user=owner, source_id=source.id)

    started = run.begin_run(job.id)

    assert started.status == IngestionStatus.RUNNING
    assert started.attempts == 1
    assert jobs.get_by_id(job.id).status == IngestionStatus.RUNNING
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_PROCESSING
    assert [e.type for e in events.list_for_job(job.id)] == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
    ]


def _claim_context(cap: int):  # noqa: ANN202 — (sources, jobs, events, run, job)
    """A stored source with one queued job, and a run service capped at ``cap``."""
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    run = _run_service(sources, jobs, events, clock, max_attempts=cap)
    job, _, _ = start(user=owner, source_id=source.id)
    return sources, jobs, events, run, job, source


def test_begin_run_below_the_cap_keeps_claiming_the_job() -> None:
    # WRK-03: under the cap nothing changes — every claim starts the job and counts
    # one attempt, including the claim of a job left ``running`` by a dead worker.
    sources, jobs, events, run, job, source = _claim_context(cap=3)

    first = run.begin_run(job.id)
    second = run.begin_run(job.id)  # redelivery: the row is still ``running``

    assert (first.status, first.attempts) == (IngestionStatus.RUNNING, 1)
    assert (second.status, second.attempts) == (IngestionStatus.RUNNING, 2)
    assert jobs.get_by_id(job.id).status == IngestionStatus.RUNNING
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_PROCESSING
    assert [e.type for e in events.list_for_job(job.id)] == [
        IngestionEventType.QUEUED,
        IngestionEventType.STARTED,
        IngestionEventType.STARTED,
    ]


def test_begin_run_at_the_cap_fails_the_job_instead_of_running_it_again() -> None:
    # WRK-02: a job that keeps killing its worker is redelivered with its row still
    # ``running`` and its attempts already spent. It must stop there — terminal
    # ``failed``, source synced, ``failed`` event — not start a further run.
    sources, jobs, events, run, job, source = _claim_context(cap=2)
    run.begin_run(job.id)
    run.begin_run(job.id)  # attempts now == cap

    assert run.begin_run(job.id) is None

    stopped = jobs.get_by_id(job.id)
    assert stopped.status == IngestionStatus.FAILED
    assert stopped.attempts == 2  # the refused claim did not count as an attempt
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_FAILED
    assert [e.type for e in events.list_for_job(job.id)][-1] == IngestionEventType.FAILED


def test_the_capped_failure_is_readable_but_says_nothing_about_the_worker() -> None:
    # Edge case: the owner-readable fields keep the fixed, non-secret summary —
    # whatever killed the worker (a path, an object key, a provider error) never
    # reaches them.
    _, jobs, events, run, job, _ = _claim_context(cap=1)
    run.begin_run(job.id)

    run.begin_run(job.id)

    assert jobs.get_by_id(job.id).last_error == "Ingestion processing failed."
    assert events.list_for_job(job.id)[-1].message == "Ingestion processing failed."


def test_begin_run_terminates_a_job_already_past_a_lowered_cap() -> None:
    # Edge case: the operator lowered the cap between runs, so the job's attempts
    # are already *above* it. ``>=`` is what makes that terminate rather than run on.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    owner = _user()
    source = _stored_source(sources, owner)
    clock = FakeClock(_NOW)
    start = _start_service(sources, jobs, events, clock)
    job, _, _ = start(user=owner, source_id=source.id)
    generous = _run_service(sources, jobs, events, clock, max_attempts=5)
    generous.begin_run(job.id)
    generous.begin_run(job.id)
    generous.begin_run(job.id)  # attempts == 3, above the cap that follows

    assert _run_service(sources, jobs, events, clock, max_attempts=2).begin_run(job.id) is None
    assert jobs.get_by_id(job.id).status == IngestionStatus.FAILED
    assert sources.get_by_id(source.id).status == SOURCE_STATUS_FAILED


def test_a_redelivery_after_the_cap_terminated_the_job_is_an_idempotent_no_op() -> None:
    # The message is still on the queue after the cap fired, so the job is claimed
    # again. It is terminal now — nothing may be written a second time.
    _, jobs, events, run, job, _ = _claim_context(cap=1)
    run.begin_run(job.id)
    run.begin_run(job.id)  # cap fires
    trail = [e.type for e in events.list_for_job(job.id)]

    assert run.begin_run(job.id) is None
    assert [e.type for e in events.list_for_job(job.id)] == trail
    assert jobs.get_by_id(job.id).status == IngestionStatus.FAILED


def test_a_first_claim_is_not_worth_a_warning(caplog) -> None:
    # Every ingestion begins with one claim; warning about it would bury the case
    # that matters in a record emitted for every source ever uploaded.
    _, _, _, run, job, _ = _claim_context(cap=5)

    with caplog.at_level(logging.WARNING, logger="app.application.ingestion"):
        run.begin_run(job.id)

    assert [r for r in caplog.records if r.name == "app.application.ingestion"] == []


def test_a_repeat_claim_warns_once_naming_the_job_source_and_attempt(caplog) -> None:
    # A phase that silently restarts is the signal the operator has none of today:
    # the job row still says ``running``, so nothing distinguishes a long ingestion
    # from one whose worker has died three times. One record per repeat claim, and
    # the attempt number is what makes it readable as a pattern rather than an event.
    _, _, _, run, job, source = _claim_context(cap=5)
    run.begin_run(job.id)

    with caplog.at_level(logging.WARNING, logger="app.application.ingestion"):
        run.begin_run(job.id)
        run.begin_run(job.id)

    records = [r for r in caplog.records if r.name == "app.application.ingestion"]
    assert [r.levelno for r in records] == [logging.WARNING, logging.WARNING]
    assert [r.attempt for r in records] == [2, 3]
    assert {r.job_id for r in records} == {str(job.id)}
    assert {r.source_id for r in records} == {str(source.id)}


def test_the_cap_terminating_a_job_is_not_silent(caplog) -> None:
    # ``None`` also means "missing or already terminal", which the worker logs as an
    # ordinary no-op. A claim that just failed a job terminally is a different event
    # and has to say so, naming the job, the source and the attempts it used up.
    _, _, _, run, job, source = _claim_context(cap=1)
    run.begin_run(job.id)

    with caplog.at_level(logging.WARNING, logger="app.application.ingestion"):
        run.begin_run(job.id)

    records = [r for r in caplog.records if r.name == "app.application.ingestion"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].job_id == str(job.id)
    assert records[0].source_id == str(source.id)
    assert records[0].attempts == 1
    assert records[0].max_attempts == 1


def test_an_ordinary_terminal_redelivery_does_not_claim_the_cap_fired(caplog) -> None:
    # The discriminating half: a job that finished normally and is redelivered is a
    # plain no-op. If it warned too, the warning would mean nothing.
    _, _, _, run, job, _ = _claim_context(cap=5)
    run.begin_run(job.id)
    run.complete(job.id)

    with caplog.at_level(logging.WARNING, logger="app.application.ingestion"):
        assert run.begin_run(job.id) is None

    assert [r for r in caplog.records if r.name == "app.application.ingestion"] == []


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
    job, _, _ = start(user=owner, source_id=source.id)
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
    job, _, _ = start(user=owner, source_id=source.id)
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
    job, _, _ = start(user=owner, source_id=source.id)
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
    job, _, _ = start(user=owner, source_id=source.id)

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
    job, _, _ = start(user=owner, source_id=source.id)

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
    job, _, _ = start(user=owner, source_id=source.id)
    run.begin_run(job.id)
    run.complete(job.id)
    read = ReadIngestion(sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership())

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
    read = ReadIngestion(sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership())

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
    read = ReadIngestion(sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership())

    with pytest.raises(SourceNotFound):
        read(user=intruder, source_id=source.id)


def test_read_missing_source_raises_source_not_found() -> None:
    # ING-04: unknown source read → 404.
    sources, jobs, events = (
        FakeSourceRepository(),
        FakeIngestionJobRepository(),
        FakeIngestionEventRepository(),
    )
    read = ReadIngestion(sources=sources, jobs=jobs, events=events, authorize=AuthorizeOwnership())

    with pytest.raises(SourceNotFound):
        read(user=_user(), source_id=uuid4())
