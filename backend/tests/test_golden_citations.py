"""C1 gate (integration) — citation grounding golden checks (EVAL-07/08).

Builds + embeds the golden book in the live pgvector test DB and drives the real
``AskQuestion`` (real retrieval + deterministic extractive adapter + shared
grounding guard). Answerable questions must cite their target and only real
source passages; an unsupported question must yield the grounded not-found
outcome. Skips cleanly without ``LEARNY_TEST_DATABASE_URL`` (EVAL-10).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Connection

from tests.conftest import requires_db
from tests.eval_runner import answer, build_corpus_in_db, embed_source, seed_source
from tests.golden_corpus import golden_book
from tests.golden_expected import (
    CITATION_CASES,
    GOLDEN_SECTION_ANCHORS,
    UNSUPPORTED_QUESTION,
)

pytestmark = requires_db


def _build_golden(db_conn: Connection):
    user, source = seed_source(db_conn, email=f"golden-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())
    embed_source(db_conn, source.id)
    return user, source


@pytest.mark.parametrize("case", CITATION_CASES, ids=lambda c: c.expected_anchor)
def test_answer_cites_target_and_only_source_passages(db_conn: Connection, case) -> None:  # noqa: ANN001 — CitationCase
    # EVAL-07: an answerable question is answered, cites its target chapter, and
    # every citation anchor belongs to the source's corpus (grounding bound).
    user, source = _build_golden(db_conn)

    result = answer(db_conn, user, source, case.question)

    assert result.status == "answered"
    assert result.citations, "an answered result must carry citations"
    cited_anchors = {citation.anchor for citation in result.citations}
    assert case.expected_anchor in cited_anchors
    # NOTE: this bound is structurally satisfied today — retrieval is source-scoped
    # and the deterministic extractive adapter can only cite retrieved (in-source)
    # evidence, so it cannot yet catch a grounding-filter regression. It becomes a
    # discriminating "no citation outside the source" guard once a generative
    # adapter that can cite freely replaces the extractive one; revisit then.
    assert cited_anchors <= GOLDEN_SECTION_ANCHORS


def test_unsupported_question_is_grounded_not_found(db_conn: Connection) -> None:
    # EVAL-08: the corpus is present but NOT embedded, so a question whose terms
    # match no chunk retrieves nothing and short-circuits to the grounded
    # not-found outcome with no citations.
    user, source = seed_source(db_conn, email=f"golden-nf-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())  # deliberately not embedded

    result = answer(db_conn, user, source, UNSUPPORTED_QUESTION)

    assert result.status == "not_found_in_source"
    assert result.citations == ()
