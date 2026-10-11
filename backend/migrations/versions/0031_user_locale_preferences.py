"""Per-user interface-language preference

Creates ``user_locale_preferences``: one row per user naming the interface
language (``en`` or ``pt-BR``) the learner chose in Account. The primary key is
``user_id`` (one choice per account) referencing ``users(id)`` ON DELETE CASCADE,
so the choice dies with its account; ``locale`` is NOT NULL text. There is no
CHECK constraint on purpose: the supported set lives in application code, so a
further locale is a catalog change and not a migration, and a stored value that
is no longer supported reads as unset. A missing row means "automatic".
``created_at``/``updated_at`` are UTC server defaults; an upsert keeps exactly
one row per user.

Downgrade drops the table; a re-upgrade restores it clean.

Revision ID: 0031_user_locale_preferences
Revises: 0030_user_provider_credentials
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0031_user_locale_preferences"
down_revision: str | None = "0030_user_provider_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_locale_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
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
            name="fk_user_locale_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_locale_preferences"),
    )


def downgrade() -> None:
    op.drop_table("user_locale_preferences")
