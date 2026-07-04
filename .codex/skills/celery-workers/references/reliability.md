# Reliability: Idempotency, Retries, Long-Task Settings

Long document tasks can run more than once. Design for redelivery, retry transient failures, and cap the rest to a terminal failure state.

## Idempotency is mandatory

`task_acks_late=True` (already set) acknowledges the message *after* execution, so a worker crash re-queues the task. Redis also redelivers if a task outlives `broker_transport_options['visibility_timeout']` (default 3600s). Both mean the same `ingestion_id` may be processed twice — the task MUST be idempotent.

**Do this** — key off DB state and use guarded upserts (source of truth is Postgres — see [state-and-progress.md](state-and-progress.md)):

```python
def __call__(self, *, ingestion_id: UUID) -> None:
    row = self._ingestions.get(ingestion_id)
    if row.status in ("completed", "failed"):
        return                      # already terminal — safe no-op on redelivery
    self._ingestions.mark_running(ingestion_id)
    ...                             # re-runnable steps; upsert, don't blind-insert
```

**Not this** — non-idempotent side effects duplicate rows/objects on every redelivery:

```python
def __call__(self, *, ingestion_id):
    self._chunks.insert_all(parse(...))   # second run inserts duplicate chunks
```

## Retry transient failures

Prefer declarative auto-retry for transient errors (network, storage, provider timeouts). Reserve non-transient errors (validation, corrupt EPUB) for a terminal failure status — do not retry them.

```python
@celery_app.task(
    bind=True,
    name="ingestion.embed_chunks",
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,          # exponential backoff between retries
    retry_backoff_max=600,       # cap the backoff at 600s
    retry_jitter=True,           # spread retries to avoid thundering herd
    max_retries=5,               # default is 3; None = retry forever
)
def embed_chunks(self, ingestion_id: str) -> None:
    ...
```

Equivalent manual form on a bound task:

```python
try:
    ...
except TimeoutError as exc:
    raise self.retry(exc=exc, countdown=60, max_retries=5)
```

Defaults worth knowing: `max_retries=3`, `default_retry_delay=180`. Use `dont_autoretry_for` to exclude specific exceptions from `autoretry_for`.

## Long-task worker settings

Keep and extend the conservative block in `celery_app.py`:

```python
celery_app.conf.update(
    task_acks_late=True,                 # already set — re-run on crash (needs idempotency)
    worker_prefetch_multiplier=1,        # already set — fair dispatch of long tasks (default 4)
    broker_connection_retry_on_startup=True,  # already set
    task_time_limit=1800,                # hard kill ceiling (seconds)
    task_soft_time_limit=1500,           # SoftTimeLimitExceeded first, so you can fail cleanly
    task_track_started=True,             # surface a STARTED state
    broker_transport_options={"visibility_timeout": 3600},  # keep ABOVE the longest task
)
```

Tune `visibility_timeout` above your longest task's worst-case duration; otherwise Redis redelivers mid-run and the task executes concurrently with itself. `task_reject_on_worker_lost=True` re-queues a task whose worker died abruptly — pair with `acks_late` for durability, but only with idempotent tasks (it can otherwise cause a redelivery loop).

Reference: [Celery — Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [Celery — Configuration and defaults](https://docs.celeryq.dev/en/stable/userguide/configuration.html), [Celery — Redis broker/backend](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
