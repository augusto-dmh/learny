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

from app.application.corpus import BuildCorpus
from app.core.config import get_settings
from app.domain.entities import CorpusSectionRecord, IngestionJob, Source
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
