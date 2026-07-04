# State and Progress: PostgreSQL Is the Source of Truth

Durable job, ingestion, corpus, and user-visible progress state lives in PostgreSQL (ADR-0014). Celery/Redis delivers tasks and coordinates workers; the result backend is transient transport, not product state.

## Write status transitions inside the task

The task opens the unit-of-work (`get_engine().begin()`), advances a persisted status/progress row through explicit transitions, and commits. The FastAPI handler reads those same rows to answer "how is my ingestion going?" — it never inspects Celery result state for product answers.

An illustrative ingestion-status table (future cycle; follows the Core-metadata style of `app/infrastructure/db/metadata.py`):

```python
ingestions = Table(
    "ingestions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source_id", UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False),
    Column("status", Text, nullable=False),          # queued|running|completed|failed
    Column("progress", Integer, nullable=False, server_default="0"),   # 0..100
    Column("error", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
```

**Do this** — progress is DB-driven and committed transactionally:

```python
def __call__(self, *, ingestion_id: UUID) -> None:
    with self._engine.begin() as conn:
        self._ingestions(conn).set(ingestion_id, status="running", progress=10)
    # ... long step (parse) ...
    with self._engine.begin() as conn:
        self._ingestions(conn).set(ingestion_id, progress=60)
    # ... long step (chunk) ...
    with self._engine.begin() as conn:
        self._ingestions(conn).set(ingestion_id, status="completed", progress=100)
```

**Not this** — durable product state parked only in Redis / the result backend (ADR-0014 forbids it):

```python
redis.set(f"ingestion:{ingestion_id}:progress", 60)   # transient — lost on flush/expiry
self.update_state(state="PROGRESS", meta={"progress": 60})  # result backend is transport, not truth
```

`update_state` / a result backend is fine for transient operational signalling, but it must never be the record a handler trusts for user-visible status.

## Terminal failure, not silent loss

On a non-transient error (or after retries are exhausted), write a terminal `failed` status with an `error` message in the same DB transaction, so the failure is visible and the record is not stuck in `running`. Combined with idempotency (see [reliability.md](reliability.md)), a redelivered task sees the terminal status and no-ops.

Reference: [Celery — Configuration and defaults](https://docs.celeryq.dev/en/stable/userguide/configuration.html), ADR-0014 (`docs/adr/0014-use-redis-and-celery-for-worker-queues.md`)
