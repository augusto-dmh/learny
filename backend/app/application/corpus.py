"""Canonical corpus build use case (design §Components).

``BuildCorpus`` is the Phase-5 orchestration: stored EPUB bytes → parsed book →
per-section derived Markdown and structure-first chunks → atomic corpus replace →
a ``corpus_built`` counts event (CORP-01/04/05/08/10). It composes the storage,
parser, markup-converter, chunking, corpus, and event ports and stays
framework-free (ADR-0009): no ebooklib/bs4/SQLAlchemy/Celery type crosses this
boundary. It runs inside the ingestion step's single transaction, so any port
failure propagates unwrapped for the step to classify and the surrounding
transaction rolls back with no partial corpus (CORP-08).
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.chunking import pack_chunks
from app.application.errors import CorpusNotFound
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.domain.entities import (
    CorpusSectionRecord,
    CorpusStructure,
    IngestionEvent,
    IngestionJob,
    SectionContent,
    Source,
    User,
)
from app.domain.ports import (
    Clock,
    CorpusRepository,
    EpubParserPort,
    IngestionEventRepository,
    MarkupConverterPort,
    SourceRepository,
    StoragePort,
)

# The canonical corpus schema version stamped on every built document (A-8).
_CORPUS_SCHEMA_VERSION = 1

# Progress-log event appended once a corpus is persisted; its message carries the
# counts of persisted sections/blocks/chunks so the job's log records the build
# (CORP-10).
_CORPUS_BUILT_EVENT = "corpus_built"


class BuildCorpus:
    """Build and persist a source's canonical corpus in one call (CORP-01..05, 08..10).

    Reads the stored EPUB bytes, parses them into a library-free ``ParsedBook``,
    derives each section's Markdown from its preserved HTML blocks via the
    converter, packs structure-first chunks (never crossing a section boundary),
    replaces the corpus aggregate atomically, and appends the ``corpus_built``
    counts event. Zero-block sections are persisted too (empty Markdown, no
    chunks). Reuses the event-append shape of ``RunIngestion._append_event``.
    """

    def __init__(
        self,
        *,
        storage: StoragePort,
        parser: EpubParserPort,
        markup: MarkupConverterPort,
        corpus: CorpusRepository,
        events: IngestionEventRepository,
        clock: Clock,
        ids: Callable[[], UUID],
        chunk_max_chars: int,
    ) -> None:
        self._storage = storage
        self._parser = parser
        self._markup = markup
        self._corpus = corpus
        self._events = events
        self._clock = clock
        self._ids = ids
        self._chunk_max_chars = chunk_max_chars

    def __call__(self, *, source: Source, job: IngestionJob) -> None:
        source_bytes = self._storage.get_object(source.object_key)
        book = self._parser.parse(source_bytes, filename=source.filename)

        records: list[CorpusSectionRecord] = []
        total_blocks = 0
        total_chunks = 0
        for section in book.sections:
            block_texts = [
                self._markup.to_markdown(block.html_fragment) for block in section.blocks
            ]
            chunks = pack_chunks(
                block_texts,
                max_chars=self._chunk_max_chars,
                section_path=section.section_path,
                anchor=section.anchor,
            )
            records.append(
                CorpusSectionRecord(
                    section=section,
                    markdown="\n\n".join(block_texts),
                    chunks=chunks,
                )
            )
            total_blocks += len(section.blocks)
            total_chunks += len(chunks)

        self._corpus.replace(
            source.id,
            title=book.title,
            authors=book.authors,
            language=book.language,
            schema_version=_CORPUS_SCHEMA_VERSION,
            sections=records,
        )

        self._events.append(
            IngestionEvent(
                id=self._ids(),
                job_id=job.id,
                type=_CORPUS_BUILT_EVENT,
                message=(
                    f"sections={len(book.sections)} blocks={total_blocks} chunks={total_chunks}"
                ),
                created_at=self._clock.now(),
            )
        )


class ReadSourceStructure:
    """Return the owner's book structure for a source, or a not-found (CORP-11).

    Ownership is enforced first via ``authorized_source`` (reused from the
    ingestion services): a missing source and a non-owner collapse to
    ``SourceNotFound`` so a source's existence is never disclosed. An owned source
    that has no corpus yet raises ``CorpusNotFound`` (A-7); the web layer maps both
    to 404. The returned ``CorpusStructure`` is the flat, position-ordered read
    model — the web layer nests it per the TOC hierarchy.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        corpus: CorpusRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID) -> CorpusStructure:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        structure = self._corpus.get_structure(source_id)
        if structure is None:
            raise CorpusNotFound("No corpus for this source.")
        return structure


class ReadSection:
    """Return one section's content for the owner, or a not-found (FE-14).

    Mirrors ``ReadSourceStructure``: ownership is enforced first via
    ``authorized_source`` so a missing source and a non-owner collapse to
    ``SourceNotFound`` (no existence disclosure). An owned source whose corpus is
    absent and an anchor that matches no section both surface as ``get_section``
    returning ``None`` → ``CorpusNotFound``; the web layer maps both to 404, so a
    valid anchor is indistinguishable from an unknown one to a non-owner.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        corpus: CorpusRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID, anchor: str) -> SectionContent:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        section = self._corpus.get_section(source_id, anchor)
        if section is None:
            raise CorpusNotFound("No section for this anchor.")
        return section
