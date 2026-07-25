"""Request-context middleware — request-id correlation + access logging (PROD-07..11/19).

A **pure ASGI** middleware (deliberately not ``BaseHTTPMiddleware``): the endpoint
and its dependencies run in the *same* context this middleware sets, so a
``user_id`` bound during auth (``resolve_current``) is visible to every log record
the handler emits. It:

- adopts a sanitized inbound ``X-Request-ID`` or generates one, binds it plus the
  request method/path into a fresh trace scope, and echoes it on the response;
- emits exactly one structured ``http.request`` access record — carrying status
  and duration — in a ``finally`` so it fires for success, handled errors, and
  unhandled 500s alike;
- records that same duration on the in-process instrument, keyed on the *route
  template* — never the raw path, which would leak resource identifiers into a
  surface with weaker access control than the resources they name;
- reports that same duration to the browser as ``Server-Timing: app;dur=…``, so
  devtools can split server time from network and render time.

**One measurement, three consumers.** The header has to be written before the
response starts, while the access record is emitted after the request finishes,
so the request is timed once — at ``http.response.start`` — and that single
number is what the header, the access record, and the instrument all carry.
``duration_ms`` is therefore the server's own share: the time from receiving the
request to starting its response, which for a streamed response deliberately
excludes the time spent streaming the body. Only when no response ever starts
does the ``finally`` measure instead, so the record is never lost.

Accepted gap: a *truly unhandled* exception is turned into a 500 by Starlette's
outermost ``ServerErrorMiddleware`` (outside this middleware), so the response it
produces carries neither the ``X-Request-ID`` nor the ``Server-Timing`` header —
it is not sent through this middleware's ``send``. Every handled response
(including exception-handler-mapped 4xx/5xx) is produced inside this middleware
and does get both. The access log and the instrument record still fire for the
unhandled case, with its final status.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.instrumentation import record_request
from app.core.tracing import (
    bind_trace,
    new_request_id,
    new_trace_scope,
    reset_trace,
    sanitize_request_id,
)

_REQUEST_ID_HEADER = "X-Request-ID"
_SERVER_TIMING_HEADER = "Server-Timing"
_SERVER_TIMING_METRIC = "app"
_access_logger = logging.getLogger("app.request")


def _elapsed_ms(start: float) -> float:
    """Return the milliseconds elapsed since ``start``, rounded to microseconds."""
    return round((time.perf_counter() - start) * 1000, 3)


def _inbound_request_id(scope: Scope) -> str | None:
    """Return the sanitized inbound ``X-Request-ID`` header value, if any."""
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            return sanitize_request_id(value.decode("latin-1"))
    return None


def _route_template(scope: Scope) -> str | None:
    """Return the matched route's template (``/api/sources/{source_id}``), or ``None``.

    The router publishes the matched route into ``scope["route"]`` *while* it
    routes — i.e. during the downstream call — so this is only meaningful once
    ``self.app`` has returned. Read defensively: anything that is not a route
    object carrying a string ``path`` yields ``None``, which the recorder buckets
    under its own placeholder. The raw ``scope["path"]`` is never substituted, so
    if a future framework release stops populating the key the instrument loses
    resolution rather than leaking identifiers.
    """
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else None


class RequestContextMiddleware:
    """Bind a per-request trace scope and emit a structured access log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _inbound_request_id(scope) or new_request_id()
        token = new_trace_scope()
        bind_trace(
            request_id=request_id,
            method=scope.get("method"),
            path=scope.get("path"),
        )
        start = time.perf_counter()
        status_holder = {"code": 500}  # default if the response never starts
        timing_holder: dict[str, float] = {}  # filled when the response starts

        send_wrapper = self._make_send_wrapper(
            send, request_id, status_holder, timing_holder, start
        )
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = timing_holder.get("duration_ms")
            if duration_ms is None:
                # No response ever started (the unhandled-exception gap above):
                # measure here so the record still fires.
                duration_ms = _elapsed_ms(start)
            _access_logger.info(
                "http.request",
                extra={"status_code": status_holder["code"], "duration_ms": duration_ms},
            )
            # One measurement, two consumers. ``record_request`` contains its own
            # failures, so the instrument cannot change the outcome it measures
            # and this call needs no guard of its own.
            record_request(
                method=scope.get("method", ""),
                route=_route_template(scope),
                status_code=status_holder["code"],
                duration_ms=duration_ms,
            )
            reset_trace(token)

    @staticmethod
    def _make_send_wrapper(
        send: Send,
        request_id: str,
        status_holder: dict[str, int],
        timing_holder: dict[str, float],
        start: float,
    ) -> Callable[[Message], Awaitable[None]]:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                duration_ms = _elapsed_ms(start)
                timing_holder["duration_ms"] = duration_ms
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                headers[_REQUEST_ID_HEADER] = request_id
                # ``Server-Timing`` is a list header: append so a metric a
                # handler set for itself survives alongside ours.
                headers.append(_SERVER_TIMING_HEADER, f"{_SERVER_TIMING_METRIC};dur={duration_ms}")
            await send(message)

        return send_wrapper
