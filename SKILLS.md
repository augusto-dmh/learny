# Learny Skills And Workflow

Learny uses skills as project-local playbooks for repeatable research, design, implementation, and publishing work. Shared reusable skills should come from the Tech Leads Club source catalog when available.

## Skill Layers

**Research and architecture**

- `modular-design-principles` reviews boundaries, contracts, state ownership, and failure isolation (the `pr-review` architecture lane loads it).

**Decision and design artifacts**

- `create-rfc` documents open proposals and trade-offs.
- `create-adr` records accepted architectural decisions.

**Workflow**

- `tlc-spec-lean` (profile `standard`) plans and builds feature cycles: one reviewed plan with its one-way doors, proof-backed checks, the build, and an independent Verifier. It is a user-level skill today; the next harness cycle vendors it into the repo.
- `pr-review` runs a multi-agent pull-request review (security, requirements, tests, architecture, regression, performance) and posts inline + summary comments via `gh`. Use only when explicitly asked to review a PR.
- `learny-finalize` applies Learny's branch, commit, verification, and PR conventions.
- `learny-ship-cycle` orchestrates one full roadmap PR end-to-end: next cycle → `tlc-spec-lean` plan, door gate, checks, build, Verifier → `learny-finalize` → fresh-context `pr-review` → finding triage (persisted to `review-triage.md`) → fixes → comment cleanup → user-gated merge.

## Workflow Shape

```text
RESEARCH -> RFC / ADR -> TDD or tlc-spec-lean feature cycle -> IMPLEMENT -> FINALIZE
```

- Research docs hold evidence and references.
- RFCs hold undecided proposals.
- ADRs hold accepted decisions.
- TDDs and `tlc-spec-lean` artifacts (`plan.md`, `checks.md`, `verification.md`) hold implementation plans.
- Publishing conventions live in `learny-finalize`.

## Stack-Specific Skills

The stack ADR is accepted in `docs/adr/0004-python-fastapi-react-nextjs-postgresql-stack.md`.
Stack-specific skills are project-local under `.claude/skills` and must come from
official or first-party sources, or be Learny-authored from official docs + ADRs.
See `.claude/skills/README.md` for provenance, `skills-lock.json` for pinned
sources, and `docs/research/2026-07-04/official-agent-skills-for-stack.md` for the
survey that selected them.

**Vendored official skills** (framework/vendor-authored, installed via the Vercel
`skills` CLI):

- `fastapi` — FastAPI team.
- `redis-core`, `redis-connections` — Redis Inc.
- `ruff`, `uv` — Astral.
- `vercel-react-best-practices`, `vercel-composition-patterns`, `web-design-guidelines` — Vercel Engineering.

**Learny-authored gap-fillers** (no official skill exists; encode ADRs + official docs):

- `epub-ingestion` — structure-preserving EPUB parsing (ADR-0002, ADR-0011, ADR-0009).
- `celery-workers` — workers outside HTTP handlers, Postgres as state source (ADR-0005, ADR-0014).
- `pgvector-hybrid-search` — pgvector + PostgreSQL native full-text search, RRF fusion (ADR-0006, ADR-0007).

Do not treat third-party blog posts, unofficial best-practice repositories, or community opinion guides as authoritative project skills unless they are explicitly reviewed and accepted.

Add review, manual QA, and triage skills only after Learny has app behavior and PRs that need validation.
