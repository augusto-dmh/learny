"""Domain layer — entities, value objects, and ports.

Per ADR-007/009 this layer imports nothing from infrastructure, FastAPI, or
provider SDKs. Adapters depend inward only.

Re-exports the Cycle-1 identity entities and ports so callers can import from
``app.domain`` without reaching into submodules.
"""

from __future__ import annotations

from app.domain.entities import (
    IssuedSession,
    PasswordCredential,
    Session,
    User,
)
from app.domain.ports import (
    Clock,
    CredentialRepository,
    PasswordHasher,
    SessionRepository,
    StoragePort,
    TokenGenerator,
    UserRepository,
)

__all__ = [
    "Clock",
    "CredentialRepository",
    "IssuedSession",
    "PasswordCredential",
    "PasswordHasher",
    "Session",
    "SessionRepository",
    "StoragePort",
    "TokenGenerator",
    "User",
    "UserRepository",
]
