"""SQLAlchemy Core table metadata for the Identity module (design §4).

This is the authoritative schema definition shared by Alembic (migrations) and,
from task B3, the repository adapters. It is Core-level metadata only — no ORM
session/engine and no domain imports, so it stays inside the infrastructure
boundary (ADR-007/009).

Tables:
- ``users``            — id (uuid pk), email (unique, lowercased via citext), created_at
- ``user_credentials`` — user_id (fk), password_hash, algo_params, updated_at
- ``sessions``         — id (uuid pk), user_id (fk), token_hash (unique), csrf_token,
                          expires_at, created_at, last_seen_at
- ``sources``          — id (uuid pk), user_id (fk, indexed), title, filename,
                          content_type, byte_size, checksum, object_key (unique),
                          status, created_at, updated_at
- ``ingestion_jobs``   — id (uuid pk), source_id (fk, indexed), status, attempts,
                          last_error, created_at, updated_at; partial unique index
                          allows at most one active (queued/running) job per source
- ``ingestion_events`` — id (uuid pk), job_id (fk, indexed), type, message, created_at
- ``corpus_documents`` — id (uuid pk), source_id (fk, unique), title, authors (jsonb),
                          language, schema_version, created_at
- ``corpus_sections``  — id (uuid pk), document_id (fk, indexed), position, depth, title,
                          section_path (jsonb), anchor, markdown, created_at;
                          unique (document_id, position)
- ``corpus_blocks``    — id (uuid pk), section_id (fk, indexed), position, block_type,
                          html_fragment, created_at
- ``corpus_chunks``    — id (uuid pk), section_id (fk, indexed), chunk_index, text,
                          section_path (jsonb), anchor, page_span (jsonb, null), created_at

The session cookie carries the raw opaque token; only its hash (``token_hash``)
is persisted (design §4 / AD-006).
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID

# Consistent constraint naming so migrations are deterministic and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    # citext extension is created by the migration; email is case-insensitively unique.
    Column("email", CITEXT, nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

user_credentials = Table(
    "user_credentials",
    metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("password_hash", Text, nullable=False),
    # Argon2id parameters (AD-006) captured for rehash-on-params-change.
    Column("algo_params", JSONB, nullable=False, server_default="{}"),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("token_hash", String(128), nullable=False, unique=True),
    Column("csrf_token", String(128), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

sources = Table(
    "sources",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("title", Text, nullable=False),
    Column("filename", Text, nullable=False),
    Column("content_type", Text, nullable=False),
    Column("byte_size", BigInteger, nullable=False),
    # sha256 hex of the stored bytes; kept for future integrity/dedup (not unique).
    Column("checksum", Text, nullable=False),
    # Opaque owner-partitioned key (sources/{user_id}/{uuid}.epub); no PII.
    Column("object_key", Text, nullable=False, unique=True),
    Column("status", Text, nullable=False, server_default="uploaded"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

ingestion_jobs = Table(
    "ingestion_jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_id",
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Free-text lifecycle status: queued | running | succeeded | failed.
    Column("status", Text, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    # Redacted, non-secret; set on retry/failure.
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Concurrency guard (ING-03): at most one active job per source. Partial so a
    # terminal job never blocks a restart.
    Index(
        "uq_ingestion_jobs_active_source",
        "source_id",
        unique=True,
        postgresql_where=text("status IN ('queued', 'running')"),
    ),
)

ingestion_events = Table(
    "ingestion_events",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "job_id",
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Progress-log entry type: queued | started | retrying | succeeded | failed.
    Column("type", Text, nullable=False),
    # Redacted summary (e.g. error text on retrying/failed); null for plain transitions.
    Column("message", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# --- Canonical corpus aggregate (ADR-0002, Cycle 4 design §Data Models) ---------
# One corpus document per source (unique source_id, CORP-09) with spine-ordered
# sections, their preserved HTML blocks, and structure-first retrieval chunks. Every
# child FK cascades so a source delete removes the whole aggregate (CORP-14).

corpus_documents = Table(
    "corpus_documents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_id",
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    # OPF DC metadata; nullable/empty when the EPUB omits them (CORP-01).
    Column("title", Text, nullable=True),
    Column("authors", JSONB, nullable=False, server_default="[]"),
    Column("language", Text, nullable=True),
    # Corpus schema version, constant 1 until a reshape migration (A-8).
    Column("schema_version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

corpus_sections = Table(
    "corpus_sections",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "document_id",
        UUID(as_uuid=True),
        ForeignKey("corpus_documents.id", ondelete="CASCADE"),
        nullable=False,
        # No standalone index: the (document_id, position) unique below leads on
        # document_id and already serves the FK lookup + ordered structure read.
    ),
    # Spine/TOC reading order (CORP-02) and TOC nesting depth (root = 0).
    Column("position", Integer, nullable=False),
    Column("depth", Integer, nullable=False),
    Column("title", Text, nullable=False),
    # Root-to-node TOC titles for citations (A-1/A-2).
    Column("section_path", JSONB, nullable=False),
    # href[#fragment] location anchor (A-4).
    Column("anchor", Text, nullable=False),
    # Derived Markdown view of this section's blocks (CORP-04).
    Column("markdown", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("document_id", "position"),
)

corpus_blocks = Table(
    "corpus_blocks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "section_id",
        UUID(as_uuid=True),
        ForeignKey("corpus_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Global reading-order position (CORP-03).
    Column("position", Integer, nullable=False),
    Column("block_type", Text, nullable=False),  # heading | paragraph | list | table | ...
    # Preserved outer HTML so the Markdown view can be re-derived (ADR-0002).
    Column("html_fragment", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

corpus_chunks = Table(
    "corpus_chunks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "section_id",
        UUID(as_uuid=True),
        ForeignKey("corpus_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Order within the section (CORP-05).
    Column("chunk_index", Integer, nullable=False),
    Column("text", Text, nullable=False),  # derived Markdown text
    # Denormalized citation anchors carried on the chunk (ADR-0003).
    Column("section_path", JSONB, nullable=False),
    Column("anchor", Text, nullable=False),
    # NULL for EPUB; reserved for PDF page citations (A-9).
    Column("page_span", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
