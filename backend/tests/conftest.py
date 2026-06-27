"""Shared pytest fixtures for backend tests.

Integration fixtures require a live Postgres reachable at
``LEARNY_TEST_DATABASE_URL``; tests using them are skipped when it is unset
(mirrors the A4 migration test). The schema is created once per session via the
real Alembic migration, and each test runs inside a transaction that is rolled
back, so DB tests are isolated and order-independent.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine

TEST_DB_URL = os.environ.get("LEARNY_TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set"
)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    if TEST_DB_URL is None:
        pytest.skip("LEARNY_TEST_DATABASE_URL not set")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DB_URL, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_conn(db_engine: Engine) -> Iterator[Connection]:
    """A connection wrapped in a transaction rolled back after each test."""
    conn = db_engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()
