# Retrieval Indexes Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/retrieval-indexes/design.md`
**Status**: Done — Execute complete + Verifier PASS (`validation.md`)

**Progress**: Phase A done — T1 `1bb8e24`, T2 `3215bf9` (271 passed). Phase B done — T3 `870e896`, T4 `02ada9b` (278 passed). Phase C done — T5 `b05b234`, T6 `7cd6464`, T7 `1055da7` (293 passed). Phase D done — T8 `4ff697a`, T9 `c19b391` (302 passed). Phase E done — T10 `0fc2d03` (314 passed). **All 10 tasks complete — Verifier next.**

---

## Test Coverage Matrix

> Generated from codebase + spec. Guidelines found: `CLAUDE.md` (progressive docs, no coverage %), `backend/pyproject.toml` (`[tool.pytest]`, `[tool.ruff]`), existing `backend/tests/*` (pytest, co-located by layer). No coverage-% gate → strong defaults applied.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain entities / ports (`domain/`) | none | Build gate only (frozen dataclasses / Protocols) | — | build gate |
| Application service (`application/retrieval.py`) | unit | All branches; 1:1 to spec ACs; all listed edge cases (via fakes) | `backend/tests/test_application_*.py` | Quick |
| Embedding adapter (`infrastructure/embeddings/`) | unit | Determinism, dim, batch order, empty-text edge | `backend/tests/test_embeddings_local.py` | Quick |
| Repository / retrieval SQL (`infrastructure/db/`) | integration | Key query paths + edge (NULL-embedding degrade, empty result, source scoping) | `backend/tests/test_repositories.py`, `backend/tests/test_retrieval.py` | Full |
| Migration (`migrations/versions/`) | integration | Columns/indexes/extension exist; `search_vector` populated; downgrade clean | `backend/tests/test_migrations.py` | Full |
| Worker task / step (`worker/`, `infrastructure/worker/`) | unit+integration | Embeddings populated post-run; retry/terminal classification; re-embed on re-ingest | `backend/tests/test_worker_tasks.py`, `backend/tests/test_ingestion_step.py` | Full |
| Web router (`infrastructure/web/retrieval.py`) | integration (e2e via TestClient) | Every route path: 200 happy + 422 + 404 + auth/CSRF + empty-200 | `backend/tests/test_web_retrieval.py` | Full |
| Config / engine (`core/config.py`, `db/engine.py`) | none | Build gate only | — | build gate |

## Parallelism Assessment

> Generated from codebase — the suite has no `pytest-xdist` config (`addopts = "-ra"`); integration tests share a session-scoped engine with per-test transaction rollback.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| Unit (fakes, pure) | Yes | No shared state; `tests/fakes.py` in-memory doubles | `test_application_ingestion.py`, `test_application_chunking.py` |
| Integration (DB) | No | Session-scoped `db_engine` + per-test `db_conn` txn rollback (shared engine) | `tests/conftest.py` `db_engine`/`db_conn` |
| Web (TestClient) | No | Shared engine + dependency-overridden `get_db_connection` on one txn | `tests/conftest.py` `auth_client` |

Suite runs **sequentially** in practice; `[P]` below is order-freedom within a phase, not a spawn directive.

## Gate Check Commands

> `uv` is at `/home/augusto/myenv/bin/uv`. Integration/web/migration tests need `LEARNY_TEST_DATABASE_URL` (the `learny_test` DB on the `pgvector/pgvector:pg16` container: `docker.exe compose up -d db`). Known repo gap: `ruff format --check .` fails on 10 pre-existing Cycle-1 files (STATE Known Gaps) — do **not** reformat unrelated files; gate on `ruff check .` (lint) + format-check only newly added/changed files.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks | `/home/augusto/myenv/bin/uv run pytest tests/<file> -q` |
| Full | After tasks with DB/web/migration tests | `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test /home/augusto/myenv/bin/uv run pytest -q` |
| Build | After phase completion | Full pytest (above) **+** `/home/augusto/myenv/bin/uv run ruff check .` |

---

## Execution Plan

