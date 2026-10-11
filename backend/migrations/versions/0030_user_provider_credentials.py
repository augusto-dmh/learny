"""Learner provider keys, sealed at rest

Creates ``user_provider_credentials``: at most one row per (user, provider)
holding a learner's API key in envelope-encrypted form (ADR-0033). The row
keeps the AES-256-GCM ciphertext and its nonce, the data key wrapped by the
operator's key-encryption key and that wrap's nonce, the KEK's id, a
fingerprint, and the key's last four characters. It never holds the plaintext
key or an unwrapped data key. ``user_id`` references ``users(id)`` ON DELETE
CASCADE, so the keys die with their account; ``UNIQUE (user_id, provider)``
keeps one key per provider. ``created_at``/``updated_at`` are UTC server
defaults. The table is empty at creation: nothing existing is migrated.

Downgrade drops the table; a re-upgrade restores it clean.

Revision ID: 0030_user_provider_credentials
Revises: 0029_user_ai_preferences
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0030_user_provider_credentials"
down_revision: str | None = "0029_user_ai_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_provider_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("dek_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("kek_id", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("last4", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_provider_credentials_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_provider_credentials"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_credentials_user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_provider_credentials")
