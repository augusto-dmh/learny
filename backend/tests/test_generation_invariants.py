"""D2 gate — citation-validity invariants for generation (GEN-19, every PR).

Three exact invariants that hold for any generator, deterministic or cloud, over
the golden book:

  (a) every cited chunk id is one of the retrieved evidence ids,
  (b) every cited anchor resolves to a section anchor in the corpus,
  (c) an ``answered`` result carries at least one citation.

The invariants run offline against the real retrieval + deterministic extractive
adapter (integration, DB) and are also parametrized over any committed replay
snapshots (skips cleanly when none are committed this cycle). Each invariant has
a test-local seeded-violation check proving it can fail — the checkers are pure
functions exercised by both the real-data path and the mutant path, so a real
regression is caught, not silently tolerated.
"""

from __future__ import annotations

from collections.abc import Set
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection

from tests.conftest import requires_db
from tests.eval.harness import Snapshot, load_cases, load_snapshots
from tests.eval_runner import answer, build_corpus_in_db, embed_source, retrieve, seed_source
from tests.golden_corpus import golden_book
from tests.golden_expected import GOLDEN_SECTION_ANCHORS

# --- The three invariants as pure checkers (shared by real-data + mutant paths) ---


def cited_ids_subset_of_retrieved(
    cited_ids: Set[UUID], retrieved_ids: Set[UUID]
) -> bool:
    """(a) Every cited chunk id must be one of the retrieved evidence ids."""
    return cited_ids <= retrieved_ids


def cited_anchors_resolve(cited_anchors: Set[str], corpus_anchors: Set[str]) -> bool:
    """(b) Every cited anchor must resolve to a section anchor in the corpus."""
    return cited_anchors <= corpus_anchors


def answered_implies_citation(status: str, cited_ids: Set[UUID]) -> bool:
    """(c) An ``answered`` result must carry at least one citation."""
    return status != "answered" or len(cited_ids) >= 1


# --- Seeded-violation checks: each invariant must be able to fail ---------------


def test_invariant_a_catches_out_of_set_citation() -> None:
    retrieved = {uuid4(), uuid4()}
    # A citation to a chunk that was never retrieved violates (a).
    stray = uuid4()
    assert cited_ids_subset_of_retrieved(set(retrieved), retrieved) is True
    assert cited_ids_subset_of_retrieved({stray}, retrieved) is False


def test_invariant_b_catches_unresolvable_anchor() -> None:
    corpus = {"ch1.xhtml", "ch2.xhtml"}
    assert cited_anchors_resolve({"ch1.xhtml"}, corpus) is True
    # An anchor absent from the corpus violates (b).
    assert cited_anchors_resolve({"ghost.xhtml"}, corpus) is False


def test_invariant_c_catches_answered_without_citations() -> None:
    assert answered_implies_citation("answered", {uuid4()}) is True
    assert answered_implies_citation("not_found_in_source", set()) is True
    # Answered but with no citation violates (c).
    assert answered_implies_citation("answered", set()) is False


# --- Real retrieval + deterministic adapter over the golden book (GEN-19) --------


@requires_db
def test_generation_invariants_hold_over_golden_book(db_conn: Connection) -> None:
    user, source = seed_source(db_conn, email=f"invariants-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())
    embed_source(db_conn, source.id)

    from app.core.config import get_settings

    top_k = get_settings().qa_evidence_top_k

    for case in load_cases():
        result = answer(db_conn, user, source, case.question)
        retrieved_ids = {
            e.chunk_id for e in retrieve(db_conn, source.id, case.question, top_k=top_k)
        }
        cited_ids = {citation.chunk_id for citation in result.citations}
        cited_anchors = {citation.anchor for citation in result.citations}

        assert cited_ids_subset_of_retrieved(cited_ids, retrieved_ids), case.case_id
        assert cited_anchors_resolve(cited_anchors, GOLDEN_SECTION_ANCHORS), case.case_id
        assert answered_implies_citation(result.status, cited_ids), case.case_id


# --- Committed replay snapshots (skips when none are committed) ------------------


def _snapshot_ids() -> list[str]:
    return [snapshot.case_id for snapshot in load_snapshots()]


@pytest.mark.parametrize("snapshot", load_snapshots(), ids=_snapshot_ids())
def test_generation_invariants_hold_over_snapshots(snapshot: Snapshot) -> None:
    retrieved_ids = {e.chunk_id for e in snapshot.evidence}
    corpus_anchors = {e.anchor for e in snapshot.evidence}
    cited_ids = set(snapshot.answer.cited_chunk_ids)
    cited_anchors = {
        e.anchor for e in snapshot.evidence if e.chunk_id in cited_ids
    }
    status = "answered" if snapshot.answer.found else "not_found_in_source"

    assert cited_ids_subset_of_retrieved(cited_ids, retrieved_ids)
    assert cited_anchors_resolve(cited_anchors, corpus_anchors)
    assert answered_implies_citation(status, cited_ids)


def test_snapshot_invariants_skip_when_none_committed() -> None:
    if load_snapshots():
        pytest.skip("snapshots are committed — the parametrized invariant test covers them")
    # No snapshots this cycle: the parametrized test above collects zero items, so
    # this explicit skip documents the offline state in `-rs` output (GEN-18/19).
    pytest.skip("no committed generation snapshots to validate")