### Phase A: Schema & config foundation (Sequential)

```
T1 → T2
```

### Phase B: Ports, entities & embedding adapter (Parallel OK after T2)

```
T2 ──┬→ T3 [P]
     └→ T4 [P]
```

### Phase C: Embed step & pipeline wiring (Sequential)

```
T3,T4 → T5 → T6 → T7
```

### Phase D: Hybrid retrieval query & service (Sequential)

```
T3,T4 → T8 → T9
```

### Phase E: Retrieval endpoint (Sequential)

```
T9 → T10
```

---

## Task Breakdown

### T1: Retrieval schema — `embedding` + `search_vector` + indexes

**What**: Add `pgvector` dep, model the `embedding` column on `corpus_chunks`, and author migration `0005_retrieval_indexes`.
**Where**: `backend/pyproject.toml`; `backend/app/infrastructure/db/metadata.py`; `backend/migrations/versions/0005_retrieval_indexes.py`
**Depends on**: None
**Reuses**: `migrations/versions/0004_corpus_schema.py` idioms; `metadata.py` naming convention
**Requirement**: RET-01, RET-02, RET-03, RET-04

**Tools**: MCP: NONE · Skill: `pgvector-hybrid-search`, `uv`

**Done when**:
- [ ] `pgvector>=0.3,<0.5` added to `backend/pyproject.toml` and locked
- [ ] `corpus_chunks` Table gains `Column("embedding", VECTOR(1536), nullable=True)`; module docstring notes the migration-only generated `search_vector`
- [ ] Migration up: `CREATE EXTENSION IF NOT EXISTS vector`; add nullable `embedding vector(1536)`; add `search_vector tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english', coalesce(section_path ->> -1, '')),'A') || setweight(to_tsvector('english', coalesce(text,'')),'D')) STORED`; HNSW index (`vector_cosine_ops`, `m=16, ef_construction=64`) + GIN index on `search_vector`
- [ ] Migration down: drops both indexes, both columns, then `DROP EXTENSION IF EXISTS vector`; leaves the Phase-5 `corpus_chunks` shape intact
- [ ] `test_migrations.py` asserts (upgrade→head) the columns/indexes/extension exist and a seeded chunk's `search_vector` is non-empty; (downgrade one step) the columns/indexes are gone
- [ ] Gate passes (Full); Test count: existing migration tests + ≥2 new pass (no silent deletions)

**Tests**: integration · **Gate**: Full

---

### T2: Retrieval settings + guarded `register_vector`

**What**: Add `LEARNY_`-prefixed retrieval/embedding knobs and wire guarded `register_vector` on the app engine.
**Where**: `backend/app/core/config.py`; `backend/app/infrastructure/db/engine.py`
**Depends on**: T1
**Reuses**: `Settings` pattern; `get_engine()` `@lru_cache`
**Requirement**: RET-13 (tuning), RET-15/RET-08 (support)

**Tools**: MCP: NONE · Skill: `pgvector-hybrid-search`

**Done when**:
- [ ] `Settings` gains `embedding_dim=1536`, `embedding_model="local-deterministic"`, `embedding_batch_size=128`, `retrieval_semantic_limit=50`, `retrieval_lexical_limit=50`, `retrieval_rrf_k=60`, `retrieval_top_k=10`, `retrieval_max_top_k=50`, `hnsw_ef_search=100`
- [ ] `get_engine()` registers `register_vector` on the `connect` event, guarded so a pre-migration connection (no `vector` type) still opens
- [ ] `.env.example` updated with the new knobs (no secrets)
- [ ] Gate passes (Build); no import-time failure connecting to a DB before migration

**Tests**: none (config/engine — build gate) · **Gate**: Build

---

### T3: Domain ports + evidence entities [P]

