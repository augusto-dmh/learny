"""PostgreSQL repository adapters for the Identity module (task B3).

SQLAlchemy 2.x Core adapters implementing the domain repository ports against
the shared table metadata (``app.infrastructure.db.metadata``). Each repository
operates on a caller-provided ``Connection`` so the transaction boundary lives
at the composition root (Phase C), not inside the adapter.

Mapping notes:
- ``User`` ↔ ``users``; email is ``citext`` (case-insensitive unique).
- ``PasswordCredential`` ↔ ``user_credentials`` (one row per user, pk = user_id).
- ``Session`` ↔ ``sessions``: the adapter hashes the raw opaque token and
  persists only ``token_hash`` (design §4); lookup is by hashing the presented
  raw token and matching the unique ``token_hash``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, insert, select, update
from sqlalchemy import delete as sa_delete

from app.domain.entities import PasswordCredential, Session, User
from app.infrastructure.db.metadata import sessions, user_credentials, users
from app.infrastructure.security.tokens import hash_token


class SqlAlchemyUserRepository:
    """``UserRepository`` backed by the ``users`` table."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, user: User) -> User:
        """Insert a user. Propagates ``IntegrityError`` on duplicate email."""
        self._conn.execute(
            insert(users).values(
                id=user.id,
                email=user.email,
                created_at=user.created_at,
            )
        )
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        row = self._conn.execute(
            select(users).where(users.c.id == user_id)
        ).one_or_none()
        return _to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        # citext makes this comparison case-insensitive at the DB level.
        row = self._conn.execute(
            select(users).where(users.c.email == email)
        ).one_or_none()
        return _to_user(row) if row is not None else None


class SqlAlchemyCredentialRepository:
    """``CredentialRepository`` backed by the ``user_credentials`` table."""

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def add(self, credential: PasswordCredential) -> PasswordCredential:
        self._conn.execute(
            insert(user_credentials).values(
                user_id=credential.user_id,
                password_hash=credential.password_hash,
                algo_params=credential.algo_params,
                updated_at=credential.updated_at,
            )
        )
        return credential

    def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        row = self._conn.execute(
            select(user_credentials).where(user_credentials.c.user_id == user_id)
        ).one_or_none()
        return _to_credential(row) if row is not None else None

    def update(self, credential: PasswordCredential) -> PasswordCredential:
        self._conn.execute(
            update(user_credentials)
            .where(user_credentials.c.user_id == credential.user_id)
            .values(
                password_hash=credential.password_hash,
                algo_params=credential.algo_params,
                updated_at=credential.updated_at,
            )
        )
        return credential


class SqlAlchemySessionRepository:
    """``SessionRepository`` backed by the ``sessions`` table.

    Stores only ``token_hash`` (SHA-256 of the raw opaque token). The raw token
    is never persisted; it is returned to the caller once at creation time.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def create(
        self,
        *,
        user_id: UUID,
        raw_token: str,
        csrf_token: str,
        expires_at: datetime,
    ) -> Session:
        session_id = uuid4()
        token_hash = hash_token(raw_token)
        row = self._conn.execute(
            insert(sessions)
            .values(
                id=session_id,
                user_id=user_id,
                token_hash=token_hash,
                csrf_token=csrf_token,
                expires_at=expires_at,
            )
            .returning(sessions)
        ).one()
        return _to_session(row)

    def get_by_raw_token(self, raw_token: str) -> Session | None:
        row = self._conn.execute(
            select(sessions).where(sessions.c.token_hash == hash_token(raw_token))
        ).one_or_none()
        return _to_session(row) if row is not None else None

    def touch(self, session_id: UUID, last_seen_at: datetime) -> None:
        self._conn.execute(
            update(sessions)
            .where(sessions.c.id == session_id)
            .values(last_seen_at=last_seen_at)
        )

    def delete(self, session_id: UUID) -> None:
        self._conn.execute(sa_delete(sessions).where(sessions.c.id == session_id))


def _to_user(row) -> User:  # noqa: ANN001 — Row is an internal SQLAlchemy type
    return User(id=row.id, email=row.email, created_at=row.created_at)


def _to_credential(row) -> PasswordCredential:  # noqa: ANN001
    return PasswordCredential(
        user_id=row.user_id,
        password_hash=row.password_hash,
        algo_params=row.algo_params,
        updated_at=row.updated_at,
    )


def _to_session(row) -> Session:  # noqa: ANN001
    return Session(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        csrf_token=row.csrf_token,
        expires_at=row.expires_at,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    )
