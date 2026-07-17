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
from contextlib import AbstractContextManager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine

TEST_DB_URL = os.environ.get("LEARNY_TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    TEST_DB_URL is None, reason="LEARNY_TEST_DATABASE_URL not set"
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--record-generation`` for the generation replay harness (design §8).

    Off by default so the offline PR suite never calls a provider; passing it
    (with ``LEARNY_ANTHROPIC_API_KEY`` set) opts the recording test into running
    the live adapter over each eval case and rewriting the committed snapshots.
    """
    parser.addoption(
        "--record-generation",
        action="store_true",
        default=False,
        help="run the live generation adapter over the eval cases and rewrite snapshots",
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
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    # Fresh, generous limiter per test so the shared module singleton does not
    # leak counts across tests (dedicated rate-limit tests install their own).
    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


@pytest.fixture
def ingestion_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the ingestion routers, isolated to a rolled-back txn.

    Mirrors ``auth_client``/``sources_client`` (DB override, non-Secure cookie,
    trusted Origin, generous limiter) and additionally overrides the start-path
    UoW factory to yield the shared ``db_conn`` *without committing* — so UoW1 and
    the ING-11 compensation UoW share the test's one rolled-back transaction — and
    the enqueuer with a recording fake (also stored on ``app.state`` so tests can
    assert its calls). The 502 test installs a failing enqueuer via a per-test
    ``dependency_overrides[get_ingestion_enqueuer]`` swap.
    """
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import (
        get_db_connection,
        get_ingestion_enqueuer,
        get_ingestion_uow,
    )
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app
    from tests.fakes import FakeIngestionEnqueuer

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override_conn() -> Iterator[Connection]:
        yield db_conn

    @contextmanager
    def _shared_uow() -> Iterator[Connection]:
        # Yield the shared rolled-back connection WITHOUT committing, so the start
        # UoW and the compensation UoW observe one transaction (isolation kept
        # exactly as ``get_db_connection`` is overridden).
        yield db_conn

    def _uow_factory() -> AbstractContextManager[Connection]:
        return _shared_uow()

    enqueuer = FakeIngestionEnqueuer()
    app.state.ingestion_enqueuer = enqueuer

    app.dependency_overrides[get_db_connection] = _override_conn
    app.dependency_overrides[get_ingestion_uow] = lambda: _uow_factory
    app.dependency_overrides[get_ingestion_enqueuer] = lambda: enqueuer
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


@pytest.fixture
def quiz_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the quiz/review routers, isolated to a rolled-back txn.

    Mirrors ``ingestion_client``: overrides ``get_db_connection`` (shared rolled-back
    ``db_conn``), the deck-POST UoW factory (``get_quiz_uow``) to yield the same
    ``db_conn`` *without committing* so UoW1 and the compensation UoW share one
    transaction, and the deck enqueuer with a recording fake (also on ``app.state``
    so tests can assert its calls). The 502 test installs a failing enqueuer via a
    per-test ``dependency_overrides[get_quiz_deck_enqueuer]`` swap.
    """
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import (
        get_db_connection,
        get_quiz_deck_enqueuer,
        get_quiz_uow,
    )
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app
    from tests.fakes import FakeQuizDeckEnqueuer

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override_conn() -> Iterator[Connection]:
        yield db_conn

    @contextmanager
    def _shared_uow() -> Iterator[Connection]:
        # Yield the shared rolled-back connection WITHOUT committing, so the deck
        # UoW and the compensation UoW observe one transaction.
        yield db_conn

    def _uow_factory() -> AbstractContextManager[Connection]:
        return _shared_uow()

    enqueuer = FakeQuizDeckEnqueuer()
    app.state.quiz_enqueuer = enqueuer

    app.dependency_overrides[get_db_connection] = _override_conn
    app.dependency_overrides[get_quiz_uow] = lambda: _uow_factory
    app.dependency_overrides[get_quiz_deck_enqueuer] = lambda: enqueuer
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


# A small EPUB byte-cap so the oversize-upload path is exercised cheaply (the
# real 50 MiB default would force allocating a 50 MiB body in-process).
SOURCES_MAX_BYTES = 1024


@pytest.fixture
def sources_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the sources routers, isolated to a rolled-back txn.

    Mirrors ``auth_client`` (same DB override, non-Secure cookie, trusted Origin,
    generous limiter) but pins ``epub_max_bytes`` to :data:`SOURCES_MAX_BYTES` so
    the oversize-reject test stays cheap while remaining a real end-to-end run
    against Postgres + MinIO.
    """
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    monkeypatch.setenv("LEARNY_EPUB_MAX_BYTES", str(SOURCES_MAX_BYTES))
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


@pytest.fixture
def throttled_sources_client(  # noqa: ANN201
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
):
    """Like ``sources_client`` but with a deliberately tight upload limiter.

    Mirrors ``throttled_client`` in ``test_web_rate_limit_validation`` (auth
    suite): 3 attempts per long window so the 4th ``POST /api/sources`` trips the
    ``rate_limit_upload`` 429 branch deterministically (spec SRC-05).
    """
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    monkeypatch.setenv("LEARNY_EPUB_MAX_BYTES", str(SOURCES_MAX_BYTES))
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    # Allow 3 attempts per long window so the 4th trips deterministically. The
    # limiter key is per-IP+route, so the auth register/csrf setup calls consume
    # separate buckets and never eat into the upload budget.
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()
