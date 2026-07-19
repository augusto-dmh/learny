"""Card origin and note provenance

Gives ``quiz_items`` a typed ``origin`` (``deck`` | ``highlight``) and a nullable
``note_anchor_id`` provenance link, and splits the uniqueness rule by origin.

``origin`` is ``TEXT NOT NULL DEFAULT 'deck'``: every pre-existing row was minted by
whole-source deck generation, so the default classifies the existing corpus correctly
with no backfill.

``note_anchor_id`` references ``note_anchors.id`` ``ON DELETE SET NULL``. The direction
matters: the derived card points at its origin, never the reverse, so deleting a note
severs the link but cannot destroy the card (ADR-0026 — nothing outside the notes
aggregate may cascade-destroy user prose, and nothing inside it may destroy derived
cards either). A severed card still renders from its own ``source_excerpt``/``anchor``
snapshot. This mirrors the ``note_links.target_note_id`` SET NULL precedent.

The shipped ``uq_quiz_items_source_id`` UNIQUE ``(source_id, content_key)`` is replaced
by two *partial* unique indexes so the two identity modes coexist in one table:

* ``uq_quiz_items_deck_content_key`` on ``(source_id, content_key) WHERE origin='deck'``
  keeps the deck upsert path byte-identical — regeneration still collapses onto one row.
* ``uq_quiz_items_highlight_anchor_key`` on ``(note_anchor_id, content_key)
  WHERE origin='highlight' AND note_anchor_id IS NOT NULL`` makes re-accepting identical
  text from the *same* highlight idempotent, while letting two different highlights
  produce cards with the same ``content_key``. Highlight cards are identified by their
  minted ``id``; ``content_key`` is demoted to a rewritable fingerprint that stays
  populated so deck generation can keep deduping against them.

Downgrade drops both partial indexes and the two columns, and restores the original
named ``uq_quiz_items_source_id`` constraint.

Revision ID: 0012_card_provenance
Revises: 0011_reader_progress
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012_card_provenance"
down_revision: str | None = "0011_reader_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL DEFAULT 'deck' classifies every pre-existing row correctly: they were
    # all minted by whole-source deck generation, so no backfill is needed.
    op.add_column(
        "quiz_items",
        sa.Column("origin", sa.Text(), server_default="deck", nullable=False),
    )
    # Provenance into the notes aggregate. SET NULL, never CASCADE: deleting the note
    # severs the link and leaves the card fully renderable from its own snapshot.
    op.add_column(
        "quiz_items",
        sa.Column("note_anchor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quiz_items_note_anchor_id_note_anchors",
        "quiz_items",
        "note_anchors",
        ["note_anchor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_quiz_items_note_anchor_id", "quiz_items", ["note_anchor_id"])

    # Split the single global unique into two origin-scoped partial uniques.
    op.drop_constraint("uq_quiz_items_source_id", "quiz_items", type_="unique")
    op.create_index(
        "uq_quiz_items_deck_content_key",
        "quiz_items",
        ["source_id", "content_key"],
        unique=True,
        postgresql_where=sa.text("origin = 'deck'"),
    )
    op.create_index(
        "uq_quiz_items_highlight_anchor_key",
        "quiz_items",
        ["note_anchor_id", "content_key"],
        unique=True,
        postgresql_where=sa.text("origin = 'highlight' AND note_anchor_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_quiz_items_highlight_anchor_key", table_name="quiz_items")
    op.drop_index("uq_quiz_items_deck_content_key", table_name="quiz_items")
    # Restore the original global upsert identity under its original name.
    op.create_unique_constraint(
        "uq_quiz_items_source_id", "quiz_items", ["source_id", "content_key"]
    )

    op.drop_index("ix_quiz_items_note_anchor_id", table_name="quiz_items")
    op.drop_constraint(
        "fk_quiz_items_note_anchor_id_note_anchors", "quiz_items", type_="foreignkey"
    )
    op.drop_column("quiz_items", "note_anchor_id")
    op.drop_column("quiz_items", "origin")
