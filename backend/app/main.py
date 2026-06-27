"""FastAPI application entrypoint.

Wires the web adapter (routers) onto the FastAPI app. Domain and application
layers are imported by adapters only — this module is part of the infrastructure
boundary and is the single composition root for HTTP.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.web.health import router as health_router


def create_app() -> FastAPI:
    """Application factory — build and configure the FastAPI app."""
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    return app


app = create_app()
