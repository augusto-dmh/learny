"""Structural checks for the tier-2 labeled pairs (EMB-20) — no DB required.

Guards the hand-authored ``LABELED_PAIRS`` against drift independent of retrieval:
the reviewable count band, query non-emptiness/uniqueness, and that every
``expected_anchor`` is a real section anchor of the golden book (derived from the
known corpus structure, ``GOLDEN_SECTION_ANCHORS`` — not from a pipeline run).
"""

from __future__ import annotations

from tests.eval_labeled import LABELED_PAIRS
from tests.golden_corpus import GOLDEN_SECTION_ANCHORS


def test_labeled_pairs_count_in_reviewable_band() -> None:
    assert 30 <= len(LABELED_PAIRS) <= 60


def test_labeled_queries_are_non_empty() -> None:
    assert all(pair.query.strip() for pair in LABELED_PAIRS)


def test_labeled_queries_are_unique() -> None:
    queries = [pair.query for pair in LABELED_PAIRS]
    assert len(set(queries)) == len(queries)


def test_every_expected_anchor_exists_in_golden_book() -> None:
    # Anchors are validated against the golden book's known section structure, so a
    # typo'd or removed chapter anchor fails here rather than silently under-counting
    # recall in the DB-backed gate.
    anchors = {pair.expected_anchor for pair in LABELED_PAIRS}
    assert anchors <= GOLDEN_SECTION_ANCHORS
    # Every chapter is exercised (no anchor left unlabeled).
    assert anchors == GOLDEN_SECTION_ANCHORS
