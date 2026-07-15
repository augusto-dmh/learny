"""Language-aware FTS: trigger-fed search_vector + per-chunk search_config/model

Replaces the hardcoded-``english`` generated ``search_vector`` (from 0005) with a
plain ``tsvector`` maintained by a ``BEFORE INSERT OR UPDATE`` trigger keyed on the
row's own ``search_config`` regconfig, so each chunk's lexical arm stems in the
book's language (QA finding F8). A ``STORED`` generated column cannot do this — its
expression must be IMMUTABLE, but ``to_tsvector(cfg::regconfig, ...)`` with a
per-row config is only STABLE — so Postgres rejects it; a trigger is the mechanism.

On ``corpus_chunks`` this migration:

- adds ``embedding_model text`` (nullable — populated per chunk when embedded);
- adds ``search_config text NOT NULL DEFAULT 'simple'`` (the resolved regconfig);
- drops the generated ``search_vector`` + its GIN index and re-adds ``search_vector``
  as a plain ``tsvector`` fed by ``corpus_chunks_search_vector_update()`` — deepest
  TOC title (``section_path ->> -1``) weight ``'A'`` over ``text`` weight ``'D'``,
  built with the row's ``search_config``;
- backfills existing rows by firing the trigger (``UPDATE ... SET search_config``);
- rebuilds the GIN index over the new column.

``downgrade`` reverses fully: it drops the GIN index, trigger, function, and plain
column, restores the generated ``english`` ``search_vector`` exactly as 0005 defined
it (with its GIN index), and drops ``search_config`` and ``embedding_model``. Triggers
and generated columns are not modeled by Alembic, so every step is raw ``op.execute``.

Revision ID: 0007_language_aware_fts
Revises: 0006_teaching_schema
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_language_aware_fts"
down_revision: str | None = "0006_teaching_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-chunk provider/model version (nullable until the chunk is embedded).
    op.execute("ALTER TABLE corpus_chunks ADD COLUMN embedding_model text")

    # The resolved Postgres regconfig for the chunk's language; 'simple' is the safe
    # default (no stemming, no stop words) for absent/unknown languages.
    op.execute(
        "ALTER TABLE corpus_chunks "
        "ADD COLUMN search_config text NOT NULL DEFAULT 'simple'"
    )

    # Swap the generated (hardcoded-english) search_vector for a plain, trigger-fed
    # one so the config can vary per row.
    op.execute("DROP INDEX IF EXISTS ix_corpus_chunks_search_vector")
    op.execute("ALTER TABLE corpus_chunks DROP COLUMN search_vector")
    op.execute("ALTER TABLE corpus_chunks ADD COLUMN search_vector tsvector")

    # Trigger builds search_vector from the row's own regconfig: deepest TOC title
    # ('A') outranks body text ('D'). Keyed on the columns that feed it.
    op.execute(
        """
        CREATE FUNCTION corpus_chunks_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(
                    to_tsvector(NEW.search_config::regconfig,
                                coalesce(NEW.section_path ->> -1, '')),
                    'A'
                )
                || setweight(
                    to_tsvector(NEW.search_config::regconfig,
                                coalesce(NEW.text, '')),
                    'D'
                );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_corpus_chunks_search_vector
        BEFORE INSERT OR UPDATE OF text, section_path, search_config
        ON corpus_chunks
        FOR EACH ROW
        EXECUTE FUNCTION corpus_chunks_search_vector_update()
        """
    )

    # Backfill: firing the (BEFORE UPDATE OF search_config) trigger recomputes
    # search_vector for every existing row under its default 'simple' config.
    op.execute("UPDATE corpus_chunks SET search_config = 'simple'")

    op.execute(
        "CREATE INDEX ix_corpus_chunks_search_vector "
        "ON corpus_chunks USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_corpus_chunks_search_vector")
    op.execute("DROP TRIGGER IF EXISTS trg_corpus_chunks_search_vector ON corpus_chunks")
    op.execute("DROP FUNCTION IF EXISTS corpus_chunks_search_vector_update()")
    op.execute("ALTER TABLE corpus_chunks DROP COLUMN search_vector")

    # Restore the generated english search_vector exactly as migration 0005 defined it.
    op.execute(
        """
        ALTER TABLE corpus_chunks
        ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(section_path ->> -1, '')), 'A')
            || setweight(to_tsvector('english', coalesce(text, '')), 'D')
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_corpus_chunks_search_vector "
        "ON corpus_chunks USING GIN (search_vector)"
    )

    op.execute("ALTER TABLE corpus_chunks DROP COLUMN search_config")
    op.execute("ALTER TABLE corpus_chunks DROP COLUMN embedding_model")
