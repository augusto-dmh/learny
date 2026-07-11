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


class InvalidSourceUpload(Exception):
    """An uploaded source failed validation before anything was persisted.

    ``kind`` distinguishes the failure so the web layer can map it to the right
    status (``extension``/``content_type`` → 415, ``size`` → 413,
    ``empty``/``title`` → 422).
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class SourceNotFound(Exception):
    """A source does not exist or is not the caller's.

    Non-owner and missing reads collapse to this single error so the web layer
    returns 404 either way (no existence disclosure — spec P1-View AC2).
    """


class StorageUnavailable(Exception):
    """Object storage could not be written; no source row was persisted (SRC-09)."""
