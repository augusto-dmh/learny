"""Identity domain ports (design §3).

Structural interfaces (``typing.Protocol``) that application services depend on.
Concrete adapters live in ``app.infrastructure`` (B2 hasher, B3 repositories,
later the storage adapter) and are wired at the composition root. No FastAPI /
SQLAlchemy / SDK imports here (ADR-007/009).

Conventions:
- Repositories return ``None`` (not raise) on a missing lookup, so application
  services control error semantics (e.g. uniform login failure, AC-3).
- Session creation goes through the raw opaque token: callers pass the raw
  token, the adapter persists only its hash, and returns the persisted
  :class:`~app.domain.entities.Session`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import PasswordCredential, Session, User


@runtime_checkable
class Clock(Protocol):
    """Source of the current time — injected so time is deterministic in tests."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


@runtime_checkable
class TokenGenerator(Protocol):
    """Source of high-entropy opaque tokens (session + CSRF).

    Injected so application services stay free of the token-generation adapter
    and so tests can supply deterministic tokens.
    """

    def generate(self) -> str:
        """Return a new high-entropy URL-safe token."""
        ...


@runtime_checkable
class PasswordHasher(Protocol):
    """Password hashing/verification port (AD-006 — Argon2id adapter in B2)."""

    def hash(self, password: str) -> str:
        """Return an encoded hash of ``password``. Never logs the input."""
        ...

    def verify(self, password: str, encoded_hash: str) -> bool:
        """Return whether ``password`` matches ``encoded_hash`` (constant-time)."""
        ...

    def needs_rehash(self, encoded_hash: str) -> bool:
        """Return whether ``encoded_hash`` was produced with outdated parameters."""
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.User`."""

    def add(self, user: User) -> User:
        """Persist a new user. Raises on duplicate email (unique constraint)."""
        ...

    def get_by_id(self, user_id: UUID) -> User | None:
        """Return the user with ``user_id``, or ``None`` if absent."""
        ...

    def get_by_email(self, email: str) -> User | None:
        """Return the user with ``email`` (case-insensitive), or ``None``."""
        ...


@runtime_checkable
class CredentialRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.PasswordCredential`."""

    def add(self, credential: PasswordCredential) -> PasswordCredential:
        """Persist a new credential for a user."""
        ...

    def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        """Return the credential for ``user_id``, or ``None`` if absent."""
        ...

    def update(self, credential: PasswordCredential) -> PasswordCredential:
        """Replace the stored hash/params for the credential's user."""
        ...


@runtime_checkable
class SessionRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.Session`.

    The adapter is responsible for hashing the raw opaque token at rest; callers
    work with raw tokens and never see ``token_hash`` directly except via lookup.
    """

    def create(
        self,
        *,
        user_id: UUID,
        raw_token: str,
        csrf_token: str,
        expires_at: datetime,
    ) -> Session:
        """Persist a new session, storing only the hash of ``raw_token``."""
        ...

    def get_by_raw_token(self, raw_token: str) -> Session | None:
        """Resolve a raw opaque token to its session row, or ``None``."""
        ...

    def touch(self, session_id: UUID, last_seen_at: datetime) -> None:
        """Update ``last_seen_at`` for an active session."""
        ...

    def delete(self, session_id: UUID) -> None:
        """Remove a session (instant revocation / logout)."""
        ...


@runtime_checkable
class StoragePort(Protocol):
    """S3-compatible object-storage port (AD-008).

    Defined now so the domain boundary is stable; the MinIO adapter is minimal
    this cycle (uploads land in a later cycle). Object keys and metadata are
    owned by PostgreSQL; this port handles only blob bytes.
    """

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        """Store ``data`` under ``key``."""
        ...

    def get_object(self, key: str) -> bytes:
        """Return the bytes stored under ``key``. Raises if absent."""
        ...
