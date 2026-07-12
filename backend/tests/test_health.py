"""A1 gate — health route + config load."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.infrastructure.db.engine import get_engine
from app.main import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_assembled_app_wires_request_context_middleware() -> None:
    """The real create_app() installs the request-context middleware, so every
    response carries an X-Request-ID (not just the isolated-middleware tests)."""
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.headers.get("X-Request-ID")


def test_config_loads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LEARNY_ENVIRONMENT", "test-env")
    monkeypatch.setenv("LEARNY_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    # Fresh instance (bypass the lru_cache used in app code).
    settings = Settings()
    assert settings.environment == "test-env"
    assert settings.database_url.endswith("/d")


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_readyz_reports_not_ready_without_db(monkeypatch) -> None:
    # Point at an unreachable DB so the readiness check fails fast.
    monkeypatch.setenv("LEARNY_DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/none")
    get_settings.cache_clear()
    # readyz now uses the shared cached engine; rebuild it against the
    # unreachable URL (its cache is independent of get_settings').
    get_engine.cache_clear()
    client = TestClient(create_app())
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not-ready"
    get_settings.cache_clear()
    get_engine.cache_clear()
