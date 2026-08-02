"""Worker reliability configuration (unit) — the durability contract, pinned.

Every recovery guarantee this project makes about background work rests on this
one config block, and until now a single key of it was asserted anywhere. Each
setting below can be changed in one line, with no test failing and no symptom
until the day a worker dies:

- ``task_acks_late`` — the message is acknowledged after the task finishes, not
  when it is handed to a worker. Early acknowledgement loses the job outright.
- ``task_reject_on_worker_lost`` — a task whose worker was killed is requeued
  rather than discarded, so its job row is not stranded in a non-terminal state.
- ``worker_prefetch_multiplier`` — one long task per worker at a time; a
  prefetching worker that dies takes its whole reserved batch with it.
- the time limits and the broker's visibility timeout — see the ordering tests.

These are outcomes of decisions, not incidental values: changing one should mean
changing this file too, deliberately.
"""

from __future__ import annotations

from app.worker.celery_app import celery_app


def _visibility_timeout() -> int:
    return celery_app.conf.broker_transport_options["visibility_timeout"]


def test_a_task_is_acknowledged_only_after_it_finishes() -> None:
    assert celery_app.conf.task_acks_late is True


def test_a_task_whose_worker_died_is_redelivered() -> None:
    # The failure this closes: a killed worker runs no ``except`` block, so nothing
    # writes a terminal state. Without rejection the message is simply gone and the
    # job row says ``running`` with no worker behind it, indefinitely.
    assert celery_app.conf.task_reject_on_worker_lost is True


def test_a_worker_holds_one_long_task_at_a_time() -> None:
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_the_time_limits_are_the_documented_bounds() -> None:
    assert celery_app.conf.task_time_limit == 1800
    assert celery_app.conf.task_soft_time_limit == 1500


def test_the_soft_limit_fires_before_the_hard_one() -> None:
    # A soft limit at or above the hard limit is never reached: the task is killed
    # outright and its cleanup never runs.
    assert celery_app.conf.task_soft_time_limit < celery_app.conf.task_time_limit


def test_the_broker_waits_longer_for_a_task_than_the_task_may_run() -> None:
    # The silent-corruption hazard: if the broker's visibility timeout were the
    # shorter of the two, a *healthy* long-running ingestion would be redelivered
    # while still running, and two workers would process the same job at once. This
    # ordering, not either number on its own, is what prevents that.
    assert _visibility_timeout() > celery_app.conf.task_time_limit


def test_the_visibility_timeout_is_the_documented_value() -> None:
    assert _visibility_timeout() == 3600
