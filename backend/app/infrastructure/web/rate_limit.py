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
    """Build a limiter key from client IP + route path (per-endpoint throttle)."""
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
