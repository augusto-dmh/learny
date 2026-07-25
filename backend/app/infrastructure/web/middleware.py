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
- reports the server's own share to the browser as ``Server-Timing: app;dur=…``
  **when the instrument is enabled**, so devtools can split server time from
  network and render time.

**The header ships on the same switch as the dev surface.** It is the one part of
the instrument that leaves the process, and it is readable by anonymous callers:
``AuthenticateUser`` deliberately hashes a dummy password to keep login timing
uniform, and that uniformity is imperfect (looking the credential up is an extra
round trip that only happens when the email exists). Microsecond server-side
timing, with network jitter already removed, hands away exactly the property the
application layer spends code defending — so it is emitted only where the
instrument is deliberately on, which is never a production process. Whether to
emit is decided by the composition root and passed in at construction:
``create_app`` reads settings at assembly time, which is where settings may
safely be read, and this module reads none (an import-time ``get_settings`` primes
the settings cache and pins a stale database URL for Alembic — lesson L-007).

The access record reports ``response_start_ms`` either way. Only the wire
exposure is gated; nothing about diagnosis changes.

**Two intervals, named apart.** A header must be written before the response
starts; the access record is emitted after the request finishes. Rather than
collapse those into one number, the request is timed at both points and each
consumer gets the interval it can honestly use:

- ``duration_ms`` — the whole request, streamed body included. It is what the
  access record has always meant, and what the instrument ranks on, so a
  streaming endpoint stays rankable by what it actually costs (the generation
  time behind a streamed answer is the point of measuring at all).
- ``response_start_ms`` — the time from receiving the request to starting the
  response: the server's own share, and all a browser can attribute to us. This
  is the number the ``Server-Timing`` header carries, taken once and reported in
  both places so the header is always traceable to a log line.

When no response ever starts, ``response_start_ms`` is absent and only the whole
duration is reported, so no record is lost.

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
    """Bind a per-request trace scope and emit a structured access log.

    ``server_timing_enabled`` decides whether responses carry the
    ``Server-Timing`` header. It defaults to off so a composition root that never
    considered the question does not publish timings by accident; ``create_app``
    passes the instrument's own switch.
    """

    def __init__(self, app: ASGIApp, *, server_timing_enabled: bool = False) -> None:
        self.app = app
        self.server_timing_enabled = server_timing_enabled

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
            send,
            request_id,
            status_holder,
            timing_holder,
            start,
            server_timing_enabled=self.server_timing_enabled,
        )
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # The whole request, streamed body included — what the access record
            # has always meant, and what a streaming endpoint actually costs.
            duration_ms = _elapsed_ms(start)
            _access_logger.info(
                "http.request",
                extra={
                    "status_code": status_holder["code"],
                    "duration_ms": duration_ms,
                    # The header's own number, so it is traceable to a log line.
                    "response_start_ms": timing_holder.get("response_start_ms"),
                },
            )
            # ``record_request`` contains its own failures, so the instrument
            # cannot change the outcome it measures and this call needs no guard
            # of its own.
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
        *,
        server_timing_enabled: bool,
    ) -> Callable[[Message], Awaitable[None]]:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                # Taken once here and reported both on the wire and in the
                # access record, so the browser's number is never a second,
                # independent measurement. The reading is taken — and logged —
                # whether or not it is published: gating the header must not
                # cost the access record a field.
                response_start_ms = _elapsed_ms(start)
                timing_holder["response_start_ms"] = response_start_ms
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                headers[_REQUEST_ID_HEADER] = request_id
                if server_timing_enabled:
                    # ``Server-Timing`` is a list header: append so a metric a
                    # handler set for itself survives alongside ours.
                    headers.append(
                        _SERVER_TIMING_HEADER, f"{_SERVER_TIMING_METRIC};dur={response_start_ms}"
                    )
            await send(message)

        return send_wrapper
