# Retrieval Indexes Specification

Cycle 5 — TDD-001 Phase 6. Adds the hybrid retrieval layer over the canonical corpus
built in Phase 5: chunk embeddings behind a Learny `EmbeddingPort`, a PostgreSQL
full-text field, and a single hybrid (semantic + lexical) candidate query fused with
Reciprocal Rank Fusion that returns citation-ready evidence. Governed by ADR-0006
(PostgreSQL hybrid search) and ADR-0007 (provider behind a port). Gray-area decisions
live in [context.md](context.md) (D-1..D-9).

## Problem Statement

A processed source today has a structured, citable corpus but nothing retrievable: no
embeddings, no full-text index, no way to turn a question into candidate passages.
Every later phase — cited Q&A (Phase 7) and teaching sessions (Phase 8) — depends on
being able to ask "which passages of this book are relevant?" and get back
citation-anchored evidence. This cycle builds that retrieval substrate.

## Goals

- [ ] Once a source is ingested, its chunks carry an embedding and a full-text search
      field, and are indexed for semantic (pgvector/HNSW) and lexical (tsvector/GIN)
      search.
- [ ] A hybrid query over a source returns the top-k chunks fused by RRF, each carrying
      stable citation anchors (chunk id, section path, anchor, page span) and a score.
- [ ] The embedding provider stays behind a Learny port: no provider SDK, model name,
      or SDK object appears in domain, application, or query code.
- [ ] The owning user can retrieve citation-ready evidence for a source over HTTP; an
      unmatched query returns an empty result, not an error.

## Out of Scope

| Feature | Reason |
|---|---|
| Answer generation, cited-answer endpoint, "not found in source" answer text | TDD Phase 7 |
| Teaching sessions / bounded-context selection | TDD Phase 8 |
| A concrete cloud embedding provider/model (OpenAI/etc.) as a wired default | D-1: deferred to its own ADR; port + deterministic local adapter only |
| Reranking / cross-encoder reordering | Deferred by ADR-0006 (§Decision Outcome 5) |
| Dedicated vector/search engine (Qdrant, Elasticsearch, …) | Deferred by ADR-0006 (§Decision Outcome 6) |
| Retrieval/search UI (search box, results screen) | D-7: raw hybrid results are not an MVP user surface; Phase 7 surfaces cited answers |
| Cross-source / whole-library retrieval | D-6: retrieval is per-source (Phase 7/8 target one book) |
| Multi-language full-text config | D-4: single `'english'` regconfig for MVP |
| Ragas / evaluation dashboard | Phase 9 / ADR-0016 (golden fixtures only) |
| Historical backfill of pre-Phase-6 corpora | A-4: re-ingestion re-embeds; no production data yet |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| # | Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|---|
| A-1 | Embedding dimension | `vector(1536)`; the deterministic local adapter emits 1536-dim vectors. `LEARNY_EMBEDDING_DIM` is informational; the migration literal is authoritative. | 1536 is a common, provider-neutral size; a different-dim model later is a dim-change migration + re-embed (embeddings are re-indexable, ADR-0001). | y (auto, D-3) |
| A-2 | Distance / index | cosine (`vector_cosine_ops`, `<=>`), HNSW `m=16, ef_construction=64`; query-time recall via `LEARNY_HNSW_EF_SEARCH` set per transaction. | Cosine is the normalized-embedding default; HNSW needs no training step, so it builds on an empty table and survives re-index. | y (auto, D-3) |
| A-3 | Full-text field | `STORED` generated `search_vector tsvector`: section title (`section_path ->> -1`, coalesced) weighted `'A'` over `text` `'D'`; GIN index; `websearch_to_tsquery('english', :q)` + `ts_rank_cd(..., 32)`. | Skill-prescribed; safe on arbitrary user input; title-weighted for citation-sensitive lookup; auto-maintained. | y (auto, D-4) |
| A-4 | No historical backfill | Embeddings are (re)generated only by (re-)ingestion; a corpus built before this cycle has NULL embeddings until re-ingested. FTS is populated for existing rows at `ALTER` time. | No production data exists yet; re-ingestion is the intended path (D-5 / Cycle-4 D-3 atomic replace). | y (auto) |
| A-5 | Embedding step failure semantics | The embed step obeys the existing `IngestionStep` retry contract: transient provider/storage faults → `RetryableIngestionError` (retry with backoff); anything else → terminal `failed`; the durable `last_error` stays the fixed redacted summary. The local adapter has no transient failures; the contract is for the future cloud adapter. | Reuses the Phase-4/5 task machinery unchanged; keeps failure handling uniform. | y (auto, D-5) |
| A-6 | Retrieval scope + anchors | The query is scoped to one `source_id` (join `corpus_chunks → corpus_sections → corpus_documents`) and projects `chunk_id, source_id, section_path, anchor, page_span, snippet, score`. `snippet` is the chunk `text` (no `ts_headline` this cycle). | Per-source matches Phase 7/8; anchors satisfy ADR-0003; a raw snippet is enough for evidence, highlighting is polish. | y (auto, D-6) |
| A-7 | Retrieval endpoint shape | `POST /api/sources/{source_id}/retrieve`, body `{query, top_k?}`; 422 on empty/whitespace query or out-of-range `top_k`; 404 on missing/non-owned source; **200 with empty list** when nothing matches. Session auth + CSRF/Origin like other state-shaped POSTs; no new rate limit. | Mirrors the structure endpoint's ownership-as-404; the empty-200 is the Phase-7 "not found" hook, not an error. | y (auto, D-7/D-8) |
| A-8 | Semantic arm with no embeddings | If a source's chunks have NULL embeddings (not yet embedded), the semantic arm returns nothing and the lexical arm alone drives results; the query never errors. | Retrieval must degrade gracefully during/after partial ingestion. | y (auto) |
| A-9 | Tuning knobs | `LEARNY_RETRIEVAL_SEMANTIC_LIMIT`, `_LEXICAL_LIMIT`, `_RRF_K` (default 60), `_TOP_K` (default), `_MAX_TOP_K`, `LEARNY_HNSW_EF_SEARCH`, `LEARNY_EMBEDDING_DIM` — all `LEARNY_`-prefixed in `Settings`, never hard-coded in query code. | ADR-0006: candidate merging/thresholding is infrastructure tuning, not a domain concept. | y (auto) |
| A-10 | `pgvector` dependency | Add `pgvector>=0.3,<0.5` to `backend/pyproject.toml`; the `vector` extension is created in the migration (`CREATE EXTENSION IF NOT EXISTS vector`), matching the `citext` pattern in `0001`. The `pgvector/pgvector:pg16` image already ships the extension. | pgvector is the only added retrieval extension (ADR-0006 — no BM25/pg_textsearch). | y (auto) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Retrieval index schema ⭐ MVP

