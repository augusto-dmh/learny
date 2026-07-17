"""Anchor aliases on corpus sections

Adds ``corpus_sections.anchor_aliases`` (``TEXT[]`` NOT NULL DEFAULT ``'{}'``), the
list of anchors that the structure-normalization pass merged into a surviving
section. They stay resolvable — section reads, quiz reconciliation, and teaching
retrieval all fall back to an alias — so a citation, quiz item, or teaching target
saved against a merged-away anchor never dangles after a re-ingest. No index: the
list is section-owned and tiny (dozens at most), read only alongside the section
itself. Downgrade drops the column.

Revision ID: 0009_anchor_aliases
Revises: 0008_quiz_schema
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009_anchor_aliases"
down_revision: str | None = "0008_quiz_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "corpus_sections",
        sa.Column(
            "anchor_aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("corpus_sections", "anchor_aliases")
