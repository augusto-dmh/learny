# ADR-014: Use Redis And Celery For Worker Queues

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, workers, queues, celery, redis, ingestion

## Context and Problem Statement

ADR-005 established that long-running document work should run in separate worker processes from the same codebase. Learny's workers will need to process EPUB ingestion, canonical corpus generation, derived Markdown/chunk generation, embedding, indexing, evaluation, and later other background tasks.

The queue technology question is whether these workers should use Celery with Redis, RQ with Redis, a PostgreSQL-backed queue, Dramatiq with Redis, or another queue system.

## Decision Drivers

- Worker jobs need retries, timeouts, progress/failure states, and operational visibility.
- Ingestion and indexing should be decoupled from HTTP request latency.
- The queue system should work in local Docker Compose and the first VPS deployment.
- The Python ecosystem and documentation should be mature enough for production-oriented use.
- The decision should support future task routing, scheduling, and worker concurrency control.

## Considered Options

- Redis plus Celery.
- Redis plus RQ.
- PostgreSQL-backed queue.
- Dramatiq plus Redis.

## Decision Outcome

Chosen option: **Redis plus Celery**, because Celery is a mature Python distributed task queue with support for dedicated workers, retries, scheduling, concurrency, task composition, and Redis integration.

The worker queue direction is:

1. Use Celery for background task execution.
2. Use Redis as the initial broker and, if appropriate for implementation, result backend.
3. Run Celery workers as separate processes/services in Docker Compose.
4. Keep task payloads explicit and stable; do not pass provider SDK objects or large source files through queue messages.
5. Persist durable job state, ingestion status, corpus status, and user-visible progress in PostgreSQL.
6. Use Celery/Redis for task delivery and worker coordination, not as the source of truth for product state.

### Positive Consequences

- Learny gets mature retry, worker, scheduling, routing, and concurrency capabilities.
- Docker Compose can model API, workers, Redis, PostgreSQL, and object storage explicitly.
- Long-running document jobs can be isolated from HTTP request handling.
- Redis can also support related transient infrastructure needs if future designs require it.
- Celery provides a known path for scaling workers horizontally.

### Negative Consequences

- Celery adds more configuration and operational surface than simpler queues such as RQ.
- Redis becomes another required service in local and VPS environments.
- Task idempotency, retries, time limits, and failure handling still need careful implementation design.
- Celery task/result state must not become the authoritative product state.

## Pros and Cons of the Options

### Redis plus Celery ✅ Chosen

- ✅ Mature Python worker ecosystem.
- ✅ Supports retries, scheduling, concurrency, task routing, and worker monitoring patterns.
- ✅ Good fit for long-running ingestion, indexing, and evaluation jobs.
- ❌ More complex than simpler job libraries.

### Redis plus RQ

- ✅ Simpler Python job queue.
- ✅ Easier initial mental model.
- ❌ Less powerful for complex task routing, scheduling, and operational workflows.
- ❌ May become limiting as ingestion/evaluation workflows grow.

### PostgreSQL-backed queue

- ✅ Fewer infrastructure services.
- ✅ Keeps queue state close to product data.
- ❌ Can increase load and contention on the primary database.
- ❌ Less clear fit for worker concurrency, retry, and queue operations at scale.

### Dramatiq plus Redis

- ✅ Solid Python worker option with a cleaner surface than Celery in some cases.
- ✅ Good Redis-backed queue support.
- ❌ Smaller ecosystem and less common operational playbook than Celery.
- ❌ Less obvious default for Learny's broad ingestion/evaluation workload.

## References

- [ADR-005: Run Document Work In Separate Workers Within The Same Codebase](0005-run-document-work-in-separate-workers-same-codebase.md)
- [ADR-008: Use Docker Compose On A VPS For The First Production-Like Deploy](0008-use-docker-compose-vps-for-first-production-like-deploy.md)
- [ADR-011: Support EPUB First For Initial Ingestion](0011-support-epub-first-for-initial-ingestion.md)
- Celery official documentation via Context7: `/websites/celeryq_dev_en_stable`
- Redis official documentation via Context7: `/redis/docs`
