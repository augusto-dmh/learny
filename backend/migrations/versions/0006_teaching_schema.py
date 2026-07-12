"""Teaching schema: teaching_sessions/turns/turn_citations (design §Data Models, Cycle 7)

Creates the teaching sessions aggregate (AD-033). ``teaching_sessions`` anchors a
bounded conversation to one corpus section of a source (FK CASCADE); ``teaching_turns``
pair a user message with a generated response and are position-unique per session
(``(session_id, turn_index)`` — the turn-index race arbiter, TEACH-17);
``teaching_turn_citations`` are rank-ordered denormalized citation snapshots, unique per
``(turn_id, rank)``. Session/turn/citation FKs cascade so deleting a source removes the
whole aggregate; ``chunk_id`` carries **no** FK so a corpus replace can delete the live
chunk without breaking stored history (AD-033/AD-018). Each child is indexed on its
parent FK.

Revision ID: 0006_teaching_schema
Revises: 0005_retrieval_indexes
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_teaching_schema"
down_revision: str | None = "0005_retrieval_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teaching_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_anchor", sa.Text(), nullable=False),
        sa.Column("target_section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_title", sa.Text(), nullable=False),
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
            name="fk_teaching_sessions_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teaching_sessions"),
    )
    op.create_index("ix_teaching_sessions_source_id", "teaching_sessions", ["source_id"])

    op.create_table(
        "teaching_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("answer_status", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["teaching_sessions.id"],
            name="fk_teaching_turns_session_id_teaching_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teaching_turns"),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_teaching_turns_session_id"),
    )
    op.create_index("ix_teaching_turns_session_id", "teaching_turns", ["session_id"])

    op.create_table(
        "teaching_turn_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        # No FK: snapshot reference so a corpus replace never breaks history (AD-033).
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["teaching_turns.id"],
            name="fk_teaching_turn_citations_turn_id_teaching_turns",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_teaching_turn_citations"),
        sa.UniqueConstraint("turn_id", "rank", name="uq_teaching_turn_citations_turn_id"),
    )
    op.create_index(
        "ix_teaching_turn_citations_turn_id", "teaching_turn_citations", ["turn_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_teaching_turn_citations_turn_id", table_name="teaching_turn_citations")
    op.drop_table("teaching_turn_citations")
    op.drop_index("ix_teaching_turns_session_id", table_name="teaching_turns")
    op.drop_table("teaching_turns")
    op.drop_index("ix_teaching_sessions_source_id", table_name="teaching_sessions")
    op.drop_table("teaching_sessions")
