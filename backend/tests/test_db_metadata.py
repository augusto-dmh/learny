"""The embedding column's declared type matches the migrations' shipped DDL."""

from __future__ import annotations

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.infrastructure.db.metadata import SettingsDimVector


def test_settings_dim_vector_declares_the_migrations_width() -> None:
    # Every embedding column ships as vector(1536) (migrations 0005 corpus_chunks,
    # 0008 quiz_items, 0013 notes). The metadata type must render the same typmod:
    # a bare VECTOR disagrees with the live column, and a compare_type autogenerate
    # would see a drift it emits as a typmod-dropping ALTER. The write width stays
    # the configured dimension — the bind processor's contract, untouched here.
    table = Table("t", MetaData(), Column("embedding", SettingsDimVector(), nullable=True))
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "VECTOR(1536)" in ddl
