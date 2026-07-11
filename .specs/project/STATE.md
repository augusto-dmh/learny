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
| AD-019 | Cycle 5 `retrieval-indexes` (TDD Phase 6) defers the concrete cloud embedding provider/model: ship a Learny `EmbeddingPort` + a **deterministic, dependency-free local adapter** as the default; the production provider is its own follow-up ADR. Keeps retrieval provider-agnostic + testable without a network/secret, consistent with CLAUDE.md ("no provider default without an ADR") and ADR-0007. | Cycle 5 context.md (D-1) |
| AD-020 | Retrieval columns live on `corpus_chunks`: nullable `embedding vector(1536)` (cosine `vector_cosine_ops`, HNSW `m=16,ef_construction=64`) + `STORED` generated `search_vector tsvector` (section title `section_path->>-1` weighted `'A'` over `text` `'D'`, GIN). `pgvector>=0.3,<0.5` added; `vector` extension created in the migration. Dim `1536` is provider-neutral; a different-dim model later is a dim-change migration + re-embed (embeddings re-indexable, ADR-0001). | Cycle 5 context.md (D-2/D-3/D-4) |
| AD-021 | Embedding runs as an **embed+index step inside `run_ingestion`**, in its own committed transaction, after the corpus-build commit and before terminal success — keeping the provider call out of the corpus-write transaction; reuses the existing `IngestionStep` retry/terminal classification. No separate `embed.run` task this cycle. Re-ingestion re-embeds. | Cycle 5 context.md (D-5) |
| AD-022 | Retrieval = single-statement hybrid **RRF** query over `corpus_chunks` **scoped to one `source_id`**, two ranked CTEs (`Σ 1/(k+rank)`), semantic arm skips NULL embeddings, behind a `RetrievalPort`, projecting a frozen `Evidence` result (`chunk_id, source_id, section_path, anchor, page_span, snippet, score`). Tuning (`semantic_limit`, `lexical_limit`, `rrf_k=60`, `top_k`, `max_top_k`, `hnsw_ef_search`, `embedding_dim`) in `LEARNY_` settings. No reranker (ADR-0006). | Cycle 5 context.md (D-6) |
| AD-023 | Cycle 5 vertical slice = backend capability **+ a thin owner-scoped `POST /api/sources/{id}/retrieve`** returning evidence; **no frontend** this cycle. Raw hybrid results are not an MVP user surface (Phase 7 cited Q&A / Phase 8 teaching are); empty match → **200 empty list** (the Phase-7 "not found in source" hook); missing/non-owned → 404. Partial, deliberate departure from AD-010's full-slice cadence — flagged at the merge gate. | Cycle 5 context.md (D-7/D-8) |

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

- Cycles 1–4 (`scaffold-and-identity`, `source-storage`, `worker-foundation`, `epub-corpus-pipeline`) all **merged to `main`** (PRs #4, #7/#8, #9, #10). Each shipped with Verifier PASS; details in their `.specs/features/*/validation.md`. Corpus schema/replace semantics: AD-017/AD-018.
- **Cycle 5 `retrieval-indexes` (TDD Phase 6) — Execute complete + Verifier PASS.** Not yet merged; branch `feat/retrieval-indexes`, 10 commits `1bb8e24..0fc2d03` (schema+migration 0005, retrieval/embedding settings + guarded register_vector, ports+evidence entities, deterministic embedding adapter, embedding-index repo, EmbedCorpus service, embed step + task wiring, hybrid RRF retrieval repo, RetrieveEvidence service, retrieve endpoint). Backend **314 passed**; ruff clean. Verifier: **22/22 ACs matched spec outcome, all edge cases covered, 6/6 sensor mutants killed, 0 gaps** (`validation.md`; run inline via tlc standalone fallback after the Verifier sub-agent hit an account session-limit). Executed via one sub-agent worker per phase (A–E). Added the hybrid retrieval layer: nullable `embedding vector(1536)` + generated `search_vector tsvector` on `corpus_chunks` (migration 0005), `EmbeddingPort` + deterministic local adapter (cloud provider deferred, AD-019), embed+index step in `run_ingestion` (AD-021), hybrid RRF `RetrievalPort` query (AD-022), owner-scoped `POST /api/sources/{id}/retrieve`, no frontend (AD-023). Decisions AD-019..AD-023; spec `RET-01..22`. New backend dep: `pgvector` (0.4.2) + numpy. New settings: `LEARNY_EMBEDDING_DIM/EMBEDDING_MODEL/EMBEDDING_BATCH_SIZE/RETRIEVAL_SEMANTIC_LIMIT/RETRIEVAL_LEXICAL_LIMIT/RETRIEVAL_RRF_K/RETRIEVAL_TOP_K/RETRIEVAL_MAX_TOP_K/HNSW_EF_SEARCH`. Next action: `learny-finalize` for the PR — planning artifacts (`.specs/features/retrieval-indexes/*`, this STATE.md, ROADMAP.md row for Phase 6) still need to land in a commit. NOTE for the merge gate: AD-023 (endpoint but no frontend) is a deliberate partial departure from AD-010's full-slice cadence — surface it to the user.
- Test DB note: retrieval integration tests need the `vector` extension present in `learny_test`; the `pgvector/pgvector:pg16` image already ships it, migration `CREATE EXTENSION IF NOT EXISTS vector` creates it.
- Test DB: integration tests read `LEARNY_TEST_DATABASE_URL` (see `backend/tests/conftest.py`; tests using it skip if unset) — set to `postgresql+psycopg://learny:learny@localhost:5432/learny_test` (a dedicated `learny_test` database, created during Cycle 2 Phase 3; distinct from the app's `learny` DB). MinIO local: `http://localhost:9000` (learny/learny-dev-secret). `db`/`minio` containers started via `docker.exe compose up -d db minio` — the bare `docker` CLI is unavailable in this WSL distro; use `docker.exe compose ...`. `uv` is not on the default shell PATH — it's at `/home/augusto/myenv/bin/uv`.

## Deviations (Cycle 1)

- SPEC_DEVIATION (additive, accepted): Phase B added a 7th domain port `TokenGenerator` so opaque/CSRF token minting stays out of the application layer and is deterministic in tests. Existing ports unchanged. Reflected in design intent; update design.md §3 ports list at finalize if desired.

## Preferences

- User prefers decisions surfaced one at a time with options + a recommendation.
