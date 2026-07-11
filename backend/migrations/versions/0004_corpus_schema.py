"""Corpus schema: corpus_documents/sections/blocks/chunks (design §Data Models, Cycle 4)

Creates the canonical corpus aggregate produced by EPUB ingestion (ADR-0002).
``corpus_documents`` holds one row per source (unique ``source_id``, CORP-09) with
book metadata; ``corpus_sections`` are its spine/TOC-ordered sections (unique per
``(document_id, position)``); ``corpus_blocks`` preserve each section's HTML block
fragments; ``corpus_chunks`` are the structure-first retrieval chunks. Every child
FK cascades from its parent so deleting a source removes the whole aggregate with no
orphans (CORP-14); each child is indexed on its parent FK.

Revision ID: 0004_corpus_schema
Revises: 0003_ingestion_schema
Create Date: 2026-07-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_corpus_schema"
down_revision: str | None = "0003_ingestion_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "corpus_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "authors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column(
            "schema_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_corpus_documents_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corpus_documents"),
        sa.UniqueConstraint("source_id", name="uq_corpus_documents_source_id"),
    )

    op.create_table(
        "corpus_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["corpus_documents.id"],
            name="fk_corpus_sections_document_id_corpus_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corpus_sections"),
        sa.UniqueConstraint("document_id", "position", name="uq_corpus_sections_document_id"),
    )
    # No standalone document_id index: the unique constraint's btree leads on
    # document_id and covers the FK lookup + position-ordered structure read.

    op.create_table(
        "corpus_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.Text(), nullable=False),
        sa.Column("html_fragment", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["corpus_sections.id"],
            name="fk_corpus_blocks_section_id_corpus_sections",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corpus_blocks"),
    )
    op.create_index("ix_corpus_blocks_section_id", "corpus_blocks", ["section_id"])

    op.create_table(
        "corpus_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("section_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=False),
        sa.Column("page_span", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["corpus_sections.id"],
            name="fk_corpus_chunks_section_id_corpus_sections",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_corpus_chunks"),
    )
    op.create_index("ix_corpus_chunks_section_id", "corpus_chunks", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_corpus_chunks_section_id", table_name="corpus_chunks")
    op.drop_table("corpus_chunks")
    op.drop_index("ix_corpus_blocks_section_id", table_name="corpus_blocks")
    op.drop_table("corpus_blocks")
    op.drop_table("corpus_sections")
    op.drop_table("corpus_documents")
