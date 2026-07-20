"""Notes retrieval index: whole-note embedding + trigger-fed search_vector

Indexes ``notes`` for hybrid retrieval so a user's own prose can join the semantic
and lexical arms without ever entering ``corpus_chunks`` (ADR-0026 d4). On ``notes``
this migration:

- adds ``embedding vector(1536)`` (nullable — populated per note when the embed_note
  task runs) and ``embedding_model text`` (nullable — the ``<model>@<dims>`` identity);
- adds ``search_vector tsvector`` fed by ``notes_search_vector_update()`` — the note
  ``title`` weighted ``'A'`` over the ``body_markdown`` weighted ``'D'``, both under the
  fixed ``'simple'`` regconfig (the note's language is unknown, so no stemming — the
  recorded upgrade is the AD-106 detector);
- backfills existing rows by firing the trigger (``UPDATE notes SET title = title``);
- builds an HNSW index (``vector_cosine_ops``, m=16/ef_construction=64 — the same params
  as the corpus index in 0005) over ``embedding`` and a GIN index over ``search_vector``.

The trigger owns ``search_vector`` (mirrors the ``corpus_chunks`` trigger from 0007), so
the app never writes it directly; unlike ``corpus_chunks`` the config is a fixed literal,
not a per-row column. ``downgrade`` reverses fully: it drops both indexes, the trigger,
the function, and all three columns. Triggers and vector indexes are not modeled by
Alembic, so every step is raw ``op.execute``.

Revision ID: 0013_notes_retrieval
Revises: 0012_card_provenance
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_notes_retrieval"
down_revision: str | None = "0012_card_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Whole-note vector + its provider/model version (both nullable until embedded).
    op.execute("ALTER TABLE notes ADD COLUMN embedding vector(1536)")
    op.execute("ALTER TABLE notes ADD COLUMN embedding_model text")

    # Trigger-fed lexical vector: title ('A') outranks body ('D'), fixed 'simple'
    # config (note language unknown — deterministic, no stemming).
    op.execute("ALTER TABLE notes ADD COLUMN search_vector tsvector")
    op.execute(
        """
        CREATE FUNCTION notes_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A')
                || setweight(to_tsvector('simple', coalesce(NEW.body_markdown, '')), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_notes_search_vector
        BEFORE INSERT OR UPDATE OF title, body_markdown
        ON notes
        FOR EACH ROW
        EXECUTE FUNCTION notes_search_vector_update()
        """
    )

    # Backfill: touching a trigger column recomputes search_vector for every row.
    op.execute("UPDATE notes SET title = title")

    # HNSW over the semantic arm's embedding (same params as the 0005 corpus index)
    # and GIN over the lexical search_vector.
    op.execute(
        "CREATE INDEX ix_notes_embedding_hnsw "
        "ON notes USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute("CREATE INDEX ix_notes_search_vector ON notes USING GIN (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notes_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_notes_embedding_hnsw")
    op.execute("DROP TRIGGER IF EXISTS trg_notes_search_vector ON notes")
    op.execute("DROP FUNCTION IF EXISTS notes_search_vector_update()")
    op.execute("ALTER TABLE notes DROP COLUMN search_vector")
    op.execute("ALTER TABLE notes DROP COLUMN embedding_model")
    op.execute("ALTER TABLE notes DROP COLUMN embedding")
