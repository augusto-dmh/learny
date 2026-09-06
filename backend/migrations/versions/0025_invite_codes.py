"""Registration invite codes

Creates ``invite_codes``: operator-minted codes gating register where
``LEARNY_INVITE_REQUIRED`` is on. The code itself is the identity (primary key,
unique); ``remaining_uses`` counts down by one per successful register and
``expires_at`` (nullable — NULL never expires) bounds the code's life. There is
no user foreign key: an invite exists before, and independently of, the account
it admits, so nothing cascades.

Downgrade drops the table.

Revision ID: 0025_invite_codes
Revises: 0024_safety_rails
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_invite_codes"
down_revision: str | None = "0024_safety_rails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invite_codes",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("remaining_uses", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("code", name="pk_invite_codes"),
    )


def downgrade() -> None:
    op.drop_table("invite_codes")
