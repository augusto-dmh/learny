"""Quiz schema: quiz_items/quiz_item_scheduling/review_log/quiz_generation_jobs

Creates the active-recall aggregate (RFC-002 Cycle E). ``quiz_items`` are the
citation-grounded cards for a source (unique ``(source_id, content_key)`` so deck
regeneration upserts content without minting duplicates); ``quiz_item_scheduling`` is
the one-per-item FSRS snapshot (indexed on ``due`` for the due-queue read);
``review_log`` is the append-only grade history (rating CHECK 1..4); and
``quiz_generation_jobs`` mirrors ``ingestion_jobs`` for the deck-generation state
machine. ``quiz_items``/``quiz_generation_jobs`` cascade from ``sources`` and the
scheduling/log rows cascade from ``quiz_items``, so deleting a source removes the
whole aggregate with no orphans. ``embedding`` reuses the ``vector`` extension created
in 0005 for near-duplicate detection (no index — exact scan at author scale). No FK
to the corpus tables anywhere: quiz items snapshot their citation so they survive a
corpus replace (which regenerates chunk ids).

Revision ID: 0008_quiz_schema
Revises: 0007_language_aware_fts
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_quiz_schema"
down_revision: str | None = "0007_language_aware_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quiz_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_type", sa.Text(), nullable=False),  # free_recall | cloze
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
        # Verified anchor_quote snapshot — survives a corpus replace (no chunk FK).
        sa.Column("source_excerpt", sa.Text(), nullable=False),
        # sha256 of the chunk text at generation time.
        sa.Column("chunk_hash", sa.Text(), nullable=False),
        # sha256(item_type \x1f norm(question) \x1f norm(answer)) — upsert identity.
        sa.Column("content_key", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),  # active | stale | orphaned
        # Near-duplicate detection identity; NULL until embedded (vector ext from 0005).
        sa.Column("embedding", VECTOR(1536), nullable=True),
        sa.Column(
            "generation_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
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
            ["source_id"],
            ["sources.id"],
            name="fk_quiz_items_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_items"),
        sa.UniqueConstraint("source_id", "content_key", name="uq_quiz_items_source_id"),
    )
    op.create_index("ix_quiz_items_source_id", "quiz_items", ["source_id"])

    op.create_table(
        "quiz_item_scheduling",
        sa.Column("quiz_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        # FSRS-6 snapshot columns (State enum, learning step, stability, difficulty).
        sa.Column("state", sa.SmallInteger(), nullable=False),
        sa.Column("step", sa.SmallInteger(), nullable=True),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["quiz_item_id"],
            ["quiz_items.id"],
            name="fk_quiz_item_scheduling_quiz_item_id_quiz_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("quiz_item_id", name="pk_quiz_item_scheduling"),
    )
    op.create_index(
        "ix_quiz_item_scheduling_due", "quiz_item_scheduling", ["due"]
    )

    op.create_table(
        "review_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quiz_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["quiz_item_id"],
            ["quiz_items.id"],
            name="fk_review_log_quiz_item_id_quiz_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_log"),
        # FSRS Rating is Again(1)/Hard(2)/Good(3)/Easy(4) — no other value is valid.
        sa.CheckConstraint("rating BETWEEN 1 AND 4", name="rating_range"),
    )
    op.create_index("ix_review_log_quiz_item_id", "review_log", ["quiz_item_id"])

    op.create_table(
        "quiz_generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        # queued | running | succeeded | failed.
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "generated_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "discarded_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "failed_sections", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
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
            ["source_id"],
            ["sources.id"],
            name="fk_quiz_generation_jobs_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quiz_generation_jobs"),
    )
    op.create_index(
        "ix_quiz_generation_jobs_source_id", "quiz_generation_jobs", ["source_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_generation_jobs_source_id", table_name="quiz_generation_jobs")
    op.drop_table("quiz_generation_jobs")
    op.drop_index("ix_review_log_quiz_item_id", table_name="review_log")
    op.drop_table("review_log")
    op.drop_index("ix_quiz_item_scheduling_due", table_name="quiz_item_scheduling")
    op.drop_table("quiz_item_scheduling")
    op.drop_index("ix_quiz_items_source_id", table_name="quiz_items")
    op.drop_table("quiz_items")
