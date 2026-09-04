"""Per-learner starter clones on the shared sample

Deck uniqueness is ``(source_id, content_key) WHERE origin='deck'``, which cannot
hold two learners' clones of the same template on one sample book. Adds a
partial unique index on ``(user_id, source_id, content_key) WHERE origin='starter'``
so clones are per-learner and operator templates stay ``origin='deck'``.

Downgrade drops the index. Existing quiz rows survive.

Revision ID: 0023_starter_quiz_origin
Revises: 0022_sample_and_activation
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_starter_quiz_origin"
down_revision: str | None = "0022_sample_and_activation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_quiz_items_starter_user_content_key",
        "quiz_items",
        ["user_id", "source_id", "content_key"],
        unique=True,
        postgresql_where=sa.text("origin = 'starter'"),
    )


def downgrade() -> None:
    op.drop_index("uq_quiz_items_starter_user_content_key", table_name="quiz_items")
