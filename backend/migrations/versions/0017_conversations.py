"""Generalize the teaching aggregate into conversations (ADR-0029)

Renames ``teaching_sessions``/``teaching_turns``/``teaching_turn_citations`` to
``conversations``/``conversation_turns``/``conversation_turn_citations`` and widens the
aggregate so one model covers every grounded conversation about a book: a conversation
carries a ``scope_anchors`` list (``[]`` = the whole book), a renameable ``title``, and a
single explicit ``include_notes`` choice, while each turn records the ``mode``
(``answer`` | ``teach``) that produced it. The three ``target_*`` columns stay as the
denormalized snapshot of the primary teach target and become nullable, since a whole-book
conversation has no target.

This is a rename in place, not a copy: the data, the ``sources`` CASCADE, the
``UNIQUE(conversation_id, turn_index)`` turn-order arbiter, and the FK-less citation
snapshot (AD-033) all survive untouched. Postgres does not rename a table's indexes or
constraints along with the table, so each one is renamed explicitly — otherwise the
database would keep ``teaching``-era identifiers that no longer match the metadata the
application reflects against.

Backfill maps every existing teaching session onto the new model exactly as it behaved:
``scope_anchors = [target_anchor]`` (a real JSON array, not a quoted string),
``title = target_title``, ``include_notes = false`` (the teaching default), and every
existing turn ``mode = 'teach'``. The added columns are filled before they are tightened
to NOT NULL, so no row is ever left with a fabricated value.

Two guards come with the widening. A CHECK keeps the target snapshot all-or-nothing now
that the NOT NULLs no longer say it, and an index on ``(updated_at DESC, id DESC)`` serves
the cross-source list's ordering, which from this release grows by a row per question
asked.

Downgrade restores the 0016 shape. Conversations that have no teach target cannot be
expressed by that shape at all — its ``target_*`` columns are NOT NULL — so they are
deleted (with their turns and citations, by cascade) before the columns are re-tightened.
A downgrade therefore loses whole-book conversations; scoped ones round-trip intact.

Revision ID: 0017_conversations
Revises: 0016_reading_volume
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_conversations"
down_revision: str | None = "0016_reading_volume"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_constraint(table: str, old: str, new: str) -> None:
    op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def _rename_index(old: str, new: str) -> None:
    op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')


def upgrade() -> None:
    op.rename_table("teaching_sessions", "conversations")
    _rename_constraint("conversations", "pk_teaching_sessions", "pk_conversations")
    _rename_constraint(
        "conversations",
        "fk_teaching_sessions_source_id_sources",
        "fk_conversations_source_id_sources",
    )
    _rename_index("ix_teaching_sessions_source_id", "ix_conversations_source_id")

    op.rename_table("teaching_turns", "conversation_turns")
    op.alter_column("conversation_turns", "session_id", new_column_name="conversation_id")
    _rename_constraint("conversation_turns", "pk_teaching_turns", "pk_conversation_turns")
    _rename_constraint(
        "conversation_turns",
        "fk_teaching_turns_session_id_teaching_sessions",
        "fk_conversation_turns_conversation_id_conversations",
    )
    _rename_constraint(
        "conversation_turns",
        "uq_teaching_turns_session_id",
        "uq_conversation_turns_conversation_id",
    )
    _rename_index("ix_teaching_turns_session_id", "ix_conversation_turns_conversation_id")

    op.rename_table("teaching_turn_citations", "conversation_turn_citations")
    _rename_constraint(
        "conversation_turn_citations",
        "pk_teaching_turn_citations",
        "pk_conversation_turn_citations",
    )
    _rename_constraint(
        "conversation_turn_citations",
        "fk_teaching_turn_citations_turn_id_teaching_turns",
        "fk_conversation_turn_citations_turn_id_conversation_turns",
    )
    _rename_constraint(
        "conversation_turn_citations",
        "uq_teaching_turn_citations_turn_id",
        "uq_conversation_turn_citations_turn_id",
    )
    _rename_index("ix_teaching_turn_citations_turn_id", "ix_conversation_turn_citations_turn_id")

    # Added nullable, backfilled, then tightened: an existing row is never NOT NULL
    # against a value the migration invented.
    op.add_column("conversations", sa.Column("title", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("scope_anchors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("conversations", sa.Column("include_notes", sa.Boolean(), nullable=True))
    op.execute(
        # jsonb_build_array, not to_jsonb: the scope is a list of anchors, and a bare
        # to_jsonb(target_anchor) would store the anchor as a quoted scalar string.
        "UPDATE conversations SET "
        "title = target_title, "
        "scope_anchors = jsonb_build_array(target_anchor), "
        "include_notes = false"
    )
    op.alter_column("conversations", "title", nullable=False)
    op.alter_column("conversations", "scope_anchors", nullable=False)
    op.alter_column("conversations", "include_notes", nullable=False)

    # A whole-book conversation has no teach target, so the snapshot loosens.
    op.alter_column("conversations", "target_anchor", existing_type=sa.Text(), nullable=True)
    op.alter_column(
        "conversations",
        "target_section_path",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
    )
    op.alter_column("conversations", "target_title", existing_type=sa.Text(), nullable=True)

    # The trio is all-or-nothing now that it is nullable, which is what the NOT NULLs
    # used to say. Every backfilled row carries a full target, so this holds on the
    # existing data without a repair step.
    # The bare name is what the metadata's ``ck_%(table_name)s_%(constraint_name)s``
    # convention expands to ``ck_conversations_target_all_or_nothing``.
    op.create_check_constraint(
        "target_all_or_nothing",
        "conversations",
        "(target_anchor IS NULL) = (target_section_path IS NULL) "
        "AND (target_anchor IS NULL) = (target_title IS NULL)",
    )

    # The cross-source list orders by (updated_at desc, id desc); from this release
    # every question asked adds a row, so the ordering gets its own index rather than
    # a sort over the user's whole set.
    op.execute(
        "CREATE INDEX ix_conversations_updated_at_id ON conversations (updated_at DESC, id DESC)"
    )

    op.add_column("conversation_turns", sa.Column("mode", sa.Text(), nullable=True))
    op.execute("UPDATE conversation_turns SET mode = 'teach'")
    op.alter_column("conversation_turns", "mode", nullable=False)


def downgrade() -> None:
    op.drop_column("conversation_turns", "mode")

    op.drop_index("ix_conversations_updated_at_id", table_name="conversations")
    op.execute("ALTER TABLE conversations DROP CONSTRAINT ck_conversations_target_all_or_nothing")

    # The 0016 shape cannot hold a targetless conversation; its turns and citations go
    # with it through the existing cascades.
    op.execute("DELETE FROM conversations WHERE target_anchor IS NULL")
    op.alter_column("conversations", "target_anchor", existing_type=sa.Text(), nullable=False)
    op.alter_column(
        "conversations",
        "target_section_path",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.alter_column("conversations", "target_title", existing_type=sa.Text(), nullable=False)

    op.drop_column("conversations", "include_notes")
    op.drop_column("conversations", "scope_anchors")
    op.drop_column("conversations", "title")

    _rename_index("ix_conversation_turn_citations_turn_id", "ix_teaching_turn_citations_turn_id")
    _rename_constraint(
        "conversation_turn_citations",
        "uq_conversation_turn_citations_turn_id",
        "uq_teaching_turn_citations_turn_id",
    )
    _rename_constraint(
        "conversation_turn_citations",
        "fk_conversation_turn_citations_turn_id_conversation_turns",
        "fk_teaching_turn_citations_turn_id_teaching_turns",
    )
    _rename_constraint(
        "conversation_turn_citations",
        "pk_conversation_turn_citations",
        "pk_teaching_turn_citations",
    )
    op.rename_table("conversation_turn_citations", "teaching_turn_citations")

    _rename_index("ix_conversation_turns_conversation_id", "ix_teaching_turns_session_id")
    _rename_constraint(
        "conversation_turns",
        "uq_conversation_turns_conversation_id",
        "uq_teaching_turns_session_id",
    )
    _rename_constraint(
        "conversation_turns",
        "fk_conversation_turns_conversation_id_conversations",
        "fk_teaching_turns_session_id_teaching_sessions",
    )
    _rename_constraint("conversation_turns", "pk_conversation_turns", "pk_teaching_turns")
    op.alter_column("conversation_turns", "conversation_id", new_column_name="session_id")
    op.rename_table("conversation_turns", "teaching_turns")

    _rename_index("ix_conversations_source_id", "ix_teaching_sessions_source_id")
    _rename_constraint(
        "conversations",
        "fk_conversations_source_id_sources",
        "fk_teaching_sessions_source_id_sources",
    )
    _rename_constraint("conversations", "pk_conversations", "pk_teaching_sessions")
    op.rename_table("conversations", "teaching_sessions")
