"""A4 gate — migration tooling applies the identity schema.

This test runs the real Alembic upgrade/downgrade against a Postgres test DB
when ``LEARNY_TEST_DATABASE_URL`` is set (e.g. under Docker Compose or CI). When
no DB is reachable it is skipped — the migration scripts are still validated for
import/compile by ``test_migration_metadata_compiles``.
"""

from __future__ import annotations

import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

TEST_DB_URL = os.environ.get("LEARNY_TEST_DATABASE_URL")


def _alembic_config(db_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_metadata_compiles() -> None:
    """The shared metadata defines the identity + sources + ingestion + corpus tables."""
    from app.infrastructure.db.metadata import (
        corpus_documents,
        corpus_sections,
        ingestion_jobs,
        metadata,
        sessions,
        sources,
        users,
    )

    assert set(metadata.tables) == {
        "users",
        "user_credentials",
        "sessions",
        "sources",
        "ingestion_jobs",
        "ingestion_events",
        "corpus_documents",
        "corpus_sections",
        "corpus_blocks",
        "corpus_chunks",
    }
    # Unique email + unique session token_hash are the security-critical constraints.
    user_uniques = {c.name for c in users.constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert any("email" in name for name in user_uniques)
    session_uniques = {
        c.name for c in sessions.constraints if c.__class__.__name__ == "UniqueConstraint"
    }
    assert any("token_hash" in name for name in session_uniques)
    # Opaque object_key is unique so a stored blob maps to at most one source row.
    source_uniques = {
        c.name for c in sources.constraints if c.__class__.__name__ == "UniqueConstraint"
    }
    assert any("object_key" in name for name in source_uniques)
    # The active-source guard is a *partial* unique index on source_id (ING-03).
    active_index = {ix.name: ix for ix in ingestion_jobs.indexes}["uq_ingestion_jobs_active_source"]
    assert active_index.unique
    assert [c.name for c in active_index.columns] == ["source_id"]
    # One corpus per source: UNIQUE(source_id) backstops CORP-09 at the schema layer.
    document_uniques = {
        tuple(c.name for c in uc.columns)
        for uc in corpus_documents.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("source_id",) in document_uniques
    # Sections are position-unique within a document (stable spine/TOC ordering).
    section_uniques = {
        tuple(c.name for c in uc.columns)
        for uc in corpus_sections.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("document_id", "position") in section_uniques


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_up_creates_identity_tables(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {"users", "user_credentials", "sessions"} <= tables
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(TEST_DB_URL)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "users" not in tables
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0002_creates_sources_table(monkeypatch) -> None:
    """0002 creates ``sources`` with the FK, user_id index, and unique object_key."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        inspector = inspect(engine)
        assert "sources" in set(inspector.get_table_names())

        fks = inspector.get_foreign_keys("sources")
        user_fk = next(fk for fk in fks if fk["constrained_columns"] == ["user_id"])
        assert user_fk["referred_table"] == "users"
        assert user_fk["options"].get("ondelete") == "CASCADE"

        index_columns = [ix["column_names"] for ix in inspector.get_indexes("sources")]
        assert ["user_id"] in index_columns

        unique_columns = [uc["column_names"] for uc in inspector.get_unique_constraints("sources")]
        assert ["object_key"] in unique_columns
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(TEST_DB_URL)
    try:
        assert "sources" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0003_creates_ingestion_tables(monkeypatch) -> None:
    """0003 creates ingestion_jobs/ingestion_events with cascade FKs and indexes."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"ingestion_jobs", "ingestion_events"} <= tables

        job_fk = next(
            fk
            for fk in inspector.get_foreign_keys("ingestion_jobs")
            if fk["constrained_columns"] == ["source_id"]
        )
        assert job_fk["referred_table"] == "sources"
        assert job_fk["options"].get("ondelete") == "CASCADE"

        event_fk = next(
            fk
            for fk in inspector.get_foreign_keys("ingestion_events")
            if fk["constrained_columns"] == ["job_id"]
        )
        assert event_fk["referred_table"] == "ingestion_jobs"
        assert event_fk["options"].get("ondelete") == "CASCADE"

        job_index_columns = [ix["column_names"] for ix in inspector.get_indexes("ingestion_jobs")]
        assert ["source_id"] in job_index_columns
        event_index_columns = [
            ix["column_names"] for ix in inspector.get_indexes("ingestion_events")
        ]
        assert ["job_id"] in event_index_columns

        # The active-job guard must be a *partial* unique index (WHERE status IN
        # (...)) — a plain unique on source_id would wrongly block restart (ING-05).
        with engine.connect() as conn:
            indexdef = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_ingestion_jobs_active_source'"
                )
            ).scalar_one()
        assert "UNIQUE" in indexdef
        assert "source_id" in indexdef
        assert "queued" in indexdef and "running" in indexdef
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(TEST_DB_URL)
    try:
        remaining = set(inspect(engine).get_table_names())
        assert "ingestion_jobs" not in remaining
        assert "ingestion_events" not in remaining
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0004_creates_corpus_tables(monkeypatch) -> None:
    """0004 creates the corpus aggregate with cascade FKs, uniques, and FK indexes."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "corpus_documents",
            "corpus_sections",
            "corpus_blocks",
            "corpus_chunks",
        } <= tables

        # The whole aggregate cascades from its parent so a source delete leaves
        # no orphaned corpus rows (CORP-14): document→source, section→document,
        # block/chunk→section, every FK ondelete=CASCADE.
        doc_fk = next(
            fk
            for fk in inspector.get_foreign_keys("corpus_documents")
            if fk["constrained_columns"] == ["source_id"]
        )
        assert doc_fk["referred_table"] == "sources"
        assert doc_fk["options"].get("ondelete") == "CASCADE"

        section_fk = next(
            fk
            for fk in inspector.get_foreign_keys("corpus_sections")
            if fk["constrained_columns"] == ["document_id"]
        )
        assert section_fk["referred_table"] == "corpus_documents"
        assert section_fk["options"].get("ondelete") == "CASCADE"

        block_fk = next(
            fk
            for fk in inspector.get_foreign_keys("corpus_blocks")
            if fk["constrained_columns"] == ["section_id"]
        )
        assert block_fk["referred_table"] == "corpus_sections"
        assert block_fk["options"].get("ondelete") == "CASCADE"

        chunk_fk = next(
            fk
            for fk in inspector.get_foreign_keys("corpus_chunks")
            if fk["constrained_columns"] == ["section_id"]
        )
        assert chunk_fk["referred_table"] == "corpus_sections"
        assert chunk_fk["options"].get("ondelete") == "CASCADE"

        # One corpus per source (CORP-09) and position-unique sections (CORP-02).
        doc_uniques = [
            uc["column_names"] for uc in inspector.get_unique_constraints("corpus_documents")
        ]
        assert ["source_id"] in doc_uniques
        section_uniques = [
            uc["column_names"] for uc in inspector.get_unique_constraints("corpus_sections")
        ]
        assert ["document_id", "position"] in section_uniques

        # Sections carry no standalone document_id index — the (document_id,
        # position) unique above covers the FK lookup and ordered structure read.
        section_indexes = [ix["column_names"] for ix in inspector.get_indexes("corpus_sections")]
        assert ["document_id"] not in section_indexes
        # Blocks/chunks are indexed on their parent FK for the ordered reads.
        block_indexes = [ix["column_names"] for ix in inspector.get_indexes("corpus_blocks")]
        assert ["section_id"] in block_indexes
        chunk_indexes = [ix["column_names"] for ix in inspector.get_indexes("corpus_chunks")]
        assert ["section_id"] in chunk_indexes
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(TEST_DB_URL)
    try:
        remaining = set(inspect(engine).get_table_names())
        assert "corpus_documents" not in remaining
        assert "corpus_sections" not in remaining
        assert "corpus_blocks" not in remaining
        assert "corpus_chunks" not in remaining
    finally:
        engine.dispose()


def _seed_chunk(engine, *, text_body: str, section_title: str) -> uuid.UUID:
    """Insert a minimal users→source→document→section→chunk chain; return the chunk id."""
    user_id = uuid.uuid4()
    source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    section_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :email)"),
            {"id": user_id, "email": f"{user_id}@example.test"},
        )
        conn.execute(
            text(
                "INSERT INTO sources "
                "(id, user_id, title, filename, content_type, byte_size, checksum, object_key) "
                "VALUES (:id, :uid, 't', 'f.epub', 'application/epub+zip', 1, 'c', :key)"
            ),
            {"id": source_id, "uid": user_id, "key": f"sources/{source_id}.epub"},
        )
        conn.execute(
            text("INSERT INTO corpus_documents (id, source_id) VALUES (:id, :sid)"),
            {"id": document_id, "sid": source_id},
        )
        conn.execute(
            text(
                "INSERT INTO corpus_sections "
                "(id, document_id, position, depth, title, section_path, anchor, markdown) "
                "VALUES (:id, :did, 0, 0, :title, :path, 'a.xhtml', 'md')"
            ),
            {
                "id": section_id,
                "did": document_id,
                "title": section_title,
                "path": f'["{section_title}"]',
            },
        )
        conn.execute(
            text(
                "INSERT INTO corpus_chunks "
                "(id, section_id, chunk_index, text, section_path, anchor) "
                "VALUES (:id, :sid, 0, :body, :path, 'a.xhtml')"
            ),
            {
                "id": chunk_id,
                "sid": section_id,
                "body": text_body,
                "path": f'["{section_title}"]',
            },
        )
    return chunk_id


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0005_upgrade_adds_retrieval_columns_indexes(monkeypatch) -> None:
    """0005 up: the vector extension + a nullable embedding and a generated
    search_vector column on corpus_chunks, backed by HNSW + GIN indexes; a seeded
    chunk's search_vector is auto-populated from title ('A') and body ('D')
    (RET-01, RET-02, RET-03)."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        # RET-01: the vector extension exists after the migration.
        with engine.connect() as conn:
            ext = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
        assert ext == 1

        # RET-01: corpus_chunks gains nullable embedding + generated search_vector.
        columns = {c["name"]: c for c in inspect(engine).get_columns("corpus_chunks")}
        assert "embedding" in columns
        assert columns["embedding"]["nullable"] is True
        assert "search_vector" in columns

        # RET-02: HNSW index on embedding (vector_cosine_ops, m=16, ef_construction=64)
        # and GIN index on search_vector both exist.
        with engine.connect() as conn:
            hnsw_def = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_corpus_chunks_embedding_hnsw'"
                )
            ).scalar_one()
            gin_def = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_corpus_chunks_search_vector'"
                )
            ).scalar_one()
        assert "hnsw" in hnsw_def and "vector_cosine_ops" in hnsw_def
        assert "m='16'" in hnsw_def.replace(" ", "") or "m=16" in hnsw_def.replace(" ", "")
        assert "ef_construction" in hnsw_def
        assert "gin" in gin_def.lower() and "search_vector" in gin_def

        # RET-03: the generated search_vector is populated automatically (no app write).
        chunk_id = _seed_chunk(engine, text_body="the quick brown fox", section_title="Intro")
        with engine.connect() as conn:
            sv = conn.execute(
                text("SELECT search_vector::text FROM corpus_chunks WHERE id = :id"),
                {"id": chunk_id},
            ).scalar_one()
        assert sv and sv.strip() != ""
        assert "brown" in sv  # body lexeme present
        assert "intro" in sv  # title lexeme present (weighted 'A')
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0005_downgrade_removes_retrieval_columns_indexes(monkeypatch) -> None:
    """0005 down (one step to 0004): drops both indexes, both columns, and the vector
    extension while leaving the Phase-5 corpus_chunks shape intact (RET-04)."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004_corpus_schema")
    engine = create_engine(TEST_DB_URL)
    try:
        assert "corpus_chunks" in set(inspect(engine).get_table_names())
        columns = {c["name"] for c in inspect(engine).get_columns("corpus_chunks")}
        assert "embedding" not in columns
        assert "search_vector" not in columns
        with engine.connect() as conn:
            remaining_ix = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE indexname IN "
                    "('ix_corpus_chunks_embedding_hnsw', 'ix_corpus_chunks_search_vector')"
                )
            ).fetchall()
            ext = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
        assert remaining_ix == []
        assert ext is None  # the vector extension is dropped on downgrade (AC4)
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")

    command.downgrade(cfg, "base")
