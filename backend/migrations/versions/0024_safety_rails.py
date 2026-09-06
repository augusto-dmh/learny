"""Per-learner daily AI spend ledger

Creates ``ai_spend_days``: one row per ``(user_id, day_utc)`` recording the AI spend
the day's generation and embedding calls cost — ``usd_micros`` (BIGINT NOT NULL
DEFAULT 0) plus the free-tier integer counters ``ask_count`` and ``teach_starts``
(INTEGER NOT NULL DEFAULT 0). The primary key makes an atomic
``INSERT ... ON CONFLICT DO UPDATE`` increment keep exactly one row per user per UTC
day under any number of same-day events, so two same-day increments never lose one.
The ``user_id`` foreign key cascades: the ledger is disposable with its user and
names nobody else.

Downgrade drops the table.

Revision ID: 0024_safety_rails
Revises: 0023_starter_quiz_origin
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0024_safety_rails"
down_revision: str | None = "0023_starter_quiz_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_spend_days",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_utc", sa.Date(), nullable=False),
        sa.Column("usd_micros", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("ask_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("teach_starts", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_spend_days_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "day_utc", name="pk_ai_spend_days"),
    )


def downgrade() -> None:
    op.drop_table("ai_spend_days")
