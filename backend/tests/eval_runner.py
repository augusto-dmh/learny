"""The golden-fixtures evaluation harness (Cycle 8, design §Components).

Composes the *real* grounding pipeline into runnable steps the golden checks
assert against — no assertions live here. Everything is deterministic and offline
(AD-038): the real EPUB parser + Markdown converter + chunker drive ingestion; a
deterministic embedding adapter and the deterministic extractive answer adapter
stand in for the (deferred) cloud provider, so the same fixture yields the same
corpus, retrieval order, and citations every run.

Ingestion runs pure (an in-memory ``FakeCorpusRepository`` captures what
``BuildCorpus`` would persist — no DB). Retrieval and citation run against the
live pgvector test DB via the real SQLAlchemy repositories (added by the
retrieval/citation golden tasks).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.application.corpus import BuildCorpus
from app.application.identity import AuthorizeOwnership
from app.application.qa import AskQuestion
from app.application.retrieval import RetrieveEvidence
from app.core.config import get_settings
from app.domain.entities import (
    CorpusSectionRecord,
    Evidence,
    IngestionJob,
    QuestionAnswer,
    Source,
    User,
)
from app.infrastructure.answering.local import DeterministicAnswerAdapter
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from app.infrastructure.ingestion.epub import EbooklibEpubParser
from app.infrastructure.ingestion.markup import Bs4MarkupConverter
from tests.fakes import (
    FakeClock,
    FakeCorpusRepository,
    FakeIngestionEventRepository,
    FakeStorage,
)

# A fixed instant for the throwaway source/job — ingestion output does not depend
# on it, but the entities require timestamps.
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_OBJECT_KEY = "golden/source.epub"


def _uuid_seq() -> Callable[[], UUID]:
    """A deterministic id source for event ids (``UUID(int=1)``, ``2``, ...)."""
    counter = count(1)
    return lambda: UUID(int=next(counter))


@dataclass(frozen=True)
class BuiltCorpus:
    """What ``BuildCorpus`` persisted, as the ingestion golden observes it.

    ``sections`` are the ``CorpusSectionRecord``s handed to ``CorpusRepository.replace``
    (each carries its parsed section identity + derived chunks); ``block_count`` and
    ``chunk_count`` are the totals the ``corpus_built`` event records.
    """

    title: str | None
    authors: tuple[str, ...]
    language: str | None
    sections: tuple[CorpusSectionRecord, ...]
    block_count: int
    chunk_count: int


def run_ingestion(epub: bytes) -> BuiltCorpus:
    """Ingest ``epub`` through the real parser/markup/chunker; capture the corpus.

    Drives ``BuildCorpus`` over a seeded in-memory storage and a capturing fake
    corpus repository, so the whole EPUB→corpus derivation runs with no DB, no
    object store, and no network — the observable output is the aggregate the
    real ``SqlAlchemyCorpusRepository`` would have written.
    """
    settings = get_settings()
    storage = FakeStorage()
    storage.objects[_OBJECT_KEY] = epub
    corpus = FakeCorpusRepository()

    build = BuildCorpus(
        storage=storage,
        parser=EbooklibEpubParser(max_uncompressed_bytes=settings.epub_max_uncompressed_bytes),
        markup=Bs4MarkupConverter(),
        corpus=corpus,
        events=FakeIngestionEventRepository(),
        clock=FakeClock(_EPOCH),
        ids=_uuid_seq(),
        chunk_max_chars=settings.chunk_max_chars,
    )
    build(source=_throwaway_source(), job=_throwaway_job())

    persisted = corpus.replace_calls[-1]
    sections: tuple[CorpusSectionRecord, ...] = persisted["sections"]  # type: ignore[assignment]
    return BuiltCorpus(
        title=persisted["title"],  # type: ignore[arg-type]
        authors=persisted["authors"],  # type: ignore[arg-type]
        language=persisted["language"],  # type: ignore[arg-type]
        sections=sections,
        block_count=sum(len(record.section.blocks) for record in sections),
        chunk_count=sum(len(record.chunks) for record in sections),
    )


# --- DB pipeline (integration — real repositories over the pgvector test DB) -----


def seed_source(db_conn: Connection, *, email: str) -> tuple[User, Source]:
    """Persist an owner + a ready source so a corpus can be built under it.

    Mirrors ``test_retrieval._persisted_source`` but returns the owner too, since
    the citation golden drives ``AskQuestion`` (which authorizes by user).
    """
    user = User(id=uuid4(), email=email, created_at=_EPOCH)
    SqlAlchemyUserRepository(db_conn).add(user)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="Golden",
        filename="golden.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        status="ready",
        created_at=_EPOCH,
        updated_at=_EPOCH,
    )
    SqlAlchemySourceRepository(db_conn).add(source)
    return user, source


def build_corpus_in_db(db_conn: Connection, source: Source, epub: bytes) -> None:
    """Ingest ``epub`` into the live corpus tables under an already-persisted source.

    Same real parser/markup/chunker as ``run_ingestion`` but persists through the
    real ``SqlAlchemyCorpusRepository``. Events are not under test, so a fake event
    repository stands in (avoids needing an ``ingestion_jobs`` row for the FK).
    """
    settings = get_settings()
    storage = FakeStorage()
    storage.objects[source.object_key] = epub
    build = BuildCorpus(
        storage=storage,
        parser=EbooklibEpubParser(max_uncompressed_bytes=settings.epub_max_uncompressed_bytes),
        markup=Bs4MarkupConverter(),
        corpus=SqlAlchemyCorpusRepository(db_conn),
        events=FakeIngestionEventRepository(),
        clock=FakeClock(_EPOCH),
        ids=_uuid_seq(),
        chunk_max_chars=settings.chunk_max_chars,
    )
    build(source=source, job=_throwaway_job())


def embed_source(db_conn: Connection, source_id: UUID) -> None:
    """Embed every chunk of ``source_id`` with the deterministic adapter."""
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source_id)
    vectors = adapter.embed_documents([chunk.text for chunk in chunks])
    index.set_embeddings(list(zip((chunk.id for chunk in chunks), vectors, strict=True)))


def retrieve(
    db_conn: Connection, source_id: UUID, query: str, *, top_k: int | None = None
) -> list[Evidence]:
    """Run the real hybrid RRF retrieval for ``query`` over ``source_id``.

    The same deterministic adapter embeds the query so the fused ordering is
    reproducible; per-arm limits / RRF k / HNSW ef come from ``LEARNY_`` settings.
    """
    settings = get_settings()
    query_vec = DeterministicEmbeddingAdapter().embed_query(query)
    return SqlAlchemyRetrievalRepository(db_conn).search(
        source_id=source_id,
        query_text=query,
        query_vec=query_vec,
        top_k=top_k if top_k is not None else settings.retrieval_top_k,
        semantic_limit=settings.retrieval_semantic_limit,
        lexical_limit=settings.retrieval_lexical_limit,
        rrf_k=settings.retrieval_rrf_k,
        ef_search=settings.hnsw_ef_search,
    )


def answer(db_conn: Connection, user: User, source: Source, question: str) -> QuestionAnswer:
    """Answer ``question`` over ``source`` through the real cited-answer path.

    Wires ``AskQuestion`` exactly as the request handler does — real source repo
    (ownership + readiness), real ``RetrieveEvidence`` over the hybrid retrieval +
    deterministic embeddings, the deterministic extractive answer adapter, and the
    settings-sourced evidence budget — so the golden citation check exercises the
    shared grounding guard, not a fake.
    """
    settings = get_settings()
    retrieve_evidence = RetrieveEvidence(
        sources=SqlAlchemySourceRepository(db_conn),
        retrieval=SqlAlchemyRetrievalRepository(db_conn),
        embeddings=DeterministicEmbeddingAdapter(),
        authorize=AuthorizeOwnership(),
        semantic_limit=settings.retrieval_semantic_limit,
        lexical_limit=settings.retrieval_lexical_limit,
        rrf_k=settings.retrieval_rrf_k,
        ef_search=settings.hnsw_ef_search,
        default_top_k=settings.retrieval_top_k,
    )
    ask = AskQuestion(
        sources=SqlAlchemySourceRepository(db_conn),
        authorize=AuthorizeOwnership(),
        retrieve=retrieve_evidence,
        generation=DeterministicAnswerAdapter(),
        evidence_top_k=settings.qa_evidence_top_k,
    )
    return ask(user=user, source_id=source.id, question=question)


def _throwaway_source() -> Source:
    return Source(
        id=uuid4(),
        user_id=uuid4(),
        title="Golden",
        filename="golden.epub",
        content_type="application/epub+zip",
        byte_size=0,
        checksum="0" * 64,
        object_key=_OBJECT_KEY,
        status="ready",
        created_at=_EPOCH,
        updated_at=_EPOCH,
    )


def _throwaway_job() -> IngestionJob:
    return IngestionJob(
        id=uuid4(),
        source_id=uuid4(),
        status="running",
        attempts=1,
        last_error=None,
        created_at=_EPOCH,
        updated_at=_EPOCH,
    )
