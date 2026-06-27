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


# --- Web (FastAPI) integration fixtures (Phase C) -------------------------------

# A valid password (>= 12 chars) and trusted Origin shared by web auth tests.
TEST_PASSWORD = "correct horse battery staple"
TEST_ORIGIN = "http://testserver"  # TestClient's host
SESSION_COOKIE_NAME = "learny_session"


@pytest.fixture
def auth_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the auth routers, isolated to a rolled-back txn.

    - ``get_db_connection`` is overridden to yield the test's transactional
      connection, so requests share one uncommitted unit of work.
    - Secure cookie is disabled (TestClient speaks HTTP; a Secure cookie would
      not be returned), mirroring local HTTP dev — Secure stays on for HTTPS.
    - A trusted Origin is configured and attached to every request so the CSRF
      Origin gate passes on happy paths; tests override it to exercise rejection.
    """
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
