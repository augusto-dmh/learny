"""Phase C gate — the reembed_document worker task (integration, live DB).

Drives the ``reembed_document`` task *function* directly against the migrated test
engine (no Redis, no eager mode), mirroring ``test_worker_tasks``: the task commits
through its own engine, so each test seeds committed rows and the fixture deletes
the seeded user afterwards (FK cascade → sources → corpus). Because the task drops
and recreates the shared HNSW index, the fixture teardown also re-asserts the index
so a mid-task failure never leaves later tests without it.

Covers: a full reembed populates every chunk's vector + model and retrieval returns
the target (EMB-19); the pass is idempotent (a re-run rewrites nothing) and rescues
a stale-model corpus (EMB-17); and the HNSW index is present and serving afterward
(EMB-18).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy import delete as sa_delete

from app.core.config import get_settings
from app.infrastructure.db.metadata import (
    corpus_chunks,
    corpus_documents,
    corpus_sections,
    users,
)
from app.infrastructure.db.repositories import SqlAlchemyEmbeddingIndexRepository
from app.infrastructure.embeddings import build_embedding_adapter
from app.worker.tasks import reembed_document
from tests.conftest import requires_db
from tests.eval_runner import build_corpus_in_db, retrieve, seed_source
from tests.fixtures_epub import valid_book

pytestmark = requires_db

# The raw (unbound) task function, driven with a stand-in ``self`` (the body ignores
# it — reembed is ops-invoked with no retry) and no broker.
_reembed = reembed_document.run.__func__

# Same HNSW DDL as migration 0005 — the fixture teardown re-asserts it defensively.
_CREATE_HNSW_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_corpus_chunks_embedding_hnsw "
    "ON corpus_chunks USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)"
)


@pytest.fixture
def reembed_env(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the task's engine at the test DB and seed a committed source + corpus.

    Returns a callable that commits an owner + ready source + built corpus (chunks
    left unembedded, or pre-embedded at ``embed_model`` to simulate a stale index)
    and records the user for cascade cleanup. Teardown deletes the users and
    re-creates the HNSW index so the shared DB is never left without it.
    """
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created_users: list = []

    def _seed(epub: bytes, *, embed_model: str | None = None):  # noqa: ANN202
        with db_engine.begin() as conn:
            user, source = seed_source(conn, email=f"{uuid4()}@example.com")
            created_users.append(user.id)
            build_corpus_in_db(conn, source, epub)
            if embed_model is not None:
                index = SqlAlchemyEmbeddingIndexRepository(conn)
                chunks = index.chunks_for_source(source.id)
                vectors = build_embedding_adapter(get_settings()).embed_documents(
                    [chunk.text for chunk in chunks]
                )
                index.set_embeddings(
                    list(zip((chunk.id for chunk in chunks), vectors, strict=True)),
                    model=embed_model,
                )
        return source

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created_users:
            conn.execute(sa_delete(users).where(users.c.id == user_id))
        conn.execute(text(_CREATE_HNSW_INDEX))


def _chunk_rows(engine: Engine, source_id):  # noqa: ANN001, ANN202
    """Return each of the source's chunk (embedding, embedding_model) rows."""
    stmt = (
        select(corpus_chunks.c.embedding, corpus_chunks.c.embedding_model)
        .select_from(corpus_chunks)
        .join(corpus_sections, corpus_chunks.c.section_id == corpus_sections.c.id)
        .join(corpus_documents, corpus_sections.c.document_id == corpus_documents.c.id)
        .where(corpus_documents.c.source_id == source_id)
    )
    with engine.connect() as conn:
        return conn.execute(stmt).all()


def _stale_count(engine: Engine, source_id, model: str) -> int:  # noqa: ANN001
    with engine.connect() as conn:
        return len(
            SqlAlchemyEmbeddingIndexRepository(conn).stale_chunks_for_source(source_id, model)
        )


def _index_exists(engine: Engine) -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    "SELECT 1 FROM pg_indexes "
                    "WHERE indexname = 'ix_corpus_chunks_embedding_hnsw'"
                )
            ).first()
            is not None
        )


def test_reembed_populates_vectors_and_model_and_returns_target(
    reembed_env, db_engine: Engine
) -> None:
    # EMB-19: a source whose chunks are unembedded (NULL) is fully embedded by a
    # reembed pass — every chunk carries the target model + a vector — and hybrid
    # retrieval then returns the target chunk.
    source = reembed_env(valid_book())
    target = build_embedding_adapter(get_settings()).model

    _reembed(None, str(source.id))

    rows = _chunk_rows(db_engine, source.id)
    assert rows  # the source has chunks
    for row in rows:
        assert row.embedding is not None
        assert row.embedding_model == target

    with db_engine.connect() as conn:
        results = retrieve(conn, source.id, "Chapter two content")
    assert any(evidence.anchor == "chap2.xhtml" for evidence in results)


def test_reembed_is_idempotent_second_run_writes_nothing(
    reembed_env, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # EMB-17: after a full reembed the stale set is empty, so a second pass loops
    # zero batches and rewrites nothing (a spy on set_embeddings is never called).
    source = reembed_env(valid_book())
    target = build_embedding_adapter(get_settings()).model

    _reembed(None, str(source.id))
    assert _stale_count(db_engine, source.id, target) == 0

    writes: list[int] = []
    original = SqlAlchemyEmbeddingIndexRepository.set_embeddings

    def _spy(self, items, *, model):  # noqa: ANN001, ANN202
        writes.append(len(items))
        return original(self, items, model=model)

    monkeypatch.setattr(SqlAlchemyEmbeddingIndexRepository, "set_embeddings", _spy)
    _reembed(None, str(source.id))

    assert writes == []  # no batch written — a fully-current source is a no-op
    # The index is still present after the (write-free) drop+recreate cycle.
    assert _index_exists(db_engine)


def test_reembed_rescues_a_stale_model_corpus(reembed_env, db_engine: Engine) -> None:
    # EMB-17: a corpus embedded at a different (stale) model is entirely stale for
    # the target, and a reembed pass brings every chunk to the target model.
    source = reembed_env(valid_book(), embed_model="text-embedding-3-large@1536")
    target = build_embedding_adapter(get_settings()).model
    assert target != "text-embedding-3-large@1536"

    total = len(_chunk_rows(db_engine, source.id))
    assert total > 0
    assert _stale_count(db_engine, source.id, target) == total  # all stale for target

    _reembed(None, str(source.id))

    assert _stale_count(db_engine, source.id, target) == 0
    for row in _chunk_rows(db_engine, source.id):
        assert row.embedding is not None
        assert row.embedding_model == target


def test_reembed_recreates_hnsw_index_and_retrieval_serves(
    reembed_env, db_engine: Engine
) -> None:
    # EMB-18: the HNSW index exists after the reembed's drop+recreate cycle and the
    # semantic arm still serves a retrieval call.
    source = reembed_env(valid_book())

    _reembed(None, str(source.id))

    assert _index_exists(db_engine)
    with db_engine.connect() as conn:
        results = retrieve(conn, source.id, "Introduction to part one")
    assert results  # retrieval succeeds against the rebuilt index
