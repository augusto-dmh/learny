# RFC-001: Select The Technology Stack For Learny

- **Status**: Accepted by [ADR-004](../adr/0004-python-fastapi-react-nextjs-postgresql-stack.md)
- **Date**: 2026-06-27
- **Driver**: Augusto
- **Approvers**: Augusto
- **Contributors**: Codex
- **Impact**: HIGH

## Background

Learny is planned as a robust application that starts with book teaching and may expand into learning workflows and second-brain features. The system must support file ingestion, document processing, retrieval, cited answers, teaching sessions, user notes, evaluation, and eventually more generalized knowledge workflows.

The current research supports a hybrid architecture: canonical structured corpus, RAG as the default answering path, and long-context fallback for broad synthesis.

The technology stack is decided by [ADR-004](../adr/0004-python-fastapi-react-nextjs-postgresql-stack.md). This RFC records the options and trade-offs that led to that decision.

## Assumptions

| Assumption | Confidence | Invalidation Trigger |
|---|---:|---|
| The product should be usable by multiple people, not only as a local script. | High | User chooses a purely personal/local tool direction. |
| The first serious workload is document ingestion plus interactive book tutoring. | High | User pivots to a generic notes app before book tutoring is implemented. |
| The application should remain provider-independent where practical. | Medium | User chooses a fully managed provider-specific implementation for speed. |
| Augusto's existing Laravel/Vue/PostgreSQL experience matters for velocity. | High | User explicitly prioritizes learning a new stack over shipping the product. |

## Decision Criteria

| Criterion | Weight | Notes |
|---|---:|---|
| Product velocity for Augusto | 5 | Should fit existing Laravel/Vue/PostgreSQL strengths unless there is a strong reason not to. |
| Document/AI ecosystem fit | 5 | Must handle ingestion, RAG, embeddings, citations, and evaluation well. |
| Robustness for daily multi-user use | 5 | Auth, queues, observability, storage, testing, and deployment matter. |
| Provider portability | 4 | Avoid coupling the domain model to one LLM/vector provider. |
| Operational simplicity | 4 | Avoid unnecessary distributed complexity early. |
| Future second-brain expansion | 3 | Notes, highlights, graph-like links, memory, and collections should fit. |
| Cost control | 3 | Repeated daily usage should avoid expensive whole-book prompts by default. |
| Documentation freshness during implementation | 3 | Fast-moving framework and AI-provider APIs should be checked against current docs. |

## Options Considered

### Option A: Laravel + Inertia/Vue + PostgreSQL/pgvector + Queue Workers + Python Document Worker

Use Laravel as the main product application, Inertia/Vue for the UI, PostgreSQL as primary data store, pgvector for the first vector store, Redis/queue workers for async jobs, and a separate Python worker/service for document parsing and advanced RAG tooling where Python libraries are stronger.

### Option B: Python/FastAPI + React/Next.js + PostgreSQL/pgvector

Use Python for the whole backend so ingestion, RAG, and evaluation libraries live in the primary service. Use React/Next.js for the frontend.

### Option C: TypeScript/Next.js Full Stack + Managed Vector Store

Use a TypeScript-first stack with Next.js, server actions/API routes, hosted PostgreSQL, and a managed vector/search provider.

### Option D: Managed AI Platform First

Use OpenAI File Search, Anthropic document/citation capabilities, or a managed knowledge base as the main document system, with a thin product shell around it.

### Option E: Local-First Second-Brain Tool First

Start as a local Markdown/SQLite/desktop-first knowledge tool and later add hosted multi-user capabilities.

## Recommended Direction

Accepted direction: **Option B**, because Learny's hardest early problems are document ingestion, retrieval, evaluation, and AI orchestration. Keeping the backend in Python reduces cross-language friction for those capabilities while still allowing a polished React/Next.js frontend.

## Pros and Cons

### Option A: Laravel + Inertia/Vue + PostgreSQL/pgvector + Python Document Worker

Pros:

- Strong fit with Augusto's existing Laravel/Vue/PostgreSQL experience.
- Laravel provides mature auth, queues, storage, testing, policies, scheduling, and admin/product scaffolding.
- PostgreSQL can hold relational product data, canonical corpus metadata, and pgvector indexes early.
- Python worker can use best-in-class document and RAG libraries without forcing the whole app into Python.
- Clear domain boundary between product app and document intelligence pipeline.

Cons:

- Two runtime ecosystems.
- Need explicit contracts between Laravel and Python worker.
- More deployment pieces than a single-process prototype.

### Option B: Python/FastAPI + React/Next.js + PostgreSQL/pgvector

Pros:

- Best backend ecosystem fit for document parsing, RAG, evaluation, and ML tooling.
- Fewer cross-language boundaries for ingestion and retrieval.

Cons:

- Slower product velocity for Augusto compared with Laravel.
- More work to recreate product basics Laravel already gives.
- Frontend/backend integration likely becomes more custom.

### Option C: TypeScript/Next.js Full Stack + Managed Vector Store

Pros:

- One language across frontend and backend.
- Strong ecosystem for polished web apps.
- Easy managed deployment paths.

Cons:

- Python document tooling is still stronger.
- Long-running ingestion and job orchestration can become awkward if forced into web runtime patterns.
- Risk of coupling product logic to provider SDKs and hosted search behavior.

### Option D: Managed AI Platform First

Pros:

- Fastest prototype.
- Hosted citations/retrieval can reduce early infrastructure work.

Cons:

- Provider lock-in risk.
- Less control over parsing, chunking, metadata, evaluation, and retrieval strategy.
- Harder to become a broader learning/second-brain platform.

### Option E: Local-First Second-Brain Tool First

Pros:

- Strong fit for personal knowledge workflows.
- Could support offline/private use.

Cons:

- Does not match the stated desire for use by other people on a daily basis.
- Multi-user collaboration, auth, hosted files, and queues would come later.
- Book teaching robustness may get delayed by local-first concerns.

## Action Items

- [x] Configure Context7 MCP or equivalent docs tooling for implementation-time library documentation lookup.
- [x] Decide between Laravel-first and Python-first stack.
- [x] Decide Python document/RAG/evaluation library adoption strategy.
- [x] Decide initial PostgreSQL/pgvector vs dedicated vector/search store direction.
- [x] Decide OpenAI and Anthropic integration boundary for citations and fallback long-context mode.
- [x] Decide whether the first deploy target should be Docker Compose VPS, Laravel Cloud, Fly.io, Railway, Render, or AWS.
- [x] Convert final decision into ADR-004.
- [x] Create the first Technical Design Document after the stack ADR is accepted: [TDD-001](../tdd/0001-mvp-architecture.md).

## Outcome

Accepted by [ADR-004](../adr/0004-python-fastapi-react-nextjs-postgresql-stack.md): **Python/FastAPI + React/Next.js + PostgreSQL/pgvector**.

Project-local implementation skills should be created from official or first-party sources where practical, including official FastAPI, React, Next.js, PostgreSQL, pgvector, OpenAI, and Anthropic documentation.
