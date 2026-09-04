"""Tutor-card origin link on quiz items (AD-297, AD-298)

Adds a nullable ``conversation_id`` on ``quiz_items`` pointing at
``conversations(id)`` ``ON DELETE SET NULL``, plus a partial unique
``(conversation_id) WHERE origin='tutor' AND conversation_id IS NOT NULL``.

``origin`` stays TEXT: application code pins the new ``'tutor'`` value. The
source CHECK ``source_id IS NOT NULL OR origin='note'`` is unchanged — tutor
cards are source-backed. Deleting the conversation severs the link and leaves
the card; the unique no longer occupies that row, so a later conversation can
mint its own.

Downgrade drops the unique index, the FK, and the column. Seeded quiz rows
survive without the link.

Revision ID: 0020_tutor_cards
Revises: 0019_tutor_state
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020_tutor_cards"
down_revision: str | None = "0019_tutor_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_items",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quiz_items_conversation_id_conversations",
        "quiz_items",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "uq_quiz_items_tutor_conversation_id",
        "quiz_items",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("origin = 'tutor' AND conversation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_quiz_items_tutor_conversation_id", table_name="quiz_items")
    op.drop_constraint(
        "fk_quiz_items_conversation_id_conversations",
        "quiz_items",
        type_="foreignkey",
    )
    op.drop_column("quiz_items", "conversation_id")
