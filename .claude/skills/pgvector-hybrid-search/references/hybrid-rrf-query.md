# Hybrid Query with Reciprocal Rank Fusion

The retrieval query runs both arms — pgvector semantic and Postgres FTS lexical — and fuses their ranked candidate lists with **Reciprocal Rank Fusion (RRF)** in a single SQL statement (ADR-0006). It projects **stable citation anchors** (ADR-0003), and the whole query is one testable seam against golden fixtures (ADR-0016).

## Why RRF here

RRF fuses two independently-scored lists using only each row's **rank** within its arm, so it needs no score calibration between cosine distance and `ts_rank_cd` (they are on different scales). For each row, sum over the arms it appears in:

```
score = Σ  1.0 / (k + rank_in_arm)
```

`k` is a smoothing constant (a common starting value is 60). Keep `k` and the per-arm `LIMIT`s in `LEARNY_`-prefixed settings — they are infrastructure tuning, not domain concepts (ADR-0006). Reranking is **out of scope** for the first implementation; do not add a reranker.

## The SQL shape

Two ranked CTEs (one per arm), fused, then joined back for anchor columns:

```sql
WITH semantic AS (
    SELECT
        id AS chunk_id,
        ROW_NUMBER() OVER (ORDER BY embedding <=> :query_vec) AS rank
    FROM chunks
    ORDER BY embedding <=> :query_vec          -- cosine distance (vector_cosine_ops)
    LIMIT :semantic_limit
),
lexical AS (
    SELECT
        id AS chunk_id,
        ROW_NUMBER() OVER (
            ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', :q), 32) DESC
        ) AS rank
    FROM chunks
    WHERE search_vector @@ websearch_to_tsquery('english', :q)
    ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', :q), 32) DESC
    LIMIT :lexical_limit
),
fused AS (
    SELECT
        COALESCE(s.chunk_id, l.chunk_id) AS chunk_id,
        COALESCE(1.0 / (:k + s.rank), 0.0)
          + COALESCE(1.0 / (:k + l.rank), 0.0) AS rrf_score
    FROM semantic s
    FULL OUTER JOIN lexical l ON s.chunk_id = l.chunk_id
)
SELECT
    c.id            AS chunk_id,
    c.section_path,
    c.page_start,
    c.page_end,
    c.source_file_id,
    c.body          AS snippet,        -- or ts_headline(...) for a highlighted excerpt
    f.rrf_score
FROM fused f
JOIN chunks c ON c.id = f.chunk_id
ORDER BY f.rrf_score DESC
LIMIT :top_k;
```

Notes:
- `SET hnsw.ef_search = :ef_search;` (or `ivfflat.probes`) before the query, from settings, to control semantic recall.
- The semantic arm passes a plain `list[float]` bound as `:query_vec` — the embedding vector comes from the `EmbeddingPort`, so no provider SDK appears in this query (ADR-0007). See [embeddings-port.md](embeddings-port.md).
- Use `chunks.c.embedding.cosine_distance(query_vec)` when building this with SQLAlchemy Core expressions instead of raw `<=>`; see [pgvector-columns-and-indexes.md](pgvector-columns-and-indexes.md).

## Citation-anchor projection (ADR-0003)

The `SELECT` MUST return anchor columns, not just a score, so every candidate is independently citable and the retrieval is measurable (recall/precision) against golden fixtures:

- `chunk_id` — stable chunk identifier
- `section_path` — heading/section trail
- page/location span — `page_start` / `page_end` (or location anchors) when available
- `source_file_id` — the owning source reference
- `snippet` — optional excerpt (raw `body` or `ts_headline(...)`)
- plus the fused `rrf_score`

## Repository adapter (Learny conventions)

Mirror `SqlAlchemyUserRepository`: a sync class taking a caller-provided `Connection`, building the statement over the shared metadata, and mapping each `Row` to a frozen domain dataclass via a module-level `_to_x` helper. The transaction/unit-of-work boundary stays at the composition root (worker/web), not in the adapter.

```python
# app/domain/entities.py — pure domain result, no outward imports (ADR-0003 anchors)
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    section_path: str
    page_start: int | None
    page_end: int | None
    source_file_id: UUID
    snippet: str
    score: float
```

```python
# app/infrastructure/db/retrieval.py
from sqlalchemy import Connection, text

from app.domain.entities import RetrievedChunk

_HYBRID_SQL = text("""... the WITH ... SELECT above ...""")


class SqlAlchemyRetrievalRepository:
    """Hybrid retrieval over the chunks table. Takes a caller-provided Connection."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def search(
        self,
        *,
        query_text: str,
        query_vec: list[float],   # plain vector from the EmbeddingPort (ADR-0007)
        top_k: int,
        semantic_limit: int,
        lexical_limit: int,
        k: int,
    ) -> list[RetrievedChunk]:
        rows = self._conn.execute(
            _HYBRID_SQL,
            {
                "q": query_text,
                "query_vec": query_vec,
                "top_k": top_k,
                "semantic_limit": semantic_limit,
                "lexical_limit": lexical_limit,
                "k": k,
            },
        ).all()
        return [_to_retrieved_chunk(r) for r in rows]


def _to_retrieved_chunk(row) -> RetrievedChunk:  # noqa: ANN001 — SQLAlchemy Row
    return RetrievedChunk(
        chunk_id=row.chunk_id,
        section_path=row.section_path,
        page_start=row.page_start,
        page_end=row.page_end,
        source_file_id=row.source_file_id,
        snippet=row.snippet,
        score=row.rrf_score,
    )
```

A `RetrievalPort` `Protocol` (in `app/domain/ports.py`) can front this adapter so application/RAG code depends on the port, not the SQL. Because the query is one seam, golden-fixture tests assert the returned `chunk_id`s and anchors for known question→passage pairs.

Sources: <https://www.postgresql.org/docs/16/textsearch-controls.html>, <https://github.com/pgvector/pgvector>
