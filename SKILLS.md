# Learny Skills And Workflow

Learny uses skills as project-local playbooks for repeatable research, design, implementation, and publishing work. Shared reusable skills should come from the Tech Leads Club source catalog when available.

## Skill Layers

**Research and architecture**

- `domain-analysis` maps business domains and bounded contexts.
- `modular-design-principles` reviews boundaries, contracts, state ownership, and failure isolation.

**Decision and design artifacts**

- `create-rfc` documents open proposals and trade-offs.
- `create-adr` records accepted architectural decisions.
- `create-technical-design-doc` creates implementation-ready technical designs when a decision is ready to build.

**Workflow**

- `tlc-spec-driven` drives feature cycles with Specify, Design, Tasks, and Execute. Use it when a feature needs traceable requirements or task decomposition. Let it create `.specs/` only when invoked.
- `skill-architect` creates future repository-specific skills after discovery and architecture.
- `learny-finalize` applies Learny's branch, commit, verification, and PR conventions.

## Workflow Shape

```text
RESEARCH -> RFC / ADR -> TDD or tlc-spec-driven feature cycle -> IMPLEMENT -> FINALIZE
```

- Research docs hold evidence and references.
- RFCs hold undecided proposals.
- ADRs hold accepted decisions.
- TDDs and `tlc-spec-driven` artifacts hold implementation plans.
- Publishing conventions live in `learny-finalize`.

## Stack-Specific Skills

The stack ADR is accepted in `docs/adr/0004-python-fastapi-react-nextjs-postgresql-stack.md`.

Stack-specific skills may now be added for Python, FastAPI, React, Next.js, PostgreSQL, pgvector, and selected AI/provider tooling. These skills should be project-local and should be based on official or first-party framework/provider documentation where practical.

Do not treat third-party blog posts, unofficial best-practice repositories, or community opinion guides as authoritative project skills unless they are explicitly reviewed and accepted.

Add review, manual QA, and triage skills only after Learny has app behavior and PRs that need validation.
