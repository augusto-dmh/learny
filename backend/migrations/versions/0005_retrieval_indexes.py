"""Retrieval indexes: embedding + generated search_vector on corpus_chunks

Adds the hybrid retrieval substrate over the Phase-5 corpus (ADR-0006). Creates the
``vector`` extension and, on ``corpus_chunks``:

- ``embedding vector(1536)`` — **nullable**, async-populated by the ingestion embed step;
- ``search_vector tsvector GENERATED ALWAYS AS (...) STORED`` — section title
  (``section_path ->> -1``) weighted ``'A'`` over ``text`` weighted ``'D'``, auto-maintained
  by Postgres (populated for existing rows at ``ALTER`` time, RET-03);
- an HNSW index (``vector_cosine_ops``, ``m=16, ef_construction=64``) on ``embedding`` and a
  GIN index on ``search_vector``.

The generated column and both indexes are emitted via raw ``op.execute`` — Alembic does not
model ``GENERATED … STORED`` columns, HNSW ``WITH (...)`` params, or operator classes.
``downgrade`` drops both indexes, both columns, then the extension, leaving the Phase-5
``corpus_chunks`` shape intact (RET-04).

Revision ID: 0005_retrieval_indexes
Revises: 0004_corpus_schema
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_retrieval_indexes"
down_revision: str | None = "0004_corpus_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector is the only added retrieval extension (ADR-0006 — no BM25/pg_textsearch).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Nullable: embeddings are async-populated by the ingestion embed step (A-8).
    op.execute("ALTER TABLE corpus_chunks ADD COLUMN embedding vector(1536)")

    # Generated tsvector: deepest TOC title ('A') outranks body text ('D'). The
    # 2-arg constant-config to_tsvector and ->> are IMMUTABLE → valid in a STORED
    # generated column, which auto-populates existing rows at ALTER time (RET-03).
    op.execute(
        """
        ALTER TABLE corpus_chunks
        ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(section_path ->> -1, '')), 'A')
            || setweight(to_tsvector('english', coalesce(text, '')), 'D')
        ) STORED
        """
    )

    # HNSW for the semantic arm — operator class must match the query operator (<=>).
    op.execute(
        """
        CREATE INDEX ix_corpus_chunks_embedding_hnsw
        ON corpus_chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    # GIN for the lexical arm over the generated tsvector.
    op.execute(
        "CREATE INDEX ix_corpus_chunks_search_vector ON corpus_chunks USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_corpus_chunks_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_corpus_chunks_embedding_hnsw")
    op.execute("ALTER TABLE corpus_chunks DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE corpus_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
