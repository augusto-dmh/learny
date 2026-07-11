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

from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class Source:
    """An uploaded source file owned by a user (Cycle 2, design §Components).

    Immutable record: the original bytes live in object storage under
    ``object_key``; this entity holds only the metadata PostgreSQL owns.
    ``object_key`` and ``checksum`` are internal — the web summary path never
    surfaces them (spec P1-Upload AC1). One EPUB file per source this cycle, so
    file attributes are inline rather than in a separate table.
    """

    id: UUID
    user_id: UUID
    title: str
    filename: str
    content_type: str
    byte_size: int
    checksum: str
    object_key: str
    status: str
    created_at: datetime
    updated_at: datetime


class IngestionStatus:
    """Ingestion job status vocabulary (spec §Assumptions).

    ``queued`` and ``running`` are the two *active* states; ``succeeded`` and
    ``failed`` are terminal. String constants (not an enum) because the DB column
    is free-text ``Text`` and ``source.status`` is a plain string projection.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# At most one job in these states may exist per source (ING-03 concurrency guard,
# enforced by a partial unique index at the persistence layer).
ACTIVE_STATUSES = frozenset({IngestionStatus.QUEUED, IngestionStatus.RUNNING})


class IngestionEventType:
    """Ordered lifecycle-event vocabulary for the ingestion progress log.

    A successful run appends ``[queued, started, succeeded]``; a failing run
    appends ``[queued, started, retrying..., failed]`` (spec P1 Observe / Retry).
    """

    QUEUED = "queued"
    STARTED = "started"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class IngestionJob:
    """A durable ingestion job driving one source through its lifecycle.

    Immutable record: the transition helpers return *new* instances so state
    changes are explicit and the persisted row is updated by the caller's
    unit of work. Ownership is reachable only via the parent ``source`` (which
    holds ``user_id``); the job carries no ``user_id`` (AD-014).
    """

    id: UUID
    source_id: UUID
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    def started(self, now: datetime) -> IngestionJob:
        """Begin an attempt: → ``running`` and increment ``attempts`` (ING-02)."""
        return replace(
            self,
            status=IngestionStatus.RUNNING,
            attempts=self.attempts + 1,
            updated_at=now,
        )

    def succeeded(self, now: datetime) -> IngestionJob:
        """Terminal success: → ``succeeded`` (ING-02)."""
        return replace(self, status=IngestionStatus.SUCCEEDED, updated_at=now)

    def retrying(self, now: datetime, error: str) -> IngestionJob:
        """Record a retryable failure: set ``last_error``, stay ``running`` (ING-07)."""
        return replace(self, last_error=error, updated_at=now)

    def failed(self, now: datetime, error: str) -> IngestionJob:
        """Terminal failure: → ``failed`` with a durable ``last_error`` (ING-08)."""
        return replace(
            self,
            status=IngestionStatus.FAILED,
            last_error=error,
            updated_at=now,
        )


@dataclass(frozen=True)
class IngestionEvent:
    """An append-only progress-log entry for an ingestion job (ING-06).

    ``message`` carries a redacted, non-secret summary (e.g. the error text on
    ``retrying``/``failed``); it is ``None`` for plain lifecycle transitions.
    """

    id: UUID
    job_id: UUID
    type: str
    message: str | None
    created_at: datetime
