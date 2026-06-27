"""Application-layer errors for the Identity module (task B4).

Framework-free exceptions raised by use-case services. The web layer (Phase C)
maps these to HTTP responses; keeping them here preserves the layering boundary
(ADR-007/009) and lets unit tests assert behaviour without FastAPI.
"""

from __future__ import annotations


class IdentityError(Exception):
    """Base class for identity use-case errors."""


class ValidationError(IdentityError):
    """Input failed validation (email format or password policy, FR-AUTH-010)."""


class EmailAlreadyExists(IdentityError):
    """Registration attempted with an email that is already taken."""


class InvalidCredentials(IdentityError):
    """Login failed. Uniform for unknown email or wrong password (no enumeration)."""


class NotAuthenticated(IdentityError):
    """No valid session resolves the presented token."""


class NotAuthorized(IdentityError):
    """An authenticated user attempted to act on a resource they do not own."""
