"""Hybrid retrieval SQL adapter (design §Components 4, ADR-0006/0003).

``SqlAlchemyRetrievalRepository`` runs one hybrid statement over ``corpus_chunks``:
a semantic arm (pgvector/HNSW cosine) and a lexical arm (Postgres full-text
search), fused with Reciprocal Rank Fusion (RRF), scoped to a single source and
projecting citation anchors into frozen :class:`~app.domain.entities.Evidence`.

Both arms draw from a ``scoped`` CTE that joins ``corpus_chunks → corpus_sections
→ corpus_documents`` filtered by ``source_id`` — so there is no cross-source
leakage (RET-17). The semantic arm skips NULL-embedding chunks, so a not-yet-
embedded corpus degrades to lexical-only results without error (RET-15). A query
matching neither arm yields an empty result set (RET-16).

The bound ``:query_vec`` is cast to ``vector`` in SQL (``CAST(... AS vector)`` —
the ``::vector`` shorthand collides with ``text()`` colon-parameter parsing) so
the semantic arm works on connections without the engine-level ``register_vector``
adaptation (e.g. the test harness engine). ``hnsw.ef_search`` is set per
transaction from a settings-derived
int — ``SET`` takes no bind parameter, so the value is interpolated as a guarded
``int()`` (never raw input), which forecloses injection. Operates on the caller's
``Connection`` so the transaction boundary lives at the composition root.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.domain.entities import Evidence

# One statement: scoped CTE (source-scoped anchor rows) → semantic arm (cosine
# distance, NULL embeddings skipped) → lexical arm (websearch FTS, cover-density
# rank) → fused (FULL OUTER JOIN summing per-arm RRF terms) → anchors, RRF-ordered.
# The ``{anchor_filter}`` slot is empty for whole-source search and carries the
# target-subtree predicate when scoped (AD-031); because the filter lives in the
# shared ``scoped`` CTE, it constrains both arms at once (TEACH-09).
_HYBRID_SQL_TEMPLATE = """
    WITH scoped AS (
        SELECT
            cc.id AS chunk_id,
            cd.source_id AS source_id,
            cc.section_path AS section_path,
            cc.anchor AS anchor,
            cc.page_span AS page_span,
            cc.text AS snippet,
            cc.embedding AS embedding,
            cc.search_vector AS search_vector,
            cc.search_config AS search_config
        FROM corpus_chunks cc
        JOIN corpus_sections cs ON cc.section_id = cs.id
        JOIN corpus_documents cd ON cs.document_id = cd.id
        WHERE cd.source_id = :source_id{anchor_filter}
    ),
    semantic AS (
        SELECT
            chunk_id,
            ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_vec AS vector)) AS rank
        FROM scoped
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :semantic_limit
    ),
    lexical AS (
        SELECT
            chunk_id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    search_vector, websearch_to_tsquery(search_config::regconfig, :q), 32
                ) DESC
            ) AS rank
        FROM scoped
        WHERE search_vector @@ websearch_to_tsquery(search_config::regconfig, :q)
        ORDER BY ts_rank_cd(
            search_vector, websearch_to_tsquery(search_config::regconfig, :q), 32
        ) DESC
        LIMIT :lexical_limit
    ),
    fused AS (
        SELECT
            COALESCE(s.chunk_id, l.chunk_id) AS chunk_id,
            COALESCE(1.0 / (:k + s.rank), 0.0)
                + COALESCE(1.0 / (:k + l.rank), 0.0) AS rrf_score
        FROM semantic s
        FULL OUTER JOIN lexical l ON s.chunk_id = l.chunk_id
    )
    SELECT
        sc.chunk_id AS chunk_id,
        sc.source_id AS source_id,
        sc.section_path AS section_path,
        sc.anchor AS anchor,
        sc.page_span AS page_span,
        sc.snippet AS snippet,
        f.rrf_score AS rrf_score
    FROM fused f
    JOIN scoped sc ON sc.chunk_id = f.chunk_id
    ORDER BY f.rrf_score DESC
    LIMIT :top_k
    """

# The whole-source statement (no anchor scope) and the target-subtree variant. The
# unfiltered statement stays byte-identical to the pre-scoping query, so the default
# retrieval path is provably unchanged (AD-031).
_HYBRID_SQL = text(_HYBRID_SQL_TEMPLATE.format(anchor_filter=""))
_HYBRID_SQL_ANCHORED = text(
    _HYBRID_SQL_TEMPLATE.format(anchor_filter="\n            AND cc.anchor = ANY(:anchors)")
)


# The notes-included variant (ADR-0026 d4, NL-02). It reuses the book arms verbatim
# — so the book ranking is unchanged when notes are on — and adds two note arms over
# ``notes`` scoped to ``:user_id`` (never another user's, NL-05): a semantic arm that
# skips NULL-embedding notes (a not-yet-embedded note degrades to lexical-only, NL-06)
# and a lexical arm over the 'simple'-config ``search_vector`` (title A / body D). An
# empty-body note is excluded from both (``body_markdown <> ''``). The note fusion is
# scaled by ``:notes_weight``; both fusions are projected through one ``UNION ALL`` into
# a common evidence shape and ordered ``rrf_score DESC, evidence_id`` — a stable tie-break
# on the unique id makes the fused ranking deterministic (NL-02). Note rows project the
# note id as the opaque evidence id, ``origin='note'``, an empty section path, a
# ``note:<id>`` anchor, no page span, and a body snippet capped at ``:notes_snippet_chars``.
# ``{anchor_filter}`` constrains only the book ``scoped`` CTE — notes have no anchors.
_HYBRID_WITH_NOTES_TEMPLATE = """
    WITH scoped AS (
        SELECT
            cc.id AS chunk_id,
            cd.source_id AS source_id,
            cc.section_path AS section_path,
            cc.anchor AS anchor,
            cc.page_span AS page_span,
            cc.text AS snippet,
            cc.embedding AS embedding,
            cc.search_vector AS search_vector,
            cc.search_config AS search_config
        FROM corpus_chunks cc
        JOIN corpus_sections cs ON cc.section_id = cs.id
        JOIN corpus_documents cd ON cs.document_id = cd.id
        WHERE cd.source_id = :source_id{anchor_filter}
    ),
    semantic AS (
        SELECT
            chunk_id,
            ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_vec AS vector)) AS rank
        FROM scoped
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :semantic_limit
    ),
    lexical AS (
        SELECT
            chunk_id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    search_vector, websearch_to_tsquery(search_config::regconfig, :q), 32
                ) DESC
            ) AS rank
        FROM scoped
        WHERE search_vector @@ websearch_to_tsquery(search_config::regconfig, :q)
        ORDER BY ts_rank_cd(
            search_vector, websearch_to_tsquery(search_config::regconfig, :q), 32
        ) DESC
        LIMIT :lexical_limit
    ),
    book_fused AS (
        SELECT
            COALESCE(s.chunk_id, l.chunk_id) AS chunk_id,
            COALESCE(1.0 / (:k + s.rank), 0.0)
                + COALESCE(1.0 / (:k + l.rank), 0.0) AS rrf_score
        FROM semantic s
        FULL OUTER JOIN lexical l ON s.chunk_id = l.chunk_id
    ),
    note_scoped AS (
        SELECT
            n.id AS note_id,
            n.title AS note_title,
            n.body_markdown AS body,
            n.embedding AS embedding,
            n.search_vector AS search_vector
        FROM notes n
        WHERE n.user_id = :user_id AND n.body_markdown <> ''
    ),
    note_semantic AS (
        SELECT
            note_id,
            ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_vec AS vector)) AS rank
        FROM note_scoped
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vec AS vector)
        LIMIT :notes_semantic_limit
    ),
    note_lexical AS (
        SELECT
            note_id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    search_vector, websearch_to_tsquery('simple', :q), 32
                ) DESC
            ) AS rank
        FROM note_scoped
        WHERE search_vector @@ websearch_to_tsquery('simple', :q)
        ORDER BY ts_rank_cd(
            search_vector, websearch_to_tsquery('simple', :q), 32
        ) DESC
        LIMIT :notes_lexical_limit
    ),
    note_fused AS (
        SELECT
            COALESCE(s.note_id, l.note_id) AS note_id,
            :notes_weight * (
                COALESCE(1.0 / (:k + s.rank), 0.0)
                + COALESCE(1.0 / (:k + l.rank), 0.0)
            ) AS rrf_score
        FROM note_semantic s
        FULL OUTER JOIN note_lexical l ON s.note_id = l.note_id
    )
    SELECT
        sc.chunk_id AS chunk_id,
        'book' AS origin,
        sc.source_id AS source_id,
        sc.section_path AS section_path,
        sc.anchor AS anchor,
        sc.page_span AS page_span,
        sc.snippet AS snippet,
        NULL::uuid AS note_id,
        NULL::text AS note_title,
        bf.rrf_score AS rrf_score
    FROM book_fused bf
    JOIN scoped sc ON sc.chunk_id = bf.chunk_id
    UNION ALL
    SELECT
        ns.note_id AS chunk_id,
        'note' AS origin,
        ns.note_id AS source_id,
        '[]'::jsonb AS section_path,
        'note:' || ns.note_id::text AS anchor,
        NULL::jsonb AS page_span,
        left(ns.body, :notes_snippet_chars) AS snippet,
        ns.note_id AS note_id,
        ns.note_title AS note_title,
        nf.rrf_score AS rrf_score
    FROM note_fused nf
    JOIN note_scoped ns ON ns.note_id = nf.note_id
    ORDER BY rrf_score DESC, chunk_id
    LIMIT :top_k
    """

_HYBRID_SQL_WITH_NOTES = text(_HYBRID_WITH_NOTES_TEMPLATE.format(anchor_filter=""))
_HYBRID_SQL_ANCHORED_WITH_NOTES = text(
    _HYBRID_WITH_NOTES_TEMPLATE.format(
        anchor_filter="\n            AND cc.anchor = ANY(:anchors)"
    )
)


class SqlAlchemyRetrievalRepository:
    """``RetrievalPort`` backed by the hybrid RRF query over ``corpus_chunks``.

    Takes a caller-provided ``Connection``; the enclosing transaction (autobegun
    by the connection) makes ``SET LOCAL hnsw.ef_search`` valid and scopes it to
    this query.
    """

    def __init__(self, connection: Connection) -> None:
        self._conn = connection

    def search(
        self,
        *,
        source_id: UUID,
        query_text: str,
        query_vec: list[float],
        top_k: int,
        semantic_limit: int,
        lexical_limit: int,
        rrf_k: int,
        ef_search: int,
        anchors: Sequence[str] | None = None,
        user_id: UUID | None = None,
        include_notes: bool = False,
    ) -> list[Evidence]:
        # SET takes no bind parameter; interpolate a guarded int (from settings),
        # never raw input, so there is no injection surface.
        self._conn.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))
        params: dict[str, object] = {
            "source_id": source_id,
            "query_vec": query_vec,
            "q": query_text,
            "semantic_limit": semantic_limit,
            "lexical_limit": lexical_limit,
            "k": rrf_k,
            "top_k": top_k,
        }
        # The note arms are active only when BOTH a user and the flag are given;
        # either omitted keeps the book-only statement (and its results) unchanged.
        use_notes = include_notes and user_id is not None
        if use_notes:
            settings = get_settings()
            params["user_id"] = user_id
            params["notes_semantic_limit"] = settings.retrieval_notes_semantic_limit
            params["notes_lexical_limit"] = settings.retrieval_notes_lexical_limit
            params["notes_weight"] = settings.retrieval_notes_weight
            params["notes_snippet_chars"] = settings.retrieval_notes_snippet_chars

        if anchors is None:
            statement = _HYBRID_SQL_WITH_NOTES if use_notes else _HYBRID_SQL
        else:
            # Bound as a list — psycopg adapts it to a Postgres array for = ANY(...).
            statement = (
                _HYBRID_SQL_ANCHORED_WITH_NOTES if use_notes else _HYBRID_SQL_ANCHORED
            )
            params["anchors"] = list(anchors)
        rows = self._conn.execute(statement, params).all()
        return [_to_evidence(row) for row in rows]


def _to_evidence(row) -> Evidence:  # noqa: ANN001 — Row is an internal SQLAlchemy type
    # ``origin``/``note_id``/``note_title`` are present only on the notes-included
    # statement; the book-only rows lack those columns, so they fall to the book
    # defaults. ``chunk_id`` is the opaque evidence id (the note id for a note).
    return Evidence(
        chunk_id=row.chunk_id,
        source_id=row.source_id,
        section_path=tuple(row.section_path),
        anchor=row.anchor,
        page_span=row.page_span,
        snippet=row.snippet,
        score=float(row.rrf_score),
        origin=getattr(row, "origin", "book"),
        note_id=getattr(row, "note_id", None),
        note_title=getattr(row, "note_title", None),
    )