**User Story**: As the platform, I want each corpus chunk to have an embedding column,
a full-text search field, and matching vector/lexical indexes, so that a source's
chunks are searchable both semantically and lexically.

**Why P1**: Nothing can be retrieved without the columns and indexes; every other story
depends on this.

**Acceptance Criteria**:

1. WHEN the migration runs THEN the `vector` extension SHALL exist and `corpus_chunks`
   SHALL have a nullable `embedding vector(1536)` column and a `STORED` generated
   `search_vector tsvector` column (section title `'A'` over `text` `'D'`).
2. WHEN the migration runs THEN an HNSW index (`vector_cosine_ops`, `m=16,
   ef_construction=64`) SHALL exist on `embedding` and a GIN index SHALL exist on
   `search_vector`.
3. WHEN a chunk row exists with non-empty `text` THEN its `search_vector` SHALL be
   populated automatically (no application write), including for rows that predate the
   migration.
4. WHEN the migration is downgraded THEN both indexes, both columns, and the extension
   SHALL be dropped, leaving the Phase-5 `corpus_chunks` shape intact.

**Independent Test**: Apply the migration against the test DB; inspect `corpus_chunks`
columns/indexes and confirm a seeded chunk's `search_vector` is non-empty; downgrade and
confirm the columns/indexes are gone.

---

### P1: Embeddings behind a Learny port ⭐ MVP

**User Story**: As an architect, I want embeddings produced only through a Learny
`EmbeddingPort` with a deterministic default adapter, so that no provider SDK or model
name leaks into the domain and retrieval is testable without a network.

