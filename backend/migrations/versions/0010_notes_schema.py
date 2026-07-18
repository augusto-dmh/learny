"""Notes schema: notes/note_anchors/tags/note_tags/note_links + block content_hash

Creates the notes & second-brain aggregate (RFC-003 Cycle E). A ``notes`` row is a
whole-Markdown document owned by a user; ``note_anchors`` carry the book-citation
payload (section anchor + snapshot, block hash/ordinal, in-block offsets, and the
quote-with-context snapshot) that lets a highlight survive re-ingestion. ``tags``/
``note_tags`` are first-class labels (unique per user by lowercased name — the app
lowercases before write); ``note_links`` are the wikilink-derived backlink index.

THE INVERSE-CASCADE RULE IS THE CORE INVARIANT: no note table has a foreign key
into ``corpus_*`` or ``sources``. ``note_anchors.source_id`` is a *bare* UUID
column, not an FK, so deleting a source or replacing its corpus (which regenerates
corpus rows) can never cascade into — and destroy — a user's note or anchor. Anchors
are reconciled/orphaned by an explicit ingestion step, never by database cascade.
The only cascades are *within* the notes aggregate: ``notes`` from ``users``,
``note_anchors``/``note_tags``/``note_links`` from ``notes``, ``note_tags`` from
``tags``; ``note_links.target_note_id`` is ON DELETE SET NULL so a deleted note's
inbound links keep their ``target_text`` and simply lose the resolved target.

Also adds ``corpus_blocks.content_hash`` (nullable): the normalized-text sha256 the
corpus build computes per block, used to bind highlight anchors to a block. It is
nullable with NO BACKFILL (AD-111) — existing blocks stay NULL until the next
re-ingest recomputes them; the quote-with-context anchor tiers cover unhashed
blocks in the meantime.

Revision ID: 0010_notes_schema
Revises: 0009_anchor_aliases
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_notes_schema"
down_revision: str | None = "0009_anchor_aliases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notes_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notes"),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])

    op.create_table(
        "note_anchors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Bare UUID — deliberately NOT a foreign key (inverse-cascade invariant): a
        # source/corpus delete must never cascade into a note anchor.
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Snapshots so an orphaned anchor still renders without the corpus.
        sa.Column("source_title", sa.Text(), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Block binding — NULL when the owning block was unhashed or unresolved; the
        # quote snapshot below then carries the anchor.
        sa.Column("block_hash", sa.Text(), nullable=True),
        sa.Column("block_ordinal", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        # Quote-with-context snapshot (exact + 32-char prefix/suffix, ADR-0026 §1).
        sa.Column("quote_exact", sa.Text(), nullable=False),
        sa.Column("quote_prefix", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("quote_suffix", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),  # active | stale | orphaned
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["notes.id"],
            name="fk_note_anchors_note_id_notes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_note_anchors"),
    )
    op.create_index("ix_note_anchors_note_id", "note_anchors", ["note_id"])
    # Reconcile/orphan-on-source-delete reads all anchors for a source (NF-07/08).
    op.create_index("ix_note_anchors_source_id", "note_anchors", ["source_id"])

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Stored already-lowercased by the application; the unique below is the
        # per-user identity so two casings of the same tag never coexist.
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tags_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_id"),
    )

    op.create_table(
        "note_tags",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["notes.id"],
            name="fk_note_tags_note_id_notes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name="fk_note_tags_tag_id_tags",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", "tag_id", name="pk_note_tags"),
    )
    # Tag-filtered note listing reads by tag_id (the PK already serves note_id).
    op.create_index("ix_note_tags_tag_id", "note_tags", ["tag_id"])

    op.create_table(
        "note_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Resolved wikilink target; NULL when the [[title]] matches no note, and set
        # NULL (never deleted) when a resolved target note is later deleted.
        sa.Column("target_note_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Always-populated raw link text so an unresolved/broken link still renders.
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["notes.id"],
            name="fk_note_links_note_id_notes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_note_id"],
            ["notes.id"],
            name="fk_note_links_target_note_id_notes",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_note_links"),
    )
    op.create_index("ix_note_links_note_id", "note_links", ["note_id"])
    # Backlinks read all links pointing at a note; also serves the SET NULL sweep.
    op.create_index("ix_note_links_target_note_id", "note_links", ["target_note_id"])

    # Block content hash for highlight anchoring (NF-02). Nullable with no backfill
    # (AD-111): existing blocks stay NULL until the next re-ingest recomputes them,
    # and the quote-with-context anchor tiers cover unhashed blocks meanwhile.
    op.add_column(
        "corpus_blocks",
        sa.Column("content_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("corpus_blocks", "content_hash")
    op.drop_index("ix_note_links_target_note_id", table_name="note_links")
    op.drop_index("ix_note_links_note_id", table_name="note_links")
    op.drop_table("note_links")
    op.drop_index("ix_note_tags_tag_id", table_name="note_tags")
    op.drop_table("note_tags")
    op.drop_table("tags")
    op.drop_index("ix_note_anchors_source_id", table_name="note_anchors")
    op.drop_index("ix_note_anchors_note_id", table_name="note_anchors")
    op.drop_table("note_anchors")
    op.drop_index("ix_notes_user_id", table_name="notes")
    op.drop_table("notes")
