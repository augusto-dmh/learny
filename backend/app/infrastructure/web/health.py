"""Health endpoints (FR-SCAF-002).

- `/healthz` — liveness: the process is up and serving. No dependencies.
- `/readyz`  — readiness: dependencies (PostgreSQL) are reachable. Reports
  not-ready (503) when the database cannot be reached, so orchestration can
  gate traffic.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe — always ok if the process can serve a request."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response) -> dict[str, str]:
    """Readiness probe — verifies the database is reachable.

    Returns 503 with ``{"status": "not-ready"}`` when the DB check fails, which
    is the expected state before a database is provisioned.
    """
    settings = get_settings()
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not-ready", "database": "unreachable"}
    return {"status": "ready", "database": "ok"}
