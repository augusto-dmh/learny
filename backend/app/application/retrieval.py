"""Retrieval use-case services (design §Components 3).

Framework-free services for the retrieval write path. ``EmbedCorpus`` embeds a
source's chunks after the Phase-5 corpus build and appends an ``embeddings_built``
counts event, mirroring ``BuildCorpus``'s composition style: it composes the
embedding, embedding-index, and event ports and stays free of SQLAlchemy/Celery/
provider-SDK types (ADR-0007/0009). It runs inside the embed step's single
transaction, so any port failure propagates unwrapped for the step to classify
and the transaction rolls back with no partially-embedded chunks (RET-12).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.domain.entities import IngestionEvent, IngestionJob, Source
from app.domain.ports import (
    Clock,
    EmbeddingIndexRepository,
    EmbeddingPort,
    IngestionEventRepository,
)

# Progress-log event appended once a source's chunks are embedded; its message
# carries the number of chunks embedded (0 when the source has no chunks), so the
# job's durable log records the embed step (RET-09).
_EMBEDDINGS_BUILT_EVENT = "embeddings_built"


class EmbedCorpus:
    """Embed a source's chunks and append an ``embeddings_built`` event (RET-09).

    Reads the source's chunks via the embedding-index repository, embeds their
    texts through the :class:`~app.domain.ports.EmbeddingPort` in batches of
    ``batch_size`` (input order preserved, each vector paired with its chunk id),
    writes the vectors back, and appends the counts event. A source with zero
    chunks is a no-op write plus an event with count 0. Reuses the event-append
    shape of ``BuildCorpus``.
    """

    def __init__(
        self,
        *,
        embeddings: EmbeddingPort,
        index: EmbeddingIndexRepository,
        events: IngestionEventRepository,
        clock: Clock,
        ids: Callable[[], UUID],
        batch_size: int,
    ) -> None:
        self._embeddings = embeddings
        self._index = index
        self._events = events
        self._clock = clock
        self._ids = ids
        self._batch_size = batch_size

    def __call__(self, *, source: Source, job: IngestionJob) -> None:
        chunks = self._index.chunks_for_source(source.id)
        if not chunks:
            self._append_built_event(job, 0)
            return

        items: list[tuple[UUID, list[float]]] = []
        for start in range(0, len(chunks), self._batch_size):
            batch = chunks[start : start + self._batch_size]
            vectors = self._embeddings.embed_documents([chunk.text for chunk in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                items.append((chunk.id, vector))

        self._index.set_embeddings(items)
        self._append_built_event(job, len(items))

    def _append_built_event(self, job: IngestionJob, count: int) -> None:
        self._events.append(
            IngestionEvent(
                id=self._ids(),
                job_id=job.id,
                type=_EMBEDDINGS_BUILT_EVENT,
                message=f"chunks={count}",
                created_at=self._clock.now(),
            )
        )
