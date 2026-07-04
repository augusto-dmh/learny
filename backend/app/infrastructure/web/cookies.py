"""Session cookie helpers (task C1, NFR-SEC-002).

Centralizes how the session cookie is set and cleared so the security attributes
are defined in exactly one place and stay consistent across endpoints:

- ``HttpOnly``  — the raw token is never readable by browser JS (NFR-SEC-003).
- ``Secure``    — sent only over HTTPS (configurable off for local HTTP dev).
- ``SameSite``  — ``Lax`` (AD-007 outer CSRF perimeter).
- ``path``      — scoped to the configured path.

The cookie value is the opaque raw session token only — never the user id, CSRF
token, or any secret (NFR-SEC-002).
"""

from __future__ import annotations

from fastapi import Response

from app.core.config import Settings


def set_session_cookie(response: Response, *, raw_token: str, settings: Settings) -> None:
    """Set the HTTP-only session cookie carrying the opaque raw token."""
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )


def clear_session_cookie(response: Response, *, settings: Settings) -> None:
    """Remove the session cookie (logout) using matching attributes."""
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
