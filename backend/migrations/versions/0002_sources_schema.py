"""Sources schema: sources (design §Data Models, Cycle 2)

Creates the ``sources`` table holding metadata for uploaded EPUB source files.
The original bytes live in object storage under ``object_key`` (unique, opaque);
PostgreSQL owns ownership, checksum, and status. ``user_id`` cascades on user
delete and is indexed for owner-scoped listing.

Revision ID: 0002_sources_schema
Revises: 0001_identity_schema
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_sources_schema"
down_revision: str | None = "0001_identity_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'uploaded'"),
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
            ["user_id"],
            ["users.id"],
            name="fk_sources_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("object_key", name="uq_sources_object_key"),
    )
    # Owner-scoped listing queries filter on user_id.
    op.create_index("ix_sources_user_id", "sources", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_sources_user_id", table_name="sources")
    op.drop_table("sources")
