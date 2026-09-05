"""Auth limiter keys on trusted-proxy X-Real-IP, never on a client XFF chain."""

from __future__ import annotations

from starlette.requests import Request

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
