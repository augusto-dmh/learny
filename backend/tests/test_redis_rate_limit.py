"""Redis fixed-window limiter (DOOR-01, DOOR-05)."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
import redis

from app.infrastructure.web.rate_limit import LimiterUnavailable
from app.infrastructure.web.redis_rate_limit import RedisFixedWindowRateLimiter

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
        first = RedisFixedWindowRateLimiter.from_url(_REDIS_URL, max_attempts=2, window_seconds=60)
        second = RedisFixedWindowRateLimiter.from_url(_REDIS_URL, max_attempts=2, window_seconds=60)
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


def test_hit_arms_the_window_expiry_on_the_first_count() -> None:
    client = _live_redis()
    key = f"arm-{uuid4()}"
    redis_key = f"learny:rl:{key}"
    limiter = RedisFixedWindowRateLimiter.from_url(
        _REDIS_URL, max_attempts=5, window_seconds=60
    )
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


def test_create_app_installs_the_redis_limiter() -> None:
    # DOOR-05 wiring: production composition uses Redis when redis_url is set.
    from app.infrastructure.web.rate_limit import get_rate_limiter, set_rate_limiter
    from app.main import create_app

    previous = get_rate_limiter()
    try:
        create_app()
        assert isinstance(get_rate_limiter(), RedisFixedWindowRateLimiter)
    finally:
        set_rate_limiter(previous)


class _UnavailableLimiter:
    def hit(self, key: str) -> tuple[bool, int]:
        raise LimiterUnavailable("down")


def test_limited_route_returns_503_when_redis_is_down() -> None:
    from fastapi.testclient import TestClient

    from app.infrastructure.web.rate_limit import get_rate_limiter, set_rate_limiter
    from app.main import create_app

    previous = get_rate_limiter()
    try:
        app = create_app()
        set_rate_limiter(_UnavailableLimiter())
        with TestClient(app) as client:
            resp = client.post(
                "/api/auth/login",
                json={"email": "a@example.com", "password": "long-enough-password"},
            )
        assert resp.status_code == 503
    finally:
        set_rate_limiter(previous)
