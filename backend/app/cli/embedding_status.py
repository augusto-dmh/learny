"""Per-source embedding state and the dimension-change procedure (``app.cli.embedding_status``).

The operator's view of which corpus is on which embedding identity (ADR-0019
amendment). It reads the same environment the application does — no flags — and
reports, per source: total chunks, chunks current for the active adapter's
identity, stale chunks (vectors from another identity), and every distinct stamp
present; then the same counts for notes, and the vector columns' actual widths
against the configured ``LEARNY_EMBEDDING_DIM``. The state is derived from the
per-chunk ``embedding_model`` stamps on every read — never denormalized, so the
report cannot drift from what retrieval actually serves.

Exit codes: ``0`` when every embedding column's width matches the active
dimension; ``1`` when any column does not, printing the exact resize + re-embed
procedure (drop index, clear vectors, resize the three embedding columns,
recreate index, per-source ``reembed.document`` calls). The command never
resizes anything itself: a dimension change is a one-way data operation the
operator runs explicitly, and a corpus with foreign stamps answers lexical-only
until its re-embed runs.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.infrastructure.db.engine import get_engine
from app.infrastructure.embeddings import build_embedding_adapter

#: The unit-of-work each read runs in (tests inject their own).
_uow: Callable[[], Connection] = get_engine().connect  # type: ignore[assignment]

# Per-source stamp census over the retrieval path's own join (chunks are scoped by
# document, so the join is what defines "a source's chunks"). ``current`` counts
# stamps equal to the active identity; ``stale`` counts vectors produced by
# another identity; the rest are pending (not yet embedded).
_SOURCE_SQL = text(
    """
    SELECT cd.source_id AS source_id,
           COUNT(*) AS total,
           COUNT(*) FILTER (WHERE cc.embedding_model = :identity) AS current,
           COUNT(*) FILTER (
               WHERE cc.embedding IS NOT NULL
                 AND cc.embedding_model IS DISTINCT FROM :identity
           ) AS stale,
           ARRAY_REMOVE(ARRAY_AGG(DISTINCT cc.embedding_model), NULL) AS stamps
    FROM corpus_chunks cc
    JOIN corpus_sections cs ON cc.section_id = cs.id
    JOIN corpus_documents cd ON cs.document_id = cd.id
    GROUP BY cd.source_id
    ORDER BY cd.source_id
    """
)

_NOTES_SQL = text(
    """
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE embedding_model = :identity) AS current,
           COUNT(*) FILTER (
               WHERE embedding IS NOT NULL
                 AND embedding_model IS DISTINCT FROM :identity
           ) AS stale,
           ARRAY_REMOVE(ARRAY_AGG(DISTINCT embedding_model), NULL) AS stamps
    FROM notes
    """
)

# The vector columns' actual typmod width (pgvector stores the dimension as the
# typmod), read from the catalog so the check reflects the live schema.
_COLUMN_DIM_SQL = text(
    """
    SELECT attrelid::regclass::text AS table_name, atttypmod AS dim
    FROM pg_attribute
    WHERE attrelid IN (
              'corpus_chunks'::regclass, 'notes'::regclass, 'quiz_items'::regclass
          )
      AND attname = 'embedding' AND NOT attisdropped
    ORDER BY 1
    """
)


def _report(conn: Connection) -> int:
    """Print the report; return the process exit code."""
    settings = get_settings()
    identity = build_embedding_adapter(settings).model
    configured_dim = settings.embedding_dim

    print(f"active embedding identity: {identity} (dimension {configured_dim})")
    print()

    print("corpus sources (chunks):")
    rows = conn.execute(_SOURCE_SQL, {"identity": identity}).all()
    if not rows:
        print("  (no sources)")
    for row in rows:
        source_id: UUID = row.source_id
        total, current, stale = int(row.total), int(row.current), int(row.stale)
        stamps = ", ".join(str(s) for s in row.stamps) if row.stamps else "(none embedded)"
        state = "current" if stale == 0 and current == total else ("mixed" if current else "stale")
        print(
            f"  {source_id}  total={total} current={current} stale={stale} "
            f"state={state} stamps=[{stamps}]"
        )
    print()

    note = conn.execute(_NOTES_SQL, {"identity": identity}).one()
    note_stamps = ", ".join(str(s) for s in note.stamps) if note.stamps else "(none embedded)"
    print(
        f"notes: total={int(note.total)} current={int(note.current)} "
        f"stale={int(note.stale)} stamps=[{note_stamps}]"
    )
    print()

    print("vector columns vs configured dimension:")
    aligned = True
    for col in conn.execute(_COLUMN_DIM_SQL).all():
        ok = int(col.dim) == configured_dim
        aligned = aligned and ok
        print(
            f"  {col.table_name}.embedding: vector({int(col.dim)}) — "
            f"{'ok' if ok else f'MISMATCH (configured {configured_dim})'}"
        )
    print()

    stale_sources = [r for r in rows if int(r.stale) > 0 or int(r.current) < int(r.total)]
    if not aligned:
        print(
            f"the embedding columns do not match the configured dimension "
            f"({configured_dim}). Run this procedure exactly, in order (it is a "
            "one-way data operation — back up first):"
        )
        print()
        print("  1. drop the HNSW index:")
        print("       DROP INDEX IF EXISTS ix_corpus_chunks_embedding_hnsw;")
        print("  2. clear every vector (they are all the wrong width now):")
        print("       UPDATE corpus_chunks SET embedding = NULL;")
        print("       UPDATE notes SET embedding = NULL;")
        print("       UPDATE quiz_items SET embedding = NULL;")
        print(f"  3. resize the columns to vector({configured_dim}):")
        print(
            "       ALTER TABLE corpus_chunks ALTER COLUMN embedding TYPE "
            f"vector({configured_dim});"
        )
        print(f"       ALTER TABLE notes ALTER COLUMN embedding TYPE vector({configured_dim});")
        print(
            f"       ALTER TABLE quiz_items ALTER COLUMN embedding TYPE vector({configured_dim});"
        )
        print("  4. recreate the index:")
        print(
            "       CREATE INDEX ix_corpus_chunks_embedding_hnsw "
            "ON corpus_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64);"
        )
        print("  5. re-embed every source (lexical-only until each one finishes):")
        for row in rows:
            print(
                "       celery -A app.worker.celery_app call reembed.document "
                f"--args '[\"{row.source_id}\"]'"
            )
        print(
            "  6. re-embed notes (one call per note id listed by:\n"
            "       SELECT id FROM notes WHERE embedding IS NULL AND body_markdown <> '';"
            " ):"
        )
        print("       celery -A app.worker.celery_app call notes.embed --args '[\"<note-id>\"]'")
        print()
        print(
            "Quiz-card embeddings (near-duplicate detection, no stamp column) are "
            "cleared by step 2 and rebuild when cards are reconciled."
        )
        return 1

    if stale_sources:
        print("sources not fully current for the active identity — re-embed:")
        for row in stale_sources:
            print(
                "    celery -A app.worker.celery_app call reembed.document "
                f"--args '[\"{row.source_id}\"]'"
            )
        print()
        print(
            "Until each re-embed finishes, that source answers lexical-only; its "
            "vectors are never fused with the active identity's."
        )
    else:
        print("every corpus is current for the active identity.")
    return 0


def main() -> int:
    """CLI entry point: one read-only connection, one report, one exit code."""
    with _uow() as conn:
        return _report(conn)


if __name__ == "__main__":
    sys.exit(main())
