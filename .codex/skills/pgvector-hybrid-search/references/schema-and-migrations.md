# Schema and Migrations

The chunks table (embedding + generated `tsvector`, HNSW + GIN indexes) is added the same way the Identity schema was: SQLAlchemy 2.x Core `Table` metadata in `app/infrastructure/db/metadata.py` plus a numbered Alembic migration that uses raw `op.execute(...)` for what Alembic cannot autogenerate. Keep all of this in the **infrastructure** layer — index params and operator classes are not domain concepts (ADR-0006).

Sources: <https://github.com/pgvector/pgvector>, <https://www.postgresql.org/docs/16/textsearch-tables.html>

## Core Table metadata

Add to the **same** `metadata` object in `app/infrastructure/db/metadata.py` (one shared `MetaData(naming_convention=NAMING_CONVENTION)`) so Alembic autogenerate and `--sql` offline mode stay in sync:

```python
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Table, Text, func
from sqlalchemy.dialects.postgresql import UUID

chunks = Table(
    "chunks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_file_id",
        UUID(as_uuid=True),
        ForeignKey("source_files.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("section_path", Text, nullable=False),   # ADR-0003 citation anchor
    Column("page_start", Integer, nullable=True),
    Column("page_end", Integer, nullable=True),
    Column("section_title", Text, nullable=True),
    Column("body", Text, nullable=False),
    Column("embedding", VECTOR(1536), nullable=False),   # HALFVEC(3072) if dims > 2000
    # search_vector (generated tsvector) is added in the migration via raw SQL,
    # since Alembic does not model GENERATED ALWAYS ... STORED columns.
    # Match metadata.py: timezone-aware DateTime with a server-side now() default.
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
```

The generated `search_vector` column and the HNSW/GIN indexes are best emitted as raw SQL in the migration rather than modeled on the `Table`, because Alembic autogenerate does not reliably render `GENERATED ALWAYS ... STORED`, HNSW `WITH (...)` params, or operator classes.

## Alembic migration

Follow the shape of `migrations/versions/0001_identity_schema.py`: numbered revision, `op.execute("CREATE EXTENSION IF NOT EXISTS ...")` for extensions with a matching `DROP` in `downgrade()`, explicit constraint/index names matching `NAMING_CONVENTION`, and `op.create_index` / raw `op.execute` for indexes.

```python
"""chunks: canonical corpus chunks with embedding + full-text search

Revision ID: 0002_chunks_retrieval
Revises: 0001_identity_schema
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

revision = "0002_chunks_retrieval"
down_revision = "0001_identity_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector is the only added retrieval extension (ADR-0006 — no BM25/pg_textsearch).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("embedding", VECTOR(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["source_files.id"],
            name="fk_chunks_source_file_id_source_files",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
    )

    # Generated tsvector: section title 'A' outranks body 'D' (see postgres-fts.md).
    op.execute(
        """
        ALTER TABLE chunks
        ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(section_title, '')), 'A')
            || setweight(to_tsvector('english', coalesce(body, '')), 'D')
        ) STORED
        """
    )

    # HNSW for semantic search — operator class must match the query operator (<=>).
    op.execute(
        """
        CREATE INDEX ix_chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    # GIN for lexical search over the generated tsvector.
    op.execute("CREATE INDEX ix_chunks_search_vector ON chunks USING GIN (search_vector)")
    # Ownership / relational filter lookups.
    op.create_index("ix_chunks_source_file_id", "chunks", ["source_file_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_source_file_id", table_name="chunks")
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_table("chunks")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

Notes:
- Emit index DDL with raw `op.execute` (HNSW params and operator classes are not autogenerated). `--sql` offline mode still works because these are literal statements.
- Keep `vector(N)` / `halfvec(N)` dims aligned with what the `EmbeddingPort` adapter produces; see [pgvector-columns-and-indexes.md](pgvector-columns-and-indexes.md) and [embeddings-port.md](embeddings-port.md).
- `register_vector` (psycopg3 adaptation) is wired in `app/infrastructure/db/engine.py`, not in migrations; see [embeddings-port.md](embeddings-port.md).
