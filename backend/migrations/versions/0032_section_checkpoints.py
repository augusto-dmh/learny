"""End-of-section checkpoints, and confidence + assistance on the review record

Creates ``section_checkpoints`` (one optional end-of-section loop a learner takes
on one section of one source, with the prediction they made before retrieving)
and ``checkpoint_attempts`` (each retrieval inside it: a ``recall`` of an existing
card or the one ``explain`` of the section). A checkpoint cascades with its user
and its source; an attempt cascades with its checkpoint, while its links to the
card it recalls and the review-log row its grade wrote are SET NULL, so deleting
a card or a log row never deletes the learner's attempt history. The once-only
transitions (respond, grade) are conditional UPDATEs over the ``*_at`` stamps, so
there is no state column to drift.

Adds ``review_log.confidence`` (1..3, NULL when not rated) and
``review_log.assisted`` (NULL for every row written before this revision: whether
those grades were unaided was never recorded, and labelling them unaided would
manufacture exactly the illusion the mastery signal exists to avoid).

Downgrade drops both tables and both columns; a re-upgrade restores them clean.

Revision ID: 0032_section_checkpoints
Revises: 0031_user_locale_preferences
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0032_section_checkpoints"
down_revision: str | None = "0031_user_locale_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "section_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
        sa.Column("section_title", sa.Text(), nullable=False),
        sa.Column("prediction", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "prediction IS NULL OR prediction BETWEEN 1 AND 3",
            name="prediction_range",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_section_checkpoints_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_section_checkpoints_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_section_checkpoints"),
    )
    op.create_index(
        "ix_section_checkpoints_user_id_source_id",
        "section_checkpoints",
        ["user_id", "source_id"],
    )
    op.create_index(
        "ix_section_checkpoints_source_id",
        "section_checkpoints",
        ["source_id"],
    )

    op.create_table(
        "checkpoint_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("quiz_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("confidence", sa.SmallInteger(), nullable=True),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "feedback_citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("review_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('recall', 'explain')",
            name="kind_values",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 1 AND 3",
            name="confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["section_checkpoints.id"],
            name="fk_checkpoint_attempts_checkpoint_id_section_checkpoints",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quiz_item_id"],
            ["quiz_items.id"],
            name="fk_checkpoint_attempts_quiz_item_id_quiz_items",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["review_log_id"],
            ["review_log.id"],
            name="fk_checkpoint_attempts_review_log_id_review_log",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_checkpoint_attempts"),
        sa.UniqueConstraint(
            "checkpoint_id",
            "position",
            name="uq_checkpoint_attempts_checkpoint_id",
        ),
    )
    op.create_index(
        "ix_checkpoint_attempts_quiz_item_id",
        "checkpoint_attempts",
        ["quiz_item_id"],
    )
    op.create_index(
        "ix_checkpoint_attempts_review_log_id",
        "checkpoint_attempts",
        ["review_log_id"],
    )

    op.add_column("review_log", sa.Column("confidence", sa.SmallInteger(), nullable=True))
    op.add_column("review_log", sa.Column("assisted", sa.Boolean(), nullable=True))
    # The bare name is what the metadata's ``ck_%(table_name)s_%(constraint_name)s``
    # convention expands to ``ck_review_log_confidence_range``.
    op.create_check_constraint(
        "confidence_range",
        "review_log",
        "confidence IS NULL OR confidence BETWEEN 1 AND 3",
    )


def downgrade() -> None:
    op.drop_constraint("confidence_range", "review_log", type_="check")
    op.drop_column("review_log", "assisted")
    op.drop_column("review_log", "confidence")
    op.drop_index("ix_checkpoint_attempts_review_log_id", table_name="checkpoint_attempts")
    op.drop_index("ix_checkpoint_attempts_quiz_item_id", table_name="checkpoint_attempts")
    op.drop_table("checkpoint_attempts")
    op.drop_index("ix_section_checkpoints_source_id", table_name="section_checkpoints")
    op.drop_index("ix_section_checkpoints_user_id_source_id", table_name="section_checkpoints")
    op.drop_table("section_checkpoints")
