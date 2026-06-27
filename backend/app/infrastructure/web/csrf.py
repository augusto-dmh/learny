"""Session-bound (synchronizer) CSRF protection (task C2, AD-007, NFR-SEC-001).

The session row carries a per-session ``csrf_token`` (minted at session
creation). On every state-changing request (POST/PUT/PATCH/DELETE) from an
authenticated principal, the SPA must echo that token in the ``X-CSRF-Token``
header; it is compared (constant-time) against the session row. This is strictly
stronger than double-submit because the expected value lives server-side and is
never derived from a cookie the attacker could inject (AD-007).

Defense in depth:
1. ``SameSite=Lax`` + ``Secure`` + ``HttpOnly`` session cookie (set in C1) — the
   outer perimeter.
2. ``Origin``/``Referer`` host check against the configured trusted origins —
   rejects cross-site form posts that would otherwise ride the cookie.
3. The synchronizer token header check — the authoritative gate.

CSRF is a pure transport concern with no domain meaning, so rejection raises a
FastAPI ``HTTPException(403)`` directly rather than an application error. GETs
never mutate, so they are exempt.

Reusability: ``enforce_csrf`` is a plain dependency — add it to any future
write endpoint's dependency list to get the same protection.
"""

from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.domain.entities import Session
from app.infrastructure.web.dependencies import get_current_session

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _origin_host(request: Request) -> str | None:
    """Return the normalized ``scheme://host[:port]`` of the request's origin.

    Prefers the ``Origin`` header; falls back to ``Referer`` (some browsers omit
    ``Origin`` on same-origin requests). Returns ``None`` when neither is present.
    """
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}".rstrip("/")
    return None


def _check_origin(request: Request) -> None:
    """Reject (403) a state-changing request whose Origin/Referer is untrusted.

    Shared by the synchronizer-token gate and the pre-session (register/login)
    gate. No-op for safe methods and when no trusted origins are configured.
    """
    if request.method in _SAFE_METHODS:
        return
    trusted = get_settings().trusted_origins()
    if not trusted:
        return
    origin = _origin_host(request)
    if origin is None or origin not in trusted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed for state-changing request.",
        )


def enforce_origin(request: Request) -> None:
    """Origin-only CSRF gate for pre-session endpoints (register/login, AD-007).

    These have no session yet, so the synchronizer-token check cannot apply; the
    Origin/Referer host check plus ``SameSite=Lax`` is the available perimeter.
    """
    _check_origin(request)


def enforce_csrf(
    request: Request,
    session: Annotated[Session, Depends(get_current_session)],
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """Reject (403) state-changing authenticated requests lacking a valid token.

    Depends on ``get_current_session`` so an unauthenticated request fails first
    with 401 (handled there); this dependency only runs for authenticated writes.
    """
    if request.method in _SAFE_METHODS:
        return

    # Origin/Referer host check (defense in depth).
    _check_origin(request)

    # Synchronizer token check (authoritative). Constant-time to avoid leaking
    # how much of the token matched.
    if not x_csrf_token or not secrets.compare_digest(x_csrf_token, session.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid CSRF token.",
        )
