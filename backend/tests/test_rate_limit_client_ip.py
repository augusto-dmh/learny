"""Auth limiter keys on trusted-proxy X-Real-IP, never on a client XFF chain."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.infrastructure.web import rate_limit
from app.infrastructure.web.rate_limit import _client_key, trusted_client_ip


def _request(
    *,
    client: str,
    headers: list[tuple[bytes, bytes]] | None = None,
    path: str = "/api/auth/login",
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers or [],
            "query_string": b"",
            "client": (client, 12345),
        }
    )


def test_untrusted_peer_cannot_spoof_x_real_ip() -> None:
    request = _request(
        client="8.8.8.8",
        headers=[(b"x-real-ip", b"203.0.113.10")],
    )
    assert trusted_client_ip(request) == "8.8.8.8"


def test_trusted_peer_uses_x_real_ip() -> None:
    request = _request(
        client="testclient",
        headers=[(b"x-real-ip", b"203.0.113.10")],
    )
    assert trusted_client_ip(request) == "203.0.113.10"
    assert _client_key(request) == "203.0.113.10:/api/auth/login"


def test_private_docker_peer_is_trusted() -> None:
    request = _request(
        client="10.0.0.5",
        headers=[(b"x-real-ip", b"198.51.100.20")],
    )
    assert trusted_client_ip(request) == "198.51.100.20"


def test_client_supplied_xff_is_ignored() -> None:
    request = _request(
        client="testclient",
        headers=[(b"x-forwarded-for", b"198.51.100.1, 10.0.0.2")],
    )
    assert trusted_client_ip(request) == "testclient"
    assert _client_key(request) == "testclient:/api/auth/login"


def test_direct_private_peer_cannot_rotate_identity_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under the production default (variable unset), a direct-connect private
    client is not a trusted proxy: its ``X-Real-IP`` is ignored and the limiter
    keys on the peer, so rotating the header mints nothing. This is the guest
    sample ask's identity source — the first anonymous surface keyed on it."""
    monkeypatch.delenv("LEARNY_TRUSTED_PROXY_HOSTS", raising=False)
    settings = Settings(_env_file=None, environment="production")
    monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)

    request = _request(
        client="10.0.0.5",
        headers=[(b"x-real-ip", b"203.0.113.10")],
        path="/api/sample/ask",
    )
    assert trusted_client_ip(request) == "10.0.0.5"
    assert _client_key(request) == "10.0.0.5:/api/sample/ask"


def test_proxied_request_still_limits_by_real_client_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behind a pinned narrow proxy CIDR (the prod overlay's shape), a genuinely
    proxied request still keys on the real client IP the proxy stamped."""
    monkeypatch.delenv("LEARNY_TRUSTED_PROXY_HOSTS", raising=False)
    settings = Settings(_env_file=None, trusted_proxy_hosts="10.28.0.0/16")
    monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)

    request = _request(
        client="10.28.0.9",
        headers=[(b"x-real-ip", b"203.0.113.10")],
        path="/api/sample/ask",
    )
    assert trusted_client_ip(request) == "203.0.113.10"
    assert _client_key(request) == "203.0.113.10:/api/sample/ask"
