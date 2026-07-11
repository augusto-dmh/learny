# Retrieval Indexes Design

**Spec**: `.specs/features/retrieval-indexes/spec.md`
**Context**: `.specs/features/retrieval-indexes/context.md` (D-1..D-9, locked)
**Status**: Approved (auto, ship-cycle)

Conforms to active decisions AD-004/006/007/009/014/016/018 and the new AD-019..023.
Governed by ADR-0006 (PostgreSQL hybrid search), ADR-0007 (provider behind a port),
ADR-0003 (citation anchors) and the project-local `pgvector-hybrid-search` skill.

---

## Architecture Overview

Two write paths and one read path, all Learny-owned infrastructure behind ports:

- **Index (write)** — after Phase-5 corpus build, an embed step embeds the source's
  chunks via `EmbeddingPort` and writes vectors; the FTS `search_vector` is a generated
  column maintained by Postgres. Both live on `corpus_chunks`.
- **Retrieve (read)** — one hybrid SQL statement runs the semantic (pgvector/HNSW) and
  lexical (tsvector/GIN) arms, fuses them with RRF, and projects citation anchors into a
  frozen `Evidence` result, behind `RetrievalPort`; a thin owner-scoped endpoint exposes it.

```mermaid
graph TD
    subgraph Ingestion task (worker)
      BR[begin_run] --> CS[corpus step: BuildCorpus]
      CS -->|own txn| ES[embed step: EmbedCorpus]
      ES -->|own txn| CO[complete]
    end
    ES -->|embed_documents| EP[EmbeddingPort<br/>local deterministic adapter]
    ES -->|set_embeddings| CC[(corpus_chunks<br/>embedding + search_vector)]
    subgraph Retrieve (HTTP)
      EPurl[POST /api/sources/id/retrieve] --> RE[RetrieveEvidence]
      RE -->|embed_query| EP
      RE -->|search| RP[RetrievalPort<br/>hybrid RRF SQL]
      RP --> CC
      RE --> EV[Evidence list]
    end
```

---

## Code Reuse Analysis

### Existing components to leverage

| Component | Location | How to use |
|---|---|---|
| `corpus_chunks` table + metadata | `infrastructure/db/metadata.py` | Add `embedding` column + migration-only generated `search_vector`; reuse `section_path`, `anchor`, `page_span`, `text` as-is |
| `RunIngestion.run_step` | `application/ingestion.py:188` | Reuse verbatim: wire a **second** `RunIngestion` with the embed step and call `run_step(job)` in its own txn — no new driver method |
| `IngestionStep` protocol + `EpubCorpusIngestionStep` | `domain/ports.py:211`, `infrastructure/worker/steps.py` | The embed step is another `IngestionStep`; mirror the storage→`RetryableIngestionError` mapping for transient provider faults |
| `RetryableIngestionError` + task retry/terminal machinery | `infrastructure/worker/steps.py`, `worker/tasks.py:137` | Extend the existing `try/except` to wrap the embed step transaction identically |
| `authorized_source` | `application/ingestion.py:51` | Ownership-as-404 for `RetrieveEvidence`, exactly like `ReadSourceStructure` |
| `ReadSourceStructure` + `get_read_source_structure` | `application/corpus.py:130`, `web/dependencies.py:274` | Template for `RetrieveEvidence` service + its dependency builder |
| Structure endpoint + `BookStructureView` | `web/sources.py` | Template for the retrieve router (auth, ownership 404, Pydantic view) |
| `SqlAlchemyCorpusRepository` | `infrastructure/db/repositories.py:303` | Same sync-`Connection` repo pattern for the new embedding-index repo |
| Settings + `get_settings()` | `core/config.py` | Add `LEARNY_`-prefixed retrieval/embedding knobs |
| Migration `0004` shape | `migrations/versions/0004_corpus_schema.py` | Numbered revision, `op.execute` for extension + raw index DDL |

### Integration points

| System | Integration |
|---|---|
| Alembic | New `0005_retrieval_indexes` (down_revision `0004_corpus_schema`); `env.py` builds its **own** engine, so the app-engine `register_vector` does not affect migrations |
| psycopg3 engine | Add a guarded `register_vector` `connect`-event to `get_engine()` so lists adapt to `vector` on both read and write paths |
| Celery task | `run_ingestion` gains a second step transaction (embed) between corpus build and `complete` |
| FastAPI | New retrieve router included in `main.py` |

