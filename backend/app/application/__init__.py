"""Application layer — use-case services orchestrating domain ports.

Re-exports the Cycle-1 identity use cases and their errors for the composition
root (Phase C web layer) to import from ``app.application``.
"""

from __future__ import annotations

from app.application.errors import (
    EmailAlreadyExists,
    IdentityError,
    InvalidCredentials,
    NotAuthenticated,
    NotAuthorized,
    ValidationError,
)
from app.application.identity import (
    DEFAULT_SESSION_TTL,
    AuthenticateUser,
    AuthorizeOwnership,
    AuthResult,
    CurrentUser,
    Logout,
    RegisterUser,
)

__all__ = [
    "DEFAULT_SESSION_TTL",
    "AuthResult",
    "AuthenticateUser",
    "AuthorizeOwnership",
    "CurrentUser",
    "EmailAlreadyExists",
    "IdentityError",
    "InvalidCredentials",
    "Logout",
    "NotAuthenticated",
    "NotAuthorized",
    "RegisterUser",
    "ValidationError",
]
