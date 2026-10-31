"""BYOK policy ledgers and per-answer usage on turns

Learner-keyed calls on a hosted instance need two ledgers and one preference
row of their own, and every turn needs a record of what its call cost and on
whose key it ran.

- ``byok_month_usage``: per (user, calendar month) the input tokens, output
  tokens and estimated cost of the learner's own-keyed calls — the soft
  monthly budget reads it. Primary key ``(user_id, period_month)``, upsert-
  incremented like ``ai_spend_days``.
- ``byok_corpus_prompt_months``: per (user, source, calendar month) the prompt
  tokens their own-keyed calls pushed through one book — the per-corpus
  ceiling reads it. Primary key ``(user_id, source_id, period_month)``.
- ``user_byok_settings``: one row per user, the learner's own monthly budget
  in USD micros (``NULL`` = no budget set).
- ``conversation_turns`` gains four nullable columns: the adapter-reported
  input/output tokens, the estimated cost in USD micros (set for a user-keyed
  turn only — a house-served turn costs the learner nothing), and whether the
  learner's own key served the turn. ``NULL`` tokens read as "the adapter
  reported nothing", which is true of every existing row; nothing is
  backfilled.

``user_id`` and ``source_id`` reference their tables ON DELETE CASCADE, so a
deleted account (or book) leaves no orphan rows. Downgrade drops the tables
and the columns; a re-upgrade restores them clean.

Revision ID: 0033_byok_policy_ledgers
Revises: 0031_user_locale_preferences
Create Date: 2026-10-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0033_byok_policy_ledgers"
down_revision: str | None = "0032_section_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "byok_month_usage",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_month", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_usd_micros", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("user_id", "period_month"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "byok_corpus_prompt_months",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_month", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("user_id", "source_id", "period_month"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "user_byok_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monthly_budget_usd_micros", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.add_column(
        "conversation_turns",
        sa.Column("usage_input_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_turns",
        sa.Column("usage_output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_turns",
        sa.Column("cost_usd_micros", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "conversation_turns",
        sa.Column("user_keyed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("conversation_turns", "user_keyed")
    op.drop_column("conversation_turns", "cost_usd_micros")
    op.drop_column("conversation_turns", "usage_output_tokens")
    op.drop_column("conversation_turns", "usage_input_tokens")
    op.drop_table("user_byok_settings")
    op.drop_table("byok_corpus_prompt_months")
    op.drop_table("byok_month_usage")
