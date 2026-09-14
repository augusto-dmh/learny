"""Per-user AI serving preference

Creates ``user_ai_preferences``: one row per user naming the declared
generation profile that should lead that user's Ask/Teach chain. The primary
key is ``user_id`` (one choice per account) referencing ``users(id)`` ON DELETE
CASCADE, so the choice dies with its account; ``profile_id`` is NOT NULL text
naming a profile in the operator's registry — a stored id is a hint, not a pin,
so resolution falls back to the operator default chain when the named profile
is no longer declared or cannot serve the requested mode.
``created_at``/``updated_at`` are UTC server defaults; an upsert keeps exactly
one row per user.

Downgrade drops the table; a re-upgrade restores it clean.

Revision ID: 0029_user_ai_preferences
Revises: 0028_quiz_deck_spend_marker
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0029_user_ai_preferences"
down_revision: str | None = "0028_quiz_deck_spend_marker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_ai_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", sa.Text(), nullable=False),
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
            name="fk_user_ai_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_ai_preferences"),
    )


def downgrade() -> None:
    op.drop_table("user_ai_preferences")
