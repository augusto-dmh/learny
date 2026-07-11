"""Ingestion schema: ingestion_jobs + ingestion_events (design §Data Models, Cycle 3)

Creates the durable ingestion-job lifecycle tables. ``ingestion_jobs`` holds one
row per ingestion attempt-set for a source; ``ingestion_events`` is its append-only
progress log. Both cascade on delete from their parent (``sources`` / ``ingestion_jobs``)
and are indexed on the parent FK. A partial unique index enforces "at most one
active (queued/running) job per source" (ING-03) at the persistence layer while
still allowing a terminal job to be restarted.

Revision ID: 0003_ingestion_schema
Revises: 0002_sources_schema
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_ingestion_schema"
down_revision: str | None = "0002_sources_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
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
            name="fk_ingestion_jobs_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
    )
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])
    # At most one active job per source (ING-03); partial so terminal jobs allow restart.
    op.create_index(
        "uq_ingestion_jobs_active_source",
        "ingestion_jobs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "ingestion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            name="fk_ingestion_events_job_id_ingestion_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_events"),
    )
    op.create_index("ix_ingestion_events_job_id", "ingestion_events", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_events_job_id", table_name="ingestion_events")
    op.drop_table("ingestion_events")
    op.drop_index("uq_ingestion_jobs_active_source", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_source_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
