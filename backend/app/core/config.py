"""Environment-based application configuration.

Secrets and connection strings come from the environment only (NFR-SEC-003);
nothing here is committed with real values. See `.env.example` for the contract.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment variables.

    Defaults are safe placeholders for local boot; production values are injected
    via the environment (Docker Compose / VPS).
    """

    model_config = SettingsConfigDict(
        env_prefix="LEARNY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "learny-backend"
    environment: str = "local"
    debug: bool = False

    # Database (used by /readyz and, later, repositories + migrations)
    database_url: str = "postgresql+psycopg://learny:learny@localhost:5432/learny"

    # Redis / Celery (worker wiring; ingestion tasks land in a later cycle)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    def broker_url(self) -> str:
        """Effective Celery broker URL (falls back to ``redis_url``)."""
        return self.celery_broker_url or self.redis_url

    def result_backend(self) -> str:
        """Effective Celery result backend URL (falls back to ``redis_url``)."""
        return self.celery_result_backend or self.redis_url

    # Session cookie attributes (NFR-SEC-002) — wired fully in Phase C.
    session_cookie_name: str = "learny_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    session_cookie_path: str = "/"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance loaded from the environment."""
    return Settings()