**What**: Add `EmbeddingPort`, `RetrievalPort`, `EmbeddingIndexRepository` protocols and `Evidence`, `ChunkToEmbed` frozen entities.
**Where**: `backend/app/domain/ports.py`; `backend/app/domain/entities.py`
**Depends on**: T2
**Reuses**: existing `Protocol`/`@runtime_checkable` + frozen-dataclass conventions
**Requirement**: RET-05, RET-13 (shape)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `EmbeddingPort` (`embed_query`, `embed_documents`), `RetrievalPort` (`search(*, source_id, query_text, query_vec, top_k, semantic_limit, lexical_limit, rrf_k, ef_search)`), `EmbeddingIndexRepository` (`chunks_for_source`, `set_embeddings`) added — no FastAPI/SQLAlchemy/SDK imports
- [ ] `Evidence` and `ChunkToEmbed` frozen dataclasses added with no outward imports
- [ ] Gate passes (Build)

**Tests**: none (protocols/dataclasses — build gate) · **Gate**: Build

---

### T4: Deterministic embedding adapter [P]

**What**: `DeterministicEmbeddingAdapter` implementing `EmbeddingPort` (pure-Python, no network).
**Where**: `backend/app/infrastructure/embeddings/__init__.py`, `.../local.py`; `backend/tests/test_embeddings_local.py`
**Depends on**: T2, T3
**Reuses**: `get_settings().embedding_dim`; `hashlib`
**Requirement**: RET-06, RET-07, RET-08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Token-hash bag into a `embedding_dim`-length vector, L2-normalized; deterministic (same text → identical vector); empty text → zero vector
- [ ] `embed_documents([...])` returns N vectors in input order, each length `embedding_dim`
- [ ] No provider SDK / model-name literal in domain/application/query modules (assert via an import-level test)
- [ ] Unit tests: determinism, length 1536, batch order, empty-text edge
- [ ] Gate passes (Quick); Test count: ≥4 new pass

**Tests**: unit · **Gate**: Quick

---

### T5: Embedding-index repository

**What**: `SqlAlchemyEmbeddingIndexRepository` — read a source's chunks to embed, write vectors.
**Where**: `backend/app/infrastructure/db/repositories.py`; `backend/tests/test_repositories.py`
**Depends on**: T3, T4
**Reuses**: `SqlAlchemyCorpusRepository` sync-`Connection` pattern; Core `update`/`select`
**Requirement**: RET-09 (support), RET-11

**Tools**: MCP: NONE · Skill: `pgvector-hybrid-search`

**Done when**:
- [ ] `chunks_for_source(source_id) -> list[ChunkToEmbed]` joins chunks→sections→documents by `source_id`, ordered stably
- [ ] `set_embeddings(items)` updates `corpus_chunks.embedding` per id via the `VECTOR` type (no global-registration dependency for the write path)
- [ ] Integration tests: round-trip embeddings for a seeded corpus; only the target source's chunks are read; re-write replaces vectors
- [ ] Gate passes (Full); Test count: ≥3 new pass

**Tests**: integration · **Gate**: Full

---

### T6: `EmbedCorpus` application service

**What**: Service that embeds a source's chunks in batches and appends an `embeddings_built` event.
**Where**: `backend/app/application/retrieval.py`; `backend/tests/test_application_retrieval.py`; fakes in `backend/tests/fakes.py`
**Depends on**: T5
**Reuses**: `BuildCorpus` composition style; `IngestionEventRepository` append; `IngestionEvent`
**Requirement**: RET-09

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `EmbedCorpus.__call__(*, source, job)` fetches chunks, embeds via `embed_documents` in `embedding_batch_size` batches, calls `set_embeddings`, appends `embeddings_built` with the count
- [ ] Zero chunks → no-op write + event count 0
- [ ] Framework-free (no SQLAlchemy/Celery/SDK import)
- [ ] Unit tests (fakes): all chunks embedded, batch boundaries respected, order preserved, zero-chunk case, event appended
- [ ] Gate passes (Quick); Test count: ≥4 new pass

**Tests**: unit · **Gate**: Quick

---

### T7: Embed step + task wiring

**What**: `EmbedCorpusIngestionStep` and the second step transaction in `run_ingestion`.
**Where**: `backend/app/infrastructure/worker/steps.py`; `backend/app/worker/tasks.py`; `backend/tests/test_ingestion_step.py`, `backend/tests/test_worker_tasks.py`
**Depends on**: T6
**Reuses**: `RunIngestion.run_step` (second wiring), `RetryableIngestionError`, storage-fault mapping, task retry/terminal `try/except`
**Requirement**: RET-10, RET-11, RET-12