**Why P1**: ADR-0007 requires the port; the deterministic adapter is what makes the
whole cycle testable and provider-agnostic (D-1).

**Acceptance Criteria**:

1. WHEN application/query code needs a vector THEN it SHALL depend only on
   `EmbeddingPort` (`embed_query`, `embed_documents`) and receive plain `list[float]`
   — no provider SDK, model name, or SDK object in `domain`/`application`/query code.
2. WHEN the default adapter embeds the same text twice THEN it SHALL return the same
   1536-dim vector (deterministic), with no network call.
3. WHEN `embed_documents` is given N texts THEN it SHALL return N vectors in input order.
4. WHEN the embedding model id is configured THEN it SHALL come from a `LEARNY_`-prefixed
   setting, never hard-coded in query or repository code.

**Independent Test**: Call the local adapter twice on the same text and assert vector
equality and length 1536; assert `import`-level that the query/repository modules
reference no provider SDK.

---

### P1: Chunks are embedded during ingestion ⭐ MVP

**User Story**: As a reader, I want my source's chunks embedded when it is ingested, so
that semantic search works after processing completes.

**Why P1**: Embeddings must be populated for the semantic arm to return anything; this is
the write half of retrieval.

**Acceptance Criteria**:

1. WHEN ingestion runs for a source with a built corpus THEN every chunk of that source
   SHALL have a non-NULL `embedding` after the job succeeds.
2. WHEN the embed step runs THEN it SHALL run in its own committed transaction, after the
   corpus-build commit and before terminal success (so the embedding provider call is
   outside the corpus-write transaction).
3. WHEN a source is re-ingested THEN its chunks SHALL be re-embedded to match the rebuilt
   corpus (no stale vectors from a prior corpus).
4. WHEN the embed step raises a transient (`RetryableIngestionError`) fault THEN the job
   SHALL retry with backoff; WHEN it raises any other error THEN the job SHALL end
   `failed` with the fixed redacted `last_error`, and no chunk SHALL be left partially
   embedded for that run (transaction rolls back).

**Independent Test**: Run ingestion on a fixture EPUB with the local adapter; assert all
of the source's chunks have non-NULL embeddings and the job is `succeeded`; re-ingest and
assert embeddings still cover exactly the rebuilt chunk set.

---

### P1: Hybrid retrieval returns citation-ready evidence ⭐ MVP

**User Story**: As the platform, I want a single hybrid query that fuses semantic and
lexical candidates with RRF and returns citation-anchored evidence for a source, so that
Q&A and teaching can ask for relevant passages.

**Why P1**: This is the phase's core outcome — "processed sources can return
citation-ready evidence."

**Acceptance Criteria**:

1. WHEN a query is run for a source THEN the system SHALL return up to `top_k` chunks of
   that source ordered by descending RRF score, each carrying `chunk_id`, `source_id`,
   `section_path`, `anchor`, `page_span`, `snippet`, and `score`.
2. WHEN a chunk matches on both the semantic and lexical arms THEN its RRF score SHALL be
   `1/(k+rank_semantic) + 1/(k+rank_lexical)` (fused, not from a single arm).
3. WHEN a source's chunks have NULL embeddings THEN the semantic arm SHALL contribute
   nothing and the query SHALL still return lexical matches without error.
4. WHEN a query matches no chunk on either arm THEN the system SHALL return an empty list
   (no error).
5. WHEN the query is run THEN it SHALL return only chunks belonging to the given
   `source_id` (no cross-source leakage).

**Independent Test**: Build a corpus from a fixture, embed it, run a query whose terms
appear in a known section, and assert the expected `chunk_id`/`anchor` is in the results;
run a nonsense query and assert an empty list; run a query scoped to source A and assert
no source-B chunk appears.

---

### P1: Owner-scoped retrieval endpoint ⭐ MVP

**User Story**: As a signed-in user, I want to POST a query for one of my sources and get
back citation-ready evidence, so that the retrieval capability is demoable and Phase 7
can build on it.

**Why P1**: Gives the phase an independently testable, demoable route and the seam Phase 7
consumes (D-7).

**Acceptance Criteria**:

1. WHEN an authenticated owner POSTs `{query, top_k?}` to
   `/api/sources/{id}/retrieve` for a processed source THEN the system SHALL return 200
   with the fused evidence list.
