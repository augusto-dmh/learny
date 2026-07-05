# The canonical corpus (ADR-0002 / ADR-0001)

The canonical corpus is the **rich structured store** produced first from the EPUB. Markdown and retrieval chunks are **derived views**, never the canonical store (ADR-0002). The skill's job ends at a durable, structured, citable corpus (ADR-0001); retrieval/answering is downstream.

## Hard rules

- **Rich structure first, derive second.** Store structured records + preserved HTML fragments. Generate Markdown/chunks *from* those records — do not re-parse the raw EPUB to make chunks.
- **No flat-chunks-only.** A pipeline that splits the whole book into flat text chunks and stores nothing else is forbidden (ADR-0002). Preserve headings, sections, tables, figures, footnotes, source offsets, and extraction confidence.
- **Schema + versioning discipline.** The canonical schema is deliberate and versioned (ADR-0002 negative consequence). Carry a `schema_version` on the document record so re-processing and migrations are explicit.
- **Postgres owns metadata/ownership/status/keys.** The original EPUB bytes stay in S3 (ADR-0013); never store the file as a DB blob.

## Fields to preserve per record

- Book level: title, creators, language, identifier, `source_object_key`, `schema_version`, ingestion status.
- Section/passage level: `section_path` (from TOC), heading text + level, ordered `position` (from spine), `anchor` (href[#fragment]), preserved `html_fragment`, `extraction_confidence`, and a **nullable `page_span`** reserved for future PDF (ADR-0011).
- Derived: Markdown text and retrieval chunks, each linked back to the canonical record and carrying citation anchors (see references/citations-and-anchors.md).

## Express it as SQLAlchemy Core (match `app/infrastructure/db/metadata.py`)

Use the **shared** `NAMING_CONVENTION` and `metadata` object already defined in `app/infrastructure/db/metadata.py` — do not create a second `MetaData`. Follow the existing conventions exactly: UUID PKs, `JSONB` for structured payloads, `DateTime(timezone=True)` with `server_default=func.now()`, FK `ondelete="CASCADE"`. This is Core `Table` metadata, **not** ORM models.

```python
"""Canonical corpus tables for EPUB ingestion (ADR-0002 / ADR-0011 / ADR-0013).

Core-level schema shared by Alembic and the ingestion repositories. No ORM
session/engine, no domain imports — stays inside the infrastructure boundary
(ADR-0009). Mirrors the conventions in the Identity metadata module.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Reuse the shared metadata + NAMING_CONVENTION already defined for the project.
from app.infrastructure.db.metadata import metadata

# One row per ingested book: ownership, S3 object key, status, schema version.
documents = Table(
    "documents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "owner_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source_object_key", Text, nullable=False),   # S3 key (ADR-0013) — not a path/blob
    Column("title", Text, nullable=True),
    Column("metadata", JSONB, nullable=False, server_default="{}"),  # DC creators/language/etc.
    Column("schema_version", Integer, nullable=False, server_default="1"),
    Column("status", String(32), nullable=False, server_default="pending"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Ordered structural records: the RICH canonical layer (structure + preserved HTML).
corpus_nodes = Table(
    "corpus_nodes",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "document_id",
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("position", Integer, nullable=False),          # reading order from book.spine
    Column("section_path", JSONB, nullable=False),        # TOC path, e.g. ["Part I", "Ch. 3"]
    Column("heading", Text, nullable=True),
    Column("heading_level", Integer, nullable=True),
    Column("anchor", Text, nullable=False),               # href[#fragment] — stable location
    Column("page_span", JSONB, nullable=True),            # NULL for EPUB; reserved for PDF
    Column("html_fragment", Text, nullable=False),        # preserved BODY HTML (ADR-0002)
    Column("extraction_confidence", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# DERIVED retrieval chunks (ADR-0001): generated FROM corpus_nodes, linked back for citations.
corpus_chunks = Table(
    "corpus_chunks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "node_id",
        UUID(as_uuid=True),
        ForeignKey("corpus_nodes.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("chunk_index", Integer, nullable=False),
    Column("text", Text, nullable=False),                 # derived Markdown/plain text
    Column("section_path", JSONB, nullable=False),        # copied for citation traceability
    Column("anchor", Text, nullable=False),
    Column("page_span", JSONB, nullable=True),            # NULL for EPUB
    Column("snippet", Text, nullable=True),               # optional source snippet
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
```

Notes:

- `page_span` is `nullable` on every layer — EPUB writes `NULL`; future PDF fills it (ADR-0011 flexibility requirement).
- Repositories over these tables take a caller-provided `Connection` with the transaction boundary at the composition root, exactly like `app/infrastructure/db/repositories.py`.
- Bump `schema_version` and write an Alembic migration when the canonical shape changes; keep old rows migratable (ADR-0002 versioning discipline).

Official references: W3C EPUB 3.3 https://www.w3.org/TR/epub-33/ ; SQLAlchemy 2.x Core Metadata/Table https://docs.sqlalchemy.org/en/20/core/metadata.html
