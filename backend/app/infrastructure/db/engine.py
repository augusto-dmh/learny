"""SQLAlchemy engine wiring (task B3).

Single place that builds the SQLAlchemy 2.x ``Engine`` from settings
(``postgresql+psycopg://…`` per CONVENTIONS). Repositories operate on a
``Connection`` handed to them by the caller, so the unit-of-work / transaction
boundary stays with the composition root (web layer in Phase C), not the
adapters.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return a cached Engine built from application settings."""
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)
