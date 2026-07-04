---
name: pgvector-hybrid-search
description: Learny's PostgreSQL hybrid retrieval layer — pgvector semantic similarity plus PostgreSQL built-in full-text search, fused with Reciprocal Rank Fusion (RRF), projecting stable citation anchors, with embeddings kept behind a Learny EmbeddingPort. Use when designing or writing the chunk retrieval query, choosing a pgvector column type or HNSW/IVFFlat index, building a tsvector/GIN full-text index, fusing semantic and lexical candidates for RAG, or wiring the embedding adapter — keywords like pgvector, hybrid search, tsvector, websearch_to_tsquery, ts_rank_cd, RRF, HNSW, cosine_distance, semantic search, retrieval, citations. Do NOT use for Redis caching or queues (vectors never live in Redis), for non-retrieval FastAPI endpoints, or for picking a dedicated vector engine or reranker (both deferred by ADR-0006).
---

# pgvector Hybrid Search

Learny's retrieval layer: pgvector semantic similarity plus PostgreSQL built-in full-text search, fused with Reciprocal Rank Fusion and returning citation anchors, all Learny-owned infrastructure behind ports (ADR-0006, ADR-0001, ADR-0003, ADR-0007).

## Consistency First

Before applying any generic pgvector or ORM tutorial, match the patterns already in this backend — they win over external defaults:

- Schema is **SQLAlchemy 2.x Core `Table` metadata** (not ORM `declarative_base`) in `app/infrastructure/db/metadata.py`, sharing one `MetaData(naming_convention=NAMING_CONVENTION)`. New chunk/embedding tables go in that same module so Alembic autogenerate and `--sql` offline mode stay in sync.
- The driver is **sync psycopg3** (`postgresql+psycopg://…`); the engine is built once via `@lru_cache get_engine()` in `app/infrastructure/db/engine.py`. There is no async engine — retrieval repositories are sync and receive a caller-provided `Connection`, keeping the transaction boundary at the composition root (web/worker), never inside the adapter.
- Ports are `typing.Protocol` classes decorated `@runtime_checkable` in `app/domain/ports.py` with **no FastAPI/SQLAlchemy/SDK imports**; domain results are frozen `@dataclass` objects in `app/domain/entities.py` with no outward imports.
- Tuning knobs (embedding model id, `hnsw.ef_search`, RRF `k`, per-arm limits) live in `app.core.config.get_settings()` (Pydantic `BaseSettings`, `env_prefix="LEARNY_"`), never hard-coded in query code.

## Quick Reference

- Mirror Learny's hexagonal layout — Core `Table` metadata, sync `Connection`-based repositories, `Protocol` ports — before copying any generic pgvector/ORM example; see [references/schema-and-migrations.md](references/schema-and-migrations.md).
- Store embeddings in a pgvector column (`vector`, or `halfvec` when dims > 2000, e.g. 3072) and index with **HNSW** using the operator class that matches your query operator (`cosine_distance`/`<=>` → `vector_cosine_ops`); reach for IVFFlat only with a specific reason; see [references/pgvector-columns-and-indexes.md](references/pgvector-columns-and-indexes.md).
- Lexical search uses **PostgreSQL built-in full-text search only** (ADR-0006) — a `STORED` generated `tsvector` column with `setweight` (section title `'A'` outranks body `'D'`), a GIN index, `websearch_to_tsquery` for user input, and `ts_rank_cd` for scoring; never add a BM25 / `pg_textsearch` / non-core extension; see [references/postgres-fts.md](references/postgres-fts.md).
- Fuse the two candidate lists with **Reciprocal Rank Fusion** in one SQL statement (a CTE per arm ranked by its score, then sum `1.0 / (k + rank)`); tune `k` and per-arm `LIMIT`s from settings, not the domain; see [references/hybrid-rrf-query.md](references/hybrid-rrf-query.md).
- Every retrieved row MUST project **stable citation anchors** — `chunk_id`, `section_path`, page/location span, `source_file` ref, and an optional snippet (ADR-0003) — mapped into a frozen domain result dataclass, so retrieval is independently measurable against golden fixtures; see [references/hybrid-rrf-query.md](references/hybrid-rrf-query.md).
- Generate embeddings behind a Learny-owned **`EmbeddingPort`** `Protocol`; the provider SDK, model name, and SDK objects never leak into query/repository code — the repo receives a plain `list[float]` (ADR-0007). Wire psycopg3 `register_vector` in the infrastructure DB layer so lists adapt to the `vector` type; see [references/embeddings-port.md](references/embeddings-port.md).

## When to apply

- Designing or writing Learny's chunk retrieval query, embedding columns, FTS indexes, or the hybrid RRF fusion.
- Choosing a pgvector column type or index, or a full-text ranking function, for the corpus.
- Wiring the embedding adapter or `register_vector` for the retrieval path.

## When NOT to apply

- Pure Redis caching or Celery queue work — **vectors never go in Redis** (they live in Postgres/pgvector); use the `redis-*` skills.
- Non-retrieval FastAPI endpoints — use the `fastapi` skill.
- Choosing a dedicated vector/search engine (Qdrant, Elasticsearch, etc.) or a reranker — both are explicitly **deferred by ADR-0006**; do not pick one here.

## References

- pgvector: <https://github.com/pgvector/pgvector>
- pgvector-python: <https://github.com/pgvector/pgvector-python>
- PostgreSQL full-text controls: <https://www.postgresql.org/docs/16/textsearch-controls.html>
- PostgreSQL full-text tables/indexes: <https://www.postgresql.org/docs/16/textsearch-tables.html>

Source: Learny-authored project-local skill encoding ADR-0001 (RAG default answer path), ADR-0003 (citations/evaluation are core), ADR-0006 (PostgreSQL hybrid search with pgvector + built-in FTS), and ADR-0007 (Learny-owned ports for AI provider integration), grounded in the official pgvector and PostgreSQL docs cited above. Distinct from vendored official skills such as `fastapi` and `redis-core`.
