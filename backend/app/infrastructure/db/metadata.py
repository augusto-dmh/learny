"""SQLAlchemy Core table metadata for the Identity module (design §4).

This is the authoritative schema definition shared by Alembic (migrations) and,
from task B3, the repository adapters. It is Core-level metadata only — no ORM
session/engine and no domain imports, so it stays inside the infrastructure
boundary (ADR-007/009).

Tables:
- ``users``            — id (uuid pk), email (unique, lowercased via citext), created_at
- ``user_credentials`` — user_id (fk), password_hash, algo_params, updated_at
- ``sessions``         — id (uuid pk), user_id (fk), token_hash (unique), csrf_token,
                          expires_at, created_at, last_seen_at

The session cookie carries the raw opaque token; only its hash (``token_hash``)
is persisted (design §4 / AD-006).
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID

# Consistent constraint naming so migrations are deterministic and reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    # citext extension is created by the migration; email is case-insensitively unique.
    Column("email", CITEXT, nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

user_credentials = Table(
    "user_credentials",
    metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("password_hash", Text, nullable=False),
    # Argon2id parameters (AD-006) captured for rehash-on-params-change.
    Column("algo_params", JSONB, nullable=False, server_default="{}"),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("token_hash", String(128), nullable=False, unique=True),
    Column("csrf_token", String(128), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
