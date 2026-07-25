"""C2 gate — every Celery task reports its duration (unit, OBS-16..18).

Every case derives from the spec's "Uniform Celery task durations" acceptance
criteria. The tasks below are declared here, in the test, and contain no timing
code whatsoever: that is the point. They are registered on the *application's*
Celery app and run through it, so what is under test is the wiring importing
``app.worker.celery_app`` performs — a task nobody instrumented still reports a
duration. Nothing here connects the signals itself; if that wiring were removed,
every case in this file would fail.

The interleaving case is the sensor for the per-attempt timing state: two tasks
overlap inside one process, and a slow one's start reading must not become a fast
one's duration.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.worker.celery_app import celery_app
from app.worker.instrumentation import (
    TASK_DURATION_LOGGER,
    TASK_DURATION_MESSAGE,
    pending_attempts,
)

#: A task slow enough that inheriting its start reading would be unmistakable.
SLOW_TASK_SECONDS = 0.30

#: Upper bound a fast task's reported duration must stay under. Comfortably below
#: ``SLOW_TASK_SECONDS`` so the assertion is about keying, not about scheduler noise.
FAST_TASK_CEILING_MS = 200.0

DOMAIN_LOGGER = "tests.worker.domain"


class _RecordingHandler(logging.Handler):
    """Collect every record emitted during one test."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def durations(self) -> list[logging.LogRecord]:
        return [
            record
            for record in self.records
            if record.name == TASK_DURATION_LOGGER and record.getMessage() == TASK_DURATION_MESSAGE
        ]

    def durations_for(self, task_name: str) -> list[logging.LogRecord]:
        return [record for record in self.durations() if record.task_name == task_name]


@pytest.fixture
def captured() -> Iterator[_RecordingHandler]:
    """Attach a recording handler to root; force the duration logger enabled."""
    handler = _RecordingHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = root.level
    root.setLevel(logging.DEBUG)
    for name in (TASK_DURATION_LOGGER, DOMAIN_LOGGER):
        logger = logging.getLogger(name)
        logger.disabled = False
        logger.setLevel(logging.NOTSET)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


# --- Tasks with no instrumentation code of their own -----------------------------


@celery_app.task(name="tests.uninstrumented_success")
def uninstrumented_success() -> str:
    return "done"


@celery_app.task(name="tests.uninstrumented_failure")
def uninstrumented_failure() -> None:
    raise ValueError("this task fails on purpose")


@celery_app.task(bind=True, name="tests.uninstrumented_retry", max_retries=1)
def uninstrumented_retry(self) -> str:  # noqa: ANN001
    if self.request.retries < 1:
        raise self.retry(countdown=0)
    return "done"


@celery_app.task(name="tests.slow")
def slow_task() -> str:
    time.sleep(SLOW_TASK_SECONDS)
    return "slow"


@celery_app.task(name="tests.fast")
def fast_task() -> str:
    return "fast"


@celery_app.task(name="tests.logs_its_own_duration")
def logs_its_own_duration() -> str:
    """Stands in for the hand-rolled per-task ``duration_ms`` records (AD-176)."""
    logging.getLogger(DOMAIN_LOGGER).info(
        "domain.task: succeeded", extra={"duration_ms": 1.5, "job_id": "a-job"}
    )
    return "done"


# --- OBS-16: any task reports name, terminal state and duration ------------------


def test_a_task_with_no_instrumentation_code_reports_its_duration(
    captured: _RecordingHandler,
) -> None:
    result = uninstrumented_success.apply()

    assert result.get() == "done"
    (record,) = captured.durations_for("tests.uninstrumented_success")
    assert record.state == "SUCCESS"
    assert isinstance(record.duration_ms, float)
    assert record.duration_ms >= 0


# --- OBS-17: a raising task still reports, with a state that says so -------------


def test_a_failing_task_reports_a_duration_under_a_distinct_state(
    captured: _RecordingHandler,
) -> None:
    uninstrumented_failure.apply()

    (failed,) = captured.durations_for("tests.uninstrumented_failure")
    assert failed.state == "FAILURE"
    assert failed.duration_ms >= 0

    uninstrumented_success.apply()
    (succeeded,) = captured.durations_for("tests.uninstrumented_success")
    assert succeeded.state != failed.state


def test_a_retried_task_reports_one_duration_per_attempt(
    captured: _RecordingHandler,
) -> None:
    assert uninstrumented_retry.apply().get() == "done"

    records = captured.durations_for("tests.uninstrumented_retry")
    assert len(records) == 2


# --- OBS-18: the existing per-task duration records keep being emitted -----------


def test_a_task_that_logs_its_own_duration_still_does_so_alongside_the_uniform_record(
    captured: _RecordingHandler,
) -> None:
    logs_its_own_duration.apply()

    own = [record for record in captured.records if record.name == DOMAIN_LOGGER]
    assert len(own) == 1
    assert own[0].duration_ms == 1.5
    assert own[0].job_id == "a-job"
    assert len(captured.durations_for("tests.logs_its_own_duration")) == 1


# --- Per-attempt timing state: no collision, no leak -----------------------------


def test_overlapping_tasks_each_report_their_own_duration(
    captured: _RecordingHandler,
) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(slow_task.apply)
        time.sleep(SLOW_TASK_SECONDS / 3)
        pool.submit(fast_task.apply).result()
        slow.result()

    (slow_record,) = captured.durations_for("tests.slow")
    (fast_record,) = captured.durations_for("tests.fast")
    assert slow_record.duration_ms >= SLOW_TASK_SECONDS * 1000
    assert fast_record.duration_ms < FAST_TASK_CEILING_MS


def test_finished_tasks_leave_no_timing_state_behind(captured: _RecordingHandler) -> None:
    before = pending_attempts()

    uninstrumented_success.apply()
    uninstrumented_failure.apply()
    uninstrumented_retry.apply()

    assert pending_attempts() == before


# --- The instrument never changes the task ---------------------------------------
#
# These assert the outcome the invariant names, not the mechanism that delivers
# it: Celery's own dispatcher already contains a receiver's exception, so they
# would hold even if the handlers dropped their guards. That is worth stating —
# the property is real and pinned, but this pair does not discriminate the
# instrument's containment from Celery's.


def test_a_failing_duration_record_leaves_the_task_result_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*_: object, **__: object) -> None:
        raise RuntimeError("duration record exploded")

    monkeypatch.setattr("app.worker.instrumentation._logger.info", _explode)

    assert uninstrumented_success.apply().get() == "done"


def test_a_failing_duration_record_leaves_a_task_failure_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*_: object, **__: object) -> None:
        raise RuntimeError("duration record exploded")

    monkeypatch.setattr("app.worker.instrumentation._logger.info", _explode)

    result = uninstrumented_failure.apply()

    assert result.state == "FAILURE"
    with pytest.raises(ValueError, match="this task fails on purpose"):
        result.get()