**Tools**: MCP: NONE · Skill: `celery-workers`

**Done when**:
- [ ] `EmbedCorpusIngestionStep` (`IngestionStep`) wraps `EmbedCorpus`; transient provider faults → `RetryableIngestionError`, else propagate (terminal)
- [ ] `run_ingestion` runs the embed step in its **own** `get_engine().begin()` after the corpus step and before `complete`, inside the same retry/terminal classification
- [ ] Tests: after a fixture run every chunk has non-NULL `embedding` and job `succeeded`; a retryable embed fault retries; a terminal embed fault → `failed` with fixed `last_error` and no partial vectors; re-ingestion re-embeds exactly the rebuilt chunk set
- [ ] Gate passes (Full); Test count: existing worker/step tests + ≥4 new pass (no silent deletions)

**Tests**: unit+integration · **Gate**: Full

---

### T8: Hybrid RRF retrieval repository

**What**: `SqlAlchemyRetrievalRepository` — the single hybrid RRF SQL statement projecting `Evidence`.
**Where**: `backend/app/infrastructure/db/retrieval.py`; `backend/tests/test_retrieval.py`
**Depends on**: T3, T4 (and T1 schema; T2 settings)
**Reuses**: `pgvector-hybrid-search` skill SQL; sync-`Connection` repo + `_to_x` mapper
**Requirement**: RET-13, RET-14, RET-15, RET-16, RET-17

**Tools**: MCP: NONE · Skill: `pgvector-hybrid-search`

**Done when**:
- [ ] One statement: scoped CTE (chunks→sections→documents by `source_id`) → `semantic` (skip NULL embeddings, `LIMIT semantic_limit`) → `lexical` (`websearch_to_tsquery('english',:q)`, `ts_rank_cd(...,32)`, `LIMIT lexical_limit`) → `fused` FULL OUTER JOIN `Σ 1/(k+rank)` → anchors, `ORDER BY score DESC LIMIT top_k`
- [ ] `SET LOCAL hnsw.ef_search = <int(ef_search)>` precedes the query (int-guarded, no bind param); query vector binds as `vector` (via `register_vector`; cast `:query_vec::vector` if needed and confirm the HNSW index is used)
- [ ] Returns frozen `Evidence` (`chunk_id, source_id, section_path, anchor, page_span, snippet, score`)
- [ ] Integration tests: expected chunk/anchor appears for a fixture query (recall); both-arm hit → fused score is the sum; NULL-embedding corpus → lexical-only, no error; nonsense query → empty list; source-A query returns no source-B chunk
- [ ] Gate passes (Full); Test count: ≥5 new pass

**Tests**: integration · **Gate**: Full

---

### T9: `RetrieveEvidence` application service

**What**: Owner-scoped orchestration: authorize → embed_query → search.
**Where**: `backend/app/application/retrieval.py`; `backend/tests/test_application_retrieval.py`
**Depends on**: T8
**Reuses**: `authorized_source`, `ReadSourceStructure` shape, `EmbeddingPort`, `RetrievalPort`, settings
**Requirement**: RET-13, RET-20 (ownership)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] `RetrieveEvidence.__call__(*, user, source_id, query, top_k)` runs `authorized_source` (404 on missing/non-owner), `embed_query`, `RetrievalPort.search` with settings-sourced limits/k/ef, returns `list[Evidence]` (empty allowed)
- [ ] Unit tests (fakes): non-owner/missing → `SourceNotFound`; empty search result passes through as `[]`; settings knobs forwarded
- [ ] Gate passes (Quick); Test count: ≥3 new pass

**Tests**: unit · **Gate**: Quick

---

### T10: Retrieval endpoint

