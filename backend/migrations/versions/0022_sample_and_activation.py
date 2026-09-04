"""Shared sample flag and once-per-user activation events

Adds ``sources.is_sample`` (BOOLEAN NOT NULL DEFAULT false) so one operator-owned
book can be listed for every signed-in user without cloning corpus rows. A
partial unique index allows only one true sample. Adds ``activation_events``
keyed ``(user_id, name)`` with CASCADE from ``users`` so first-session events
insert once per user.

Downgrade drops the index, column, and table. Existing sources survive as
ordinary (non-sample) rows.

Revision ID: 0022_sample_and_activation
Revises: 0021_review_quality
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0022_sample_and_activation"
down_revision: str | None = "0021_review_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "is_sample",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_sources_one_sample",
        "sources",
        ["is_sample"],
        unique=True,
        postgresql_where=sa.text("is_sample"),
    )
    op.create_table(
        "activation_events",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_activation_events_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "name", name="pk_activation_events"),
    )


def downgrade() -> None:
    op.drop_table("activation_events")
    op.drop_index("uq_sources_one_sample", table_name="sources")
    op.drop_column("sources", "is_sample")
