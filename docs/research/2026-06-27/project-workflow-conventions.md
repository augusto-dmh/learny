# Workflow Research: Learny Project Workflow

## What Was Established

- Shared workflow skills should come from the latest Tech Leads Club skill catalog when available.
- Learny should keep durable decisions in ADRs and RFCs.
- Learny should keep project context in `CLAUDE.md`.
- Learny should route publishing tasks to `learny-finalize`.

## Project Workflow

- Research docs hold evidence, references, and exploratory trade-offs.
- RFCs hold undecided proposals and comparison criteria.
- ADRs hold accepted technical decisions.
- Technical design docs or `tlc-spec-driven` feature artifacts hold implementation-ready plans.
- `learny-finalize` handles branch naming, commit metadata, PR body rendering, and publishing conventions.

## Documentation Boundaries

- Do not create `.specs/` upfront. Let `tlc-spec-driven` create its own files only when a feature cycle requires them.
- Do not create a separate persistent state document just to duplicate ADR/RFC decisions.
- Do not create a standalone stack snapshot before the stack is accepted. Keep current stack context in `CLAUDE.md` and the stack decision in RFC/ADR docs.
- Do not add stack-specific skills until the stack ADR is accepted.

## Current Recommendation

Keep project context in `CLAUDE.md`, keep durable decisions in `docs/rfc` and `docs/adr`, install shared skills from Tech Leads Club source, and use a Learny-specific finalize skill for GitHub workflow consistency.

Suggested next PRs:

1. `chore(workflow): add project workflow conventions`
2. `docs(stack): decide initial application stack`
3. `docs(design): specify book ingestion foundation`
4. First application scaffold PR after the stack ADR is accepted.
