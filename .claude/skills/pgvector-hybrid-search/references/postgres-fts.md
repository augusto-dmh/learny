# PostgreSQL Full-Text Search (lexical arm)

Learny's lexical arm uses **PostgreSQL built-in full-text search only** — `tsvector`/`tsquery`/`ts_rank` (ADR-0006). Do **not** add a BM25, `pg_textsearch`, or any non-core extension. This gives exact-term, section-title, and citation-sensitive matching that pure vector search misses.

Sources: <https://www.postgresql.org/docs/16/textsearch-controls.html>, <https://www.postgresql.org/docs/16/textsearch-tables.html>

## Building the query text

- `to_tsvector([config regconfig,] document text) -> tsvector` — normalizes a document into lexemes.
- `websearch_to_tsquery([config,] querytext) -> tsquery` — **the safe user-facing parser**: it never errors on arbitrary input and supports quoted `"phrases"` and `-negation`. Prefer it over `plainto_tsquery`/`phraseto_tsquery` for search-box input.
- Always pass the **2-arg form with an explicit config** (`'english'`) in indexes, generated columns, and queries so the stored and query-time vectors use the same configuration:

```sql
SELECT to_tsvector('english', body) @@ websearch_to_tsquery('english', :q);
```

## Weighting: `setweight` A–D

`setweight(tsvector, 'A'|'B'|'C'|'D')` labels lexemes so some fields outrank others. Concatenate weighted vectors with `||`. Learny weights **section titles `'A'`** above **body text `'D'`** so title hits surface first:

```sql
setweight(to_tsvector('english', coalesce(section_title, '')), 'A')
    || setweight(to_tsvector('english', coalesce(body, '')), 'D')
```

`coalesce(col, '')` guards NULLs (concatenating a NULL `tsvector` yields NULL).

## Scoring: `ts_rank_cd`

`ts_rank_cd([weights float4[],] vector tsvector, query tsquery [, normalization integer]) -> float4` — cover-density ranking, which suits passage/chunk ranking because it accounts for how close and how often query terms appear.

- Default weight array is `{0.1, 0.2, 0.4, 1.0}` for `{D, C, B, A}` — so `'A'` (titles) contribute the most.
- The `normalization` integer is a bitmask controlling document-length impact, e.g. `1` divides by `1 + log(document length)`, `2` divides by the document length, `4` by mean harmonic distance between extents (`ts_rank_cd` only); `32` divides the rank by itself + 1, scaling it into `0..1` (`rank/(rank+1)`). Combine with `|`.

```sql
ts_rank_cd(search_vector, websearch_to_tsquery('english', :q), 32) AS lexical_score
```

## Stored generated `tsvector` column + GIN index

Prefer a `STORED` generated column so the `tsvector` is maintained automatically and stays GIN-indexable:

```sql
ALTER TABLE chunks
    ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(section_title, '')), 'A')
        || setweight(to_tsvector('english', coalesce(body, '')), 'D')
    ) STORED;

CREATE INDEX ix_chunks_search_vector ON chunks USING GIN (search_vector);
```

Alternative when a stored column is unwanted: an expression GIN index

```sql
CREATE INDEX ix_chunks_body_fts ON chunks USING GIN (to_tsvector('english', body));
```

The stored-column approach is preferred for Learny because the weighted title-vs-body vector is reused by every query and by golden-fixture tests. See [schema-and-migrations.md](schema-and-migrations.md) for the Alembic shape (the generated column and GIN index are emitted via raw `op.execute`).
