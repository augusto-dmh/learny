"""Redis fixed-window limiter — checks that need NO live Redis server.

Kept outside ``test_redis_rate_limit.py``'s module-level live-Redis skip gate
so they always run (review finding 5): a dead relay fails closed, the app
wires the Redis limiter, and a down limiter answers 503 — none of it needs
anything listening on localhost:6379.
"""

from __future__ import annotations

import pytest

from app.infrastructure.web.rate_limit import LimiterUnavailable
from app.infrastructure.web.redis_rate_limit import RedisFixedWindowRateLimiter


def test_dead_redis_fails_closed() -> None:
    # DOOR-05: a connection/command failure is LimiterUnavailable, not allow.
    limiter = RedisFixedWindowRateLimiter.from_url(
        "redis://127.0.0.1:9/0",
        socket_connect_timeout=0.15,
        socket_timeout=0.15,
    )
    with pytest.raises(LimiterUnavailable):
        limiter.hit("anything")


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
