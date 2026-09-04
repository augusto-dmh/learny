"""Review-quality columns: discard reasons, flags, and undo snapshots

Adds ``quiz_generation_jobs.discard_reasons`` (JSONB NOT NULL DEFAULT ``{}``) so a
succeeded deck can explain yield (REV-01). Adds ``quiz_items.flagged_at``
(TIMESTAMPTZ NULL) as an orthogonal hide-from-due flag — not a fourth status, so
reconcile keeps owning ``active|stale|orphaned`` (AD-305). Adds ``review_log.undone_at``
plus previous-scheduling snapshot columns so undo restores the pre-grade FSRS state
without deleting the log row (AD-306). Pre-cycle log rows keep NULL snapshots and
cannot be undone. Existing job rows take ``{}`` with no backfill; existing cards stay
unflagged.

Downgrade drops the new columns. Seeded quiz rows, jobs, and log rows survive.

Revision ID: 0021_review_quality
Revises: 0020_tutor_cards
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021_review_quality"
down_revision: str | None = "0020_tutor_cards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_generation_jobs",
        sa.Column(
            "discard_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "quiz_items",
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "review_log",
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("review_log", sa.Column("prev_state", sa.SmallInteger(), nullable=True))
    op.add_column("review_log", sa.Column("prev_step", sa.SmallInteger(), nullable=True))
    op.add_column("review_log", sa.Column("prev_stability", sa.Float(), nullable=True))
    op.add_column("review_log", sa.Column("prev_difficulty", sa.Float(), nullable=True))
    op.add_column(
        "review_log",
        sa.Column("prev_due", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "review_log",
        sa.Column("prev_last_review", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("review_log", "prev_last_review")
    op.drop_column("review_log", "prev_due")
    op.drop_column("review_log", "prev_difficulty")
    op.drop_column("review_log", "prev_stability")
    op.drop_column("review_log", "prev_step")
    op.drop_column("review_log", "prev_state")
    op.drop_column("review_log", "undone_at")
    op.drop_column("quiz_items", "flagged_at")
    op.drop_column("quiz_generation_jobs", "discard_reasons")
