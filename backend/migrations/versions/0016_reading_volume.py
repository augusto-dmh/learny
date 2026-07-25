"""Per-day reading volume on the study-day rollup

Adds ``study_days.words_advanced``: how many of a book's words the reader newly
covered on that user-local day, ``BIGINT`` NOT NULL DEFAULT ``0``. Words are stored
rather than pages so a day's many small advances accumulate losslessly and the page
quantum stays a presentation constant that can change without rewriting history; the
study window derives its pages figure from this column at read time.

64-bit, unlike its neighbours. They move by one per event; this one moves by however
many words the reader's own anchor says they covered, and the endpoint that feeds it is
deliberately unthrottled — so its addend has no small ceiling, and a caller alternating
between two ends of a long book could reach a 32-bit overflow in a few thousand
requests. An overflow here does not merely lose a figure: it aborts the upsert, and with
it the position write sharing that transaction, so the reader could no longer save their
place for the rest of the day. A wider column removes the reachable ceiling outright.

The DEFAULT means every existing row takes 0 with no backfill — a rollup that predates
the counter simply reports no reading volume, never a fabricated one. The column joins
the existing per-kind counters and is incremented by the same atomic ``INSERT ... ON
CONFLICT DO UPDATE`` path; ``reviews_count`` and ``reading_updates`` keep their exact
meaning, so no heatmap cell changes shade.

Downgrade drops the column.

Revision ID: 0016_reading_volume
Revises: 0015_study_days
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_reading_volume"
down_revision: str | None = "0015_study_days"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "study_days",
        # NOT NULL with a server default: existing rows take 0 without a backfill, and
        # the atomic increment always reads a real integer, never NULL.
        sa.Column("words_advanced", sa.BigInteger(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("study_days", "words_advanced")