---

## Components

### 1. Schema: `embedding` + `search_vector` on `corpus_chunks`
- **Purpose**: Make chunks semantically and lexically searchable.
- **Location**: `migrations/versions/0005_retrieval_indexes.py`; `infrastructure/db/metadata.py`.
- **Details**:
  - `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`.
  - `embedding vector(1536)` **nullable** (async-populated; modeled on the `corpus_chunks` Table as `VECTOR(1536)` for the Core write path).
  - `search_vector tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english', coalesce(section_path ->> -1, '')), 'A') || setweight(to_tsvector('english', coalesce(text, '')), 'D')) STORED` — emitted via raw `op.execute` (Alembic does not model `GENERATED … STORED`); **not** placed on the Table (the retrieval query is raw SQL and does not need it in metadata). `to_tsvector`'s 2-arg constant-config form is IMMUTABLE (required for a generated column).
  - `ix_corpus_chunks_embedding_hnsw` HNSW `(embedding vector_cosine_ops) WITH (m=16, ef_construction=64)` and `ix_corpus_chunks_search_vector` GIN `(search_vector)` — raw `op.execute`.
  - `downgrade()` drops both indexes, both columns, then `DROP EXTENSION IF EXISTS vector`.
- **Reuses**: migration `0004` idioms; naming convention.

### 2. `EmbeddingPort` + `DeterministicEmbeddingAdapter`
- **Purpose**: Provider-agnostic text→vector; default deterministic adapter (D-1).
- **Location**: `domain/ports.py` (port); `infrastructure/embeddings/local.py` (adapter).
- **Interfaces**: `embed_query(text: str) -> list[float]`; `embed_documents(texts: list[str]) -> list[list[float]]`.
- **Adapter behavior**: pure-Python, no network. Hash tokens of the text into a
  `LEARNY_EMBEDDING_DIM`-length (1536) accumulator (token → index via `blake2b`), then
  L2-normalize. Deterministic (same text → same vector) and weakly meaningful (shared
  tokens raise cosine similarity), which stabilizes golden-fixture semantic ordering.
  Empty text → a zero vector (semantic arm still safe; lexical arm carries recall).
- **Dependencies**: `hashlib` (stdlib), `get_settings().embedding_dim`.
- **Reuses**: settings pattern; no provider SDK (ADR-0007).

### 3. `EmbedCorpus` service + embedding-index repository + `EmbedCorpusIngestionStep`
- **Purpose**: Populate `corpus_chunks.embedding` for a source after corpus build.
- **Location**: `application/retrieval.py` (`EmbedCorpus`); `infrastructure/db/repositories.py`
  (`SqlAlchemyEmbeddingIndexRepository`); `infrastructure/worker/steps.py`
  (`EmbedCorpusIngestionStep`); `domain/ports.py` (`EmbeddingIndexRepository`).
- **`EmbeddingIndexRepository`**: `chunks_for_source(source_id) -> list[ChunkToEmbed]`
  (id + text, joined chunks→sections→documents by `source_id`);
  `set_embeddings(items: Sequence[tuple[UUID, list[float]]]) -> None` (Core
  `update(corpus_chunks).where(id==...).values(embedding=vec)`; the `VECTOR` type
  serializes the list).
- **`EmbedCorpus.__call__(*, source, job)`**: fetch chunks; embed in batches of
  `LEARNY_EMBEDDING_BATCH_SIZE` via `embed_documents`; `set_embeddings`; append an
  `embeddings_built` event with the count. Zero chunks → no-op + event count 0. Runs in
  the embed step's transaction (all-or-nothing per run → RET-12).
- **`EmbedCorpusIngestionStep`**: `IngestionStep`; wraps `EmbedCorpus`; maps transient
  provider faults to `RetryableIngestionError`, everything else propagates (terminal).
- **Task wiring** (`worker/tasks.py`): after the corpus `run_step` txn commits, open a new
  `get_engine().begin()` and call a second `RunIngestion` (wired with the embed step)
  `.run_step(job)`, inside the same `try/except` that classifies retry vs terminal. Retry
  re-runs the whole task (corpus replace is atomic + re-embed is idempotent → RET-11).
