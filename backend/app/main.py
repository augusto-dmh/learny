"""FastAPI application entrypoint.

Wires the web adapter (routers) onto the FastAPI app. Domain and application
layers are imported by adapters only — this module is part of the infrastructure
boundary and is the single composition root for HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.web.auth import router as auth_router
from app.infrastructure.web.error_handlers import register_error_handlers
from app.infrastructure.web.health import router as health_router
from app.infrastructure.web.ingestion import router as ingestion_router
from app.infrastructure.web.middleware import RequestContextMiddleware
from app.infrastructure.web.questions import router as questions_router
from app.infrastructure.web.retrieval import router as retrieval_router
from app.infrastructure.web.sources import router as sources_router
from app.infrastructure.web.teaching import router as teaching_router


def create_app() -> FastAPI:
    """Application factory — build and configure the FastAPI app."""
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    # Outermost user middleware: wraps routing + exception handling so handled
    # responses carry the request id and every request is access-logged.
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(sources_router)
    app.include_router(ingestion_router)
    app.include_router(retrieval_router)
    app.include_router(questions_router)
    app.include_router(teaching_router)
    return app


app = create_app()
