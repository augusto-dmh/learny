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
| AD-017 | EPUB parsing uses **ebooklib** behind a Learny `EpubParserPort` (edge adapter in `infrastructure/ingestion/`); Docling deferred as a possible second adapter when PDF arrives. Resolves CLAUDE.md's open parsing-library choice. | Cycle 4 Discuss (D-1) |
| AD-018 | Canonical corpus schema: `corpus_documents` (UNIQUE `source_id`) → `corpus_sections` (TOC-derived `section_path`, `anchor`, derived `markdown`) → `corpus_blocks` (preserved HTML) + `corpus_chunks` (structure-first, ≤ `LEARNY_CHUNK_MAX_CHARS`, nullable `page_span`). Ownership via parent `source` only. Re-ingestion = atomic replace (delete+cascade+insert) inside the single step transaction; no corpus versioning without a future ADR. | Cycle 4 Specify/Design (D-3/D-4) |

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

- Cycles 1–3 (`scaffold-and-identity`, `source-storage`, `worker-foundation`) all **merged to `main`** (PRs #4, #7/#8, #9). Each shipped with Verifier PASS; details in their `.specs/features/*/validation.md`.
- **Cycle 4 `epub-corpus-pipeline` (TDD Phase 5) — Execute complete + Verifier PASS.** Not yet merged; branch `feat/epub-corpus-pipeline`, 13 commits `05df554..a4dacb7` (domain+ports, chunking, schema+migration 0004, corpus repository, EPUB fixtures, ebooklib parser, markdown converter, BuildCorpus service, ingestion step+worker wiring, ReadSourceStructure, structure endpoint, FE client, FE structure view). Backend **263 passed** / frontend **48 passed**; ruff/tsc clean. Verifier: **14/14 ACs Verified, all edge cases covered, 6/6 sensor mutants killed, 0 gaps, 0 spec-precision gaps** (`validation.md`). Executed via one sub-agent worker per phase (A–F). No deviations. New backend deps: `ebooklib`, `beautifulsoup4`. New setting: `LEARNY_CHUNK_MAX_CHARS` (default 2000). Parsing-library choice resolved: ebooklib (AD-017); corpus schema/replace semantics: AD-018. Next action: `learny-finalize` for the PR — planning artifacts (`.specs/features/epub-corpus-pipeline/*`, this STATE.md, ROADMAP.md row update for Phases 4–5) still need to land in a commit; CLAUDE.md's "do not assume parsing library" line can also be updated to cite the accepted choice.
- Test DB: integration tests read `LEARNY_TEST_DATABASE_URL` (see `backend/tests/conftest.py`; tests using it skip if unset) — set to `postgresql+psycopg://learny:learny@localhost:5432/learny_test` (a dedicated `learny_test` database, created during Cycle 2 Phase 3; distinct from the app's `learny` DB). MinIO local: `http://localhost:9000` (learny/learny-dev-secret). `db`/`minio` containers started via `docker.exe compose up -d db minio` — the bare `docker` CLI is unavailable in this WSL distro; use `docker.exe compose ...`. `uv` is not on the default shell PATH — it's at `/home/augusto/myenv/bin/uv`.

## Deviations (Cycle 1)

- SPEC_DEVIATION (additive, accepted): Phase B added a 7th domain port `TokenGenerator` so opaque/CSRF token minting stays out of the application layer and is deterministic in tests. Existing ports unchanged. Reflected in design intent; update design.md §3 ports list at finalize if desired.

## Preferences

- User prefers decisions surfaced one at a time with options + a recommendation.
