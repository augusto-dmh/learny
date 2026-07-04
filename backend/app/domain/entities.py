"""Identity domain entities (design §3).

Pure domain objects: no FastAPI, SQLAlchemy, or provider-SDK imports
(ADR-007/009 — ``domain`` depends on nothing outward). Persistence,
hashing, and HTTP concerns live in ``app.infrastructure`` adapters that
implement the ports in ``app.domain.ports``.

Security invariants encoded here:
- ``User`` carries no password material (AD-006 / spec AC-4) — credentials
  live only on ``PasswordCredential``.
- ``Session`` carries only the *hash* of the opaque token; the raw token is
  returned once at creation time and never persisted on the entity (design §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class User:
    """An authenticated account holder.

    Deliberately holds no password/hash/secret field: password material is
    isolated on :class:`PasswordCredential` so a ``User`` is safe to surface in
    summaries and logs (spec AC-4 / NFR-SEC-004).
    """

    id: UUID
    email: str
    created_at: datetime


@dataclass(frozen=True)
class PasswordCredential:
    """An Argon2id password hash for a user (AD-006).

    ``algo_params`` captures the hashing parameters in effect when the hash was
    produced, enabling rehash-on-params-change (B2). The plaintext password is
    never stored on this entity — only the encoded ``password_hash``.
    """

    user_id: UUID
    password_hash: str
    algo_params: dict[str, object]
    updated_at: datetime


@dataclass(frozen=True)
class Session:
    """A server-side opaque session (AD-006/007).

    Only ``token_hash`` is persisted; the raw opaque token lives solely in the
    HTTP-only cookie and is resolved back to this row on each authenticated
    request. ``csrf_token`` is the session-bound synchronizer token (AD-007).
    """

    id: UUID
    user_id: UUID
    token_hash: str
    csrf_token: str
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime

    def is_expired(self, now: datetime) -> bool:
        """Return whether this session has passed its expiry at ``now``."""
        return now >= self.expires_at


@dataclass(frozen=True)
class IssuedSession:
    """A freshly created session plus its one-time raw token.

    Repositories return this from ``create`` so the web layer can set the cookie
    with the raw opaque token exactly once; the raw token is never stored.
    """

    session: Session
    raw_token: str
