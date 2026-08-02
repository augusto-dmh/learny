"""FastAPI application entrypoint.

Wires the web adapter (routers) onto the FastAPI app. Domain and application
layers are imported by adapters only — this module is part of the infrastructure
boundary and is the single composition root for HTTP.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.instrumentation import InstrumentRecorder, set_recorder
from app.core.logging import configure_logging
from app.infrastructure.web.auth import router as auth_router
from app.infrastructure.web.cards import router as cards_router
from app.infrastructure.web.conversations import router as conversations_router
from app.infrastructure.web.error_handlers import register_error_handlers
from app.infrastructure.web.evals import router as evals_router
from app.infrastructure.web.health import router as health_router
from app.infrastructure.web.ingestion import router as ingestion_router
from app.infrastructure.web.instrument import router as instrument_router
from app.infrastructure.web.middleware import RequestContextMiddleware
from app.infrastructure.web.notes import router as notes_router
from app.infrastructure.web.quiz import router as quiz_router
from app.infrastructure.web.retrieval import router as retrieval_router
from app.infrastructure.web.sources import router as sources_router
from app.infrastructure.web.study import router as study_router
from app.infrastructure.web.vault import router as vault_router

#: ``LEARNY_ENVIRONMENT`` value that marks a process as production.
PRODUCTION_ENVIRONMENT = "production"

# One logger per dev surface. They are independently switchable everywhere else,
# and the logger name is the axis an operator filters a refusal by, so a shared
# one would file the dashboard's refusal under the instrument.
_instrument_logger = logging.getLogger("app.instrument")
_eval_dashboard_logger = logging.getLogger("app.eval_dashboard")


def instrument_surface_exposed(settings: Settings) -> bool:
    """Whether this process may expose the instrument: flag set AND not production.

    The flag alone used to decide it, which left production safe only because the
    production compose omits the variable — while the same service also loads an
    operator-authored env file and ``Settings`` reads ``.env``, so either can turn
    it on with nothing failing. Refusal is therefore a property of the application
    rather than of a YAML file: a process configured as production never exposes
    process-wide SQL statement text and a full route inventory, whatever its
    environment hands it. A flag that is set and refused is logged, so the
    misconfiguration is visible instead of silent.

    Collection is untouched: what is refused is *exposure*. Production diagnosis
    remains the structured log, which carries both the durations and every slow
    statement.
    """
    if not settings.dev_instrument_enabled:
        return False
    if settings.environment.strip().lower() == PRODUCTION_ENVIRONMENT:
        _instrument_logger.warning(
            "instrument.surface.refused",
            extra={"environment": settings.environment},
        )
        return False
    return True


def eval_dashboard_surface_exposed(settings: Settings) -> bool:
    """Whether this process may expose the eval dashboard: flag set AND not production.

    The same two-part rule as the instrument, and for the same reason: a flag
    alone leaves production safe only by the absence of a variable, while the
    service loads an operator-authored env file and ``Settings`` also reads
    ``.env``. Refusal is a property of the application, so a process configured
    as production never serves eval case text, model identifiers, or prompt
    hashes, whatever its environment hands it. The switch is separate from the
    instrument's so either dev surface can be enabled without dragging in the
    other. A flag that is set and refused is logged rather than silently ignored.
    """
    if not settings.dev_eval_dashboard_enabled:
        return False
    if settings.environment.strip().lower() == PRODUCTION_ENVIRONMENT:
        _eval_dashboard_logger.warning(
            "eval_dashboard.surface.refused",
            extra={"environment": settings.environment},
        )
        return False
    return True


def create_app() -> FastAPI:
    """Application factory — build and configure the FastAPI app."""
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    # The instrument's bounds are configuration, so the recorder the process uses
    # is built here rather than left at its module defaults — otherwise
    # LEARNY_INSTRUMENT_CAPACITY and LEARNY_SLOW_QUERY_STATEMENT_CHARS would be
    # documented settings that changed nothing. Assembly time is where settings
    # may safely be read; import time is not (lesson L-007).
    set_recorder(
        InstrumentRecorder(
            capacity=settings.instrument_capacity,
            statement_max_chars=settings.slow_query_statement_chars,
        )
    )
    exposed = instrument_surface_exposed(settings)
    # Outermost user middleware: wraps routing + exception handling so handled
    # responses carry the request id and every request is access-logged. The
    # ``Server-Timing`` header is the one part of the instrument that leaves the
    # process, so it ships on the same switch as the surface — never on a
    # production process. The access record keeps its timing field either way.
    app.add_middleware(RequestContextMiddleware, server_timing_enabled=exposed)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(sources_router)
    app.include_router(ingestion_router)
    app.include_router(retrieval_router)
    app.include_router(conversations_router)
    app.include_router(quiz_router)
    app.include_router(notes_router)
    app.include_router(cards_router)
    app.include_router(vault_router)
    app.include_router(study_router)
    # Mounted only when this process may expose the instrument, so with the flag
    # off — or with it set on a production process — the dev instrument path
    # matches no route at all: 404, and absent from the OpenAPI schema.
    # Authentication gates it independently once it is mounted.
    if exposed:
        app.include_router(instrument_router)
    # The eval dashboard rides its own switch, so enabling the instrument does not
    # drag in a second surface. Same refusal shape: flag off, or a production
    # process, and the path matches no route and is absent from the schema.
    if eval_dashboard_surface_exposed(settings):
        app.include_router(evals_router)
    return app


app = create_app()
