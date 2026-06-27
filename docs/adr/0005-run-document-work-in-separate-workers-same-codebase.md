# ADR-005: Run Document Work In Separate Workers Within The Same Codebase

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, runtime, workers, fastapi, ingestion, retrieval, evaluation

## Context and Problem Statement

Learny's backend stack is Python/FastAPI. The application must handle normal HTTP product workflows as well as long-running document ingestion, parsing, corpus generation, embedding, retrieval indexing, and evaluation jobs.

The runtime question is whether these document-intelligence tasks should run inside the FastAPI request process, in separate worker processes from the same codebase, or as a separate service. The decision affects reliability, deployment complexity, retries, observability, and the clarity of application boundaries.

## Decision Drivers

- HTTP requests should stay responsive and should not be blocked by long-running document work.
- Ingestion, indexing, and evaluation need retries, progress tracking, failure states, and observability.
- The project should avoid premature microservice complexity.
- Domain and application code should be shared without duplicating contracts across separate repositories or services.
- Future extraction to a separate service should remain possible if scale or ownership requires it.

## Considered Options

- Run document work inside the FastAPI process using in-process background tasks.
- Run document work in separate worker processes from the same codebase.
- Run document intelligence as a separate internal service.
- Split into multiple services from the beginning.

## Decision Outcome

Chosen option: **Run document work in separate worker processes from the same codebase**, because it separates HTTP responsiveness from long-running work while keeping deployment, code sharing, and domain boundaries simple enough for the initial product.

The runtime model is:

1. FastAPI handles synchronous API requests, authentication, upload initiation, session actions, and status reads.
2. Worker processes handle document parsing, canonical corpus generation, derived Markdown/chunk generation, embeddings, indexing, retrieval evaluation, and other long-running tasks.
3. API and workers share the same repository and domain/application code.
4. Workers communicate through explicit job payloads, persisted records, and status transitions.
5. Queue technology is not decided by this ADR and should be selected in a follow-up implementation design.

### Positive Consequences

- HTTP behavior remains responsive even when ingestion is slow or CPU/IO-heavy.
- Long-running work can have explicit retries, backoff, idempotency, progress tracking, and failure states.
- The system avoids an early service split while still creating a real runtime boundary.
- Shared code reduces duplication between API and worker execution paths.
- A future extraction to a separate document-intelligence service remains possible if scale, deployment, or ownership requires it.

### Negative Consequences

- The project must introduce queue/job infrastructure earlier than a request-only application.
- Workers need operational handling: process supervision, concurrency limits, logs, metrics, and failure recovery.
- Shared code can still become coupled if module boundaries and public contracts are not enforced.
- Queue technology, job schema, and idempotency rules still need explicit design.

## Pros and Cons of the Options

### Separate workers, same codebase ✅ Chosen

- ✅ Keeps HTTP request handling separate from long-running document work.
- ✅ Supports retries, progress tracking, and failure handling.
- ✅ Avoids early microservice overhead.
- ✅ Keeps domain/application code shared and consistent.
- ❌ Requires queue and worker operations from the first serious ingestion workflow.

### FastAPI in-process background tasks

- ✅ Simplest runtime model.
- ✅ Minimal infrastructure.
- ❌ Weak fit for long-running ingestion, indexing, and evaluation.
- ❌ Poorer retry, durability, concurrency, and observability story.

### Separate document-intelligence service

- ✅ Stronger runtime and deployment isolation.
- ✅ Cleaner scaling path if ingestion and retrieval workloads grow independently.
- ❌ Adds service contracts, deployment units, monitoring, and local development complexity too early.
- ❌ Can slow early product iteration before the domain model is stable.

### Multiple services from the beginning

- ✅ Strong theoretical isolation.
- ❌ Premature for the current project stage.
- ❌ Increases coordination, versioning, deployment, and observability cost before there is enough product signal.

## References

- [ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback](0001-hybrid-book-intelligence-architecture.md)
- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