- **Reuses**: `RunIngestion.run_step`, `RetryableIngestionError`, the storage-fault mapping.

### 4. `RetrievalPort` + `SqlAlchemyRetrievalRepository` + `Evidence`
- **Purpose**: One hybrid RRF query returning citation-ready evidence for a source.
- **Location**: `domain/ports.py` (`RetrievalPort`); `domain/entities.py` (`Evidence`,
  `ChunkToEmbed`); `infrastructure/db/retrieval.py` (repo, raw SQL seam).
- **`RetrievalPort.search`**: `search(*, source_id: UUID, query_text: str, query_vec:
  list[float], top_k: int, semantic_limit: int, lexical_limit: int, rrf_k: int,
  ef_search: int) -> list[Evidence]`.
- **SQL** (single statement; scoped CTE joins chunks→sections→documents by `source_id`):
  `scoped` → `semantic` (`ORDER BY embedding <=> :query_vec`, `WHERE embedding IS NOT
  NULL`, `LIMIT :semantic_limit`) → `lexical` (`ts_rank_cd(search_vector,
  websearch_to_tsquery('english', :q), 32) DESC`, `WHERE search_vector @@ …`, `LIMIT
  :lexical_limit`) → `fused` (`FULL OUTER JOIN`, `Σ COALESCE(1.0/(:k+rank),0)`) → join
  back to `scoped` for anchors, `ORDER BY rrf_score DESC LIMIT :top_k`. Precede with
  `SET LOCAL hnsw.ef_search = <int(ef_search)>` (value interpolated as a guarded int — SET
  takes no bind params). `page_span` maps straight through (NULL for EPUB).
- **`Evidence`** (frozen): `chunk_id: UUID`, `source_id: UUID`, `section_path: tuple[str,
  ...]`, `anchor: str`, `page_span: dict | None`, `snippet: str`, `score: float`.
- **Reuses**: `pgvector-hybrid-search` skill SQL; sync-`Connection` repo pattern; `_to_x`
  row-mapping helper.

### 5. `RetrieveEvidence` service + retrieve endpoint
- **Purpose**: Owner-scoped orchestration + HTTP surface.
- **Location**: `application/retrieval.py` (`RetrieveEvidence`); `infrastructure/web/retrieval.py`
  (router); `web/dependencies.py` (builder); `main.py` (include).
- **`RetrieveEvidence.__call__(*, user, source_id, query, top_k)`**: `authorized_source`
  (404 on missing/non-owner); `embed_query(query)`; `RetrievalPort.search(...)` with
  settings-sourced limits/k/ef; return `list[Evidence]` (possibly empty).
- **Endpoint**: `POST /api/sources/{source_id}/retrieve`, `dependencies=[enforce_origin,
  enforce_csrf]`, body `RetrieveRequest{query: str, top_k: int | None}`. Pydantic
  validation: `query` non-empty after strip (min_length/validator → 422); `top_k` in
  `1..LEARNY_RETRIEVAL_MAX_TOP_K` (→ 422); default `top_k` = `LEARNY_RETRIEVAL_TOP_K`.
  Response `RetrieveResponse{results: list[EvidenceView]}`; `EvidenceView` exposes only
  anchor/snippet/score (no `object_key`/internal ids beyond `chunk_id`). Empty match →
  200 with `results: []`. Application errors → HTTP via existing global handlers
  (`SourceNotFound` → 404).
- **Reuses**: structure-endpoint router shape, `get_authenticated_user`, CSRF/Origin deps,
  `get_db_connection`.

### 6. Config + engine
- **`Settings`** (`core/config.py`): `embedding_dim=1536`, `embedding_model="local-deterministic"`,
  `embedding_batch_size=128`, `retrieval_semantic_limit=50`, `retrieval_lexical_limit=50`,
  `retrieval_rrf_k=60`, `retrieval_top_k=10`, `retrieval_max_top_k=50`, `hnsw_ef_search=100`.
- **`get_engine()`** (`infrastructure/db/engine.py`): add a guarded `connect`-event
  `register_vector(dbapi_conn)` (swallow the "vector type not found" error so connections to
  a pre-migration DB still open; queries needing vectors then fail explicitly).
- **`pyproject.toml`**: add `pgvector>=0.3,<0.5`.

