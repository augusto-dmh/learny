# Learny Project Context

Learny is a learning application that starts as robust book teaching and may expand into broader learning and second-brain workflows. The first product direction is: ingest books, preserve structure, support cited question answering, and teach specific passages in context.

## Current Status

- The repository currently contains research and decision artifacts only. There is no runtime application scaffold yet.
- The stack is not accepted yet. RFC-001 currently compares Laravel/Inertia/Vue/PostgreSQL with Python document workers against Python-first, TypeScript-first, managed AI platform, and local-first alternatives.
- Do not assume Laravel, Vue, Python, LangGraph, OpenAI, Anthropic, or any vector database is final until an ADR accepts the stack.

## Durable Decisions

- Use ADRs for accepted architectural decisions.
- Use RFCs for open proposals and trade-off analysis.
- Use `docs/research/YYYY-MM-DD/` for durable research outputs and evidence archives.
- Do not create a separate persistent `STATE.md` just to duplicate ADR/RFC content.
- Do not create `.specs/` upfront. Let `tlc-spec-driven` create its own structure when it is intentionally invoked for a feature cycle.

## Established Direction

- Book intelligence should use a hybrid architecture: structured canonical corpus first, RAG as the default answer path, and long-context fallback for broad synthesis.
- Canonical document processing should preserve headings, sections, page/location anchors, metadata, and citations instead of treating the book as flat chunks only.
- Citations, evaluation, and traceability are core requirements, not late polish.
- Prefer provider-independent domain boundaries where practical; provider SDKs should sit behind ports/adapters once implementation begins.

## Workflow

- Use project-local skills from `.codex/skills` where available.
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

- Do not add stack-specific application code or skills until Learny's stack is accepted.
- Do not install global-only skills when the intent is to preserve project-local workflow.
