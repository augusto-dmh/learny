"""SQLAlchemy engine wiring (task B3).

Single place that builds the SQLAlchemy 2.x ``Engine`` from settings
(``postgresql+psycopg://…`` per CONVENTIONS). Repositories operate on a
``Connection`` handed to them by the caller, so the unit-of-work / transaction
boundary stays with the composition root (web layer in Phase C), not the
adapters.
"""

from __future__ import annotations

from functools import lru_cache

from pgvector.psycopg import register_vector
from sqlalchemy import Engine, create_engine, event

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return a cached Engine built from application settings.

    Registers ``pgvector`` on every new DBAPI connection so Python ``list[float]``
    values adapt to the Postgres ``vector`` type on both read and write paths. The
    registration is guarded: against a DB where the ``vector`` extension is not yet
    installed (e.g. a pre-migration boot), ``register_vector`` raises because the type
    is absent — we swallow that so the connection still opens; queries that actually
    need the vector type then fail explicitly. Migrations use their own engine
    (``env.py``), so they are unaffected.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

    @event.listens_for(engine, "connect")
    def _register_vector(dbapi_conn, _record):  # noqa: ANN001, ANN202
        try:
            register_vector(dbapi_conn)
        except Exception:  # noqa: BLE001 — vector type absent pre-migration; open anyway
            pass

    return engine
