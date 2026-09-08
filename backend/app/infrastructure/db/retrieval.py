"""Hybrid retrieval SQL adapter (design §Components 4, ADR-0006/0003).

``SqlAlchemyRetrievalRepository`` runs one hybrid statement over ``corpus_chunks``:
a semantic arm (pgvector/HNSW cosine) and a lexical arm (Postgres full-text
search), fused with Reciprocal Rank Fusion (RRF), scoped to a single source and
projecting citation anchors into frozen :class:`~app.domain.entities.Evidence`.

Both arms draw from a ``scoped`` CTE that joins ``corpus_chunks → corpus_sections
→ corpus_documents`` filtered by ``source_id`` — so there is no cross-source
leakage (RET-17). An optional reading-position bound (``not_past_anchor``)
further restricts the CTE's book rows to sections at or before the bound
anchor's section in document order (SPOILER-01/02); the note arms are never
bounded (SPOILER-11). The semantic arm skips NULL-embedding chunks, so a
not-yet-embedded corpus degrades to lexical-only results without error (RET-15).
A query matching neither arm yields an empty result set (RET-16).

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

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Connection, text

from app.core.config import get_settings
from app.domain.entities import Evidence

logger = logging.getLogger(__name__)

# One statement: scoped CTE (source-scoped anchor rows) → semantic arm (cosine
# distance, NULL embeddings skipped) → lexical arm (websearch FTS, cover-density
# rank) → fused (FULL OUTER JOIN summing per-arm RRF terms) → anchors, RRF-ordered.
# The ``{anchor_filter}`` slot is empty for whole-source search and carries the
# target-subtree predicate when scoped (AD-031); the ``{bound_filter}`` slot is
# empty unless a reading-position bound is supplied and sits beside it so the two
# compose as a logical AND (SPOILER-07). Because both filters live in the shared
# ``scoped`` CTE, they constrain both arms at once (TEACH-09) and shrink the
# candidate pool before fusion — admissible rows keep the shipped RRF scores
# (SPOILER-04).
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
        WHERE cd.source_id = :source_id{anchor_filter}{bound_filter}
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

# The two optional scoped-CTE predicates, spliced into the ``{anchor_filter}`` /
# ``{bound_filter}`` slots. The target-subtree predicate is the teaching scope
# (AD-031). The reading-position bound keeps chunks whose section's document-order
# position (``corpus_sections.position``) is at or before the bound anchor's section
# (AD-347) — the bound section itself stays admissible, later sections never; the
# chunk-level ``chunk_index`` and the stored ``percent`` play no part, and neither
# does ``page_span`` (SPOILER-03: the predicate is section order for every format).
# A bound anchor matching no section makes the scalar subquery NULL, and
# ``position <= NULL`` is unknown — eliminating every book row. That fail-closed
# behaviour is plain SQL NULL comparison semantics; no COALESCE may ever "rescue"
# it into a no-filter (SPOILER-14, AD-349).
_ANCHOR_FILTER = "\n            AND cc.anchor = ANY(:anchors)"
_POSITION_BOUND_FILTER = """
            AND cs.position <= (
                SELECT bound_section.position
                FROM corpus_sections bound_section
                WHERE bound_section.document_id = cs.document_id
                  AND bound_section.anchor = :not_past_anchor
            )"""

# The statement variants: whole-source vs target-subtree ({anchor_filter}) ×
# book-only vs notes-included, each in an unbounded and a bound form. The unbounded
# statements are byte-identical to the pre-bound queries, so callers that pass no
# bound keep the shipped behaviour exactly (SPOILER-12).
_HYBRID_SQL = text(_HYBRID_SQL_TEMPLATE.format(anchor_filter="", bound_filter=""))
_HYBRID_SQL_ANCHORED = text(
    _HYBRID_SQL_TEMPLATE.format(anchor_filter=_ANCHOR_FILTER, bound_filter="")
)
_HYBRID_SQL_BOUND = text(
    _HYBRID_SQL_TEMPLATE.format(anchor_filter="", bound_filter=_POSITION_BOUND_FILTER)
)
_HYBRID_SQL_ANCHORED_BOUND = text(
    _HYBRID_SQL_TEMPLATE.format(anchor_filter=_ANCHOR_FILTER, bound_filter=_POSITION_BOUND_FILTER)
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
# ``{anchor_filter}``/``{bound_filter}`` constrain only the book ``scoped`` CTE —
# notes have no anchors and are never bounded (SPOILER-11).
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
        WHERE cd.source_id = :source_id{anchor_filter}{bound_filter}
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

_HYBRID_SQL_WITH_NOTES = text(_HYBRID_WITH_NOTES_TEMPLATE.format(anchor_filter="", bound_filter=""))
_HYBRID_SQL_ANCHORED_WITH_NOTES = text(
    _HYBRID_WITH_NOTES_TEMPLATE.format(anchor_filter=_ANCHOR_FILTER, bound_filter="")
)
_HYBRID_SQL_WITH_NOTES_BOUND = text(
    _HYBRID_WITH_NOTES_TEMPLATE.format(anchor_filter="", bound_filter=_POSITION_BOUND_FILTER)
)
_HYBRID_SQL_ANCHORED_WITH_NOTES_BOUND = text(
    _HYBRID_WITH_NOTES_TEMPLATE.format(
        anchor_filter=_ANCHOR_FILTER, bound_filter=_POSITION_BOUND_FILTER
    )
)

# Cheap indexed existence check for a supplied bound anchor (``corpus_sections`` by
# anchor via the source's document). The bound statement itself already fails closed
# on a miss — the subquery yields NULL and eliminates every book row — so this check
# exists only to make the miss diagnosable: it logs one warning naming the source and
# the unmatched anchor (SPOILER-14). It never widens the result set.
_BOUND_ANCHOR_EXISTS_SQL = text(
    "SELECT EXISTS ("
    "SELECT 1 FROM corpus_sections s "
    "JOIN corpus_documents d ON s.document_id = d.id "
    "WHERE d.source_id = :source_id AND s.anchor = :not_past_anchor)"
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
        not_past_anchor: str | None = None,
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

        # The reading-position bound (SPOILER-01) applies to the book arms of EVERY
        # statement variant; note arms are never bounded (SPOILER-11). The bound
        # anchor is already canonical — matched directly against corpus_sections, no
        # alias expansion. An unmatched anchor eliminates every book row inside the
        # statement itself (``position <= NULL``); the existence check only adds the
        # diagnosable warning (SPOILER-14).
        bound = not_past_anchor is not None
        if bound:
            exists = self._conn.execute(
                _BOUND_ANCHOR_EXISTS_SQL,
                {"source_id": source_id, "not_past_anchor": not_past_anchor},
            ).scalar()
            if not exists:
                logger.warning(
                    "retrieval.position_bound_unmatched",
                    extra={"source_id": str(source_id), "anchor": not_past_anchor},
                )
            params["not_past_anchor"] = not_past_anchor

        if anchors is None:
            if use_notes:
                statement = _HYBRID_SQL_WITH_NOTES_BOUND if bound else _HYBRID_SQL_WITH_NOTES
            else:
                statement = _HYBRID_SQL_BOUND if bound else _HYBRID_SQL
        else:
            # Bound as a list — psycopg adapts it to a Postgres array for = ANY(...).
            params["anchors"] = list(anchors)
            if use_notes:
                statement = (
                    _HYBRID_SQL_ANCHORED_WITH_NOTES_BOUND
                    if bound
                    else _HYBRID_SQL_ANCHORED_WITH_NOTES
                )
            else:
                statement = _HYBRID_SQL_ANCHORED_BOUND if bound else _HYBRID_SQL_ANCHORED
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
