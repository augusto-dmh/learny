"""Email verify/reset tokens and the verified stamp

Creates ``email_tokens``: single-use tokens for address verification and
password reset (DOOR-34..37). Only the SHA-256 of the raw opaque token is
stored (``secret_hash``, unique — the sessions ``token_hash`` contract); the
raw token exists solely in the outbound mail body. ``purpose`` is the closed
``verify``|``reset`` vocabulary the application constants own, ``expires_at``
bounds the token's life, and ``consumed_at`` is the single-use marker the
consuming conditional UPDATE stamps. The ``user_id`` foreign key cascades: a
token names nobody once its user is gone.

Also adds a nullable ``users.email_verified_at``: the confirmation stamp set
when a live verify token is consumed (DOOR-35). NULL until then — verification
never gates the first session (AD-327) — and NULL for accounts that predate
the rail.

Downgrade drops the column and the table.

Revision ID: 0027_email_verify_reset
Revises: 0026_user_tos_stamp
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0027_email_verify_reset"
down_revision: str | None = "0026_user_tos_stamp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "email_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("secret_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_tokens"),
        sa.UniqueConstraint("secret_hash", name="uq_email_tokens_secret_hash"),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_tokens_user_id", table_name="email_tokens")
    op.drop_table("email_tokens")
    op.drop_column("users", "email_verified_at")
