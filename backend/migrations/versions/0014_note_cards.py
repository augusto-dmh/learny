"""Card ownership by user + note-promoted cards

Extends ``quiz_items`` so a note can be promoted to review cards (RFC-003 Cycle F,
AD-148/149). Three shifts land together because the ownership switch forces them:

* ``user_id`` is added, backfilled from each card's source, then made ``NOT NULL``
  with an ``ON DELETE CASCADE`` FK to ``users`` and an index. Ownership was reachable
  only through the parent source (AD-014); a note card has no source, so ownership is
  denormalized onto the card itself (AD-149). Every pre-existing card is deck- or
  highlight-origin and therefore source-backed, so the backfill is total and no row is
  left ``NULL`` before the ``NOT NULL`` tightening.
* ``source_id`` becomes nullable, guarded by a CHECK ``source_id IS NOT NULL OR
  origin = 'note'`` so only a note card may be source-less.
* ``note_id`` (FK ``notes`` ``ON DELETE SET NULL``, indexed) is the promoted-note
  provenance — SET NULL so deleting the note severs the link without destroying the
  derived card (AD-145), mirroring ``note_anchor_id`` from 0012 — and ``note_changed_at``
  records when the note last changed under a promoted card (AD-144).

**Downgrade deletes ``origin='note'`` rows first.** Those rows are source-less by
construction, so restoring ``source_id NOT NULL`` is impossible while they exist. The
data loss is confined to the new note-card regime this migration introduced (it did not
exist before the upgrade), mirroring 0012's backfill-then-reverse shape; deck and
highlight cards are untouched. Then the CHECK, ``note_changed_at``, ``note_id`` (index +
FK + column), ``user_id`` (index + FK + column) are dropped and ``source_id`` is restored
to ``NOT NULL``.

Revision ID: 0014_note_cards
Revises: 0013_notes_retrieval
Create Date: 2026-07-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014_note_cards"
down_revision: str | None = "0013_notes_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Denormalized ownership (AD-149). Add nullable, backfill from the source, then
    #    tighten to NOT NULL — every pre-existing card is source-backed, so the backfill
    #    is total and the tightening cannot fail.
    op.add_column(
        "quiz_items",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        "UPDATE quiz_items SET user_id = sources.user_id "
        "FROM sources WHERE quiz_items.source_id = sources.id"
    )
    op.alter_column("quiz_items", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_quiz_items_user_id_users",
        "quiz_items",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_quiz_items_user_id", "quiz_items", ["user_id"])

    # 2. A note card has no source: relax source_id and gate the exception by origin.
    op.alter_column("quiz_items", "source_id", nullable=True)
    op.create_check_constraint(
        "ck_quiz_items_source_or_note",
        "quiz_items",
        "source_id IS NOT NULL OR origin = 'note'",
    )

    # 3. Promoted-note provenance (SET NULL, never CASCADE — the card survives the note's
    #    deletion, AD-145) + the note-changed flag the review badge derives from (AD-144).
    op.add_column(
        "quiz_items",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_quiz_items_note_id_notes",
        "quiz_items",
        "notes",
        ["note_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_quiz_items_note_id", "quiz_items", ["note_id"])
    op.add_column(
        "quiz_items",
        sa.Column("note_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Note cards are source-less by construction, so source_id cannot return to NOT NULL
    # while they exist. Delete them first — the loss is confined to the note-card regime
    # this migration introduced; deck and highlight cards are untouched.
    op.execute("DELETE FROM quiz_items WHERE origin = 'note'")

    op.drop_column("quiz_items", "note_changed_at")
    op.drop_index("ix_quiz_items_note_id", table_name="quiz_items")
    op.drop_constraint(
        "fk_quiz_items_note_id_notes", "quiz_items", type_="foreignkey"
    )
    op.drop_column("quiz_items", "note_id")

    op.drop_constraint("ck_quiz_items_source_or_note", "quiz_items", type_="check")
    op.alter_column("quiz_items", "source_id", nullable=False)

    op.drop_index("ix_quiz_items_user_id", table_name="quiz_items")
    op.drop_constraint(
        "fk_quiz_items_user_id_users", "quiz_items", type_="foreignkey"
    )
    op.drop_column("quiz_items", "user_id")
