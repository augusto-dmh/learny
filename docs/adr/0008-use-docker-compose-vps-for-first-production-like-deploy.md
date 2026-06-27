# ADR-008: Use Docker Compose On A VPS For The First Production-Like Deploy

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, deployment, docker, vps, operations

## Context and Problem Statement

Learny's initial stack includes a FastAPI backend, React/Next.js frontend, PostgreSQL with pgvector, worker processes, and likely queue/storage infrastructure. The project needs a first production-like deployment target that makes these runtime pieces explicit without overcommitting to a managed platform or cloud architecture too early.

The deployment question is whether Learny should start on Docker Compose on a VPS, use a managed platform such as Railway/Render/Fly.io, start directly on AWS, or stay local-only until later.

## Decision Drivers

- The first environment should reflect the real runtime architecture: API, frontend, database, workers, queue, and storage.
- Operational behavior should be visible and understandable early.
- Deployment should avoid premature cloud complexity.
- The setup should remain portable to another host or platform later.
- Local development should mirror production-like service boundaries where practical.

## Considered Options

- Docker Compose on a VPS.
- Managed application platform such as Railway, Render, or Fly.io.
- AWS from the start.
- Local-only Docker Compose first.

## Decision Outcome

Chosen option: **Docker Compose on a VPS**, because it gives Learny explicit control over its initial runtime pieces while keeping deployment simpler than a full cloud setup.

The deployment direction is:

1. Use Docker Compose for the first production-like VPS deployment.
2. Run FastAPI, Next.js, PostgreSQL/pgvector, queue infrastructure, and worker processes as explicit services.
3. Keep local Docker Compose aligned with the production-like service topology where practical.
4. Do not choose a specific VPS provider in this ADR.
5. Do not choose the final queue, object storage, reverse proxy, TLS, backup, or observability implementation in this ADR.
6. Revisit managed platforms or cloud-native deployment after the product has real workload and operational signals.

### Positive Consequences

- Runtime dependencies and process boundaries are visible from the beginning.
- The deployment matches ADR-005's separate worker process model.
- PostgreSQL/pgvector, queue workers, and application services can be tested together.
- The project avoids early lock-in to a managed deployment platform.
- The same service topology can support local development and production-like testing.

### Negative Consequences

- The project owner must operate the VPS, Docker, backups, updates, TLS, and monitoring.
- Managed deploy conveniences such as autoscaling, hosted logs, and platform dashboards are not automatic.
- Operational discipline is required earlier than with a fully managed platform.
- A later migration to managed infrastructure may still be needed if usage grows.

## Pros and Cons of the Options

### Docker Compose on a VPS ✅ Chosen

- ✅ Makes API, frontend, workers, database, queue, and storage boundaries explicit.
- ✅ Keeps deployment portable and understandable.
- ✅ Avoids cloud/platform complexity while the product is still forming.
- ❌ Requires server operations, backups, TLS, and monitoring setup.

### Managed application platform

- ✅ Faster hosted deployment experience.
- ✅ Less direct server maintenance.
- ❌ Platform constraints may complicate workers, pgvector, storage, networking, or cost control.
- ❌ Can hide operational details Learny needs to understand early.

### AWS from the start

- ✅ Strong long-term production path.
- ✅ Rich managed database, storage, queue, observability, and scaling options.
- ❌ Too much platform design and operational surface for the current stage.
- ❌ Risks delaying product work.

### Local-only Docker Compose first

- ✅ Good for development.
- ✅ Low operational burden.
- ❌ Does not answer the first production-like deployment target.
- ❌ Delays decisions about real networking, persistence, backups, and process supervision.

## References

- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
- [ADR-005: Run Document Work In Separate Workers Within The Same Codebase](0005-run-document-work-in-separate-workers-same-codebase.md)
- [ADR-006: Use PostgreSQL Hybrid Search With pgvector And Full-Text Search](0006-use-postgresql-hybrid-search-with-pgvector-and-full-text.md)
