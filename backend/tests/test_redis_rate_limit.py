"""Redis fixed-window limiter (DOOR-01, DOOR-05)."""

from __future__ import annotations

from uuid import uuid4

import pytest
import redis

from app.infrastructure.web.redis_rate_limit import (
    LimiterUnavailable,
    RedisFixedWindowRateLimiter,
)

_REDIS_URL = "redis://localhost:6379/15"


def _live_redis() -> redis.Redis:
    client = redis.Redis.from_url(
        _REDIS_URL,
        socket_connect_timeout=0.4,
        socket_timeout=0.4,
    )
    client.ping()
    return client


def test_two_clients_share_one_window() -> None:
    # DOOR-01: two limiter instances (two API processes) share Redis counts.
    client = _live_redis()
    key = f"share-{uuid4()}"
    redis_key = f"learny:rl:{key}"
    try:
        first = RedisFixedWindowRateLimiter.from_url(
            _REDIS_URL, max_attempts=2, window_seconds=60
        )
        second = RedisFixedWindowRateLimiter.from_url(
            _REDIS_URL, max_attempts=2, window_seconds=60
        )
        assert first.hit(key) == (True, 0)
        assert second.hit(key) == (True, 0)
        allowed, retry_after = first.hit(key)
        assert allowed is False
        assert retry_after >= 1
    finally:
        client.delete(redis_key)


def test_dead_redis_fails_closed() -> None:
    # DOOR-05: a connection/command failure is LimiterUnavailable, not allow.
    limiter = RedisFixedWindowRateLimiter.from_url(
        "redis://127.0.0.1:9/0",
        socket_connect_timeout=0.15,
        socket_timeout=0.15,
    )
    with pytest.raises(LimiterUnavailable):
        limiter.hit("anything")
