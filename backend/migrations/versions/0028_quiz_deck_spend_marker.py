"""One-time deck-spend marker on quiz generation jobs

Adds a nullable ``spend_recorded_at`` timestamp to ``quiz_generation_jobs``:
the idempotency marker the deck worker stamps with a single conditional
UPDATE inside the same transaction that debits the pass's usage and
finalizes the job. A redelivered deck task (``acks_late`` or a visibility-
timeout redelivery) observes a stamped marker and skips the debit, so a
crash between the old separate debit and finalize transactions can no
longer charge one generation twice. NULL until the settling transaction
commits — including after a mid-transaction rollback, which un-does the
debit and the stamp together.

Downgrade drops the column.

Revision ID: 0028_quiz_deck_spend_marker
Revises: 0027_email_verify_reset
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_quiz_deck_spend_marker"
down_revision: str | None = "0027_email_verify_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_generation_jobs",
        sa.Column("spend_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quiz_generation_jobs", "spend_recorded_at")
