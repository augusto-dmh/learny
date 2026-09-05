"""Redis-backed ``RateLimiter`` shared across API processes.

Celery already talks to Redis as a broker; this adapter uses a pooled redis-py
client so limiter ``hit`` calls do not open a TCP connection per request.
Keys are colon-separated Strings (INCR + EXPIRE). Redis errors raise
``LimiterUnavailable`` so callers can fail closed (503) instead of skipping
the throttle.
"""

from __future__ import annotations

import redis
from redis.exceptions import RedisError

from app.infrastructure.web.rate_limit import LimiterUnavailable, RateLimiter


class RedisFixedWindowRateLimiter:
    """Fixed-window limiter whose counts live in Redis (AD-330).

    ``hit`` matches :class:`RateLimiter`: ``(allowed, retry_after_seconds)``.
    """

    def __init__(
        self,
        client: redis.Redis,
        *,
        max_attempts: int = 10,
        window_seconds: int = 60,
    ) -> None:
        self._client = client
        self._max = max_attempts
        self._window = window_seconds

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        max_attempts: int = 10,
        window_seconds: int = 60,
        socket_connect_timeout: float = 1.0,
        socket_timeout: float = 1.0,
    ) -> RedisFixedWindowRateLimiter:
        pool = redis.ConnectionPool.from_url(
            url,
            max_connections=50,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )
        client = redis.Redis(connection_pool=pool)
        return cls(client, max_attempts=max_attempts, window_seconds=window_seconds)

    def hit(self, key: str) -> tuple[bool, int]:
        redis_key = f"learny:rl:{key}"
        try:
            count = int(self._client.incr(redis_key))
            if count == 1:
                self._client.expire(redis_key, self._window)
            if count > self._max:
                ttl = int(self._client.ttl(redis_key))
                retry_after = ttl if ttl > 0 else self._window
                return False, max(1, retry_after)
            return True, 0
        except RedisError as exc:
            raise LimiterUnavailable("rate limiter unavailable") from exc


def make_redis_limiter(url: str) -> RateLimiter:
    """Composition-root helper: pooled Redis limiter with the in-memory defaults."""
    return RedisFixedWindowRateLimiter.from_url(url)
