"""A4 gate — migration tooling applies the identity schema.

This test runs the real Alembic upgrade/downgrade against a Postgres test DB
when ``LEARNY_TEST_DATABASE_URL`` is set (e.g. under Docker Compose or CI). When
no DB is reachable it is skipped — the migration scripts are still validated for
import/compile by ``test_migration_metadata_compiles``.
"""

from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

TEST_DB_URL = os.environ.get("LEARNY_TEST_DATABASE_URL")


def _alembic_config(db_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_metadata_compiles() -> None:
    """The shared metadata defines the identity + sources tables with constraints."""
    from app.infrastructure.db.metadata import metadata, sessions, sources, users

    assert set(metadata.tables) == {"users", "user_credentials", "sessions", "sources"}
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