---

## Data Models

```python
# domain/entities.py
@dataclass(frozen=True)
class ChunkToEmbed:
    id: UUID
    text: str

@dataclass(frozen=True)
class Evidence:
    chunk_id: UUID
    source_id: UUID
    section_path: tuple[str, ...]
    anchor: str
    page_span: dict | None       # None for EPUB (A-9); shape reserved for PDF
    snippet: str                 # chunk text (no ts_headline this cycle)
    score: float                 # fused RRF score
```

**Relationships**: `Evidence` projects `corpus_chunks` (+ `source_id` via the
sections→documents join). `ChunkToEmbed` is the embed step's read DTO.

---

## Error Handling Strategy

| Scenario | Handling | User impact |
|---|---|---|
| Transient provider/storage fault in embed step | `RetryableIngestionError` → task backoff retry; re-runs corpus+embed idempotently | Job stays processing, retries |
| Non-retryable embed error | Propagates → task `fail` with fixed redacted `last_error`; embed txn rolls back (no partial vectors for the run) | Source `failed`, inspectable event |
| Source not owned / missing on retrieve | `authorized_source` → `SourceNotFound` → 404 | 404 (existence not disclosed) |
| Empty/whitespace query or out-of-range `top_k` | Pydantic 422 before retrieval runs | 422 validation error |
| Query matches nothing | Query returns empty list → 200 `results: []` | Empty results (Phase-7 "not found" hook) |
| Chunks not yet embedded (NULL) | Semantic arm empty; lexical arm returns; no error | Lexical-only results |
| Missing auth / CSRF / Origin | Rejected by deps before retrieval | 401/403 |

---

## Risks & Concerns

| Concern | Location | Impact | Mitigation |
|---|---|---|---|
| `register_vector` at connect fails against a DB without the `vector` extension (pre-migration boot, other DBs) | `infrastructure/db/engine.py` | App/worker connections could fail to open | Guard the registration in `try/except` and skip when the type is absent; migrations use their own engine (`env.py`) so they are unaffected |
| Raw `text()` query binding a `list[float]` as `:query_vec` may be type-ambiguous to psycopg | `infrastructure/db/retrieval.py` | Semantic arm errors or ignores the index | `register_vector` adapts lists to `vector`; if needed, cast `:query_vec::vector` in SQL. Verify the index is used (semantic arm returns) in an integration test |
| `SET LOCAL hnsw.ef_search` cannot take a bind param | `infrastructure/db/retrieval.py` | SQL injection if interpolated naïvely | Interpolate `int(ef_search)` only (typed int from settings), never raw input |
| `search_vector` generated column not modeled on the Table → Alembic autogenerate might propose dropping it | `metadata.py` | Spurious autogenerate diff | Project hand-writes migrations (0004 precedent); documented in the metadata docstring. Not a runtime risk |
| Deterministic adapter's semantic arm is not truly semantic | `infrastructure/embeddings/local.py` | Weak semantic recall until a real model is wired | Accepted (D-1); FTS arm carries real recall; production provider is a follow-up ADR (Phase 7) |
| Integration tests require the `vector` extension in `learny_test` | `tests/` | Tests error without it | `CREATE EXTENSION IF NOT EXISTS vector` in the migration; the `pgvector/pgvector:pg16` image ships it; tests skip when `LEARNY_TEST_DATABASE_URL` is unset (existing pattern) |

---

## Tech Decisions (non-obvious)

| Decision | Choice | Rationale |
|---|---|---|
| Embed step reuses `RunIngestion.run_step` via a second wiring | Yes | Zero new driver code; identical retry/terminal classification; idempotent under redelivery |
| `search_vector` title source | `section_path ->> -1` (deepest TOC title) | The chunk has no flat title column; the deepest path element is the section title; `->>`/`to_tsvector('english', …)` are immutable → valid in a generated column |
| Vector write path | Core `update().values(embedding=list)` via `VECTOR` type | Avoids relying on global registration for writes; the type serializes the list |
| Retrieval is per-source | `WHERE source_id = :source_id` in the scoped CTE | Phase 7/8 target one book; prevents cross-source leakage (RET-17) |

> Project-level decisions recorded as AD-019..023 in `.specs/project/STATE.md`.
