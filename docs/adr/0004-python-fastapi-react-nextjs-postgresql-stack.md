# ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, stack, python, fastapi, react, nextjs, postgresql, ai

## Context and Problem Statement

Learny needs a production-oriented stack for a multi-user learning application that starts with robust book teaching and can later expand into broader learning and second-brain workflows.

The accepted product architecture requires document ingestion, structured corpus storage, retrieval, cited answers, teaching sessions, notes, evaluation, and provider-independent AI boundaries. The stack decision must support both product delivery and serious document intelligence work.

## Decision Drivers

- Strong fit for document parsing, RAG, evaluation, and AI orchestration.
- Ability to build a multi-user web application with explicit API contracts.
- Durable relational storage for users, sources, corpus metadata, sessions, notes, and evaluations.
- Provider-independent boundaries for LLMs, embeddings, vector stores, and retrieval implementation.
- Documentation and agent guidance must come from official or first-party sources where practical.

## Considered Options

- Laravel + Inertia/Vue + PostgreSQL/pgvector + queue workers + Python document worker.
- Python/FastAPI + React/Next.js + PostgreSQL/pgvector.
- TypeScript/Next.js full stack + managed vector store.
- Managed AI platform first.
- Local-first second-brain tool first.

## Decision Outcome

Chosen option: **Python/FastAPI + React/Next.js + PostgreSQL/pgvector**, because Learny's hardest early problems are document ingestion, retrieval, evaluation, and AI orchestration. Keeping the backend in Python reduces cross-language friction for those capabilities while still allowing a polished React/Next.js frontend.

The initial stack direction is:

1. Use Python and FastAPI for the backend API and application services.
2. Use React and Next.js for the frontend.
3. Use PostgreSQL as the primary system of record.
4. Use pgvector as the initial vector storage/search capability unless later scale or retrieval requirements justify a dedicated vector store.
5. Keep AI providers, embedding providers, retrievers, and vector stores behind explicit application boundaries.
6. Build project-local AI/code-assistance skills only from official or first-party framework and provider sources where practical.

### Positive Consequences

- The primary backend language matches the strongest ecosystem for document parsing, RAG, evaluation, and ML/AI tooling.
- Ingestion, retrieval, and evaluation can use Python-native libraries without a cross-runtime worker boundary at the beginning.
- FastAPI encourages explicit API contracts and type-driven request/response models.
- React/Next.js provides a strong frontend path for a polished learning application.
- PostgreSQL/pgvector keeps initial product data and vector data operationally simple.

### Negative Consequences

- Learny will not benefit from Laravel's built-in product scaffolding for auth, policies, queues, storage, and testing.
- More product infrastructure decisions must be made explicitly for authentication, authorization, background jobs, file storage, and application testing.
- Frontend/backend integration will require explicit API design instead of an Inertia-style server-driven monolith.
- The project needs discipline to avoid letting AI framework details leak into core product logic.

## Official-Source Skills Policy

Learny should use project-local skills to guide implementation, but stack-specific skills must be based on official or first-party sources where practical. Examples include official FastAPI, React, Next.js, PostgreSQL, pgvector, OpenAI, and Anthropic documentation.

Third-party blog posts, unofficial best-practice repositories, and community opinion guides may be useful as research inputs, but they should not become authoritative project skills unless explicitly reviewed and accepted.

This mirrors the desired quality bar of framework-backed guidance such as official framework documentation, official tooling documentation, and first-party AI provider documentation.

## Pros and Cons of the Options

### Python/FastAPI + React/Next.js + PostgreSQL/pgvector ✅ Chosen

- ✅ Best fit for document parsing, RAG, evaluation, and AI tooling.
- ✅ Avoids an early PHP/Python worker split.
- ✅ Supports explicit API boundaries between frontend, backend, and AI/provider adapters.
- ❌ Requires explicit product infrastructure choices that Laravel would otherwise provide.
- ❌ Requires more care around frontend/backend contracts.

### Laravel + Inertia/Vue + PostgreSQL/pgvector + Python document worker

- ✅ Strong product scaffolding and high velocity for a Laravel-experienced developer.
- ✅ Mature auth, queues, storage, testing, policies, and scheduling.
- ❌ Introduces two runtimes early.
- ❌ Requires a Laravel/Python contract for the hardest document intelligence work.

### TypeScript/Next.js full stack + managed vector store

- ✅ One language across frontend and backend.
- ✅ Strong frontend ecosystem and managed deployment options.
- ❌ Python document tooling remains stronger.
- ❌ Long-running ingestion and evaluation workflows can become awkward in web-runtime patterns.

### Managed AI platform first

- ✅ Fastest prototype path.
- ❌ Higher provider lock-in risk.
- ❌ Less control over parsing, chunking, metadata, evaluation, and retrieval behavior.

### Local-first second-brain tool first

- ✅ Strong fit for personal knowledge workflows.
- ❌ Does not match the current multi-user hosted product direction.
- ❌ Delays robust book teaching infrastructure.

## References

- [RFC-001: Select The Technology Stack For Learny](../rfc/0001-technology-stack-selection.md)
- [ADR-001: Use Hybrid Structured Corpus, RAG, And Long-Context Fallback](0001-hybrid-book-intelligence-architecture.md)
- [ADR-002: Keep A Rich Canonical Document Format And Derive Markdown](0002-canonical-document-format.md)
- [ADR-003: Treat Citations And Evaluation As Core Product Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- FastAPI official documentation via Context7: `/fastapi/fastapi`
- React official documentation via Context7: `/reactjs/react.dev`
- Next.js official documentation via Context7: `/vercel/next.js`
- pgvector official documentation via Context7: `/pgvector/pgvector`
