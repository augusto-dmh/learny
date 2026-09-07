"""Redis fixed-window limiter — live checks against a real Redis (DOOR-01, DOOR-05).

The module-level probe skips the whole module when nothing listens on
``localhost:6379`` (review finding 5): these tests exercise real windows and
expiries, which no fake can prove. The tests that need NO server — the
dead-relay fail-closed contract and the composition wiring — live in
``tests/test_rate_limit_fail_closed.py`` and always run.
"""

from __future__ import annotations

import socket
import time
from uuid import uuid4

import pytest
import redis

from app.infrastructure.web.redis_rate_limit import RedisFixedWindowRateLimiter

_REDIS_URL = "redis://localhost:6379/15"


def _redis_up() -> bool:
    """Short-timeout probe: is anything accepting connections on :6379?"""
    try:
        with socket.create_connection(("localhost", 6379), timeout=0.3):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _redis_up(), reason="live Redis unavailable")


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
        first = RedisFixedWindowRateLimiter.from_url(_REDIS_URL, max_attempts=2, window_seconds=60)
        second = RedisFixedWindowRateLimiter.from_url(_REDIS_URL, max_attempts=2, window_seconds=60)
        assert first.hit(key) == (True, 0)
        assert second.hit(key) == (True, 0)
        allowed, retry_after = first.hit(key)
        assert allowed is False
        assert retry_after >= 1
    finally:
        client.delete(redis_key)


def test_hit_arms_the_window_expiry_on_the_first_count() -> None:
    client = _live_redis()
    key = f"arm-{uuid4()}"
    redis_key = f"learny:rl:{key}"
    limiter = RedisFixedWindowRateLimiter.from_url(_REDIS_URL, max_attempts=5, window_seconds=60)
    try:
        assert limiter.hit(key) == (True, 0)
        ttl = int(client.ttl(redis_key))
        assert 0 < ttl <= 60
    finally:
        client.delete(redis_key)


def test_window_without_a_ttl_is_re_armed_and_eventually_releases() -> None:
    # A crash between INCR and EXPIRE (or an older binary) leaves a key with no
    # expiry: under a non-atomic INCR/conditional-EXPIRE limiter every later hit
    # skips the EXPIRE branch, the TTL stays -1, and the budget 429s forever.
    client = _live_redis()
    key = f"persisted-{uuid4()}"
    redis_key = f"learny:rl:{key}"
    window = 2
    limiter = RedisFixedWindowRateLimiter.from_url(
        _REDIS_URL, max_attempts=2, window_seconds=window
    )
    try:
        # Seed the partial-failure remnant: over budget, persisted, no TTL.
        client.set(redis_key, "3")
        assert int(client.ttl(redis_key)) == -1

        # The limiter refuses the hit and reports the FULL window as the wait,
        # because the hit itself re-armed the missing expiry.
        allowed, retry_after = limiter.hit(key)
        assert allowed is False
        assert retry_after == window
        assert 0 < int(client.ttl(redis_key)) <= window

        # The window is finite again: once it passes, the caller is let back in
        # (no manual DEL, no indefinite lockout).
        time.sleep(window + 0.5)
        assert limiter.hit(key) == (True, 0)
    finally:
        client.delete(redis_key)
