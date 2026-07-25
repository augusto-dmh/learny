"""Dev-only instrument surface (OBS-19..22).

One read-only page's worth of JSON: the slowest endpoints this process has served,
ranked, and the slow statements it has captured. It is the consumer half of the
instrument — it holds no state, computes no timings, and only renders what the
recorder already holds.

**Two independent gates, both required.**

- ``LEARNY_DEV_INSTRUMENT_ENABLED`` decides whether the route exists at all. The
  router is included by :func:`app.main.create_app` only when the flag is true
  *and* the process is not configured as production, so with the flag off — or
  with it set on a production process — the path matches nothing: 404, and no
  entry in the OpenAPI schema either. A diagnostic route that is merely *guarded*
  is still a standing surface; one that is never mounted is not (AD-172), and a
  production process refuses to mount it whatever its environment says (AD-181).
- ``get_authenticated_user`` decides whether a caller may read it. Defense in
  depth at negligible cost — the browser reaches this through the existing
  same-origin proxy carrying its session cookie, so it costs no convenience
  (AD-174). The dependency is declared on the route rather than as a handler
  parameter because the response is process-wide, not user-scoped: nothing here
  is filtered by who is asking, and pretending otherwise would be misleading.

Collection is never gated (AD-173): the flag guards this route, not the recorder,
so a process that turns out to be slow can be diagnosed without a restart that
would discard the very evidence being chased.

**The response says what it does not cover.** Samples live in one process's
bounded buffers, so this is one API worker's slice of traffic and nothing from the
Celery workers, discarded on restart. That is stated in the payload itself
(:data:`SCOPE_NOTICE`) rather than only in a runbook, because a partial view read
as a total one is worse than no view at all (AD-171).

Nothing user-supplied reaches this response. Route templates, not paths; statement
text, not bound parameters — the recorder has no parameter that accepts an
identifier, so the property is inherited rather than re-implemented here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.instrumentation import (
    EndpointStat,
    InstrumentRecorder,
    QuerySample,
    get_recorder,
)
from app.infrastructure.web.dependencies import get_authenticated_user

router = APIRouter(tags=["instrument"])

#: What the numbers below do and do not cover, carried in the payload so a reader
#: cannot mistake one process's slice for the whole deployment (AD-171).
SCOPE_NOTICE = (
    "Samples from this API process only. Production runs several API workers, so this "
    "is roughly one worker's slice of traffic; Celery task durations are in a different "
    "process and appear in the structured logs, never here. Everything is discarded on "
    "restart."
)


class EndpointTimingView(BaseModel):
    """One ``(method, route template)`` group's timings, as the surface renders it."""

    method: str
    route: str
    count: int
    mean_ms: float
    max_ms: float
    p95_ms: float

    @classmethod
    def from_stat(cls, stat: EndpointStat) -> EndpointTimingView:
        return cls(
            method=stat.method,
            route=stat.route,
            count=stat.count,
            mean_ms=stat.mean_ms,
            max_ms=stat.max_ms,
            p95_ms=stat.p95_ms,
        )


class SlowQueryView(BaseModel):
    """One captured slow statement. SQL text only — bound values never reach here."""

    statement: str
    duration_ms: float

    @classmethod
    def from_sample(cls, sample: QuerySample) -> SlowQueryView:
        return cls(statement=sample.statement, duration_ms=sample.duration_ms)


class InstrumentView(BaseModel):
    """The whole surface: what it covers, how much it retains, and the two rankings."""

    scope: str
    capacity: int
    endpoints: list[EndpointTimingView]
    slow_queries: list[SlowQueryView]


@router.get("/api/dev/instrument", dependencies=[Depends(get_authenticated_user)])
def read_instrument(
    recorder: Annotated[InstrumentRecorder, Depends(get_recorder)],
) -> InstrumentView:
    """Return the ranked endpoints and the captured slow statements.

    Both collections are empty when nothing has been recorded — an idle process is
    a 200 with nothing in it, never an error. The slow-query list is bounded by the
    recorder's own capacity rather than a second limit invented here, so the one
    configured number is the one that governs.

    The recorder is declared as a dependency like every other collaborator in this
    layer, rather than fetched from module state inside the body: it is what the
    handler reads, so it belongs in the signature, and it stays reachable through
    ``app.dependency_overrides``. The producers (the ASGI middleware, the
    SQLAlchemy event) have no injection point and go on using the free functions.
    """
    snapshot = recorder.snapshot()
    return InstrumentView(
        scope=SCOPE_NOTICE,
        capacity=recorder.capacity,
        endpoints=[EndpointTimingView.from_stat(stat) for stat in snapshot.endpoints],
        slow_queries=[SlowQueryView.from_sample(sample) for sample in snapshot.slow_queries],
    )
