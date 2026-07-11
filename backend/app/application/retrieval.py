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

from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.domain.entities import Evidence, IngestionEvent, IngestionJob, Source, User
from app.domain.ports import (
    Clock,
    EmbeddingIndexRepository,
    EmbeddingPort,
    IngestionEventRepository,
    RetrievalPort,
    SourceRepository,
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


class RetrieveEvidence:
    """Return owner-scoped, citation-ready evidence for a source (RET-13/20).

    Ownership is enforced first via ``authorized_source`` (reused from the
    ingestion services): a missing source and a non-owner collapse to
    ``SourceNotFound`` so a source's existence is never disclosed, exactly like
    ``ReadSourceStructure``. It then embeds the (already-validated) query through
    the :class:`~app.domain.ports.EmbeddingPort` and runs the hybrid
    :class:`~app.domain.ports.RetrievalPort` with the settings-sourced per-arm
    limits, RRF ``k``, and HNSW ``ef_search``, returning the fused
    :class:`~app.domain.entities.Evidence` list (possibly empty).

    Query-string validation is not done here — the web layer owns 422 for an
    empty query and out-of-range ``top_k``; this service assumes a validated
    query. When ``top_k`` is omitted it falls back to ``default_top_k``
    (``LEARNY_RETRIEVAL_TOP_K``). Framework-free (no SQLAlchemy/FastAPI/SDK type
    crosses this boundary, ADR-0007/0009).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        retrieval: RetrievalPort,
        embeddings: EmbeddingPort,
        authorize: AuthorizeOwnership,
        semantic_limit: int,
        lexical_limit: int,
        rrf_k: int,
        ef_search: int,
        default_top_k: int,
    ) -> None:
        self._sources = sources
        self._retrieval = retrieval
        self._embeddings = embeddings
        self._authorize = authorize
        self._semantic_limit = semantic_limit
        self._lexical_limit = lexical_limit
        self._rrf_k = rrf_k
        self._ef_search = ef_search
        self._default_top_k = default_top_k

    def __call__(
        self, *, user: User, source_id: UUID, query: str, top_k: int | None = None
    ) -> list[Evidence]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        query_vec = self._embeddings.embed_query(query)
        return self._retrieval.search(
            source_id=source_id,
            query_text=query,
            query_vec=query_vec,
            top_k=top_k if top_k is not None else self._default_top_k,
            semantic_limit=self._semantic_limit,
            lexical_limit=self._lexical_limit,
            rrf_k=self._rrf_k,
            ef_search=self._ef_search,
        )
