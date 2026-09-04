"""Tutor-ladder columns on conversations (AD-291)

Adds five columns to ``conversations`` so the application-owned hint ladder has a
durable home: ``tutor_phase`` and ``hint_level`` (all-or-nothing NULL together),
``tutor_ordinary_turns`` and ``tutor_scaffold_misses`` (NOT NULL, default 0), and
``tutor_check_text`` (the restatement that closed the session).

Answer threads and rows written before this revision keep both phase and hint
NULL (TUTOR-26). A half-populated pair is refused by CHECK rather than left for
the policy to guess.

Downgrade drops the CHECK and the five columns. Seeded conversations survive.

Revision ID: 0019_tutor_state
Revises: 0018_citation_spans
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019_tutor_state"
down_revision: str | None = "0018_citation_spans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    "tutor_phase",
    "hint_level",
    "tutor_ordinary_turns",
    "tutor_scaffold_misses",
    "tutor_check_text",
)


def upgrade() -> None:
    op.add_column("conversations", sa.Column("tutor_phase", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("hint_level", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("tutor_ordinary_turns", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "conversations",
        sa.Column("tutor_scaffold_misses", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("conversations", sa.Column("tutor_check_text", sa.Text(), nullable=True))
    # The bare name expands via ``ck_%(table_name)s_%(constraint_name)s`` to
    # ``ck_conversations_tutor_phase_hint_all_or_nothing``.
    op.create_check_constraint(
        "tutor_phase_hint_all_or_nothing",
        "conversations",
        "(tutor_phase IS NULL) = (hint_level IS NULL)",
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE conversations DROP CONSTRAINT ck_conversations_tutor_phase_hint_all_or_nothing"
    )
    for column in reversed(_COLUMNS):
        op.drop_column("conversations", column)
