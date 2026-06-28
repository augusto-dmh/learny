# STATE — Project Memory

Persistent decision log, blockers, and handoff for tlc-spec-driven cycles.
Architecture decisions live in `docs/adr/` and `docs/tdd/`; this file references them, never duplicates them.

## Decisions Log

Accepted architecture (locked — sourced from ADRs/TDD, not re-decided here):

| ID | Decision | Source |
|---|---|---|
| AD-001 | Workflow model: TDD-001's 10-phase plan is the roadmap; tlc runs one cycle per slice; ADRs/TDD are locked constraints, not re-opened in Design. | this session |
| AD-002 | First cycle scope = scaffold + full identity (TDD-001 Implementation Plan Phases 1+2). | this session |
| AD-003 | Open questions #1/#2/#3 (lib, CSRF, object storage) resolved inside tlc Discuss → recorded as AD-006..AD-008 below. | this session |
| AD-004 | Stack: Python/FastAPI, React/Next.js, PostgreSQL+pgvector, Redis/Celery, S3-compatible storage. | ADR-004, ADR-006, ADR-014, ADR-013 |
| AD-005 | Backend-owned auth, HTTP-only cookies; thin same-origin Next.js proxy; FastAPI authoritative for authz. | ADR-012, ADR-015, ADR-017 |
| AD-006 | Argon2id hashing (pwdlib/argon2-cffi) + opaque server-side session tokens in PostgreSQL. | Discuss → context.md (TDD OQ #1) |
| AD-007 | SameSite=Lax+Secure+HttpOnly cookie + Origin check + session-bound (synchronizer) CSRF token. | Discuss → context.md (TDD OQ #2) |
| AD-008 | Self-hosted MinIO in Docker Compose for local and first VPS; swappable via storage port. | Discuss → context.md (TDD OQ #3) |

## Blockers

- None. AD-006/007/008 resolved.

## Handoff

- Cycle 1 `scaffold-and-identity` **Execute complete + Verifier PASS** (validation.md). 13 commits 07cc25d..15bf93f on `feat/scaffold-and-identity`. Backend 69 tests / frontend 19 tests green; ruff clean; full compose stack verified; 6/6 mutants killed.
- Gap-1 ✅ closed (commit 7acbb3e): `web` healthcheck added; all 6 services verified `(healthy)`.
- Gap-2 (informational, deferred): wire `AuthorizeOwnership` to an endpoint when first user-owned resource (sources, TDD Phase 3) lands.
- Pending: commit `.specs/` artifacts; open PR via `learny-finalize`. Test DB: `postgresql+psycopg://learny:learny@localhost:5432/learny`.

## Deviations (Cycle 1)

- SPEC_DEVIATION (additive, accepted): Phase B added a 7th domain port `TokenGenerator` so opaque/CSRF token minting stays out of the application layer and is deterministic in tests. Existing ports unchanged. Reflected in design intent; update design.md §3 ports list at finalize if desired.

## Preferences

- User prefers decisions surfaced one at a time with options + a recommendation.
