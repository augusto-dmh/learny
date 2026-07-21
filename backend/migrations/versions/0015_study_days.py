"""Study-day activity rollup

Creates ``study_days``: one row per (user, user-local day) recording study activity
with per-kind counters — ``reviews_count`` (submitted reviews) and ``reading_updates``
(saved reading positions) — both ``INTEGER`` NOT NULL DEFAULT ``0``. The primary key
is ``(user_id, day)`` so an atomic ``INSERT ... ON CONFLICT DO UPDATE`` increment keeps
exactly one row per user-local day under any number of same-day events. The ``user_id``
foreign key cascades: this is the durable study record, disposable only with the user
(unlike stored user prose). Adherence and the heatmap derive from these rows at read
time; nothing derived is stored.

Downgrade drops the table.

Revision ID: 0015_study_days
Revises: 0014_note_cards
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_study_days"
down_revision: str | None = "0014_note_cards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_days",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        # Per-kind counters (AD-151); DEFAULT 0 so an inserted-then-incremented row is
        # always valid and the increment reads a real integer, never NULL.
        sa.Column("reviews_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reading_updates", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_study_days_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "day", name="pk_study_days"),
    )


def downgrade() -> None:
    op.drop_table("study_days")
