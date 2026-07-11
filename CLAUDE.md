# Learny Project Context

Learny is a learning application that starts as robust book teaching and may expand into broader learning and second-brain workflows. The first product direction is: ingest books, preserve structure, support cited question answering, and teach specific passages in context.

## Current Status

- The repository currently contains research, decision, and design artifacts only. There is no runtime application scaffold yet.
- The initial stack is accepted in ADR-004: Python/FastAPI backend, React/Next.js frontend, PostgreSQL primary storage, and pgvector as the initial vector storage/search capability.
- Do not assume auth library/session store, concrete object-storage provider, concrete provider/model defaults, or dedicated vector database choices until follow-up ADRs or technical designs accept them.

## Durable Decisions

- Use ADRs for accepted architectural decisions.
- Use RFCs for open proposals and trade-off analysis.
- Use `docs/research/YYYY-MM-DD/` for durable research outputs and evidence archives.
- Do not create a separate persistent `STATE.md` just to duplicate ADR/RFC content.
- Do not create `.specs/` upfront. Let `tlc-spec-driven` create its own structure when it is intentionally invoked for a feature cycle.

## Established Direction

- Book intelligence should use a hybrid architecture: structured canonical corpus first, RAG as the default answer path, and long-context fallback for broad synthesis.
- The first MVP scope is document ingestion, cited Q&A, and structured teaching sessions. Quizzes, notes, memory, and second-brain workflows are deferred.
- The MVP should support email/password user accounts from the start, with user ownership and authorization for sources, corpus records, and teaching sessions.
- Browser authentication should be backend-owned by FastAPI and use secure HTTP-only cookies, not browser-accessible bearer token storage.
- Browser-facing API calls should go through a thin same-origin Next.js route/proxy boundary to FastAPI. FastAPI remains authoritative for auth, authorization, product logic, and user-owned resources.
- Initial ingestion should support EPUB first. PDF and other formats are deferred until the EPUB-based corpus and tutor path are working.
- EPUB parsing uses ebooklib behind a Learny-owned ingestion port (accepted in the EPUB corpus pipeline design); Docling remains a candidate second adapter when PDF support arrives.
- Uploaded source files should be stored in S3-compatible object storage from the start; PostgreSQL stores metadata, ownership, ingestion status, corpus links, and object keys.
- Canonical document processing should preserve headings, sections, page/location anchors, metadata, and citations instead of treating the book as flat chunks only.
- Citations, evaluation, and traceability are core requirements, not late polish.
- MVP evaluation should use golden fixtures for ingestion, retrieval, and citations before adding Ragas or an evaluation dashboard.
- Long-running document ingestion, corpus generation, embedding, indexing, and evaluation work should run in separate worker processes from the same codebase, not inside HTTP request handlers.
- Worker queues should use Redis plus Celery. PostgreSQL remains the source of truth for durable job, ingestion, corpus, and progress state.
- Initial retrieval should use PostgreSQL hybrid search: pgvector for semantic search plus PostgreSQL full-text search for lexical/exact lookup.
- The first production-like deployment target should be Docker Compose on a VPS, with local Docker Compose kept aligned where practical.
- Prefer provider-independent domain boundaries where practical; provider SDKs should sit behind ports/adapters once implementation begins.
- AI provider integration should use Learny-owned ports with thin provider adapters; OpenAI, Anthropic, model names, SDK objects, and provider citation formats should not leak into core domain logic.
- AI/RAG orchestration should be Learny-owned. Specialized libraries such as Docling or Ragas may be used at edges when they solve concrete parsing or evaluation problems; broad frameworks such as LlamaIndex or LangGraph should not become the core architecture without a follow-up decision.
- Stack-specific implementation guidance and project-local skills should come from official or first-party framework/provider sources where practical.

## Workflow

- Use project-local skills from `.claude/skills` where available.
- Use `tlc-spec-driven` for feature planning or implementation cycles when work is large enough to need specs/tasks.
- Use ADR/RFC/TDD skills for architecture and design artifacts.
- Use `learny-finalize` for commit metadata, PR body generation, and publishing conventions.
- Keep PRs small and reviewable; load `learny-finalize` for the exact publishing convention.

## Progressive Documentation Loading

Only read documents relevant to the current task. Do not load all project documentation at once.

- General project orientation: read `CLAUDE.md`.
- Skill and workflow questions: read `SKILLS.md`.
- Accepted architectural decisions: read the relevant file under `docs/adr/`.
- Open proposals and trade-offs: read the relevant file under `docs/rfc/`.
- Research recovery: avoid reading archived research by default. Read `docs/research/YYYY-MM-DD/` only when the user explicitly asks to recover prior research evidence.
- New research output: write durable research results under `docs/research/YYYY-MM-DD/<topic>.md`; materialize actionable conclusions into ADRs, RFCs, or feature artifacts.
- Feature planning or implementation: invoke `tlc-spec-driven` and let it load or create its own files as needed.

## Current Constraints

- Stack-specific application code is now allowed only when it follows ADR-004 and an implementation plan or feature cycle.
- Do not add unofficial third-party best-practice skills as authoritative project guidance unless explicitly reviewed and accepted.
- Do not install global-only skills when the intent is to preserve project-local workflow.
