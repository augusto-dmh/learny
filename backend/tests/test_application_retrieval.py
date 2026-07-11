"""T6 gate (unit) — EmbedCorpus application service (RET-09).

Drives ``EmbedCorpus`` over fake ports (embedding/embedding-index/events) so the
orchestration is asserted in isolation: every chunk of the source is embedded and
paired with its chunk id in reading order, the embedding provider is called in
``batch_size`` batches, a zero-chunk source is a no-op write, and one
``embeddings_built`` event carries the exact chunk count. Assertions target the
persisted ``(chunk_id, vector)`` pairs (via the fake index repo), not call counts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

from app.application.retrieval import EmbedCorpus
from app.domain.entities import ChunkToEmbed, IngestionJob, Source
from tests.fakes import (
    FakeClock,
    FakeEmbeddingIndexRepository,
    FakeEmbeddingPort,
    FakeIngestionEventRepository,
)

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)


def _source() -> Source:
    return Source(
        id=uuid4(),
        user_id=uuid4(),
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key="sources/a-book.epub",
        status="processing",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _job(source_id: UUID) -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=source_id,
        status="running",
        attempts=1,
        last_error=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _chunks(n: int) -> list[ChunkToEmbed]:
    return [ChunkToEmbed(id=uuid4(), text=f"chunk-{i}") for i in range(n)]


def _embed(
    *,
    index: FakeEmbeddingIndexRepository,
    embeddings: FakeEmbeddingPort,
    events: FakeIngestionEventRepository,
    batch_size: int,
) -> EmbedCorpus:
    ids = count(1)
    return EmbedCorpus(
        embeddings=embeddings,
        index=index,
        events=events,
        clock=FakeClock(_NOW),
        ids=lambda: UUID(int=next(ids)),
        batch_size=batch_size,
    )


def test_embed_corpus_embeds_all_chunks_in_order() -> None:
    source = _source()
    job = _job(source.id)
    chunks = _chunks(3)
    index = FakeEmbeddingIndexRepository({source.id: chunks})
    embeddings = FakeEmbeddingPort()
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=embeddings, events=events, batch_size=128)(
        source=source, job=job
    )

    # One set_embeddings write carrying every chunk id paired with its vector, in
    # reading order (vector value == the chunk's overall position, per the fake).
    assert len(index.set_calls) == 1
    assert index.set_calls[0] == [
        (chunks[0].id, [0.0]),
        (chunks[1].id, [1.0]),
        (chunks[2].id, [2.0]),
    ]


def test_embed_corpus_respects_batch_boundaries() -> None:
    source = _source()
    job = _job(source.id)
    chunks = _chunks(5)
    index = FakeEmbeddingIndexRepository({source.id: chunks})
    embeddings = FakeEmbeddingPort()
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=embeddings, events=events, batch_size=2)(
        source=source, job=job
    )

    # 5 chunks embedded in batches of 2 → [2, 2, 1], texts kept in reading order.
    assert [len(batch) for batch in embeddings.document_batches] == [2, 2, 1]
    assert [text for batch in embeddings.document_batches for text in batch] == [
        c.text for c in chunks
    ]
    # Every chunk id persisted with the position-ordered vector, across batches.
    assert index.set_calls[0] == [(chunks[i].id, [float(i)]) for i in range(5)]


def test_embed_corpus_zero_chunks_is_noop_with_event_count_zero() -> None:
    source = _source()
    job = _job(source.id)
    index = FakeEmbeddingIndexRepository({source.id: []})
    embeddings = FakeEmbeddingPort()
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=embeddings, events=events, batch_size=128)(
        source=source, job=job
    )

    # No embedding call and no write for a source with no chunks (no-op write).
    assert embeddings.document_batches == []
    assert index.set_calls == []
    # Still exactly one embeddings_built event, carrying count 0.
    appended = events.list_for_job(job.id)
    assert len(appended) == 1
    assert appended[0].type == "embeddings_built"
    assert appended[0].message == "chunks=0"


def test_embed_corpus_appends_embeddings_built_event_with_count() -> None:
    source = _source()
    job = _job(source.id)
    index = FakeEmbeddingIndexRepository({source.id: _chunks(3)})
    events = FakeIngestionEventRepository()

    _embed(index=index, embeddings=FakeEmbeddingPort(), events=events, batch_size=128)(
        source=source, job=job
    )

    appended = events.list_for_job(job.id)
    assert len(appended) == 1
    event = appended[0]
    assert event.type == "embeddings_built"
    assert event.message == "chunks=3"
    assert event.job_id == job.id
