"""B1 gate (integration) — retrieval recall golden checks (EVAL-05/06).

Builds + embeds the golden book in the live pgvector test DB and drives the real
hybrid RRF retrieval. Each recall query's content tokens appear only in its target
chapter, so the target is a rank-1 both-arm hit; a second source proves scoping.
Skips cleanly without ``LEARNY_TEST_DATABASE_URL`` (EVAL-10).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Connection

from app.infrastructure.db.repositories import SqlAlchemyEmbeddingIndexRepository
from tests.conftest import requires_db
from tests.eval_runner import build_corpus_in_db, embed_source, retrieve, seed_source
from tests.golden_corpus import golden_book
from tests.golden_expected import RETRIEVAL_CASES

pytestmark = requires_db


def _build_golden(db_conn: Connection):
    _, source = seed_source(db_conn, email=f"golden-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())
    embed_source(db_conn, source.id)
    return source


@pytest.mark.parametrize("case", RETRIEVAL_CASES, ids=lambda c: c.expected_anchor)
def test_recall_target_is_top_ranked(db_conn: Connection, case) -> None:  # noqa: ANN001
    # EVAL-05: the target chapter is the rank-1 fused hit (unique lexical + nearest
    # semantic), outranking the other chapters' single-arm neighbours.
    source = _build_golden(db_conn)

    results = retrieve(db_conn, source.id, case.query)

    assert results, "expected retrieval hits for the golden book"
    assert results[0].anchor == case.expected_anchor


def test_retrieval_is_source_scoped(db_conn: Connection) -> None:
    # EVAL-06: the same book built in a second source is never returned for a query
    # scoped to source A, and every hit belongs to A.
    source_a = _build_golden(db_conn)
    _, source_b = seed_source(db_conn, email=f"golden-b-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source_b, golden_book())
    embed_source(db_conn, source_b.id)
    b_ids = {
        chunk.id
        for chunk in SqlAlchemyEmbeddingIndexRepository(db_conn).chunks_for_source(source_b.id)
    }

    results = retrieve(db_conn, source_a.id, RETRIEVAL_CASES[0].query)

    assert results, "expected source-A hits"
    assert {evidence.chunk_id for evidence in results}.isdisjoint(b_ids)
    assert all(evidence.source_id == source_a.id for evidence in results)