**What**: `POST /api/sources/{id}/retrieve` router + dependency builder + `main.py` include.
**Where**: `backend/app/infrastructure/web/retrieval.py`; `backend/app/infrastructure/web/dependencies.py`; `backend/app/main.py`; `backend/tests/test_web_retrieval.py`
**Depends on**: T9
**Reuses**: structure-endpoint router shape, `get_authenticated_user`, `enforce_csrf`/`enforce_origin`, `get_db_connection`, global error handlers
**Requirement**: RET-18, RET-19, RET-20, RET-21, RET-22

**Tools**: MCP: NONE · Skill: `fastapi`

**Done when**:
- [ ] Router: `POST /api/sources/{source_id}/retrieve`, `dependencies=[enforce_origin, enforce_csrf]`, auth via `get_authenticated_user`; `RetrieveRequest{query, top_k?}` with 422 on empty/whitespace query and `top_k` outside `1..retrieval_max_top_k`; default `top_k=retrieval_top_k`
- [ ] `RetrieveResponse{results: list[EvidenceView]}`; `EvidenceView` exposes anchor/section_path/snippet/score/chunk_id only (no internal storage fields); empty match → 200 `results: []`
- [ ] `get_retrieve_evidence(conn)` dependency mirrors `get_read_source_structure`; router included in `main.py`
- [ ] Integration/e2e tests (TestClient): owner matching query → 200 with evidence; empty query → 422; bad `top_k` → 422; another user's/missing source → 404; missing CSRF/Origin → rejected; nonsense query → 200 empty
- [ ] Gate passes (Build); Test count: ≥6 new pass (no silent deletions)

**Tests**: integration (e2e) · **Gate**: Build

**Commit**: `feat(retrieval): owner-scoped hybrid retrieval endpoint`

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
| ---- | ----------------- | ------------- | ------ |
| T1 | None | (root of Phase A) | ✅ Match |
| T2 | T1 | T1 → T2 | ✅ Match |
| T3 | T2 | T2 → T3 [P] | ✅ Match |
| T4 | T2, T3 | T2 → T4 [P]; T3,T4 feed C/D | ✅ Match |
| T5 | T3, T4 | T3,T4 → T5 | ✅ Match |
| T6 | T5 | T5 → T6 | ✅ Match |
| T7 | T6 | T6 → T7 | ✅ Match |
| T8 | T3, T4 | T3,T4 → T8 | ✅ Match |
| T9 | T8 | T8 → T9 | ✅ Match |
| T10 | T9 | T9 → T10 | ✅ Match |

> Note: T4 depends on T3 (adapter implements the T3 port) so within Phase B they are ordered T3→T4, not truly independent; `[P]` is retained only to mark that T3 has no dependency on T4. The worker runs Phase B in listed order.

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
| ---- | ---------- | --------------- | --------- | ------ |
| T1 | Migration + metadata | integration | integration | ✅ OK |
| T2 | Config/engine | none | none | ✅ OK |
| T3 | Domain ports/entities | none | none | ✅ OK |
| T4 | Embedding adapter | unit | unit | ✅ OK |
| T5 | Repository | integration | integration | ✅ OK |
| T6 | Application service | unit | unit | ✅ OK |
| T7 | Worker task/step | unit+integration | unit+integration | ✅ OK |
| T8 | Retrieval SQL repo | integration | integration | ✅ OK |
| T9 | Application service | unit | unit | ✅ OK |
| T10 | Web router | integration (e2e) | integration (e2e) | ✅ OK |

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1 | schema+migration (1 cohesive DDL unit) | ✅ Granular |
| T2 | config + engine event (2 small, cohesive) | ✅ Granular |
| T3 | ports + entities (1 concept: retrieval contracts) | ✅ Granular |
| T4 | 1 adapter | ✅ Granular |
| T5 | 1 repository | ✅ Granular |
| T6 | 1 service | ✅ Granular |
| T7 | 1 step + its task wiring (cohesive) | ✅ Granular |
| T8 | 1 repository (the hybrid query) | ✅ Granular |
| T9 | 1 service | ✅ Granular |
| T10 | 1 endpoint + wiring | ✅ Granular |

All checks pass — approved for Execute (auto, ship-cycle).
