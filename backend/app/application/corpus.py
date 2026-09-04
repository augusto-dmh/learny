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

import hashlib
import logging
from collections.abc import Callable
from dataclasses import replace
from uuid import UUID

from app.application.chunking import pack_chunks
from app.application.errors import CorpusNotFound
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import readable_source
from app.application.language import detect_language, sample_text
from app.application.media import (
    emphasize_dropped_images,
    markdown_images,
    omit_empty_alt_images,
    rewrite_markdown_images,
)
from app.application.normalization import normalize_book
from app.application.quiz_qc import normalize_text
from app.domain.entities import (
    CorpusSectionRecord,
    CorpusStructure,
    IngestionEvent,
    IngestionJob,
    ParsedBook,
    ParsedMedia,
    SectionContent,
    Source,
    User,
)
from app.domain.ports import (
    ActivationEventRepository,
    Clock,
    CorpusRepository,
    DocumentParserPort,
    ImageEncoderPort,
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

# Progress-log event appended after the structure-normalization pass; its message
# carries what the pass changed (titles/merges/depths/stripped noise, ING-07).
_CORPUS_NORMALIZED_EVENT = "corpus_normalized"

logger = logging.getLogger(__name__)


def _content_hash(block_markdown: str) -> str:
    """Return the normalized-text sha256 of a block's derived Markdown (NF-02).

    Normalizes (whitespace-collapse + lowercase, the shared quiz-QC idiom) before
    hashing so the hash is a stable identity of the block's content across
    re-derivation, then returns the full hex digest (matching the ``chunk_hash``
    snapshot style).
    """
    return hashlib.sha256(normalize_text(block_markdown).encode("utf-8")).hexdigest()


class BuildCorpus:
    """Build and persist a source's canonical corpus in one call (CORP-01..05, 08..10).

    Reads the stored source bytes, parses them into a library-free ``ParsedBook``,
    runs the format-agnostic normalization pass (F7 structure cleanup, ING-01),
    derives each section's Markdown from its preserved HTML blocks via the
    converter, packs structure-first chunks (never crossing a section boundary),
    replaces the corpus aggregate atomically, and appends the ``corpus_normalized``
    and ``corpus_built`` counts events. Zero-block sections are persisted too (empty
    Markdown, no chunks). Reuses the event-append shape of ``RunIngestion._append_event``.
    """

    def __init__(
        self,
        *,
        storage: StoragePort,
        parser: DocumentParserPort,
        markup: MarkupConverterPort,
        corpus: CorpusRepository,
        events: IngestionEventRepository,
        clock: Clock,
        ids: Callable[[], UUID],
        chunk_max_chars: int,
        encoder: ImageEncoderPort,
    ) -> None:
        self._storage = storage
        self._parser = parser
        self._markup = markup
        self._corpus = corpus
        self._events = events
        self._clock = clock
        self._ids = ids
        self._chunk_max_chars = chunk_max_chars
        self._encoder = encoder

    def __call__(self, *, source: Source, job: IngestionJob) -> None:
        source_bytes = self._storage.get_object(source.object_key)
        parsed = self._parser.parse(source_bytes, filename=source.filename)
        # Fill a missing language by detection (ADR-0025): PDFs carry none, and the
        # tag feeds both the persisted FTS config and localized normalization. A
        # parser-declared language (EPUB OPF) is never overridden; an undecisive
        # detection leaves None, which downstream treats exactly as before.
        if parsed.language is None:
            detected = detect_language(sample_text(parsed))
            if detected is not None:
                parsed = replace(parsed, language=detected)
        # Format-agnostic structure cleanup (F7) between parse and record building:
        # titles/hierarchy/boilerplate are fixed once, so EPUB and PDF corpora share
        # it and merged-away anchors survive as aliases (ING-01, AD-084).
        normalized = normalize_book(parsed)
        book = normalized.book

        section_block_texts = [
            [self._markup.to_markdown(block.html_fragment) for block in section.blocks]
            for section in book.sections
        ]
        href_to_hash, dropped, packaged_srcs = self._store_figures(
            source, book, section_block_texts
        )

        records: list[CorpusSectionRecord] = []
        total_blocks = 0
        total_chunks = 0
        for section, block_texts in zip(book.sections, section_block_texts, strict=True):
            rewritten = [
                _rewrite_figure_markdown(
                    text,
                    source_id=source.id,
                    href_to_hash=href_to_hash,
                    dropped_hrefs=dropped,
                    packaged_hrefs=packaged_srcs,
                )
                for text in block_texts
            ]
            chunks = pack_chunks(
                block_texts,
                max_chars=self._chunk_max_chars,
                section_path=section.section_path,
                anchor=section.anchor,
                page_spans=[block.page_span for block in section.blocks],
            )
            records.append(
                CorpusSectionRecord(
                    section=section,
                    markdown="\n\n".join(rewritten),
                    chunks=chunks,
                    # Per-block content hash for highlight anchoring (NF-02): the
                    # sha256 of each block's *pre-rewrite* Markdown, aligned with
                    # ``section.blocks``, so extract does not churn note anchors.
                    block_hashes=tuple(_content_hash(text) for text in block_texts),
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

        counts = normalized.counts
        self._events.append(
            IngestionEvent(
                id=self._ids(),
                job_id=job.id,
                type=_CORPUS_NORMALIZED_EVENT,
                message=(
                    f"titles_replaced={counts.titles_replaced} "
                    f"sections_merged={counts.sections_merged} "
                    f"depths_adjusted={counts.depths_adjusted} "
                    f"noise_blocks_stripped={counts.noise_blocks_stripped}"
                ),
                created_at=self._clock.now(),
            )
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

    def _store_figures(
        self,
        source: Source,
        book: ParsedBook,
        section_block_texts: list[list[str]],
    ) -> tuple[dict[str, str], set[str], set[str]]:
        """Encode packaged rasters, put WebP objects, and return rewrite maps.

        Empty-alt nodes are not stored. Encode failures drop that image only —
        they never fail the ingest job.
        """
        by_href, by_name = _index_media(book.media)
        packaged_srcs: set[str] = set(by_href) | set(by_name)
        needed: dict[str, ParsedMedia] = {}
        for block_texts in section_block_texts:
            for text in block_texts:
                for alt, src in markdown_images(text):
                    item = _resolve_media(src, by_href, by_name)
                    if item is None:
                        continue
                    packaged_srcs.add(src)
                    if alt.strip():
                        needed[src] = item

        href_to_hash: dict[str, str] = {}
        dropped: set[str] = set()
        for src, item in needed.items():
            try:
                encoded = self._encoder.encode(item.data, content_type=item.content_type)
            except Exception:  # noqa: BLE001 — one figure must not fail ingest
                logger.warning(
                    "ingestion.encode_figure_failed",
                    extra={"source_id": str(source.id), "src": src},
                    exc_info=True,
                )
                encoded = None
            if encoded is None:
                dropped.add(src)
                continue
            key = f"sources/{source.user_id}/{source.id}/media/{encoded.sha256}.webp"
            self._storage.put_object(key, encoded.data, content_type=encoded.content_type)
            href_to_hash[src] = encoded.sha256
        return href_to_hash, dropped, packaged_srcs


def _index_media(
    media: tuple[ParsedMedia, ...],
) -> tuple[dict[str, ParsedMedia], dict[str, ParsedMedia]]:
    by_href = {item.href: item for item in media}
    by_name: dict[str, ParsedMedia] = {}
    for item in media:
        by_name.setdefault(_href_name(item.href), item)
    return by_href, by_name


def _resolve_media(
    src: str,
    by_href: dict[str, ParsedMedia],
    by_name: dict[str, ParsedMedia],
) -> ParsedMedia | None:
    return by_href.get(src) or by_name.get(_href_name(src))


def _href_name(href: str) -> str:
    return href.rsplit("/", 1)[-1]


def _rewrite_figure_markdown(
    markdown: str,
    *,
    source_id: UUID,
    href_to_hash: dict[str, str],
    dropped_hrefs: set[str],
    packaged_hrefs: set[str],
) -> str:
    rewritten = rewrite_markdown_images(markdown, source_id=source_id, href_to_hash=href_to_hash)
    rewritten = omit_empty_alt_images(rewritten, packaged_hrefs=packaged_hrefs)
    return emphasize_dropped_images(rewritten, dropped_hrefs=dropped_hrefs)


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
        activations: ActivationEventRepository | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._authorize = authorize
        self._activations = activations
        self._clock = clock

    def __call__(self, *, user: User, source_id: UUID) -> CorpusStructure:
        readable_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
            activations=self._activations,
            clock=self._clock,
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
        activations: ActivationEventRepository | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._sources = sources
        self._corpus = corpus
        self._authorize = authorize
        self._activations = activations
        self._clock = clock

    def __call__(self, *, user: User, source_id: UUID, anchor: str) -> SectionContent:
        readable_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
            activations=self._activations,
            clock=self._clock,
        )
        section = self._corpus.get_section(source_id, anchor)
        if section is None:
            raise CorpusNotFound("No section for this anchor.")
        return section
