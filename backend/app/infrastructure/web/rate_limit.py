"""Pluggable rate-limit hooks (task C3, FR-AUTH-009; user keys per DOOR-02).

Two key policies behind one swappable ``RateLimiter``:

- Auth endpoints (register/login) throttle on the trusted-proxy client IP + route,
  so one actor cannot mint fresh budgets by header tricks.
- The expensive authenticated surfaces (conversations, quiz generation, source
  upload, ingest-start) throttle on the authenticated caller's ``user_id`` + route
  template, so two learners behind one shared proxy IP each get their own budget.

The default is a process-local fixed-window counter — fine for a single-process
dev/MVP boot. It deliberately implements the same ``RateLimiter`` protocol a
Redis-backed limiter would, so swapping in a distributed limiter is a one-line
wiring change with no endpoint edits.

On limit breach the dependency raises ``HTTPException(429)`` with a ``Retry-After``
header; a limiter that cannot record a hit fails closed with 503. Replace the
active limiter via :func:`set_rate_limiter` (e.g. in tests or when wiring a Redis
adapter at the composition root).
"""

from __future__ import annotations

import ipaddress
import threading
import time
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.domain.entities import User
from app.infrastructure.web.dependencies import get_authenticated_user


class LimiterUnavailable(Exception):
    """Raised when the active limiter cannot record a hit (fail closed)."""


class RateLimiter(Protocol):
    """Port for a rate limiter. ``hit`` records an attempt and reports the verdict."""

    def hit(self, key: str) -> tuple[bool, int]:
        """Record an attempt for ``key``.

        Returns ``(allowed, retry_after_seconds)``. When ``allowed`` is ``False``
        the caller should reject; ``retry_after_seconds`` is a hint for the
        ``Retry-After`` header.
        """
        ...


class InMemoryFixedWindowRateLimiter:
    """Process-local fixed-window limiter (conservative default).

    Allows up to ``max_attempts`` per ``window_seconds`` per key. State is a dict
    guarded by a lock; entries are cheap and overwritten as windows roll over, so
    memory stays bounded by the number of distinct active keys.
    """

    def __init__(self, *, max_attempts: int = 10, window_seconds: float = 60.0) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._lock = threading.Lock()
        # key -> (window_start_monotonic, count)
        self._buckets: dict[str, tuple[float, int]] = {}

    def hit(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= self._window:
                # Window rolled over; start a fresh one.
                start, count = now, 0
            count += 1
            self._buckets[key] = (start, count)
            if count > self._max:
                retry_after = max(1, int(self._window - (now - start)))
                return False, retry_after
            return True, 0


# Active limiter (module-level singleton). Swap via set_rate_limiter.
_limiter: RateLimiter = InMemoryFixedWindowRateLimiter()


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Replace the active limiter (composition root / tests)."""
    global _limiter
    _limiter = limiter


def get_rate_limiter() -> RateLimiter:
    """Return the active limiter."""
    return _limiter


def _hit(key: str) -> None:
    """Record one attempt; 429 when the window is exceeded, 503 if Redis is down."""
    try:
        allowed, retry_after = get_rate_limiter().hit(key)
    except LimiterUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable.",
        ) from None
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def _peer_is_trusted(peer: str, trusted: tuple[str, ...]) -> bool:
    if peer in trusted:
        return True
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for entry in trusted:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if address in network:
            return True
    return False


def trusted_client_ip(request: Request) -> str:
    """Client IP for auth throttles: ``X-Real-IP`` only when the TCP peer is trusted.

    A client-supplied ``X-Forwarded-For`` chain is never consulted.
    """
    peer = request.client.host if request.client else "unknown"
    if not _peer_is_trusted(peer, get_settings().trusted_proxy_host_list()):
        return peer
    forwarded = request.headers.get("x-real-ip", "").strip()
    if not forwarded:
        return peer
    return forwarded.split(",")[0].strip()


def _client_key(request: Request) -> str:
    """Build a limiter key from trusted client IP + route path."""
    return f"{trusted_client_ip(request)}:{request.url.path}"


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency: throttle auth attempts; 429 when the window is exceeded."""
    _hit(_client_key(request))


def rate_limit_upload(
    user: Annotated[User, Depends(get_authenticated_user)], request: Request
) -> None:
    """FastAPI dependency: throttle the expensive source writes per user.

    Applied to source upload and to ingest-start (both flood storage/worker
    capacity), so a client cannot flood object storage with writes. Keys on the
    authenticated caller's ``user_id`` + route template — see
    :func:`_user_route_key` — not on the client IP, so two learners behind one
    shared proxy IP each get their own budget. The dependency resolves the
    authenticated user itself: router dependencies run before handler parameters,
    so an unauthenticated request is a 401 here and spends no budget.
    """
    _hit(_user_route_key(user, request))


def _user_route_key(user: User, request: Request) -> str:
    """Build a limiter key from the authenticated user + route *template*.

    The bucket is named by the caller's identity (``user_id``) and the route as
    declared (``/api/conversations/{conversation_id}/turns``) rather than as
    requested. Two consequences, both deliberate: a learner's budget follows them
    across NATs and proxies (two learners behind one shared IP never spend each
    other's budget), and on a surface whose paths interpolate an id the concrete
    path would mint a fresh budget per id — so a client that starts N conversations
    would get N independent turn budgets against retrieval and generation, which is
    the expensive thing the throttle exists to protect. Falls back to the concrete
    path when no route matched (it cannot be reached through a router, but a
    dependency should not assume its caller).
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None) or request.url.path
    return f"{user.id}:{path}"


def rate_limit_conversations(
    user: Annotated[User, Depends(get_authenticated_user)], request: Request
) -> None:
    """FastAPI dependency: throttle the whole unified conversation surface per user (CONV-22).

    Shares the same swappable limiter as ``rate_limit_auth`` but keys on the
    authenticated caller's ``user_id`` + route *template* — see
    :func:`_user_route_key`. The dependency resolves the authenticated user itself:
    router dependencies run before handler parameters, so an unauthenticated request
    is a 401 here, before any budget is spent.

    What ADR-0029's single dependency guarantees, exactly: start, rename, delete,
    and both turn endpoints carry one policy, so there is **one limit value** to
    reason about across the surface, and each learner's turn budgets are shared
    across all of their conversations rather than granted per conversation — while
    two learners behind one shared proxy IP still get separate budgets. It is not
    one bucket for the whole surface: each route template still counts separately,
    so renaming conversations does not spend the budget for asking questions.
    """
    _hit(_user_route_key(user, request))


def rate_limit_quiz(
    user: Annotated[User, Depends(get_authenticated_user)], request: Request
) -> None:
    """FastAPI dependency: throttle deck generation + card/review writes per user.

    Shares the same swappable limiter and user+template key as
    ``rate_limit_conversations`` (see :func:`_user_route_key`), applied to the
    state-changing quiz endpoints (deck POST + review POST, the card surfaces, and
    the tutor-card accept) so a caller cannot flood batch generation or the
    scheduling writes (QUIZ-18), and so one learner's budget is never spent by
    another behind the same IP.
    """
    _hit(_user_route_key(user, request))


def rate_limit_notes(request: Request) -> None:
    """FastAPI dependency: throttle note writes + highlight capture; 429 when exceeded.

    Shares the same swappable limiter and per-IP+route key as ``rate_limit_auth``
    (same ``KNOWN LIMITATION`` under the proxy topology), applied to the
    state-changing notes endpoints (create/update/delete + capture) so a client
    cannot flood the note writes or the corpus resolution capture does (NF-09).
    """
    _hit(_client_key(request))
