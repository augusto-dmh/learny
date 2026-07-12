"""Request/task trace context for log correlation (PROD-07..11/14/18/20, AD-041).

A single ``ContextVar`` holds the trace fields bound for the current request or
worker task (``request_id``, ``user_id``, ``job_id``, ``source_id``, ...). A
``logging.Filter`` reads that store at emit time and stamps the fields onto every
``LogRecord`` — so any log line produced anywhere inside a request/task is
correlated without the call site having to pass ``extra=`` each time.

The store is context-local: the request middleware and the worker task each open
a *fresh* scope (``new_trace_scope``) that they reset on the way out, and each
request/task runs in its own copied context, so trace fields never leak across
concurrent requests or between tasks.

Standard library only — no runtime dependency is introduced (AD-041).
"""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from logging import Filter, LogRecord
from uuid import uuid4

# The per-context trace store. ``None`` means "no active scope" — outside a
# request/task nothing is injected (PROD-20). Never mutate a shared default.
_TRACE: ContextVar[dict[str, str] | None] = ContextVar("learny_trace", default=None)

# Inbound ``X-Request-ID`` is attacker-controllable: bound its length and charset
# so it cannot inject newlines/control chars into a log line or grow unbounded.
_MAX_REQUEST_ID_LEN = 128
_UNSAFE_REQUEST_ID_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def new_request_id() -> str:
    """Return a fresh opaque request id (no dashes, safe for headers/logs)."""
    return uuid4().hex


def sanitize_request_id(raw: str | None) -> str | None:
    """Return a safe, bounded request id, or ``None`` when there is nothing usable.

    Strips characters outside ``[A-Za-z0-9._-]`` and truncates to
    ``_MAX_REQUEST_ID_LEN``. An empty/whitespace value (or one left empty after
    stripping) yields ``None`` so the caller can generate one instead.
    """
    if raw is None:
        return None
    cleaned = _UNSAFE_REQUEST_ID_CHARS.sub("", raw.strip())[:_MAX_REQUEST_ID_LEN]
    return cleaned or None


def new_trace_scope() -> Token[dict[str, str] | None]:
    """Begin a fresh trace scope; return a token to pass to :func:`reset_trace`.

    Sets a brand-new dict so a request/task starts with no inherited fields and
    its mutations stay isolated to this context.
    """
    return _TRACE.set({})


def reset_trace(token: Token[dict[str, str] | None]) -> None:
    """End the scope opened by :func:`new_trace_scope`."""
    _TRACE.reset(token)


def bind_trace(**fields: object) -> None:
    """Bind trace fields for the current scope (``None`` values are ignored).

    Mutates the current scope's dict in place so fields bound later in the request
    (e.g. ``user_id`` once auth resolves) are visible to every subsequent record.
    If called outside a scope, it opens one implicitly so the fields are not lost.
    """
    store = _TRACE.get()
    if store is None:
        store = {}
        _TRACE.set(store)
    for key, value in fields.items():
        if value is not None:
            store[key] = str(value)


def current_trace() -> dict[str, str]:
    """Return a copy of the current scope's trace fields (empty when no scope)."""
    store = _TRACE.get()
    return dict(store) if store else {}


class TraceContextFilter(Filter):
    """Stamp the current scope's trace fields onto each record before emission.

    Does not overwrite an attribute the record already carries (an explicit
    ``extra=`` on the call site wins), and is a no-op outside a scope (PROD-20).
    """

    def filter(self, record: LogRecord) -> bool:
        for key, value in current_trace().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True
