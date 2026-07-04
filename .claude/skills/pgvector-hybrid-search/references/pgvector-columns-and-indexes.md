# pgvector Columns and Indexes

How to store and index embeddings in Postgres for Learny's semantic arm. Keep every choice here in the **infrastructure** layer — operator classes and index params are not domain concepts (ADR-0006).

Sources: <https://github.com/pgvector/pgvector>, <https://github.com/pgvector/pgvector-python>

## Extension

The Python `pgvector` package is **not yet a dependency** — add it to `backend/pyproject.toml` (`pgvector>=0.3,<0.5`) before importing `pgvector.sqlalchemy` / `pgvector.psycopg`. The Postgres `vector` extension itself ships in the `pgvector/pgvector:pg16` image.

pgvector is the **only** added extension for retrieval (ADR-0006 — no BM25 / `pg_textsearch`). Create it in the migration, matching the repo's existing pattern (`0001_identity_schema.py` does the same for `citext`):

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
# downgrade():
op.execute("DROP EXTENSION IF EXISTS vector")
```

## Column type: `vector` vs `halfvec`

- `vector(N)` — 4 bytes/dim, up to 16000 dims. **Indexable up to 2000 dims.**
- `halfvec(N)` — 2 bytes/dim (half precision), up to 16000 dims storage, **indexable up to 4000 dims**.

Rule: if your embedding has more than 2000 dims (e.g. a 3072-dim model), store it as `halfvec(3072)` and use a `halfvec_*` operator class so it stays indexable. Otherwise `vector(N)` is the default. Because embeddings are derived and re-indexable (ADR-0001), the dimension is fixed by whatever the current `EmbeddingPort` adapter produces — keep the model id in config, not in SQL.

## Distance operators and matching operator classes

The query operator and the index's operator class **must match** or the index will not be used:

| Operator | Distance | `vector` opclass | `halfvec` opclass | pgvector-python method |
|---|---|---|---|---|
| `<=>` | cosine | `vector_cosine_ops` | `halfvec_cosine_ops` | `.cosine_distance(vec)` |
| `<->` | L2 / Euclidean | `vector_l2_ops` | `halfvec_l2_ops` | `.l2_distance(vec)` |
| `<#>` | negative inner product | `vector_ip_ops` | `halfvec_ip_ops` | `.max_inner_product(vec)` |
| `<+>` | L1 / taxicab | `vector_l1_ops` | `halfvec_l1_ops` | `.l1_distance(vec)` |

**Cosine (`<=>` / `vector_cosine_ops`) is the typical default for normalized embeddings**, and it is what Learny's semantic arm uses unless the embedding model dictates otherwise.

## Index: HNSW (default) vs IVFFlat

**Prefer HNSW.** It has better recall/speed and no training step (it can be built on an empty table), which matters because embeddings are re-indexed when the chunking or embedding model changes.

```sql
CREATE INDEX ix_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

- Build params: `m` (default 16) = max connections per layer; `ef_construction` (default 64) = build-time candidate list size.
- Query-time recall knob: `SET hnsw.ef_search = 100;` (default 40). Set it per-connection/transaction from a `LEARNY_`-prefixed setting, not hard-coded.

IVFFlat is an option only with a specific reason (e.g. very large tables where build time/size dominates). It **requires data present before building** (it trains on existing rows):

```sql
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
SET ivfflat.probes = 10;  -- query-time recall knob
```

## pgvector-python with SQLAlchemy Core

The repo uses Core `Table` metadata, so define the column with the `VECTOR` / `HALFVEC` type and call comparator methods on `Table.c.<column>` expressions:

```python
from pgvector.sqlalchemy import VECTOR  # also: HALFVEC

# in app/infrastructure/db/metadata.py, on the chunks Table:
Column("embedding", VECTOR(1536), nullable=False)   # or HALFVEC(3072) when dims > 2000
```

```python
from sqlalchemy import select
from app.infrastructure.db.metadata import chunks

# semantic ordering on a Core column expression; query_vec is a plain list[float]
stmt = (
    select(chunks.c.id, chunks.c.embedding.cosine_distance(query_vec).label("distance"))
    .order_by(chunks.c.embedding.cosine_distance(query_vec))
    .limit(candidate_limit)
)
```

Declaring the HNSW index on the `Table` (so it lives with the metadata) uses the dialect kwargs:

```python
from sqlalchemy import Index

Index(
    "ix_chunks_embedding_hnsw",
    chunks.c.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
```

In practice, prefer emitting the vector index via raw `op.execute(...)` in the Alembic migration (Alembic will not autogenerate HNSW params reliably) — see [schema-and-migrations.md](schema-and-migrations.md).
