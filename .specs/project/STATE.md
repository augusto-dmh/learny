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
| AD-009 | Source upload transport = direct multipart through FastAPI (bytes stream through the API to storage). Presigned direct-to-storage upload deferred. | ADR-018 / Cycle 2 context.md (D-1) |
| AD-010 | Cycles ship as full vertical slices (backend + frontend) per feature, matching Cycle 1 cadence. | Cycle 2 context.md (D-2) |
| AD-011 | S3-compatible storage adapter uses boto3 (S3 API) behind `StoragePort`, keeping MinIO/S3/R2 swappable. | Cycle 2 context.md (D-3) |
| AD-012 | Cycle 3 `worker-foundation` (TDD Phase 4) ships the ingestion job engine only — Celery task drives the full `queued→running→succeeded/failed` lifecycle with a **stub body** (`# TODO(Phase 5): parse EPUB`, no parsing). Real parsing stays in Phase 5; the two are separate PRs. | Cycle 3 Specify (user: "Just 4") |
| AD-013 | Ingestion trigger = explicit `POST /api/sources/{id}/ingestion` (start/restart) only; Cycle 2 upload flow unchanged; `source.status` stays `uploaded` until started. No auto-enqueue on upload. | Cycle 3 Specify |
| AD-014 | Durable job state = `ingestion_jobs` + append-only `ingestion_events` (both this cycle); ownership reachable only via parent `source`; queue messages carry ids only (`source_id`, `ingestion_job_id`). `source.status` is a projection: `uploaded→processing→ready/failed`. | Cycle 3 Specify |
| AD-015 | Cycle 3 includes a minimal frontend slice (AD-010): ingestion status badge + "Start ingestion" control on the existing sources screen via the same-origin proxy. No polling/auto-refresh this cycle. | Cycle 3 Specify |
| AD-016 | Worker-triggering commands commit durable job state first, then enqueue **after commit** through a Learny `IngestionEnqueuer` port, compensating to terminal `failed` if enqueue fails; Celery/`apply_async` never enters application or domain code. Future worker-triggered features (embedding, indexing, evaluation) follow this. Active-job uniqueness is a partial unique index; the Phase-5 parse seam is an injectable `IngestionStep` port (no-op stub this cycle). | Cycle 3 Design |

## Blockers

- None. AD-006/007/008 resolved.

## Known Gaps (non-blocking)

- `backend/pyproject.toml` pins `ruff>=0.9,<1`; the resolved `ruff` (0.15.20) formats
  10 Cycle-1 files differently than whatever ~0.9.x originally formatted them
  (`uv run ruff format --check .` fails on those 10, confirmed pre-existing on
  `main` prior to Cycle 2). `ruff check .` (lint) and all test gates are
  unaffected. Deliberately not fixed during Cycle 2 (source-storage) to avoid
  scope creep — user chose to defer. Follow-up: pin ruff to an exact version or
  do one dedicated repo-wide reformat commit.

## Handoff

- Cycle 1 `scaffold-and-identity` **Execute complete + Verifier PASS** (validation.md). Merged to `main` (PR #4). Backend 69 tests / frontend 19 tests green; ruff clean; full compose stack verified; 6/6 mutants killed.
- Gap-1 ✅ closed: `web` healthcheck added; all 6 services verified `(healthy)`.
- **Cycle 2 `source-storage` (TDD Phase 3) — Execute complete + Verifier PASS + 2 fix-tasks landed.** Not yet merged; branch `feat/source-storage` (10 commits: 4b641bd, 566385e, 52a1536, 1c8b69f, 8aead7e, 2ad5cb0, 1a109c6, d7223b8, 2a1f890 fix-tasks, + planning-artifact commit still pending at finalize). Backend 123 passed / frontend 32 passed, both ruff/tsc clean. Verifier: 18/18 ACs, 2/3 sensor mutations killed live (1 surviving mutant + 1 uncovered edge case both closed by the follow-up fix commit `2a1f890` — re-verified via manual mutation re-run, not a second full Verifier pass). `validation.md` + spec.md traceability (SRC-01..12, all ✅ Verified) updated. Gap-2 ✅ closed: `GetSource`/`ListSources` wire `AuthorizeOwnership`, non-owner/missing → 404. T7 shipped with an accepted `SPEC_DEVIATION` (no new proxy routes — reused Cycle 1's generic catch-all proxy instead of design.md's dedicated route files; see tasks.md T7). Next action: `learny-finalize` for the PR (planning artifacts `.specs/features/source-storage/*`, `docs/adr/0018-*`, this STATE.md still need to land in a commit too).
- **Cycle 3 `worker-foundation` (TDD Phase 4) — Execute complete + Verifier PASS.** Not yet merged; branch `feat/worker-foundation`, 8 commits `ebff6f6..9e3060d` (ef0d59f domain+ports, 9f4d4b3 schema+migration 0003, 8003b5a app services, 812901c repositories, bef1001 celery worker, 0e59125 web endpoints, be88bda FE client, 9e3060d FE screen). Backend 183 passed / frontend 39 passed; ruff clean on new files. Verifier: **12/12 ACs Verified, 8/8 sensor mutants killed, 0 gaps** (`validation.md`). Two accepted deviations: (a) `StartIngestion` uses an app-level active-job pre-check with the DB partial-unique index as the race backstop + a web-boundary `IntegrityError`→409 map — ING-03 guarded at both layers; (b) frontend `SPEC_DEVIATION` — `SourcesPanel` keeps the row `uploaded`/button-disabled during the request and flips to `processing` only on success (an optimistic pre-await flip would unmount the button), end states match story AC3/AC4. Ingestion task body is a **stub** (`# TODO(Phase 5): parse EPUB`) per AD-012. Next action: `learny-finalize` for the PR (planning artifacts `.specs/features/worker-foundation/*` + `.specs/project/ROADMAP.md`/`STATE.md` edits still need to land in a commit).
- Test DB: integration tests read `LEARNY_TEST_DATABASE_URL` (see `backend/tests/conftest.py`; tests using it skip if unset) — set to `postgresql+psycopg://learny:learny@localhost:5432/learny_test` (a dedicated `learny_test` database, created during Cycle 2 Phase 3; distinct from the app's `learny` DB). MinIO local: `http://localhost:9000` (learny/learny-dev-secret). `db`/`minio` containers started via `docker.exe compose up -d db minio` — the bare `docker` CLI is unavailable in this WSL distro; use `docker.exe compose ...`. `uv` is not on the default shell PATH — it's at `/home/augusto/myenv/bin/uv`.

## Deviations (Cycle 1)

- SPEC_DEVIATION (additive, accepted): Phase B added a 7th domain port `TokenGenerator` so opaque/CSRF token minting stays out of the application layer and is deterministic in tests. Existing ports unchanged. Reflected in design intent; update design.md §3 ports list at finalize if desired.

## Preferences

- User prefers decisions surfaced one at a time with options + a recommendation.
