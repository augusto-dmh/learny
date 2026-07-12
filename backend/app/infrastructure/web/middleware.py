"""Request-context middleware — request-id correlation + access logging (PROD-07..11/19).

A **pure ASGI** middleware (deliberately not ``BaseHTTPMiddleware``): the endpoint
and its dependencies run in the *same* context this middleware sets, so a
``user_id`` bound during auth (``resolve_current``) is visible to every log record
the handler emits. It:

- adopts a sanitized inbound ``X-Request-ID`` or generates one, binds it plus the
  request method/path into a fresh trace scope, and echoes it on the response;
- emits exactly one structured ``http.request`` access record — carrying status
  and duration — in a ``finally`` so it fires for success, handled errors, and
  unhandled 500s alike.

Accepted gap: a *truly unhandled* exception is turned into a 500 by Starlette's
outermost ``ServerErrorMiddleware`` (outside this middleware), so the response it
produces does not carry the ``X-Request-ID`` header. Every handled response
(including exception-handler-mapped 4xx/5xx) is produced inside this middleware
and does get the header. The access log still fires for the unhandled case.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.tracing import (
    bind_trace,
    new_request_id,
    new_trace_scope,
    reset_trace,
    sanitize_request_id,
)

_REQUEST_ID_HEADER = "X-Request-ID"
_access_logger = logging.getLogger("app.request")


def _inbound_request_id(scope: Scope) -> str | None:
    """Return the sanitized inbound ``X-Request-ID`` header value, if any."""
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            return sanitize_request_id(value.decode("latin-1"))
    return None


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

        send_wrapper = self._make_send_wrapper(send, request_id, status_holder)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 3)
            _access_logger.info(
                "http.request",
                extra={"status_code": status_holder["code"], "duration_ms": duration_ms},
            )
            reset_trace(token)

    @staticmethod
    def _make_send_wrapper(
        send: Send, request_id: str, status_holder: dict[str, int]
    ) -> Callable[[Message], Awaitable[None]]:
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                headers[_REQUEST_ID_HEADER] = request_id
            await send(message)

        return send_wrapper
