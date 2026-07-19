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
                          section_path (jsonb), anchor, anchor_aliases (text[]), markdown,
                          created_at; unique (document_id, position)
- ``corpus_blocks``    — id (uuid pk), section_id (fk, indexed), position, block_type,
                          html_fragment, created_at
- ``corpus_chunks``    — id (uuid pk), section_id (fk, indexed), chunk_index, text,
                          section_path (jsonb), anchor, page_span (jsonb, null),
                          embedding (vector(1536), null), embedding_model (text, null),
                          search_config (text, not null), created_at

The session cookie carries the raw opaque token; only its hash (``token_hash``)
is persisted (design §4 / AD-006).

``corpus_chunks.search_vector`` (a plain ``tsvector`` maintained by a ``BEFORE INSERT OR
UPDATE`` trigger, migration ``0007_language_aware_fts``; originally a ``STORED`` generated
column in ``0005_retrieval_indexes``) and the HNSW/GIN retrieval indexes are added via raw
SQL only — they are intentionally *not* modeled on the ``corpus_chunks`` Table below.
Alembic does not reliably render trigger-fed columns, HNSW ``WITH (...)`` params, or
operator classes, and the raw retrieval query does not need them in metadata (ADR-0006).
The trigger owns ``search_vector``, so the app never writes it directly.
"""

from __future__ import annotations

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID

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
    # Anchors normalization merged into this section, kept resolvable as aliases so
    # no saved citation dangles after a re-ingest (AD-085); empty for clean books.
    Column(
        "anchor_aliases",
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'"),
    ),
    # Derived Markdown view of this section's blocks (CORP-04).
    Column("markdown", Text, nullable=False),
    # Whitespace-token count of ``markdown`` (``len(markdown.split())``), stamped at
    # build time and backfilled by 0011, so whole-book percent / minutes-left are
    # derivable without re-parsing. NOT NULL with a DEFAULT 0 so a row is valid before
    # the build sets a real count (0 => no prose, no divide-by-zero downstream).
    Column("word_count", Integer, nullable=False, server_default="0"),
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
    # Normalized-text sha256 the corpus build computes per block (NF-02), used to
    # bind highlight anchors to a block. Nullable, no backfill (AD-111): pre-0010
    # blocks stay NULL until the next re-ingest recomputes them.
    Column("content_hash", Text, nullable=True),
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
    # Async-populated semantic vector for the retrieval semantic arm (RET-01); the
    # deterministic local adapter emits 1536-dim vectors. NULL until (re-)ingestion
    # embeds the chunk. The matching HNSW index is created in 0005 via raw SQL.
    Column("embedding", VECTOR(1536), nullable=True),
    # Provider@dims identity written alongside each vector (EMB-14); NULL until the
    # chunk is embedded. Enables idempotent re-embedding when the model changes.
    Column("embedding_model", Text, nullable=True),
    # Resolved Postgres text-search regconfig for the chunk's language (EMB-08); the
    # 0007 trigger builds ``search_vector`` from it. DB default 'simple' fills it.
    Column("search_config", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# --- Teaching sessions aggregate (Cycle 7 design §Data Models) -------------------
# A session anchors a bounded conversation to one corpus section of a ready source;
# its turns pair a user message with a generated response, and each turn's citations
# are denormalized snapshots (no chunk FK) so history survives corpus re-ingestion
# (AD-033/AD-018). Turn and citation ranks are position-unique within their parent.

teaching_sessions = Table(
    "teaching_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_id",
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Target snapshot: the stable citation anchor plus its section path + title, so
    # the target renders without re-reading the corpus (target resolve is per-turn).
    Column("target_anchor", Text, nullable=False),
    Column("target_section_path", JSONB, nullable=False),
    Column("target_title", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

teaching_turns = Table(
    "teaching_turns",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "session_id",
        UUID(as_uuid=True),
        ForeignKey("teaching_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Zero-based position within the session; the unique below is the turn-index
    # race arbiter (TEACH-17).
    Column("turn_index", Integer, nullable=False),
    Column("message", Text, nullable=False),
    # answered | not_found_in_source (TEACH-07).
    Column("answer_status", Text, nullable=False),
    # Empty for not-found turns, which are still persisted (TEACH-14).
    Column("answer_text", Text, nullable=False, server_default=""),
    Column("model", Text, nullable=False),
    Column("evidence_count", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("session_id", "turn_index"),
)

teaching_turn_citations = Table(
    "teaching_turn_citations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "turn_id",
        UUID(as_uuid=True),
        ForeignKey("teaching_turns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Rank = citation position within the turn (TEACH-20).
    Column("rank", Integer, nullable=False),
    # Snapshot reference only — no FK, so a corpus replace can delete the live chunk
    # without breaking stored history (AD-033).
    Column("chunk_id", UUID(as_uuid=True), nullable=False),
    Column("section_path", JSONB, nullable=False),
    Column("anchor", Text, nullable=False),
    Column("snippet", Text, nullable=False),
    Column("score", Float, nullable=False),
    UniqueConstraint("turn_id", "rank"),
)

# --- Active recall aggregate (Cycle E, RFC-002; design §Data Models) -------------
# Citation-grounded quiz cards per source with a one-per-item FSRS scheduling snapshot
# and an append-only review log; a deck-generation job mirrors ``ingestion_jobs``.
# ``quiz_items``/``quiz_generation_jobs`` cascade from ``sources`` and the scheduling/
# log rows cascade from ``quiz_items``, so a source delete removes the whole aggregate
# with no orphans. Items snapshot their citation (``anchor``/``section_path``/
# ``source_excerpt``) with no FK into the corpus tables, so they survive a corpus
# replace (which regenerates chunk ids). ``embedding`` reuses the vector extension
# (0005) for near-duplicate detection — no index (exact scan at author scale).

quiz_items = Table(
    "quiz_items",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "source_id",
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("item_type", Text, nullable=False),  # free_recall | cloze
    Column("question", Text, nullable=False),
    Column("answer", Text, nullable=False),
    # Root-to-node TOC titles for the citation (snapshot; reconciled on re-ingest).
    Column("section_path", JSONB, nullable=False),
    Column("anchor", Text, nullable=False),
    # Verified anchor_quote snapshot — survives a corpus replace (no chunk FK).
    Column("source_excerpt", Text, nullable=False),
    # sha256 of the chunk text at generation time.
    Column("chunk_hash", Text, nullable=False),
    # sha256(item_type \x1f norm(question) \x1f norm(answer)) — upsert identity.
    Column("content_key", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),  # active|stale|orphaned
    # Near-duplicate detection identity; NULL until embedded (vector ext from 0005).
    Column("embedding", VECTOR(1536), nullable=True),
    Column("generation_meta", JSONB, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Deck regeneration upserts on this identity without minting duplicates (QUIZ-02).
    UniqueConstraint("source_id", "content_key"),
)

quiz_item_scheduling = Table(
    "quiz_item_scheduling",
    metadata,
    Column(
        "quiz_item_id",
        UUID(as_uuid=True),
        ForeignKey("quiz_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    # FSRS-6 snapshot columns (State enum int, learning step, memory params).
    Column("state", SmallInteger, nullable=False),
    Column("step", SmallInteger, nullable=True),
    Column("stability", Float, nullable=True),
    Column("difficulty", Float, nullable=True),
    Column("due", DateTime(timezone=True), nullable=False, index=True),
    Column("last_review", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

review_log = Table(
    "review_log",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "quiz_item_id",
        UUID(as_uuid=True),
        ForeignKey("quiz_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("rating", SmallInteger, nullable=False),
    Column("reviewed_at", DateTime(timezone=True), nullable=False),
    Column("review_duration_ms", Integer, nullable=True),
    # FSRS Rating is Again(1)/Hard(2)/Good(3)/Easy(4) — no other value is valid.
    CheckConstraint("rating BETWEEN 1 AND 4", name="rating_range"),
)

quiz_generation_jobs = Table(
    "quiz_generation_jobs",
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
    # Terminal-success counts (QUIZ-09).
    Column("generated_count", Integer, nullable=False, server_default="0"),
    Column("discarded_count", Integer, nullable=False, server_default="0"),
    Column("failed_sections", Integer, nullable=False, server_default="0"),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# --- Notes & second-brain aggregate (RFC-003 Cycle E; ADR-0026 §1-2) -------------
# Whole-Markdown notes owned by a user, with book-citation ``note_anchors``, first-
# class ``tags``/``note_tags``, and wikilink-derived ``note_links``. THE INVERSE-
# CASCADE RULE IS THE CORE INVARIANT: no note table FKs into ``corpus_*``/``sources``
# — ``note_anchors.source_id`` is a bare UUID — so a source delete or corpus replace
# can never destroy user prose. The only cascades are within the aggregate (notes
# from users; anchors/tags/links from notes; note_tags from tags). A deleted note's
# inbound ``note_links`` are SET NULL, keeping their ``target_text``.

notes = Table(
    "notes",
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
    Column("body_markdown", Text, nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

note_anchors = Table(
    "note_anchors",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "note_id",
        UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Bare UUID — deliberately NOT a foreign key (inverse-cascade invariant).
    Column("source_id", UUID(as_uuid=True), nullable=False, index=True),
    # Snapshots so an orphaned anchor still renders without the corpus.
    Column("source_title", Text, nullable=False),
    Column("anchor", Text, nullable=False),
    Column("section_path", JSONB, nullable=False),
    # Block binding — NULL when the block was unhashed/unresolved; the quote snapshot
    # then carries the anchor.
    Column("block_hash", Text, nullable=True),
    Column("block_ordinal", Integer, nullable=True),
    Column("start_offset", Integer, nullable=True),
    Column("end_offset", Integer, nullable=True),
    # Quote-with-context snapshot (exact + 32-char prefix/suffix, ADR-0026 §1).
    Column("quote_exact", Text, nullable=False),
    Column("quote_prefix", Text, nullable=False, server_default=""),
    Column("quote_suffix", Text, nullable=False, server_default=""),
    Column("status", Text, nullable=False, server_default="active"),  # active|stale|orphaned
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

tags = Table(
    "tags",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # Stored already-lowercased by the application; the unique below is the per-user
    # identity so two casings of the same tag never coexist.
    Column("name", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "name"),
)

note_tags = Table(
    "note_tags",
    metadata,
    Column(
        "note_id",
        UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)

note_links = Table(
    "note_links",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "note_id",
        UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    # Resolved wikilink target; NULL when the [[title]] matches no note, and SET NULL
    # (never deleted) when a resolved target note is later deleted.
    Column(
        "target_note_id",
        UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    # Always-populated raw link text so an unresolved/broken link still renders.
    Column("target_text", Text, nullable=False),
)

# --- Reader progress (RFC-004 Cycle B; design §Data Models) ----------------------
# One row per (user, source) recording where the reader stopped: the resolved
# section ``anchor`` and the server-computed whole-book ``percent`` at it. Both FKs
# cascade — unlike a note anchor this is disposable reading state, not user prose, so
# deleting a user or source removes their positions. Last-write-wins on the (user,
# source) primary key via ``INSERT ... ON CONFLICT DO UPDATE``.

reading_positions = Table(
    "reading_positions",
    metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "source_id",
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("anchor", Text, nullable=False),
    Column("percent", Numeric(precision=5, scale=2), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
