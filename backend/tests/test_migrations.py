"""A4 gate — migration tooling applies the identity schema.

This test runs the real Alembic upgrade/downgrade against a Postgres test DB
when ``LEARNY_TEST_DATABASE_URL`` is set (e.g. under Docker Compose or CI). When
no DB is reachable it is skipped — the migration scripts are still validated for
import/compile by ``test_migration_metadata_compiles``.
"""

from __future__ import annotations

import logging
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.logging import SensitiveDataFilter

TEST_DB_URL = os.environ.get("LEARNY_TEST_DATABASE_URL")


def _alembic_config(db_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture(autouse=True, scope="module")
def _restore_schema_to_head() -> None:
    """Leave the shared test DB migrated to ``head`` after this module.

    These tests deliberately ``downgrade(..., "base")`` and commit the dropped
    schema. The session-scoped ``db_engine`` fixture (conftest) runs its
    upgrade-to-head only once — the first time any test requests ``db_conn`` — so
    if a DB-using module runs *after* this one (which depends on test ordering),
    it would otherwise find no schema. Restoring head on teardown makes the shared
    database consistent regardless of which module first touches it.
    """
    yield
    if TEST_DB_URL is not None:
        command.upgrade(_alembic_config(TEST_DB_URL), "head")


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
        "teaching_sessions",
        "teaching_turns",
        "teaching_turn_citations",
        "quiz_items",
        "quiz_item_scheduling",
        "review_log",
        "quiz_generation_jobs",
        "notes",
        "note_anchors",
        "tags",
        "note_tags",
        "note_links",
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
def test_upgrade_honors_caller_provided_url(monkeypatch) -> None:
    """env.py must not clobber an explicitly configured URL with settings (F4).

    The session test bootstrap configures the test-database URL via
    ``Config.set_main_option`` only. When ``env.py`` overrode it with the
    settings-resolved URL, first-run migrations landed on the dev database and
    the earliest-collected DB tests failed on a fresh test database. Point the
    settings URL at a dead endpoint: if env.py prefers settings over the
    caller's URL, this upgrade fails to connect.
    """
    from app.core.config import get_settings

    monkeypatch.setenv(
        "LEARNY_DATABASE_URL", "postgresql+psycopg://nobody:wrong@127.0.0.1:9/nowhere"
    )
    get_settings.cache_clear()
    try:
        command.upgrade(_alembic_config(TEST_DB_URL), "head")
    finally:
        get_settings.cache_clear()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_upgrade_falls_back_to_settings_url(monkeypatch) -> None:
    """Without a caller-provided URL, env.py resolves the settings URL.

    This is the CLI/container path (`alembic upgrade head` with no programmatic
    Config): the settings-resolved ``LEARNY_DATABASE_URL`` must be injected when
    the caller set nothing, or containers stop migrating on boot.
    """
    from app.core.config import get_settings

    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")  # no set_main_option
    finally:
        get_settings.cache_clear()


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


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0006_creates_teaching_tables(monkeypatch) -> None:
    """0006 creates the teaching aggregate with cascade FKs, a no-FK snapshot
    chunk_id, the turn-index/citation-rank uniques, and FK indexes."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "teaching_sessions",
            "teaching_turns",
            "teaching_turn_citations",
        } <= tables

        # Session→source, turn→session, citation→turn all cascade so a source delete
        # removes the whole aggregate with no orphans.
        session_fk = next(
            fk
            for fk in inspector.get_foreign_keys("teaching_sessions")
            if fk["constrained_columns"] == ["source_id"]
        )
        assert session_fk["referred_table"] == "sources"
        assert session_fk["options"].get("ondelete") == "CASCADE"

        turn_fk = next(
            fk
            for fk in inspector.get_foreign_keys("teaching_turns")
            if fk["constrained_columns"] == ["session_id"]
        )
        assert turn_fk["referred_table"] == "teaching_sessions"
        assert turn_fk["options"].get("ondelete") == "CASCADE"

        citation_fk = next(
            fk
            for fk in inspector.get_foreign_keys("teaching_turn_citations")
            if fk["constrained_columns"] == ["turn_id"]
        )
        assert citation_fk["referred_table"] == "teaching_turns"
        assert citation_fk["options"].get("ondelete") == "CASCADE"

        # chunk_id is a snapshot reference — deliberately NOT a foreign key (AD-033),
        # so a corpus replace can delete the live chunk without breaking history.
        citation_fk_columns = [
            fk["constrained_columns"]
            for fk in inspector.get_foreign_keys("teaching_turn_citations")
        ]
        assert ["chunk_id"] not in citation_fk_columns

        # Position uniques: one turn per (session, turn_index) is the race arbiter
        # (TEACH-17); one citation per (turn, rank) fixes citation order (TEACH-20).
        turn_uniques = [
            uc["column_names"] for uc in inspector.get_unique_constraints("teaching_turns")
        ]
        assert ["session_id", "turn_index"] in turn_uniques
        citation_uniques = [
            uc["column_names"] for uc in inspector.get_unique_constraints("teaching_turn_citations")
        ]
        assert ["turn_id", "rank"] in citation_uniques

        # Each child is indexed on its parent FK for the ordered reads.
        session_indexes = [ix["column_names"] for ix in inspector.get_indexes("teaching_sessions")]
        assert ["source_id"] in session_indexes
        turn_indexes = [ix["column_names"] for ix in inspector.get_indexes("teaching_turns")]
        assert ["session_id"] in turn_indexes
        citation_indexes = [
            ix["column_names"] for ix in inspector.get_indexes("teaching_turn_citations")
        ]
        assert ["turn_id"] in citation_indexes
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(TEST_DB_URL)
    try:
        remaining = set(inspect(engine).get_table_names())
        assert "teaching_sessions" not in remaining
        assert "teaching_turns" not in remaining
        assert "teaching_turn_citations" not in remaining
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0007_upgrade_language_aware_search_vector(monkeypatch) -> None:
    """0007 up: replaces the generated search_vector with a trigger-fed plain
    tsvector keyed on each chunk's own search_config, and adds embedding_model +
    search_config columns (EMB-07/08/09). A seeded chunk is auto-populated under
    its default 'simple' config; switching a row's config to 'portuguese' recomputes
    the tsvector with that language's stemmer — proving the per-row regconfig."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("corpus_chunks")}
        # EMB-07: nullable embedding_model.
        assert "embedding_model" in columns
        assert columns["embedding_model"]["nullable"] is True
        # EMB-08: NOT NULL search_config defaulting to 'simple'.
        assert "search_config" in columns
        assert columns["search_config"]["nullable"] is False
        assert "search_vector" in columns

        # EMB-09: the GIN index is rebuilt over the (now plain) search_vector.
        with engine.connect() as conn:
            gin_def = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_corpus_chunks_search_vector'"
                )
            ).scalar_one()
        assert "gin" in gin_def.lower() and "search_vector" in gin_def

        # The trigger populates search_vector on insert under the default 'simple'
        # config: 'simple' does not stem, so the raw body/title lexemes appear.
        chunk_id = _seed_chunk(engine, text_body="the quick brown fox", section_title="Intro")
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT search_config, search_vector::text AS sv "
                    "FROM corpus_chunks WHERE id = :id"
                ),
                {"id": chunk_id},
            ).one()
        assert row.search_config == "simple"
        assert row.sv and "brown" in row.sv and "intro" in row.sv

        # Per-row regconfig: updating search_config (and a Portuguese body) fires the
        # BEFORE UPDATE OF trigger and re-stems under 'portuguese' — the gerund
        # 'correndo' collapses to the lemma 'corr', which 'simple' would never do.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE corpus_chunks "
                    "SET text = 'as criancas estavam correndo', search_config = 'portuguese' "
                    "WHERE id = :id"
                ),
                {"id": chunk_id},
            )
            pt_sv = conn.execute(
                text("SELECT search_vector::text FROM corpus_chunks WHERE id = :id"),
                {"id": chunk_id},
            ).scalar_one()
        assert "corr" in pt_sv
        assert "correndo" not in pt_sv
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0007_downgrade_restores_generated_search_vector(monkeypatch) -> None:
    """0007 down (one step to 0006): drops the trigger/function, the plain
    search_vector, search_config, and embedding_model, and restores the generated
    (english) search_vector + its GIN index (EMB-07/09 reversibility)."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0006_teaching_schema")
    engine = create_engine(TEST_DB_URL)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("corpus_chunks")}
        assert "search_config" not in columns
        assert "embedding_model" not in columns
        assert "search_vector" in columns

        with engine.connect() as conn:
            # search_vector is a generated column again (RET-03 shape restored).
            is_generated = conn.execute(
                text(
                    "SELECT is_generated FROM information_schema.columns "
                    "WHERE table_name = 'corpus_chunks' AND column_name = 'search_vector'"
                )
            ).scalar_one()
            # The trigger is gone.
            trigger = conn.execute(
                text(
                    "SELECT 1 FROM pg_trigger "
                    "WHERE tgname = 'trg_corpus_chunks_search_vector'"
                )
            ).scalar()
            gin_def = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_corpus_chunks_search_vector'"
                )
            ).scalar_one()
        assert is_generated == "ALWAYS"
        assert trigger is None
        assert "gin" in gin_def.lower()
    finally:
        engine.dispose()

    command.downgrade(cfg, "base")


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0008_creates_quiz_tables(monkeypatch) -> None:
    """0008 up: the four quiz tables with cascade FKs (source→sources for items/jobs,
    quiz_item_id→quiz_items for scheduling/log), the (source_id, content_key) upsert
    unique, a nullable embedding column, the rating 1..4 CHECK, no FK into the corpus
    tables (snapshot survives a corpus replace), and the due/source_id/quiz_item_id
    indexes. Down one step to 0007 removes all four cleanly, re-up restores them
    (upgrade→downgrade→upgrade round-trip, QUIZ-01)."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "quiz_items",
            "quiz_item_scheduling",
            "review_log",
            "quiz_generation_jobs",
        } <= tables

        # Items/jobs cascade from their source; scheduling/log cascade from their item,
        # so deleting a source removes the whole aggregate with no orphans.
        item_fk = next(
            fk
            for fk in inspector.get_foreign_keys("quiz_items")
            if fk["constrained_columns"] == ["source_id"]
        )
        assert item_fk["referred_table"] == "sources"
        assert item_fk["options"].get("ondelete") == "CASCADE"

        job_fk = next(
            fk
            for fk in inspector.get_foreign_keys("quiz_generation_jobs")
            if fk["constrained_columns"] == ["source_id"]
        )
        assert job_fk["referred_table"] == "sources"
        assert job_fk["options"].get("ondelete") == "CASCADE"

        sched_fk = next(
            fk
            for fk in inspector.get_foreign_keys("quiz_item_scheduling")
            if fk["constrained_columns"] == ["quiz_item_id"]
        )
        assert sched_fk["referred_table"] == "quiz_items"
        assert sched_fk["options"].get("ondelete") == "CASCADE"

        log_fk = next(
            fk
            for fk in inspector.get_foreign_keys("review_log")
            if fk["constrained_columns"] == ["quiz_item_id"]
        )
        assert log_fk["referred_table"] == "quiz_items"
        assert log_fk["options"].get("ondelete") == "CASCADE"

        # No FK into the corpus tables — quiz_items snapshot their citation so they
        # survive a corpus replace (which regenerates chunk ids). Design invariant.
        item_referred = {fk["referred_table"] for fk in inspector.get_foreign_keys("quiz_items")}
        assert "corpus_chunks" not in item_referred
        assert "corpus_sections" not in item_referred

        # Upsert identity: unique (source_id, content_key) (QUIZ-02).
        item_uniques = [uc["column_names"] for uc in inspector.get_unique_constraints("quiz_items")]
        assert ["source_id", "content_key"] in item_uniques

        # Near-duplicate embedding column present and nullable (dedup identity, QUIZ-08).
        item_columns = {c["name"]: c for c in inspector.get_columns("quiz_items")}
        assert "embedding" in item_columns
        assert item_columns["embedding"]["nullable"] is True

        # The rating column is bounded to FSRS's 1..4 by a CHECK (QUIZ-12).
        with engine.connect() as conn:
            check_def = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = 'review_log'::regclass AND contype = 'c'"
                )
            ).scalar_one()
        assert "1" in check_def and "4" in check_def

        # Due index drives the due-queue read; source_id/quiz_item_id index the FKs.
        item_idx = [ix["column_names"] for ix in inspector.get_indexes("quiz_items")]
        assert ["source_id"] in item_idx
        sched_idx = [ix["column_names"] for ix in inspector.get_indexes("quiz_item_scheduling")]
        assert ["due"] in sched_idx
        job_idx = [ix["column_names"] for ix in inspector.get_indexes("quiz_generation_jobs")]
        assert ["source_id"] in job_idx
        log_idx = [ix["column_names"] for ix in inspector.get_indexes("review_log")]
        assert ["quiz_item_id"] in log_idx
    finally:
        engine.dispose()

    # Down one step to 0007: all four quiz tables are dropped cleanly.
    command.downgrade(cfg, "0007_language_aware_fts")
    engine = create_engine(TEST_DB_URL)
    try:
        remaining = set(inspect(engine).get_table_names())
        assert "quiz_items" not in remaining
        assert "quiz_item_scheduling" not in remaining
        assert "review_log" not in remaining
        assert "quiz_generation_jobs" not in remaining
    finally:
        engine.dispose()

    # Re-upgrade restores them — the schema round-trips.
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        restored = set(inspect(engine).get_table_names())
        assert {
            "quiz_items",
            "quiz_item_scheduling",
            "review_log",
            "quiz_generation_jobs",
        } <= restored
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0009_adds_anchor_aliases_column(monkeypatch) -> None:
    """0009 up: corpus_sections gains a NOT NULL anchor_aliases TEXT[] defaulting to
    the empty array; down one step to 0008 drops it, and a re-up restores it
    (upgrade→downgrade→upgrade round-trip, AD-085)."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("corpus_sections")}
        assert "anchor_aliases" in columns
        assert columns["anchor_aliases"]["nullable"] is False
        # Exercise the NOT NULL DEFAULT '{}' server default: insert a section via
        # raw SQL WITHOUT anchor_aliases (through a minimal users→source→document→
        # section chain) so the column falls to its default, then read it back. The
        # whole chain is rolled back so no committed row leaks into the shared DB.
        user_id = uuid.uuid4()
        source_id = uuid.uuid4()
        document_id = uuid.uuid4()
        section_id = uuid.uuid4()
        with engine.connect() as conn:
            coltype = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'corpus_sections' AND column_name = 'anchor_aliases'"
                )
            ).scalar_one()
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
                    "VALUES (:id, :did, 0, 0, 't', '[]', 'a.xhtml', 'md')"
                ),
                {"id": section_id, "did": document_id},
            )
            stored_aliases = conn.execute(
                text("SELECT anchor_aliases FROM corpus_sections WHERE id = :id"),
                {"id": section_id},
            ).scalar_one()
            conn.rollback()
        assert coltype == "ARRAY"
        # The omitted value read back as the empty array from the server default, not NULL.
        assert stored_aliases == []
    finally:
        engine.dispose()

    # Down one step to 0008: the column is dropped, the table survives.
    command.downgrade(cfg, "0008_quiz_schema")
    engine = create_engine(TEST_DB_URL)
    try:
        assert "corpus_sections" in set(inspect(engine).get_table_names())
        columns = {c["name"] for c in inspect(engine).get_columns("corpus_sections")}
        assert "anchor_aliases" not in columns
    finally:
        engine.dispose()

    # Re-upgrade restores the column — the schema round-trips.
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("corpus_sections")}
        assert "anchor_aliases" in columns
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_migration_0010_creates_notes_tables(monkeypatch) -> None:
    """0010 up: the five notes tables plus corpus_blocks.content_hash. THE CORE
    INVARIANT is proven at the schema layer — note_anchors.source_id carries NO
    foreign key into sources/corpus, so a source delete can never cascade into a
    note anchor. Within-aggregate cascades hold (notes→users, anchors/tags/links→
    notes, note_tags→tags), note_links.target_note_id is SET NULL, and tags are
    unique per (user_id, name). Down one step to 0009 drops it all cleanly, re-up
    restores it (upgrade→downgrade→upgrade round-trip)."""
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    cfg = _alembic_config(TEST_DB_URL)

    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"notes", "note_anchors", "tags", "note_tags", "note_links"} <= tables

        # note_anchors.source_id is a BARE UUID — the inverse-cascade invariant. It
        # references no table, so a source/corpus delete cannot reach a note anchor.
        anchor_referred = {
            fk["referred_table"] for fk in inspector.get_foreign_keys("note_anchors")
        }
        assert "sources" not in anchor_referred
        assert "corpus_documents" not in anchor_referred
        assert "corpus_sections" not in anchor_referred
        anchor_fk_columns = [
            fk["constrained_columns"] for fk in inspector.get_foreign_keys("note_anchors")
        ]
        assert ["source_id"] not in anchor_fk_columns

        # Within-aggregate cascades: notes→users, anchors/tags/links→notes, tags→notes_tags.
        notes_fk = next(
            fk for fk in inspector.get_foreign_keys("notes")
            if fk["constrained_columns"] == ["user_id"]
        )
        assert notes_fk["referred_table"] == "users"
        assert notes_fk["options"].get("ondelete") == "CASCADE"

        anchor_note_fk = next(
            fk for fk in inspector.get_foreign_keys("note_anchors")
            if fk["constrained_columns"] == ["note_id"]
        )
        assert anchor_note_fk["referred_table"] == "notes"
        assert anchor_note_fk["options"].get("ondelete") == "CASCADE"

        note_tag_fks = {
            tuple(fk["constrained_columns"]): fk
            for fk in inspector.get_foreign_keys("note_tags")
        }
        assert note_tag_fks[("note_id",)]["options"].get("ondelete") == "CASCADE"
        assert note_tag_fks[("tag_id",)]["referred_table"] == "tags"
        assert note_tag_fks[("tag_id",)]["options"].get("ondelete") == "CASCADE"

        # note_links: outbound cascade from its note; target set NULL when the target
        # note is deleted so the inbound link survives with its text.
        link_fks = {
            tuple(fk["constrained_columns"]): fk
            for fk in inspector.get_foreign_keys("note_links")
        }
        assert link_fks[("note_id",)]["options"].get("ondelete") == "CASCADE"
        assert link_fks[("target_note_id",)]["referred_table"] == "notes"
        assert link_fks[("target_note_id",)]["options"].get("ondelete") == "SET NULL"

        # Tags are unique per (user_id, name) — the per-user identity (app lowercases).
        tag_uniques = [uc["column_names"] for uc in inspector.get_unique_constraints("tags")]
        assert ["user_id", "name"] in tag_uniques

        # corpus_blocks gains a nullable content_hash (no backfill, AD-111).
        block_columns = {c["name"]: c for c in inspector.get_columns("corpus_blocks")}
        assert "content_hash" in block_columns
        assert block_columns["content_hash"]["nullable"] is True
    finally:
        engine.dispose()

    # Down one step to 0009: the five tables drop and content_hash is removed.
    command.downgrade(cfg, "0009_anchor_aliases")
    engine = create_engine(TEST_DB_URL)
    try:
        remaining = set(inspect(engine).get_table_names())
        assert not (
            {"notes", "note_anchors", "tags", "note_tags", "note_links"} & remaining
        )
        block_columns = {c["name"] for c in inspect(engine).get_columns("corpus_blocks")}
        assert "content_hash" not in block_columns
    finally:
        engine.dispose()

    # Re-upgrade restores everything — the schema round-trips.
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL)
    try:
        restored = set(inspect(engine).get_table_names())
        assert {"notes", "note_anchors", "tags", "note_tags", "note_links"} <= restored
    finally:
        engine.dispose()


@pytest.mark.skipif(TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set")
def test_in_process_migration_preserves_app_root_logging(monkeypatch) -> None:
    """An in-process migration must not reconfigure the app-owned root logger.

    ``env.py`` deliberately does NOT call alembic's ``fileConfig`` — that boilerplate
    resets the root logger from ``alembic.ini`` on load, replacing its handlers and
    dropping the app's sensitive-data redaction filter (NFR-SEC-004). This pins the
    behaviour: attach a redaction filter to the root handlers, run an upgrade
    in-process, and confirm the handlers (and the filter on them) survive.
    Re-introducing ``fileConfig`` replaces the root handlers and fails this. The
    original logging config is restored so no shared state leaks to other tests.
    """
    monkeypatch.setenv("LEARNY_DATABASE_URL", TEST_DB_URL)
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    marker = SensitiveDataFilter()
    for handler in saved_handlers:
        handler.addFilter(marker)
    try:
        command.upgrade(_alembic_config(TEST_DB_URL), "head")

        assert root.handlers == saved_handlers, (
            "in-process migration replaced the root logger's handlers"
        )
        assert all(marker in handler.filters for handler in root.handlers), (
            "in-process migration dropped the app redaction filter from root handlers"
        )
    finally:
        root.handlers[:] = saved_handlers
        for handler in saved_handlers:
            handler.removeFilter(marker)
