"""Claim-level spans on stored citation snapshots (AD-269)

Adds three nullable columns to ``conversation_turn_citations``: ``quoted_text``, the
sentence the generation adapter reported as the one it cited, and ``start_char`` /
``end_char``, that sentence's ``str`` offsets into the ``snippet`` stored on the same
row. Together they let a reader hover a citation mark and see the claim rather than the
whole passage, and let "show in book" highlight the sentence instead of flashing the
section.

Nullable and unbacked by default on purpose. Every row written before this revision is a
citation whose quote was never captured, and the deterministic adapter reports no spans
at all, so a fabricated backfill would be the one thing worse than no quote: a highlight
over a sentence nobody cited. A null span keeps exactly the pre-span behaviour — the
snippet is the passage, and the section is the highlight target.

The offsets live beside the snippet rather than pointing into the live corpus, which is
what makes them survive a re-ingest: the citation snapshot already carries its own text
with no FK into ``corpus_chunks`` (AD-033), so a corpus replace can regenerate every
chunk id without moving the text these indices address.

Downgrade drops the three columns. No other data is touched, and a downgraded database
reads exactly as it did before this revision.

Revision ID: 0018_citation_spans
Revises: 0017_conversations
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_citation_spans"
down_revision: str | None = "0017_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("quoted_text", "start_char", "end_char")


def upgrade() -> None:
    op.add_column(
        "conversation_turn_citations",
        sa.Column("quoted_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "conversation_turn_citations",
        sa.Column("start_char", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_turn_citations",
        sa.Column("end_char", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("conversation_turn_citations", column)
