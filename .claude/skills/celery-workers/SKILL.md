---
name: celery-workers
description: Learny Celery worker conventions for long-running background work — EPUB ingestion, canonical corpus generation, embedding, indexing, and retrieval evaluation run in separate worker processes over the same codebase, never inside FastAPI request handlers. Use when adding or reviewing a Celery task, wiring app.worker.celery_app, designing task payloads/args, configuring retries/backoff/acks_late/prefetch/time-limits, composing ingest→corpus→embed→index→evaluate pipelines, tracking job/ingestion progress, or running the worker/beat services in local or Docker Compose. Covers where task state lives (PostgreSQL is source of truth; Redis is transport). Not for FastAPI HTTP handlers (see the fastapi skill), Redis data modeling (see redis-core), or adopting a broad orchestration framework (ADR-0009 forbids it).
---

# Celery Workers

Learny-owned conventions for running long-running document-intelligence work in Celery worker processes over the shared backend codebase, never inside FastAPI request handlers.

## Consistency First

Before applying any generic Celery pattern, match Learny's existing conventions. Read `backend/app/worker/celery_app.py` (the real app object, config block, and Settings wiring), the hexagonal layout under `backend/app/` (`domain/` ports as `typing.Protocol`, framework-free `application/` use-case classes, `infrastructure/` adapters), and the composition pattern in `backend/app/infrastructure/db/` (`get_engine().begin()` unit-of-work, caller-provided `Connection`). A task is a thin adapter that wires ports and calls an application service — the same shape the web layer uses. When a Learny pattern and a generic default disagree, the Learny pattern wins.

## When to apply

- Adding, moving, or reviewing a Celery task for ingestion, corpus generation, embedding, indexing, or evaluation.
- Deciding what a task accepts as arguments and how it reports progress and failure.
- Configuring retries, backoff, `acks_late`, prefetch, time limits, or Redis visibility timeout.
- Composing a multi-step pipeline (chain / group / chord) from Learny application services.
- Running or wiring the `worker` (and optional `beat`) services locally or in Docker Compose.

## When NOT to apply

- Writing FastAPI HTTP handlers or Pydantic request/response models — use the `fastapi` skill. Handlers only enqueue work and read status; they never do heavy work (ADR-0005).
- Modeling Redis keys or data structures — use `redis-core`. Here Redis is broker/result transport only.
- Reaching for a broad orchestration framework (LlamaIndex / LangGraph / LangChain). Orchestration is Learny-owned (ADR-0009); compose with Celery canvas over Learny services.

## Quick Reference

- Never do heavy work in an HTTP handler — ingestion, corpus generation, embedding, indexing, and evaluation run only in Celery workers (ADR-0005); handlers enqueue with `.delay()`/`.apply_async()` and read DB status. See [references/task-design.md](references/task-design.md).
- Tasks are thin adapters over Learny application services — a task opens a DB `Connection` via `get_engine().begin()`, wires repositories/ports, and calls a use-case class; it holds no business logic (mirrors the web composition root). See [references/task-design.md](references/task-design.md).
- Pass small, stable, JSON-serializable args only (e.g. `ingestion_id` / `source_id`) — never EPUB bytes, ORM rows, or provider SDK objects; load blobs from the `StoragePort` inside the task (ADR-0014). See [references/task-design.md](references/task-design.md).
- Make every task idempotent because `acks_late=True` and Redis visibility-timeout redelivery mean a task can run more than once — key off DB state and use guarded upserts. See [references/reliability.md](references/reliability.md).
- Retry transient failures with `autoretry_for` + `retry_backoff` / `retry_backoff_max` / `retry_jitter` (or `raise self.retry(...)` on a bound task); cap `max_retries` and let non-transient errors fail to a terminal DB status. See [references/reliability.md](references/reliability.md).
- Keep the long-task settings: `task_acks_late=True` + `worker_prefetch_multiplier=1`, tune `broker_transport_options['visibility_timeout']` above the longest task so Redis does not redeliver mid-run, and add `task_time_limit` / `task_soft_time_limit`. See [references/reliability.md](references/reliability.md).
- PostgreSQL is the source of truth for job / ingestion / corpus / progress state (ADR-0014); write status transitions to Postgres inside the task and treat the Redis result backend as transient transport, not durable state. See [references/state-and-progress.md](references/state-and-progress.md).
- Compose multi-step pipelines with Learny-owned Celery canvas (`chain` / `|`, `group`, `chord`, immutable `.si()`) — do NOT introduce LlamaIndex/LangGraph as orchestration; specialized libs (Docling, Ragas) sit behind Learny ports called from tasks (ADR-0009). See [references/pipelines.md](references/pipelines.md).
- Register tasks under `app.worker`, configure via `celery_app.conf.update(...)`, and drive broker/backend from `Settings` — match the existing `celery_app.py`, never hardcode URLs. See [references/runtime.md](references/runtime.md).
- Run workers (and, if needed, a single `beat` scheduler) as separate Compose services from the same image: `celery -A app.worker.celery_app:celery_app worker -c N -Q …`, health-checked with `inspect ping`. See [references/runtime.md](references/runtime.md).

## References

- [Celery: Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [Celery: Configuration and defaults](https://docs.celeryq.dev/en/stable/userguide/configuration.html)
- [Celery: Canvas — designing workflows](https://docs.celeryq.dev/en/stable/userguide/canvas.html)
- [Celery: Calling tasks](https://docs.celeryq.dev/en/stable/userguide/calling.html)
- [Celery: Periodic tasks (beat)](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
- [Celery: Using Redis as broker/backend](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- [Celery: CLI reference](https://docs.celeryq.dev/en/stable/reference/cli.html)

Source: Learny-authored project-local skill encoding ADR-0005 (separate workers, same codebase), ADR-0014 (Redis + Celery; Postgres is the source of truth), ADR-0009 (Learny-owned orchestration, edge libraries behind ports), and ADR-0007 (provider-port boundary), grounded in the official Celery documentation cited above. Distinct from vendored official skills (e.g. `fastapi`, `redis-core`).
