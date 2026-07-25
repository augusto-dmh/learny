"""Uniform Celery task durations (OBS-16..18).

Ingestion and embedding are the longest operations in the product, yet most tasks
report nothing about how long they took. Celery already announces every execution
through the ``task_prerun`` / ``task_postrun`` signals, so timing hangs off those:
one structured ``task.duration`` record per task *attempt*, carrying the task
name, the terminal state and the elapsed milliseconds, for every registered task
and with no instrumentation code inside any of them.

**Additive, never a refactor** (AD-176). The hand-rolled ``duration_ms`` records a
few tasks emit today carry domain fields a signal cannot know — job ids, source
ids, event counts — and live tests assert them. They stay exactly as they are;
this is a second, uniform record alongside them.

**Timing state is keyed per attempt.** ``task_postrun`` needs the reading that
``task_prerun`` took, so it is stashed between the two. A worker runs many tasks
at once — prefork children, and threads within one child — so the stash is keyed
by task id, guarded by a lock, and removed when the attempt ends. A retried task
keeps its task id across attempts, so each id holds a *stack* of readings: whether
Celery runs the next attempt after the previous one has finished or nested inside
it, last-in-first-out pairs each ``postrun`` with its own ``prerun`` and every
attempt is timed separately. An entry is removed on ``task_postrun``, which fires
for failures as well as successes, so a failing task leaves nothing behind.

**The instrument never changes the task.** Celery already contains a receiver's
exception (``Signal.send`` logs it and moves on — "send" and "send_robust" do the
same thing there), so the task's return value, its exception and its retry
behaviour survive a broken duration record either way. Both handlers contain
their own failures anyway: it keeps the intent legible at the site, it does not
rest on a detail of Celery's dispatcher, and it keeps a misbehaving instrument at
one debug line instead of an ``ERROR`` traceback on every task attempt.
"""

from __future__ import annotations

import logging
import threading
import time

from celery.signals import task_postrun, task_prerun

#: Structured task-duration records. Separate from the task modules' own loggers so
#: a deployment can filter uniform timings apart from domain progress logs.
TASK_DURATION_LOGGER = "app.task"

#: Message of the structured record emitted for a finished task attempt.
TASK_DURATION_MESSAGE = "task.duration"

#: Identifies our receivers to Celery's signal registry, so connecting twice (the
#: worker imports the Celery app once, tests may import it again) registers once.
_DISPATCH_UID = "learny-task-duration"

_logger = logging.getLogger(TASK_DURATION_LOGGER)

# task id -> stack of ``time.perf_counter`` readings, one per attempt in flight.
_starts: dict[str, list[float]] = {}
_lock = threading.Lock()


def pending_attempts() -> int:
    """Number of task attempts currently being timed in this process.

    A worker at rest reports zero. A number that grows without settling means
    attempts are starting without finishing, which is worth knowing about.
    """
    with _lock:
        return sum(len(readings) for readings in _starts.values())


def _record_start(task_id: str) -> None:
    with _lock:
        _starts.setdefault(task_id, []).append(time.perf_counter())


def _take_start(task_id: str) -> float | None:
    """Pop this attempt's start reading, dropping the key once it holds none."""
    with _lock:
        readings = _starts.get(task_id)
        if not readings:
            return None
        start = readings.pop()
        if not readings:
            del _starts[task_id]
        return start


def _on_task_prerun(task_id: str | None = None, **_: object) -> None:
    try:
        if task_id is not None:
            _record_start(str(task_id))
    except Exception:  # noqa: BLE001 — the instrument never escalates into the task
        _logger.debug("instrument.task.start_failed", exc_info=True)


def _on_task_postrun(
    task_id: str | None = None,
    task: object = None,
    state: str | None = None,
    **_: object,
) -> None:
    try:
        if task_id is None:
            return
        start = _take_start(str(task_id))
        if start is None:
            return
        _logger.info(
            TASK_DURATION_MESSAGE,
            extra={
                "task_name": getattr(task, "name", None),
                "task_id": str(task_id),
                "state": state,
                "retries": getattr(getattr(task, "request", None), "retries", None),
                "duration_ms": round((time.perf_counter() - start) * 1000, 3),
            },
        )
    except Exception:  # noqa: BLE001 — the instrument never escalates into the task
        _logger.debug("instrument.task.dropped", exc_info=True)


def install_task_duration_signals() -> None:
    """Connect the duration receivers to Celery's task signals (idempotent)."""
    task_prerun.connect(_on_task_prerun, weak=False, dispatch_uid=_DISPATCH_UID)
    task_postrun.connect(_on_task_postrun, weak=False, dispatch_uid=_DISPATCH_UID)
