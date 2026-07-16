"""Tier-2 retrieval eval — recall@k / MRR regression gate (EMB-21/22).

Builds + embeds the golden book once in the live pgvector test DB, then drives the
real hybrid RRF retrieval for every hand-labeled pair (``eval_labeled``) and scores
the ranking of each pair's target chapter. The metrics are pinned to fixed
thresholds the deterministic adapter genuinely clears, so a retrieval regression
(broken lexical config, dropped model write, mis-ordered fusion) drops recall/MRR
below the bar and fails the gate. A snapshot dict records the model+dims identity
alongside the numbers so the committed baseline is unambiguously the deterministic
``local-deterministic@1536`` arm (the OpenAI snapshot is a keyed follow-up).

A ``@pytest.mark.live`` variant recomputes the same metrics under the OpenAI adapter
and is skipped when ``LEARNY_OPENAI_API_KEY`` is unset (CI stays offline).
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine

from app.core.config import get_settings
from app.infrastructure.embeddings import build_embedding_adapter
from app.infrastructure.embeddings.local import DeterministicEmbeddingAdapter
from tests.conftest import requires_db
from tests.eval_labeled import LABELED_PAIRS
from tests.eval_runner import build_corpus_in_db, embed_source, retrieve, seed_source
from tests.golden_corpus import golden_book

pytestmark = requires_db

_log = logging.getLogger(__name__)

# Fixed regression thresholds — set just under the deterministic adapter's measured
# recall/MRR on the labeled set (observed recall@1=1.0, recall@5=1.0, mrr=1.0). Kept
# below the observed values so the gate is meaningful without being flaky; a genuine
# retrieval regression drops a target out of rank 1 and trips these.
_MIN_RECALL_AT_1 = 0.9
_MIN_RECALL_AT_5 = 1.0
_MIN_MRR = 0.93


def _rank_of_target(results, expected_anchor: str) -> int | None:  # noqa: ANN001
    """1-based rank of the first result whose anchor matches, else ``None``."""
    for rank, evidence in enumerate(results, start=1):
        if evidence.anchor == expected_anchor:
            return rank
    return None


def _snapshot(conn: Connection, source_id, *, model: str, dimensions: int) -> dict:  # noqa: ANN001
    """Score every labeled pair through real retrieval and assemble the snapshot."""
    ranks = [
        _rank_of_target(retrieve(conn, source_id, pair.query, top_k=5), pair.expected_anchor)
        for pair in LABELED_PAIRS
    ]
    n = len(ranks)
    return {
        "model": model,
        "dimensions": dimensions,
        "n": n,
        "recall@1": sum(1 for r in ranks if r == 1) / n,
        "recall@5": sum(1 for r in ranks if r is not None and r <= 5) / n,
        "mrr": sum((1.0 / r) if r else 0.0 for r in ranks) / n,
    }


@pytest.fixture(scope="class")
def golden_conn(db_engine: Engine):  # noqa: ANN201
    """A class-scoped connection/txn so the golden corpus is built + embedded once."""
    conn = db_engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


class TestDeterministicRetrievalMetrics:
    """The committed baseline: metrics under the deterministic offline adapter."""

    @pytest.fixture(scope="class")
    def source_id(self, golden_conn: Connection):  # noqa: ANN201
        _, source = seed_source(golden_conn, email=f"eval-{uuid4()}@example.com")
        build_corpus_in_db(golden_conn, source, golden_book())
        embed_source(golden_conn, source.id)  # deterministic adapter (provider=local)
        return source.id

    def test_metrics_meet_thresholds(self, golden_conn: Connection, source_id) -> None:  # noqa: ANN001
        settings = get_settings()
        snapshot = _snapshot(
            golden_conn,
            source_id,
            model=DeterministicEmbeddingAdapter().model,
            dimensions=settings.embedding_dim,
        )
        _log.info("tier-2 retrieval snapshot (deterministic): %s", snapshot)
        print(f"\ntier-2 retrieval snapshot (deterministic): {snapshot}")

        # Snapshot is pinned to the deterministic model + configured dims.
        assert snapshot["model"] == DeterministicEmbeddingAdapter().model
        assert snapshot["dimensions"] == settings.embedding_dim
        assert snapshot["n"] == len(LABELED_PAIRS)
        # Regression gate.
        assert snapshot["recall@1"] >= _MIN_RECALL_AT_1
        assert snapshot["recall@5"] >= _MIN_RECALL_AT_5
        assert snapshot["mrr"] >= _MIN_MRR


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("LEARNY_OPENAI_API_KEY"),
    reason="LEARNY_OPENAI_API_KEY unset — live OpenAI retrieval metrics skipped",
)
class TestOpenAIRetrievalMetrics:
    """The keyed arm: recompute the same metrics under the real OpenAI adapter.

    Selects the OpenAI provider via env (both document and query embedding go
    through it) and asserts the same regression thresholds, proving the labeled set
    is discriminating under a real cloud model too. Skipped without a key.
    """

    @pytest.fixture(scope="class")
    def openai_source(self, db_engine: Engine, monkeypatch_class):  # noqa: ANN201
        monkeypatch_class.setenv("LEARNY_EMBEDDING_PROVIDER", "openai")
        get_settings.cache_clear()
        conn = db_engine.connect()
        trans = conn.begin()
        _, source = seed_source(conn, email=f"eval-openai-{uuid4()}@example.com")
        build_corpus_in_db(conn, source, golden_book())
        embed_source(conn, source.id)  # OpenAI adapter (provider=openai)
        try:
            yield conn, source.id
        finally:
            trans.rollback()
            conn.close()
            get_settings.cache_clear()

    def test_metrics_meet_thresholds(self, openai_source) -> None:  # noqa: ANN001
        conn, source_id = openai_source
        settings = get_settings()
        adapter = build_embedding_adapter(settings)
        snapshot = _snapshot(
            conn, source_id, model=adapter.model, dimensions=settings.embedding_dim
        )
        _log.info("tier-2 retrieval snapshot (openai): %s", snapshot)
        print(f"\ntier-2 retrieval snapshot (openai): {snapshot}")

        assert snapshot["model"] == adapter.model
        assert snapshot["dimensions"] == settings.embedding_dim
        assert snapshot["n"] == len(LABELED_PAIRS)
        assert snapshot["recall@1"] >= _MIN_RECALL_AT_1
        assert snapshot["recall@5"] >= _MIN_RECALL_AT_5
        assert snapshot["mrr"] >= _MIN_MRR


@pytest.fixture(scope="class")
def monkeypatch_class():  # noqa: ANN201
    """A class-scoped monkeypatch (pytest's built-in one is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch

    mpatch = MonkeyPatch()
    try:
        yield mpatch
    finally:
        mpatch.undo()
