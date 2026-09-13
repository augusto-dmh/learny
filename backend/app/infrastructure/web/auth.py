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
- ``POST /api/auth/email/verify`` → 204, stamps ``email_verified_at`` (DOOR-35);
  uniform 403 for a token that is not live.
- ``POST /api/auth/email/verify/resend`` → 204, re-sends the verify mail (auth required).
- ``POST /api/auth/password/reset-request`` → 204 always; mail only for a known
  address (DOOR-36).
- ``POST /api/auth/password/reset`` → 204, sets the new password (DOOR-37); 403
  for a token that is not live.
- ``POST /api/auth/logout``   → 204, clears cookie (auth required; CSRF added in C2).
- ``GET  /api/auth/me``       → 200 user summary + CSRF token + stored AI-profile
  id (auth required); 401 otherwise.
- ``DELETE /api/auth/account`` → 204, clears cookie (auth + CSRF; 502 leaves the account).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.application.identity import (
    AuthenticateUser,
    DeleteAccount,
    Logout,
    RegisterUser,
    RequestPasswordReset,
    ResetPassword,
    SendEmailVerification,
    VerifyEmail,
)
from app.domain.entities import Session, User
from app.infrastructure.web.cookies import clear_session_cookie, set_session_cookie
from app.infrastructure.web.csrf import enforce_csrf, enforce_origin
from app.infrastructure.web.dependencies import (
    AppSettings,
    CurrentPrincipal,
    get_ai_profile_choice,
    get_authenticate_user,
    get_authenticated_user,
    get_current_session,
    get_delete_account,
    get_logout,
    get_register_user,
    get_request_password_reset,
    get_reset_password,
    get_send_email_verification,
    get_verify_email,
)
from app.infrastructure.web.rate_limit import rate_limit_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    """Register/login request body.

    Email/password are validated and normalized authoritatively in the
    application layer (``validate_email``/``validate_password``, FR-AUTH-010), so
    these are plain strings here — the boundary does not duplicate policy. The
    invite code is likewise a plain optional string: where
    ``LEARNY_INVITE_REQUIRED`` is on, the application service demands a live code
    and answers the uniform 403 itself (DOOR-20); with the flag off it is ignored.
    ``accepted_tos`` defaults to False here — an omitted consent never registers
    (DOOR-25) — which is the boundary that gives the default its force.
    """

    email: str
    password: str
    invite_code: str | None = None
    accepted_tos: bool = False


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
    echoes in the ``X-CSRF-Token`` header on writes (AD-007), and the caller's
    stored AI-profile choice (``ai_profile_id``, null when unset) so the account
    page has it on first paint. The id is returned exactly as stored: an id the
    operator renamed or removed is reported as-is — serving falls back to the
    deployment default, and the UI renders the choice as unset."""

    csrf_token: str
    ai_profile_id: str | None = None


class VerifyEmailBody(BaseModel):
    """The raw single-use token from the verify mail. The token *is* the auth:
    these endpoints are pre-session by design, so they carry the Origin gate and
    the auth rate limiter (like register/login) but no session or CSRF token."""

    token: str


class ResetPasswordRequestBody(BaseModel):
    """The address a reset mail is requested for. Whether the account exists is
    never reflected in the response (uniform 204, DOOR-36)."""

    email: str


class ResetPasswordBody(BaseModel):
    """The raw single-use reset token plus the new password. The password is
    validated authoritatively in the application layer (FR-AUTH-010)."""

    token: str
    password: str


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth), Depends(enforce_origin)],
)
def register(
    body: Credentials,
    response: Response,
    settings: AppSettings,
    service: Annotated[RegisterUser, Depends(get_register_user)],
) -> UserSummary:
    """Create an account and start a session (FR-AUTH-001). 409 if email taken."""
    result = service(
        email=body.email,
        password=body.password,
        invite_code=body.invite_code,
        accepted_tos=body.accepted_tos,
    )
    set_session_cookie(response, raw_token=result.issued.raw_token, settings=settings)
    return UserSummary.from_entity(result.user)


@router.post(
    "/login",
    dependencies=[Depends(rate_limit_auth), Depends(enforce_origin)],
)
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
    "/email/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_auth), Depends(enforce_origin)],
)
def verify_email(
    body: VerifyEmailBody,
    response: Response,
    service: Annotated[VerifyEmail, Depends(get_verify_email)],
) -> Response:
    """Confirm an address with the raw single-use verify token (DOOR-35).

    The token is the auth — no session, no CSRF. Not-live (unknown, replayed,
    expired, wrong-purpose) is one uniform 403.
    """
    service(raw_token=body.token)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/email/verify/resend",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_auth), Depends(enforce_origin)],
)
def resend_verification_email(
    response: Response,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[SendEmailVerification, Depends(get_send_email_verification)],
) -> Response:
    """Re-send the verify mail for the signed-in account (DOOR-38).

    Authenticated (the mail always goes to the caller's own address), throttled
    on the client IP like the other pre-session writes. The send is best-effort:
    204 either way (DOOR-40), so the response never leaks relay health.
    """
    service(user_id=user.id, email=user.email)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/password/reset-request",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_auth), Depends(enforce_origin)],
)
def request_password_reset(
    body: ResetPasswordRequestBody,
    response: Response,
    service: Annotated[RequestPasswordReset, Depends(get_request_password_reset)],
) -> Response:
    """Ask for a reset mail (DOOR-36).

    204 whether or not the email exists — mail goes out only for a registered
    address, so the endpoint cannot be used to enumerate accounts.
    """
    service(email=body.email)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_auth), Depends(enforce_origin)],
)
def reset_password(
    body: ResetPasswordBody,
    response: Response,
    service: Annotated[ResetPassword, Depends(get_reset_password)],
) -> Response:
    """Set a new password with the raw single-use reset token (DOOR-37).

    The token is the auth. Not-live is the same uniform 403 as verify; a
    well-formed but rejected password is a 422 that burns no token.
    """
    service(raw_token=body.token, password=body.password)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
def delete_account(
    response: Response,
    settings: AppSettings,
    user: Annotated[User, Depends(get_authenticated_user)],
    service: Annotated[DeleteAccount, Depends(get_delete_account)],
) -> Response:
    """Erase the caller's account (DOOR-30..32). Auth + CSRF required.

    Storage objects are deleted before the user row (fail closed on storage:
    502 and the account survives). The row delete cascades every child table,
    including sessions, so the cookie is cleared on the way out.
    """
    service(user=user)
    clear_session_cookie(response, settings=settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
def me(
    principal: CurrentPrincipal,
    ai_profile_choice: Annotated[str | None, Depends(get_ai_profile_choice)],
) -> MeResponse:
    """Return the authenticated user summary + CSRF token + stored AI-profile id.

    401 if unauthenticated. The choice rides the existing first paint (null when
    nothing is stored), so the account page needs no extra roundtrip.
    """
    user, session = principal
    return MeResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        csrf_token=session.csrf_token,
        ai_profile_id=ai_profile_choice,
    )
