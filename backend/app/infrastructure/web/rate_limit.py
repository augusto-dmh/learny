"""Pluggable rate-limit hook for auth endpoints (task C3, FR-AUTH-009).

A conservative, swappable throttle on register/login to blunt credential-stuffing
and brute force. The default is a process-local fixed-window counter keyed by
client IP + route — fine for a single-process dev/MVP boot and good enough to
satisfy the abuse requirement. It deliberately implements the same ``RateLimiter``
protocol a Redis-backed limiter would, so swapping in a distributed limiter later
(once multiple API processes run behind the worker topology) is a one-line wiring
change with no endpoint edits.

On limit breach the dependency raises ``HTTPException(429)`` with a ``Retry-After``
header. Replace the active limiter via :func:`set_rate_limiter` (e.g. in tests or
when wiring a Redis adapter at the composition root).
"""

from __future__ import annotations

import threading
import time
from typing import Protocol

from fastapi import HTTPException, Request, status


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


def _client_key(request: Request) -> str:
    """Build a limiter key from client IP + route path (per-endpoint throttle).

    KNOWN LIMITATION (FR-AUTH-009): browser auth traffic reaches FastAPI through
    the same-origin Next.js proxy (ADR-017), so ``request.client.host`` is the
    proxy's IP for *every* user, not the real client. The per-IP key therefore
    collapses to a single shared bucket per route: it cannot isolate individual
    attackers, and one actor sending ``max_attempts`` requests can exhaust the
    window for everyone (a cheap global lockout). This is acceptable only for
    the single-process MVP boot. Before running behind the real proxy topology,
    derive the client IP from a forwarded-client header the trusted proxy sets
    (e.g. ``X-Real-IP``) -- reading only the hop the proxy appends, never the raw
    client-supplied chain -- and configure the backend to trust that proxy.
    """
    client = request.client.host if request.client else "unknown"
    return f"{client}:{request.url.path}"


def rate_limit_auth(request: Request) -> None:
    """FastAPI dependency: throttle auth attempts; 429 when the window is exceeded."""
    allowed, retry_after = get_rate_limiter().hit(_client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit_upload(request: Request) -> None:
    """FastAPI dependency: throttle source uploads; 429 when the window is exceeded.

    Shares the same swappable limiter and per-IP+route key as ``rate_limit_auth``
    (same ``KNOWN LIMITATION`` under the proxy topology), applied to the upload
    endpoint so a client cannot flood object storage with writes.
    """
    allowed, retry_after = get_rate_limiter().hit(_client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit_questions(request: Request) -> None:
    """FastAPI dependency: throttle questions; 429 when the window is exceeded.

    Shares the same swappable limiter and per-IP+route key as ``rate_limit_auth``
    (same ``KNOWN LIMITATION`` under the proxy topology), applied to the questions
    endpoint so a client cannot flood retrieval/generation (QA-22).
    """
    allowed, retry_after = get_rate_limiter().hit(_client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