2. WHEN the query is empty/whitespace, or `top_k` is outside `1..LEARNY_RETRIEVAL_MAX_TOP_K`
   THEN the system SHALL return 422 without running retrieval.
3. WHEN the source does not exist or is owned by another user THEN the system SHALL return
   404 (ownership is never disclosed), consistent with the structure endpoint.
4. WHEN the request omits/violates auth or CSRF/Origin THEN the system SHALL reject it
   (401/403) before retrieval, like other state-shaped POSTs.
5. WHEN retrieval matches nothing THEN the system SHALL return 200 with an empty list.

**Independent Test**: As owner, POST a matching query → 200 with evidence; POST empty
query → 422; POST for another user's source → 404; POST a nonsense query → 200 empty.

---

## Edge Cases

- WHEN a source has a corpus but zero chunks (all-empty sections) THEN retrieval SHALL
  return an empty list without error.
- WHEN `top_k` is omitted THEN the system SHALL use `LEARNY_RETRIEVAL_TOP_K`.
- WHEN a chunk's `section_path` is an empty array THEN the generated `search_vector` SHALL
  fall back to `''` for the title weight (coalesced) and index only the body.
- WHEN the same query text is embedded twice THEN the semantic ordering SHALL be identical
  (deterministic adapter) so golden-fixture assertions are stable.
- WHEN a very long query is submitted THEN `websearch_to_tsquery` SHALL not error (safe
  parser) and the embedding adapter SHALL accept it.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| RET-01 | P1: Retrieval index schema | Design | Pending |
| RET-02 | P1: Retrieval index schema (indexes) | Design | Pending |
| RET-03 | P1: Retrieval index schema (generated FTS, existing rows) | Design | Pending |
| RET-04 | P1: Retrieval index schema (downgrade) | Design | Pending |
| RET-05 | P1: Embeddings behind a Learny port (port dependency only) | Design | Pending |
| RET-06 | P1: Embeddings behind a Learny port (deterministic) | Design | Pending |
| RET-07 | P1: Embeddings behind a Learny port (batch order) | Design | Pending |
| RET-08 | P1: Embeddings behind a Learny port (model id in config) | Design | Pending |
| RET-09 | P1: Chunks embedded during ingestion (all chunks embedded) | Design | Pending |
| RET-10 | P1: Chunks embedded during ingestion (own transaction, after corpus) | Design | Pending |
| RET-11 | P1: Chunks embedded during ingestion (re-embed on re-ingest) | Design | Pending |
| RET-12 | P1: Chunks embedded during ingestion (retry/terminal, no partial) | Design | Pending |
| RET-13 | P1: Hybrid retrieval (top-k, anchors, ordering) | Design | Pending |
| RET-14 | P1: Hybrid retrieval (RRF fusion formula) | Design | Pending |
| RET-15 | P1: Hybrid retrieval (NULL-embedding degrade) | Design | Pending |
| RET-16 | P1: Hybrid retrieval (empty result) | Design | Pending |
| RET-17 | P1: Hybrid retrieval (source scoping) | Design | Pending |
| RET-18 | P1: Retrieval endpoint (200 evidence) | Design | Pending |
| RET-19 | P1: Retrieval endpoint (422 validation) | Design | Pending |
| RET-20 | P1: Retrieval endpoint (404 ownership) | Design | Pending |
| RET-21 | P1: Retrieval endpoint (auth/CSRF) | Design | Pending |
| RET-22 | P1: Retrieval endpoint (empty 200) | Design | Pending |

**Coverage:** 22 total, 0 mapped to tasks yet, 22 pending design.

---

## Success Criteria

- [ ] `corpus_chunks` has `embedding` + `search_vector` with HNSW + GIN indexes; migration
      up/down is clean and reversible.
- [ ] After ingesting a fixture EPUB, every chunk has a non-NULL embedding and a populated
      `search_vector`.
- [ ] For a fixture query with a known target passage, the expected chunk/anchor appears in
      the candidate set (Phase-6 retrieval-fixture recall metric).
- [ ] The hybrid query and endpoint return citation-ready evidence; unmatched queries
      return an empty result, not an error.
- [ ] No provider SDK, model name, or SDK object appears in `domain`, `application`, or the
      retrieval query/repository modules.
