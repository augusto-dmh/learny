"""Section word counts and reading positions

Adds ``corpus_sections.word_count`` (``INTEGER`` NOT NULL DEFAULT ``0``): the
whitespace-delimited token count of the section's derived Markdown, so whole-book
percent and minutes-left are derivable without re-parsing per request. Existing
rows are backfilled from their stored ``markdown`` with the same whitespace-token
count the corpus build uses (``len(markdown.split())``): blank/whitespace-only
markdown counts 0, otherwise the number of ``\\s+``-delimited tokens of the trimmed
text. The DEFAULT ``0`` keeps the column NOT NULL for any row inserted before the
build stamps a real count and mirrors the NOT NULL + server-default idiom of
``0009_anchor_aliases``.

Also creates ``reading_positions``: one row per (user, source) recording where the
reader stopped — the resolved section ``anchor`` plus the server-computed whole-book
``percent`` (``NUMERIC(5,2)``, trustworthy for the Home surface). Both foreign keys
cascade so deleting a user or a source removes their stored positions; unlike a note
anchor this is disposable reading state, not user prose, so the cascade is correct.

Downgrade drops the table and the column.

Revision ID: 0011_reader_progress
Revises: 0010_notes_schema
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_reader_progress"
down_revision: str | None = "0010_notes_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL DEFAULT 0 so pre-existing rows are valid immediately (they get 0),
    # then the backfill below overwrites them with their real token count.
    op.add_column(
        "corpus_sections",
        sa.Column("word_count", sa.Integer(), server_default="0", nullable=False),
    )
    # Backfill each existing row with its whitespace-token count, matching the
    # build's ``len(markdown.split())`` exactly: split on any ``\s+`` run and count
    # the non-empty tokens, so leading/trailing/blank whitespace (spaces, tabs, or
    # newlines) counts 0 and no divide-by-zero can arise downstream.
    op.execute(
        r"""
        UPDATE corpus_sections
        SET word_count = (
            SELECT count(*)
            FROM regexp_split_to_table(markdown, '\s+') AS token
            WHERE token <> ''
        )
        """
    )

    op.create_table(
        "reading_positions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The resolved (canonical) section anchor the reader stopped at.
        sa.Column("anchor", sa.Text(), nullable=False),
        # Server-computed whole-book percent at that anchor (0.00–100.00).
        sa.Column("percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_reading_positions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_reading_positions_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "source_id", name="pk_reading_positions"),
    )


def downgrade() -> None:
    op.drop_table("reading_positions")
    op.drop_column("corpus_sections", "word_count")
