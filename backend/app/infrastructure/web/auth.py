"""Auth routers + cookie sessions (task C1, FR-AUTH-001..004).

Thin FastAPI adapter over the framework-free identity services. Each handler:
1. delegates to a use-case service (assembled in ``dependencies``),
2. sets/clears the HTTP-only session cookie (``cookies`` helper, NFR-SEC-002),
3. returns a minimal, secret-free JSON summary.

Application errors raised by the services are translated to HTTP status codes by
the global handlers in ``error_handlers`` — handlers here contain no error
mapping or domain logic.

Contract (also consumed by the Next.js proxy in Phase D):
- ``POST /api/auth/register`` → 201, sets session cookie, body: user summary.
- ``POST /api/auth/login``    → 200, sets session cookie, body: user summary.
- ``POST /api/auth/logout``   → 204, clears cookie (auth required; CSRF added in C2).
- ``GET  /api/auth/me``       → 200 user summary + CSRF token (auth required); 401 otherwise.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.application.identity import AuthenticateUser, Logout, RegisterUser
from app.domain.entities import Session, User
from app.infrastructure.web.cookies import clear_session_cookie, set_session_cookie
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    AppSettings,
    CurrentPrincipal,
    get_authenticate_user,
    get_current_session,
    get_logout,
    get_register_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    """Register/login request body.

    Email/password are validated and normalized authoritatively in the
    application layer (``validate_email``/``validate_password``, FR-AUTH-010), so
    these are plain strings here — the boundary does not duplicate policy.
    """

    email: str
    password: str


class UserSummary(BaseModel):
    """Public, secret-free view of a user (safe to return/log, AC-4)."""

    id: UUID
    email: str
    created_at: datetime

    @classmethod
    def from_entity(cls, user: User) -> UserSummary:
        return cls(id=user.id, email=user.email, created_at=user.created_at)


class MeResponse(UserSummary):
    """``/me`` payload — user summary plus the session-bound CSRF token the SPA
    echoes in the ``X-CSRF-Token`` header on writes (AD-007)."""

    csrf_token: str


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_origin)],
)
def register(
    body: Credentials,
    response: Response,
    settings: AppSettings,
    service: Annotated[RegisterUser, Depends(get_register_user)],
) -> UserSummary:
    """Create an account and start a session (FR-AUTH-001). 409 if email taken."""
    result = service(email=body.email, password=body.password)
    set_session_cookie(response, raw_token=result.issued.raw_token, settings=settings)
    return UserSummary.from_entity(result.user)


@router.post("/login", dependencies=[Depends(enforce_origin)])
def login(
    body: Credentials,
    response: Response,
    settings: AppSettings,
    service: Annotated[AuthenticateUser, Depends(get_authenticate_user)],
) -> UserSummary:
    """Validate credentials and start a session (FR-AUTH-002). 401 on failure."""
    result = service(email=body.email, password=body.password)
    set_session_cookie(response, raw_token=result.issued.raw_token, settings=settings)
    return UserSummary.from_entity(result.user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
def logout(
    response: Response,
    settings: AppSettings,
    session: Annotated[Session, Depends(get_current_session)],
    service: Annotated[Logout, Depends(get_logout)],
) -> Response:
    """End the session and clear the cookie (FR-AUTH-003). Auth + CSRF required."""
    service(session_id=session.id)
    clear_session_cookie(response, settings=settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
def me(principal: CurrentPrincipal) -> MeResponse:
    """Return the authenticated user summary + CSRF token (FR-AUTH-004). 401 if unauth."""
    user, session = principal
    return MeResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        csrf_token=session.csrf_token,
    )
